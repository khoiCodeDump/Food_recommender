from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from os import path
from flask_login import LoginManager
import ast
import pandas as pd
from flask_caching import Cache
import faiss
import numpy as np

db = SQLAlchemy()
DB_NAME = "database"
cache = Cache(config={'CACHE_TYPE': 'simple'})
model_name = 'paraphrase-mpnet-base-v2'

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'hjshjhdjah kjshkjdhjs'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'
    db.init_app(app)

    cache.init_app(app)

    from .views import views
    from .auth import auth
    
    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')
    
    from .models import User 

    create_database(app, model_name)
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    return app

def create_weighted_embedding(model, recipe, weights):
    ingredients_text = ', '.join([ingredient.name for ingredient in recipe.ingredients])
    tags_text = ', '.join([tag.name for tag in recipe.tags])
    steps_text = '. '.join(recipe.steps.split('|'))
    
    text_data = [
        f"Recipe: {recipe.name}",
        f"Ingredients: {ingredients_text}",
        f"Tags: {tags_text}",
        f"Description: {recipe.desc}",
        f"Steps: {steps_text}"
    ]
    
    embeddings = model.encode(text_data)
    weighted_embedding = np.average(embeddings, axis=0, weights=weights)
    return weighted_embedding

def update_recipes_embeddings(model):
    from .models import Recipe

    if path.exists('instance/' + DB_NAME):
        print("Updating recipe embeddings...")
        recipes_len = Recipe.query.count()
        batch_size = 100
        weights = [1.0, 1.5, 1.4, 1.0, 1.3]
        for i in range(0, recipes_len, batch_size):            
            # Query recipes in the current batch
            recipes = Recipe.query.offset(i).limit(batch_size).all()
       
            for recipe in recipes:
                print(f"Updating recipe {recipe.id}")
                # Generate new embedding for each recipe
                new_embedding = create_weighted_embedding(model, recipe, weights)
                
                # Update the recipe's embedding
                recipe.embedding = new_embedding.tolist()

            print(f"Committed recipes {i+1} - {min(i + batch_size, recipes_len)}")
            db.session.commit()
        print("Recipe embeddings updated successfully.")
    else:

        print("Database does not exist.")

def create_database(app, model_name):
    from .models import Recipe, Tag, Ingredient, create_faiss_index, set_faiss_index
    from sentence_transformers import SentenceTransformer

    with app.app_context():

        model = SentenceTransformer(model_name)

        if not path.exists('instance/' + DB_NAME):
            tags = {}
            ingredients = {}
            db.create_all()
            raw_recipes = pd.read_csv('archive/RAW_recipes.csv')
    
            for index, row in raw_recipes.iterrows():
                ingredients_list = ast.literal_eval(row["ingredients"])
                m_steps = ast.literal_eval(row["steps"])
                tags_list = ast.literal_eval(row["tags"])
    
                steps_list = '|'.join(m_steps)
                
                recipe = Recipe(name = row["name"], cook_time = int(row["minutes"]),steps = steps_list, desc = row["description"])
                
                db_tag_list = []
                db_ingredient_list = []
                
                for ingredient in ingredients_list:
                    if not ingredient:
                        continue
                    if ingredient not in ingredients:
                        db_ingredient = Ingredient(name=ingredient)
                        ingredients[ingredient] = db_ingredient
                        db_ingredient_list = db_ingredient_list + [db_ingredient]
                    else:
                        db_ingredient = ingredients[ingredient]

                    recipe.ingredients.append(db_ingredient)
                    
                for tag in tags_list:
                    if not tag:
                        continue
                    if tag not in tags:
                        db_tag = Tag(name=tag)
                        tags[tag] = db_tag
                        db_tag_list = db_tag_list + [db_tag]
                    else:
                        db_tag = tags[tag]
                        
                    recipe.tags.append(db_tag)

                
                ingredients_text = ', '.join(ingredients_list)
                tags_text = ', '.join(tags_list)
                steps_text = '. '.join(m_steps)
                
                text_data = (
                    f"Recipe's Name: {row['name']}."
                    f"Recipe's Ingredients: {ingredients_text}."
                    f"Recipe's Tags: {tags_text}."
                    f"Recipe's Description: {row['description']}."
                    f"Recipe's Instructions: {steps_text}."
                )
                
                # Generate embedding for the recipe
                embedding = model.encode(text_data)
                
                # Update the recipe with the generated embedding
                recipe.embedding = embedding.tolist()


                db.session.add_all(db_tag_list)
                db.session.add_all(db_ingredient_list)
                db.session.add(recipe)
                db.session.commit()
            
                print(f"Commited {recipe.id} to database")

            print('Created Database!')
        

        if not path.exists(f'recipe_index_{model_name}.faiss'):
            update_recipes_embeddings(model)
            m_faiss_index = create_faiss_index()
            faiss.write_index(m_faiss_index, f'recipe_index_{model_name}.faiss')
        else:
            set_faiss_index(faiss.read_index(f'recipe_index_{model_name}.faiss'))

        
        all_recipes_ids = [recipe.id for recipe in Recipe.query.with_entities(Recipe.id).all()]
        cache.set('all_recipes_ids', all_recipes_ids, timeout=0)
        cache.set('all_recipes_ids_len', len(all_recipes_ids), timeout=0)




