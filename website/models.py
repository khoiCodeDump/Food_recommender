from . import db
from flask_login import UserMixin
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from website import faiss_index, recipe_list

model = SentenceTransformer('all-MiniLM-L6-v2')


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

def create_faiss_index():
    print("test0")
    # Fetch all recipes and their embeddings
    recipes = Recipe.query.filter(Recipe.embedding != None).all()
    print("test1")
    
    # Get embeddings and convert them into a numpy array
    embeddings = np.array([recipe.embedding for recipe in recipes])
    print("test2")
    
    # Dimension of the embeddings (for FAISS)
    embedding_dim = embeddings.shape[1]
    print("test3")
    
    # Create a FAISS index (using L2 distance for simplicity)
    index = faiss.IndexFlatL2(embedding_dim)
    print("test4")
    
    # Add all recipe embeddings to the index
    index.add(embeddings)
    print("test5")
    
    return index, recipes

def add_recipe_to_faiss(recipe):
    
    # Reshape the embedding to fit FAISS input
    embedding = np.array([recipe.embedding], dtype=np.float32)
    
    # Add the embedding to the FAISS index
    faiss_index.add(embedding)

    # Optionally, save the updated FAISS index to disk
    faiss.write_index(faiss_index, 'recipe_index.faiss')

def semantic_search_recipes(user_query):
    # Generate an embedding for the user's query
    query_embedding = model.encode(user_query)
    
    # Search the FAISS index for the top_k most similar recipes
    distances, indices = faiss_index.search(np.array([query_embedding]))
    
    # Retrieve the corresponding recipes
    similar_recipes = [recipe_list[i] for i in indices[0]]
    
    return similar_recipes