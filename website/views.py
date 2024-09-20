from flask import Blueprint, render_template, request, jsonify, redirect, url_for, make_response, send_from_directory, abort
from flask_login import login_required, current_user
from .models import User, Recipe, Tag, Ingredient, Image, Video
from . import db
from werkzeug.utils import secure_filename
import json
import pickle
import os
import time
import bleach

views = Blueprint('views', __name__)
quantity = 45
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}


@views.route('/', methods=['GET', 'POST'])
@login_required
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

    
@views.route('/profile', methods=['GET'])
def profile():
    data = {"route": 1}
    return render_template("profile.html", data=data, tags=Tag.query.all(), ingredients= Ingredient.query.all() ) 

@views.route('/load_profile', methods=['GET'])
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
        tags_db = bleach.clean(request.form.get("Tags"))
        ingredients_db = bleach.clean(request.form.get("Ingredients"))
        
        tags_db = [bleach.clean(tag.strip()) for tag in tags_db.split(",")]
        ingredients_db = [bleach.clean(ingredient.strip()) for ingredient in ingredients_db.split(",")]

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
            print(f"New image: {image.filename}")
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
            if os.path.exists(old_video.url):
                os.remove(old_video.url)
                db.session.delete(old_video)

        # Handle new video upload
        new_video = request.files.get('new_video')
        if new_video and allowed_file(new_video.filename):
            print(f"New video: {new_video.filename}")
            filename = secure_filename(new_video.filename)
            video_path = os.path.join(user_data_dir, 'videos', filename)
            os.makedirs(os.path.dirname(video_path), exist_ok=True)
            new_video.save(video_path)
            new_video = Video(filename=filename, url=video_path, recipe=recipe)
            db.session.add(new_video)

        # Update tags and ingredients
        recipe.tags = []
        recipe.ingredients = []
        for tag in tags_db:
            queried_tag = Tag.query.filter(Tag.name == tag).first() or Tag(name=tag)
            recipe.tags.append(queried_tag)
        
        for ingredient in ingredients_db:
            queried_ing = Ingredient.query.filter(Ingredient.name == ingredient).first() or Ingredient(name=ingredient)
            recipe.ingredients.append(queried_ing)

        db.session.commit()
        return redirect(url_for('views.profile'))
    
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

# Add this helper function
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@views.route('/images/<path:filename>', methods=['GET'])
def serve_image(filename):
    media_dir = os.path.join( os.path.join('../data', str(current_user.id)), 'images')
    try:
        return send_from_directory(media_dir, filename)
    except FileNotFoundError as e:
        abort(404)

@views.route('/videos/<path:filename>', methods=['GET'])
def serve_video(filename):
    media_dir = os.path.join( os.path.join('../data', str(current_user.id)), 'videos')
    try:
        return send_from_directory(media_dir, filename)
    except FileNotFoundError as e:
        abort(404)

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

@views.route('/search', methods=['GET'])
def search():
    tags_res = Tag.query.all()
    tags = set()
    for tag in tags_res:
        tags.add(tag.name)

    ingredients_res = Ingredient.query.all()
    ingredients = set()
    for ingredient in ingredients_res:
        ingredients.add(ingredient.name)


    search_field = request.args.get('search-field')
        
    if search_field == '':
        return redirect(url_for('home'))

    # search_field = re.findall(r'\w+', search_field)
    search_field = search_field.split(",")
    
    result = None
    recipes = set()
    clone_recipe_ids = set()
    
    for field in search_field:
        field = field.strip()
        if field in ingredients:
            ingredient_results = Ingredient.query.filter(Ingredient.name==field).first()
            
            if len(recipes) == 0:
                for recipe in ingredient_results.recipes:
                     recipes.add(recipe.id)
            else:
                for recipe in ingredient_results.recipes:
                    if recipe.id in recipes:
                        clone_recipe_ids.add(recipe.id)

                recipes = clone_recipe_ids
                clone_recipe_ids = set()

            if result ==None:
                result = Recipe.query.filter(Recipe.id.in_(list(recipes)))
            else:
                result = result.filter(Recipe.id.in_(list(recipes)))
                
        elif field in tags:
            tag_results = Tag.query.filter(Tag.name==field).first()
            
            if len(recipes) == 0:
                for recipe in tag_results.recipes:
                     recipes.add(recipe.id)
            else:
                for recipe in tag_results.recipes:
                    if recipe.id in recipes:
                        clone_recipe_ids.add(recipe.id)

                recipes = clone_recipe_ids
                clone_recipe_ids = set()

            if result ==None:
                result = Recipe.query.filter(Recipe.id.in_(list(recipes)))
            else:
                result = result.filter(Recipe.id.in_(list(recipes)))
                    
        else:
            search_results = Recipe.query.filter(Recipe.name.contains(field))
            
            if len(recipes) == 0:
                for recipe in search_results:
                     recipes.add(recipe.id)
            else:
                #the clone is the union of recipe_ids in both separate sets
                for recipe in search_results:
                    if recipe.id in recipes:
                        clone_recipe_ids.add(recipe.id)
                
                recipes = clone_recipe_ids
                clone_recipe_ids = set()
            
            if result ==None:
                result = Recipe.query.filter(Recipe.id.in_(recipes))
            else:
                result = result.filter(Recipe.id.in_(recipes))
                    

    search_recipes = []
    for result_recipe in result:
        search_recipes.append(result_recipe.id)

    if not os.path.exists('data/' + str(current_user.id)):
        os.mkdir('data/' + str(current_user.id))

    try:
        with open('data/' + str(current_user.id) + '/search_result.pkl', 'wb') as f:
            pickle.dump(search_recipes, f)
    except IOError as e:
        print(f"Error writing search results: {e}")
                
    data = {"route": 2}
    # return redirect( url_for('views.load_search', search_field=",".join(search_field)), code=302)
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

@views.route('/delete_recipe', methods=['POST'])
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


