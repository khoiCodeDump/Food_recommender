from flask import Blueprint, render_template, request, jsonify, redirect, url_for, make_response, abort
from flask_login import login_required, current_user
from .models import Recipe, Tag, Ingredient, Image, Video
from . import db
from werkzeug.utils import secure_filename
from .utils import allowed_file, search_recipes, serve_media
import json
import pickle
import os
import time
import bleach

views = Blueprint('views', __name__)
quantity = 45

@views.route('/', methods=['GET', 'POST'])
def home():
    data = {"route": 0}
    
    return render_template("home.html", data=data, tags=Tag.query.all(), ingredients= Ingredient.query.all() )

@views.route('/load', methods=['GET'])
def load():
    time.sleep(0.2)
    count = request.args.get('count', 0, type=int)
    
    try:
        ids = [ id + 1 for id in range(count, count+quantity)]
        res = Recipe.query.filter(Recipe.id.in_(ids)).all()
        data = {}
        for stuff in res:
            data[stuff.id] = stuff.name
        res = make_response(data)
    except:
        print("No more recipes")
        res = make_response(jsonify({}), 200)

    return res

@views.route('/images/<path:filename>', methods=['GET'])
def serve_image(filename):
    return serve_media(filename, 'images')

@views.route('/videos/<path:filename>', methods=['GET'])
def serve_video(filename):
    return serve_media(filename, 'videos')

@views.route('/recipes/<meal_id>', methods=['GET'])
def get_recipe(meal_id):
    cur_recipe = Recipe.query.get(meal_id)
    temp = cur_recipe.steps
    typeList = "ol"
    if temp[0] >= "0" and temp[0] <= "9":
        typeList = "ul"
    
    # Get all valid image URLs for this recipe
    image_urls = []
    images_to_remove = []
    for image in cur_recipe.images:
        if os.path.exists(image.url):
            image_urls.append(url_for('views.serve_image', filename=image.filename))
        else:
            images_to_remove.append(image)
    
    # Get all valid video URLs for this recipe
    video_urls = []
    videos_to_remove = []
    for video in cur_recipe.videos:
        if os.path.exists(video.url):
            video_urls.append(url_for('views.serve_video', filename=video.filename))
        else:
            videos_to_remove.append(video)
    
    # Update the recipe references by removing non-existent files
    if images_to_remove or videos_to_remove:
        for image in images_to_remove:
            cur_recipe.images.remove(image)
            db.session.delete(image)
        for video in videos_to_remove:
            cur_recipe.videos.remove(video)
            db.session.delete(video)
        db.session.commit()

    return render_template("recipe_base.html", 
                           user=current_user, 
                           recipe_info=cur_recipe, 
                           typeList=typeList,
                           image_urls=image_urls,
                           video_urls=video_urls)

@views.route('/search', methods=['POST'])
def search():
    tags = {tag.strip() for tag in set(request.form.get('Tags', '').split(',')) if tag.strip()}
    ingredients = {ingredient.strip() for ingredient in set(request.form.get('Ingredients', '').split(',')) if ingredient.strip()}
    search_field = bleach.clean(request.form.get("search-field"))

    if search_field == '' and not tags and not ingredients:
        # Redirect to the referring page or to the home page if there's no referrer
        return redirect(request.referrer or url_for('views.home'))

    # search_field = re.findall(r'\w+', search_field)
    search_field = search_field.split(",")
    
    result = None
    recipes = set()
    
    for tag in tags:
        tag_res = Tag.query.filter(Tag.name==tag).first()
        result = search_recipes(recipes=recipes, query_res=tag_res, result=result)

    for ingredient in ingredients:
        ingredient_res = Ingredient.query.filter(Ingredient.name==ingredient).first()
        result = search_recipes(recipes=recipes, query_res=ingredient_res, result=result)
    
    for field in search_field:
        field = field.strip()
        
        ingredient_res = Ingredient.query.filter(Ingredient.name==field).first()
        if ingredient_res:
            result = search_recipes(recipes=recipes, query_res=ingredient_res, result=result)

        tag_res = Tag.query.filter(Tag.name==field).first()
        if tag_res:
            result = search_recipes(recipes=recipes, query_res=tag_res, result=result)
            continue
        
        name_res = Recipe.query.filter(Recipe.name.contains(field))
        if name_res:        
            result = search_recipes(recipes=recipes, query_res=name_res, result=result)
    

    _recipes = []
    for result_recipe in result:
        print(result_recipe.id)
        _recipes.append(result_recipe.id)

    if not os.path.exists('data/' + str(current_user.id)):
        os.mkdir('data/' + str(current_user.id))

    try:
        with open('data/' + str(current_user.id) + '/search_result.pkl', 'wb') as f:
            pickle.dump(_recipes, f)
    except IOError as e:
        print(f"Error writing search results: {e}")
                
    data = {"route": 2}
    return render_template("search_view.html", data=data, search_field=search_field, tags=Tag.query.all(), ingredients=Ingredient.query.all())

@views.route('/load_search', methods=['GET'])
def load_search():

    time.sleep(0.2)
    count = request.args.get('count', 0, type=int)
    try:
        with open('data/' + str(current_user.id) + '/search_result.pkl', 'rb') as f:
            recipe_list = pickle.load(f)

        res = Recipe.query.filter(Recipe.id.in_(recipe_list))
        res = res[count: count + quantity]
        data = {}
        for stuff in res:
            data[stuff.id] = stuff.name
        res = make_response(data)
    except:
        print("No more posts")
        res = make_response(jsonify({}), 200)

    return res

@views.route('/profile', methods=['GET'])
@login_required
def profile():
    data = {"route": 1}
    return render_template("profile.html", data=data, tags=Tag.query.all(), ingredients= Ingredient.query.all() ) 

@views.route('/load_profile', methods=['GET'])
@login_required
def load_profile():
    time.sleep(0.2)
    count = request.args.get('count', 0, type=int)

    try:
        res = Recipe.query.filter(Recipe.user_id==current_user.id).all()
        res = res[count: count + quantity]
        data = {}
        for stuff in res:
            data[stuff.id] = stuff.name
        res = make_response(data)
    except:
        print("No more posts")
        res = make_response(jsonify({}), 200)

    return res
    
@views.route('/post_recipe', methods=['GET', 'POST'])
@login_required
def post_recipe():

    if request.method == 'POST':
        recipe_id = request.form.get('recipe_id')
        if recipe_id:
            # Updating existing recipe
            recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
            if not recipe:
                abort(403)  # Forbidden if the recipe doesn't exist or doesn't belong to the user
        else:
            # Creating new recipe
            recipe = Recipe(user_id=current_user.id)
            db.session.add(recipe)

        # Update recipe fields
        recipe.name = bleach.clean(request.form.get("Title"))
        recipe.cook_time = bleach.clean(request.form.get("Cook_time"))
        recipe.desc = bleach.clean(request.form.get("Description"))
        steps = bleach.clean(request.form.get("Instructions"))

        temp = [bleach.clean(step.strip()) for step in steps.split("\r\n")]
        recipe.steps = "|".join(temp)
        
        # Ensure user directory exists
        user_data_dir = os.path.join('data', str(current_user.id))
        os.makedirs(user_data_dir, exist_ok=True)

        # Handle existing images
        existing_images = [value for key, value in request.form.items() if key.startswith('existing_images_')]
        for image in recipe.images:
            if image.filename in existing_images:
                existing_images.remove(image.filename)
            else:
                os.remove(image.url)
                db.session.delete(image)


        # Handle new image uploads
        new_images = []
        for key, value in request.files.items():
            if key.startswith('new_images_'):
                new_images.extend(request.files.getlist(key))
        for image in new_images:
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                image_path = os.path.join(user_data_dir, 'images', filename)
                os.makedirs(os.path.dirname(image_path), exist_ok=True)
                image.save(image_path)
                new_image = Image(filename=filename, url=image_path, recipe=recipe)
                db.session.add(new_image)

        # Handle existing video
        existing_video = request.form.get('existing_video')
        if not existing_video:
            old_video = Video.query.filter_by(recipe_id=recipe.id).first()
            if old_video and os.path.exists(old_video.url):
                os.remove(old_video.url)
                db.session.delete(old_video)

        # Handle new video upload
        new_video = request.files.get('new_video')
        if new_video and allowed_file(new_video.filename):
            filename = secure_filename(new_video.filename)
            video_path = os.path.join(user_data_dir, 'videos', filename)
            os.makedirs(os.path.dirname(video_path), exist_ok=True)
            new_video.save(video_path)
            new_video = Video(filename=filename, url=video_path, recipe=recipe)
            db.session.add(new_video)

        # Update tags and ingredients
        recipe.tags = []
        recipe.ingredients = []

        # Remove any empty strings
        tags = {tag.strip() for tag in set(request.form.get('Tags', '').split(',')) if tag.strip()}
        ingredients = {ingredient.strip() for ingredient in set(request.form.get('Ingredients', '').split(',')) if ingredient.strip()}

        # Process tags
        for tag_name in tags:
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.session.add(tag)
            recipe.tags.append(tag)

        # Process ingredients
        for ingredient_name in ingredients:
            ingredient = Ingredient.query.filter_by(name=ingredient_name).first()
            if not ingredient:
                ingredient = Ingredient(name=ingredient_name)
                db.session.add(ingredient)
            recipe.ingredients.append(ingredient)

        #Commit changes to database
        db.session.commit()
        return redirect(url_for('views.get_recipe', meal_id=recipe.id))
    
    # GET request
    recipe_id = request.args.get('recipe_id')
    if not recipe_id:
        return render_template("post_recipe_form.html", user=current_user, recipe=[], tags=Tag.query.all(), ingredients=Ingredient.query.all())
        
    # Updating existing recipe
    recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
    if not recipe:
        abort(403)  # Forbidden if the recipe doesn't exist or doesn't belong to the user
    existing_images = Image.query.filter_by(recipe_id=recipe.id).all()
    existing_video = Video.query.filter_by(recipe_id=recipe.id).first()
    return render_template("post_recipe_form.html", user=current_user, recipe=recipe, tags=Tag.query.all(), ingredients=Ingredient.query.all(), existing_images=existing_images, existing_video=existing_video)

@views.route('/delete_recipe', methods=['POST'])
@login_required
def delete_recipe():

    recipe = json.loads(request.data)
    recipe_id = recipe['recipe']
    recipe = Recipe.query.get(recipe_id)
    
    if recipe:
        if recipe.user_id == current_user.id:
            for image in recipe.images:
                os.remove(image.url)
                db.session.delete(image)
            for video in recipe.videos:
                os.remove(video.url)
                db.session.delete(video)
            for tag in recipe.tags:
                if len(tag.recipes) == 1:  # Only this recipe is associated
                    db.session.delete(tag)
            for ingredient in recipe.ingredients:
                if len(ingredient.recipes) == 1:  # Only this recipe is associated
                    db.session.delete(ingredient)
            db.session.delete(recipe)
            db.session.commit()
        
    return jsonify({}) 


