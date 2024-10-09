from . import db
from flask_login import UserMixin
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from website import model_name
import re
import collections

model = SentenceTransformer(model_name)
faiss_index = None

tag_table = db.Table('recipe_tag',
                    db.Column('recipe_id', db.Integer, db.ForeignKey('recipe.id')),
                    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id')),
                    # db.Column('ingredient_id', db.Integer, db.ForeignKey('ingredient.id'))
                )
ingredient_table = db.Table('recipe_ingredient',
                    db.Column('recipe_id', db.Integer, db.ForeignKey('recipe.id')),
                    db.Column('ingredient_id', db.Integer, db.ForeignKey('ingredient.id'))
                )

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    first_name = db.Column(db.String(150))    
    recipe_id = db.relationship('Recipe', backref='user')

@dataclass
class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    cook_time = db.Column(db.Integer)
    steps = db.Column(db.Text)
    desc = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tags = db.relationship('Tag', secondary=tag_table, backref='recipes')
    ingredients = db.relationship('Ingredient', secondary=ingredient_table, backref='recipes')
    images = db.relationship('Image', backref='recipe', lazy='dynamic')
    videos = db.relationship('Video', backref='recipe', lazy='dynamic')
    embedding = db.Column(db.PickleType, nullable=True)

@dataclass
class Tag(db.Model):
    id:int = db.Column(db.Integer, primary_key=True)
    name:str = db.Column(db.String(1000))

@dataclass
class Ingredient(db.Model):
    id:int = db.Column(db.Integer, primary_key=True)
    name:str = db.Column(db.String(1000))

@dataclass
class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))
    url = db.Column(db.String(1000))
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))

@dataclass
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))
    url = db.Column(db.String(1000))
    length = db.Column(db.Integer)  # Duration in seconds
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))

def generate_recipe_embeddings():
    
    # Query all recipes without embeddings
    recipes = Recipe.query.filter(Recipe.embedding == None).all()
    batch_size = 100
    for i in range(0, len(recipes), batch_size):
        batch = recipes[i:i+batch_size]
        
        for recipe in batch:
            ingredients_text = ', '.join([ingredient.name for ingredient in recipe.ingredients])
            tags_text = ', '.join([tag.name for tag in recipe.tags])
            steps_text = '. '.join(recipe.steps.split('|'))
            
            text_data = (
                f"Recipe Name: {recipe.name}. "
                f"Ingredients: {ingredients_text}. "
                f"Tags: {tags_text}. "
                f"Description: {recipe.desc}. "
                f"Steps: {steps_text}."
            )
            
            # Generate embedding for the recipe
            embedding = model.encode(text_data)
            
            # Update the recipe with the generated embedding
            recipe.embedding = embedding.tolist()
            
            print(f"Generated embedding for recipe {recipe.id}")
        
        # Commit the changes to the database for the batch
        db.session.commit()
        print(f"Committed batch of {i} to {i+batch_size} recipes")
    
    print(f"Generated embeddings for {len(recipes)} recipes.")

def set_faiss_index(index):
    global faiss_index
    faiss_index = index

def create_faiss_index(batch_size=1000):

    global faiss_index
    
    # Get total count of recipes with embeddings
    total_recipes = Recipe.query.filter(Recipe.embedding != None).count()
    print(f"Total recipes with embeddings: {total_recipes}")

    # Adjust nlist based on total recipes
    nlist = min(256, max(1, total_recipes // 39))  # Ensure at least 39 points per centroid
    print(f"Using {nlist} clusters for {total_recipes} recipes")

    try:
        # Collect training data
        training_data = []
        training_size = max(10000, 39 * nlist)  # Ensure we have at least 10,000 points or 39 * nlist, whichever is larger
        
        print(f"Collecting {training_size} points for training")
        for i in range(0, training_size, batch_size):
            recipes = Recipe.query.filter(Recipe.embedding != None).with_entities(Recipe.embedding).offset(i).limit(batch_size).all()
            if not recipes:
                break
            embeddings = np.array([recipe.embedding for recipe in recipes], dtype=np.float32)
            training_data.append(embeddings)
        
        training_data = np.vstack(training_data)
        print(f"Collected {len(training_data)} points for training")

        # Create and train the index
        embedding_dim = training_data.shape[1]
        m = 8  # number of subquantizers
        bits = 8  # bits per subquantizer

        quantizer = faiss.IndexFlatL2(embedding_dim)
        faiss_index = faiss.IndexIVFPQ(quantizer, embedding_dim, nlist, m, bits)
        
        print(f"Training index with {len(training_data)} points")
        faiss_index.train(training_data)

        # Add all embeddings to the index
        for i in range(0, total_recipes, batch_size):
            print(f"Processing batch {i//batch_size + 1}")
            
            recipes = Recipe.query.filter(Recipe.embedding != None).with_entities(Recipe.id, Recipe.embedding).offset(i).limit(batch_size).all()
            
            embeddings = np.array([recipe.embedding for recipe in recipes], dtype=np.float32)
            faiss_index.add(embeddings)
            
            print(f"Added {len(recipes)} recipes to index. Total: {total_recipes}")
        
        print("FAISS index creation completed successfully.")

        return faiss_index
        
    except Exception as e:
        print(f"An error occurred during index creation: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, []

def add_recipe_to_faiss(recipe):
    global faiss_index
    # Reshape the embedding to fit FAISS input
    embedding = np.array([recipe.embedding], dtype=np.float32)

    index_length = faiss_index.ntotal
    print(f"Before add: Number of vectors in FAISS index: {index_length}")
    # Add the embedding to the FAISS index
    faiss_index.add(embedding)

    index_length = faiss_index.ntotal
    print(f"After add: Number of vectors in FAISS index: {index_length}")
    # Optionally, save the updated FAISS index to disk
    faiss.write_index(faiss_index, f'recipe_index_{model_name}.faiss')

def remove_recipe_from_faiss(recipe):
    global faiss_index

    # Convert the recipe embedding to numpy array
    recipe_embedding = np.array([recipe.embedding], dtype=np.float32)

    # Search for the exact embedding in the FAISS index
    _, indices = faiss_index.search(recipe_embedding, 1)
    
    if indices[0][0] != -1:
        # Remove the embedding from the FAISS index
        faiss_index.remove_ids(np.array([indices[0][0]]))
        print(f"Removed recipe {recipe.id} from FAISS index.")
        
    else:
        print(f"Recipe {recipe.id} not found in FAISS index.")

    # Optionally, save the updated FAISS index to disk
    faiss.write_index(faiss_index, f'recipe_index_{model_name}.faiss')

def search_recipes(recipes, query_res, result):
    clone_recipe_ids = set()

    if len(recipes) == 0:
        if hasattr(query_res, 'recipes'):
            for recipe in query_res.recipes:
                recipes.add(recipe.id)
        else:
            for recipe in query_res:
                recipes.add(recipe.id)
    else:
        if hasattr(query_res, 'recipes'):   
            for recipe in query_res.recipes:
                if recipe.id in recipes:
                    clone_recipe_ids.add(recipe.id)
        else:
            for recipe in query_res:
                if recipe.id in recipes:
                    clone_recipe_ids.add(recipe.id)
        
        recipes = clone_recipe_ids
        clone_recipe_ids = set()
        
    if result is None:
        res = Recipe.query.filter(Recipe.id.in_(list(recipes)))
    else:
        res = result.filter(Recipe.id.in_(list(recipes)))
        
    return res

def semantic_search_recipes(user_query, all_recipes_ids, k_elements, similarity_threshold=0.1):
    
    global faiss_index
    
    
    # Generate an embedding for the user's query
    query_embedding = model.encode(user_query)

    # Search the FAISS index for the most similar recipes
    distances, indices = faiss_index.search(np.array([query_embedding], dtype=np.float32), k_elements)
    
    # Filter results based on the similarity threshold
    similar_recipes = []
    # Clean the user query and split it into words
    cleaned_query = re.sub(r'[^\w\s]', ' ', user_query)  # Replace non-word characters with spaces
    query_words = cleaned_query.lower().split()  # Convert to lowercase and split into words
    result = None
    recipes = set()
    for word in query_words:
        ingredient_res = Ingredient.query.filter(Ingredient.name == word).first()
        if ingredient_res:
            result = search_recipes(recipes=recipes, query_res=ingredient_res, result=result)

        tag_res = Tag.query.filter(Tag.name == word).first()
        if tag_res:
            result = search_recipes(recipes=recipes, query_res=tag_res, result=result)
            continue
    
        if word:
            name_res = Recipe.query.filter(Recipe.name.contains(word))
            if name_res:        
                result = search_recipes(recipes=recipes, query_res=name_res, result=result)
    
    for recipe in result:
        similar_recipes.append(recipe.id)
    
    similar_recipes = dict.fromkeys(similar_recipes)

    for distance, index in zip(distances[0], indices[0]):
        similarity = 1 / (1 + distance)  # Convert distance to similarity
        if similarity >= similarity_threshold:
            similar_recipes[all_recipes_ids[index]] = None
    
    similar_recipes = list(similar_recipes)
    
    return similar_recipes
