from . import db
from flask_login import UserMixin
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from website import model_name
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from scipy.sparse import vstack
import scipy.sparse as sp
import numpy as np


model = SentenceTransformer(model_name)
faiss_index = None
vectorizer = None
tfidf_matrix = None

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
            numbered_steps = " ".join([f"{i+1}. {step}" for i, step in enumerate(recipe.steps.split("|"))])

            text_data = (
                f"The recipe name is {recipe.name}",
                f"The recipe takes {recipe.cook_time} minutes to cook",
                f"To cook the recipe, the following ingredients are required, separated by commas: {ingredients_text}."
                f"The recipe has the following associated tags, separated by commas: {tags_text}."
                f"The description of the recipe is: {recipe.desc}. "
                f"Here are the instructions to cook the recipe: {numbered_steps}."
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
    global faiss_index, vectorizer, tfidf_matrix
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

    recipe_text = prepare_recipe_text(recipe)
    new_tfidf = vectorizer.transform([recipe_text])

    # Update the TF-IDF matrix
    tfidf_matrix = vstack([tfidf_matrix, new_tfidf])
    sp.save_npz('tfidf_matrix.npz', tfidf_matrix)

def remove_recipe_from_faiss(recipe):
    global faiss_index, tfidf_matrix
    
    # Remove the embedding from the FAISS index
    faiss_index.remove_ids(np.array([recipe.id - 1]))
    print(f"Removed recipe {recipe.id} from FAISS index.")
        
    # Optionally, save the updated FAISS index to disk
    faiss.write_index(faiss_index, f'recipe_index_{model_name}.faiss')

    row_to_remove = recipe.id - 1  # Assuming recipe IDs start from 1
    mask = np.ones(tfidf_matrix.shape[0], dtype=bool)
    mask[row_to_remove] = False
    tfidf_matrix = tfidf_matrix[mask]

    print(f"Removed recipe {recipe.id} from TF-IDF matrix.")
    print(f"Updated TF-IDF matrix shape: {tfidf_matrix.shape}")

    # Save the updated TF-IDF matrix
    sp.save_npz('tfidf_matrix.npz', tfidf_matrix)
    
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

def clean_query(user_query):
    # First, remove 's at the end of words
    cleaned_query = re.sub(r"'s\b", '', user_query)
    
    # Then remove other non-word characters (except apostrophes within words)
    cleaned_query = re.sub(r"[^\w\s']|\s'|'\s", ' ', cleaned_query)
    
    # Finally, remove any remaining apostrophes and extra spaces
    cleaned_query = re.sub(r"'", '', cleaned_query)
    cleaned_query = ' '.join(cleaned_query.split())
    
    return cleaned_query.lower()

def semantic_search_recipes(user_query, k_elements, similarity_threshold=0.1):
    
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
            similar_recipes.append(index+1)
        
    return similar_recipes


def set_tfidvectorizer(m_vectorizer, matrix):
    global vectorizer, tfidf_matrix
    vectorizer = m_vectorizer
    tfidf_matrix = matrix

# Function to prepare text for TF-IDF
def prepare_recipe_text(recipe):
    ingredients = ' '.join([i.name for i in recipe.ingredients])
    tags = ' '.join([t.name for t in recipe.tags])
    return f"{recipe.name} {ingredients} {recipe.desc} {tags}"

def initialize_tfidvectorizer(all_recipes_ids_len):
    global vectorizer, tfidf_matrix
    recipe_texts = []
    for i in range(0, all_recipes_ids_len):    
        print(f"Formatting text for recipe {i+1}")
        recipe = Recipe.query.get(i+1)
        recipe_texts.append(prepare_recipe_text(recipe))

    # Initialize TfidfVectorizer with appropriate parameters
    vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))

    # Fit the vectorizer to your text data
    tfidf_matrix = vectorizer.fit_transform(recipe_texts)

    return vectorizer, tfidf_matrix


def tfidf_search_recipes(query, top_n=100):
    
    # Transform the query to a vector using the same vectorizer
    query_vector = vectorizer.transform([query])

    # Compute cosine similarity between the query and all recipe vectors
    cosine_similarities = cosine_similarity(query_vector, tfidf_matrix).flatten()

    # Get the top N most similar recipes
    top_indices = cosine_similarities.argsort()[-top_n:][::-1]

    recipes = []

    for index in top_indices:
        print(cosine_similarities[index])
        recipes.append(int(index + 1))
    # Return the top matching recipes
    return recipes

def combined_search_recipes(user_query, k_elements=100, semantic_threshold=0.1, tfidf_threshold=0.2, tfidf_boost=1.5):
    global faiss_index, model, vectorizer, tfidf_matrix

    # Semantic Search
    query_embedding = model.encode(user_query)
    distances, indices = faiss_index.search(np.array([query_embedding], dtype=np.float32), k_elements)
    
    results = {}
    for distance, index in zip(distances[0], indices[0]):
        similarity = 1 / (1 + distance)  # Convert distance to similarity
        if similarity >= semantic_threshold:
            results[index + 1] = similarity

    # TF-IDF Search
    query_vector = vectorizer.transform([user_query])
    cosine_similarities = cosine_similarity(query_vector, tfidf_matrix).flatten()
    
    for i, similarity in enumerate(cosine_similarities):
        if similarity >= tfidf_threshold:
            recipe_id = i + 1
            boosted_similarity = similarity * tfidf_boost
            if recipe_id in results:
                results[recipe_id] = max(results[recipe_id], boosted_similarity)
            else:
                results[recipe_id] = boosted_similarity

    # Sort results by score in descending order
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)

    # Return recipe IDs
    return [ int(recipe_id) for recipe_id, _ in sorted_results]
