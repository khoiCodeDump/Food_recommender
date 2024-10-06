from . import db
from flask_login import UserMixin
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

model_name = 'all-MiniLM-L6-v2'
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
            steps = recipe.steps.split('|')
            steps = [s.strip() for s in steps]
            text_data = f"{recipe.name} {recipe.ingredients} {recipe.tags or ''} {recipe.desc}. {'. '.join(steps)}"
            
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
    # Add the embedding to the FAISS index
    faiss_index.add(embedding)

    # Optionally, save the updated FAISS index to disk
    faiss.write_index(faiss_index, f'recipe_index_{model_name}.faiss')

def remove_recipe_from_faiss(recipe_id):
    global faiss_index
    
    # Get all recipe embeddings and their IDs
    recipes = Recipe.query.filter(Recipe.embedding != None).with_entities(Recipe.id, Recipe.embedding).all()
    
    # Filter out the recipe you want to remove
    filtered_recipes = [(id, emb) for id, emb in recipes if id != recipe_id]
    
    # Extract embeddings and IDs
    embeddings = np.array([emb for _, emb in filtered_recipes], dtype=np.float32)
    ids = [id for id, _ in filtered_recipes]
    
    # Recreate the FAISS index
    embedding_dim = embeddings.shape[1]
    quantizer = faiss.IndexFlatL2(embedding_dim)
    nlist = min(256, max(1, len(embeddings) // 39))
    m = 8
    bits = 8
    new_faiss_index = faiss.IndexIVFPQ(quantizer, embedding_dim, nlist, m, bits)
    
    # Train and add the filtered embeddings
    new_faiss_index.train(embeddings)
    new_faiss_index.add(embeddings)
    
    # Update the global index
    faiss_index = new_faiss_index
    
    # Optionally, save the updated FAISS index to disk
    faiss.write_index(faiss_index, f'recipe_index_{model_name}.faiss')

def semantic_search_recipes(user_query, all_recipes_ids, k_elements, similarity_threshold=0.50):
    global faiss_index
    # Generate an embedding for the user's query
    query_embedding = model.encode(user_query)

    # Search the FAISS index for the most similar recipes
    distances, indices = faiss_index.search(np.array([query_embedding], dtype=np.float32), k_elements)
    
    # Filter results based on the similarity threshold
    similar_recipes = []
    for distance, index in zip(distances[0], indices[0]):
        similarity = 1 / (1 + distance)  # Convert distance to similarity
        if similarity >= similarity_threshold:
            similar_recipes.append(all_recipes_ids[index])
    return similar_recipes
    