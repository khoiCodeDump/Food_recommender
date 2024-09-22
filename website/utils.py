from .models import Recipe
from flask import abort, send_from_directory
from flask_login import current_user

import os

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

def serve_media(filename, media_type):
    media_dir = os.path.join(os.path.join('../data', str(current_user.id)), media_type)
    try:
        return send_from_directory(media_dir, filename)
    except FileNotFoundError as e:
        abort(404)
