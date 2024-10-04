from flask import Blueprint, render_template, request, jsonify, redirect, url_for, make_response, abort
from flask_login import login_required, current_user
from .models import Recipe, Tag, Ingredient, Image, Video, semantic_search_recipes, add_recipe_to_faiss
from . import db
from werkzeug.utils import secure_filename
from .utils import allowed_file, search_recipes, serve_media, query_openai
import json
import os
import time
import bleach
from website import cache  
from sentence_transformers import SentenceTransformer


views = Blueprint('views', __name__)
quantity = 45
model = SentenceTransformer('all-MiniLM-L6-v2')

@views.route('/', methods=['GET', 'POST'])
def home():
    data = {"route": 0}
    all_tags = cache.get('all_tags')
    all_ingredients = cache.get('all_ingredients')
 

    if all_tags is None:
        all_tags = Tag.query.all()
        cache.set('all_tags', all_tags)
        print("New tags cache")

    if all_ingredients is None:
        all_ingredients = Ingredient.query.all()
        cache.set('all_ingredients', all_ingredients)
        print("New ingredients cache")


    return render_template("home.html", data=data, tags=all_tags, ingredients=all_ingredients )

@cache.cached(timeout=60)  # Use the cache decorator directly
@views.route('/load', methods=['GET'])
def load():
    time.sleep(0.2)
    count = request.args.get('count', 0, type=int)
    
    try:
        ids = [id + 1 for id in range(count, count+quantity)]
        res = Recipe.query.filter(Recipe.id.in_(ids)).all()
        data = {}
        for stuff in res:
            first_image = stuff.images.first()
            image_url = url_for('views.serve_image', filename=first_image.filename) if first_image else url_for('static', filename='images/food_image_empty.png')

            data[stuff.id] = {
                'name': stuff.name,
                'image_url': image_url
            }
        res = make_response(data)
    except Exception as e:
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

# @views.route('/search', methods=['POST'])
# def search():
#     tags = {tag.strip() for tag in set(request.form.get('Tags', '').split(',')) if tag.strip()}
#     ingredients = {ingredient.strip() for ingredient in set(request.form.get('Ingredients', '').split(',')) if ingredient.strip()}
#     search_field = bleach.clean(request.form.get("search-field"))

#     if search_field == '' and not tags and not ingredients:
#         # Redirect to the referring page or to the home page if there's no referrer
#         return redirect(request.referrer or url_for('views.home'))

#     allTags = list(tags)
#     allIngredients = list(ingredients)
#     allNames = []

#     # search_field = re.findall(r'\w+', search_field)
#     search_field = search_field.split(",")
    
#     result = None
#     recipes = set()
    
#     for tag in tags:
#         tag_res = Tag.query.filter(Tag.name==tag).first()
#         result = search_recipes(recipes=recipes, query_res=tag_res, result=result)

#     for ingredient in ingredients:
#         ingredient_res = Ingredient.query.filter(Ingredient.name==ingredient).first()
#         result = search_recipes(recipes=recipes, query_res=ingredient_res, result=result)
    
#     for field in search_field:
#         field = field.strip()
        
#         ingredient_res = Ingredient.query.filter(Ingredient.name==field).first()
#         if ingredient_res:
#             allIngredients.append(str(field))
#             result = search_recipes(recipes=recipes, query_res=ingredient_res, result=result)

#         tag_res = Tag.query.filter(Tag.name==field).first()
#         if tag_res:
#             allTags.append(str(field))
#             result = search_recipes(recipes=recipes, query_res=tag_res, result=result)
#             continue
        
#         if field:
#             name_res = Recipe.query.filter(Recipe.name.contains(field))
#             if name_res:        
#                 allNames.append(str(field))
#                 result = search_recipes(recipes=recipes, query_res=name_res, result=result)
    
#     _recipes = []
#     for result_recipe in result:
#         _recipes.append(result_recipe.id)

#     cache.set(f"user:{current_user.id}:search_result", _recipes)
                
#     data = {"route": 2}
#     search_field = {
#         "tags" : allTags,
#         "ingredients" : allIngredients,
#         "names" : allNames
#     }
#     return render_template("search_view.html", data=data, search_field= search_field, tags=cache.get("all_tags"), ingredients=cache.get("all_ingredients"))
@views.route('/search', methods=['POST'])
def search():
    user_query = bleach.clean(request.form.get("search-field"))
    tags = [tag.strip() for tag in set(request.form.get('Tags', '').split(',')) if tag.strip()]
    ingredients = [ingredient.strip() for ingredient in set(request.form.get('Ingredients', '').split(',')) if ingredient.strip()]
    user_query = ",".join(tags) + ",".join(ingredients) + "," + user_query
    if not user_query:
        return redirect(request.referrer or url_for('views.home'))
    
   
    all_recipes_embeddings = cache.get('all_recipes_embeddings')

    if all_recipes_embeddings is None:
        all_recipes_embeddings = Recipe.query.filter(Recipe.embedding != None).with_entities(Recipe.id, Recipe.embedding).all()
        cache.set('all_recipes_embeddings', all_recipes_embeddings)
        cache.set('all_recipes_embeddings_len', len(all_recipes_embeddings))
        print("New recipes embeddings cache")
        print(f"all_recipes_len: {cache.get('all_recipes_embeddings_len')}")

    # Query the fine-tuned OpenAI model with the user's search query
    results = semantic_search_recipes(user_query=user_query, all_recipes_embeddings=all_recipes_embeddings, k_elements=cache.get('all_recipes_embeddings_len'))
    
    results_ids = [result[0][0] for result in results]
    
    cache.set(f"user:{current_user.id}:search_result", results_ids)
    # Return the search results to the user
    data = {"route": 2}
    # search_field = {
    #     "tags" : {},
    #     "ingredients" : {},
    #     "names" : user_query
    # }
    return render_template("search_view.html", data=data, search_field= user_query, tags=cache.get("all_tags"), ingredients=cache.get("all_ingredients"))

@views.route('/load_search', methods=['GET'])
def load_search():

    time.sleep(0.2)
    count = request.args.get('count', 0, type=int)
    try:

        recipe_list = cache.get(f"user:{current_user.id}:search_result")
        res = Recipe.query.filter(Recipe.id.in_(recipe_list[count: count + quantity]))
        data = {}
        for stuff in res:
            first_image = stuff.images.first()
            image_url = url_for('views.serve_image', filename=first_image.filename) if first_image else url_for('static', filename='images/food_image_empty.png')
            data[stuff.id] = {
                'name': stuff.name,
                'image_url': image_url
            }
        res = make_response(data)
    except:
        print("No more posts")
        res = make_response(jsonify({}), 200)

    return res

@views.route('/profile', methods=['GET'])
@login_required
def profile():
    data = {"route": 1}
    if not cache.get(f"user:{current_user.id}:profile"):
        ids = [recipe.id for recipe in Recipe.query.filter(Recipe.user_id==current_user.id).all()]
        cache.set(f"user:{current_user.id}:profile", ids)

    return render_template("profile.html", data=data, tags=cache.get("all_tags"), ingredients= cache.get("all_ingredients") ) 

@views.route('/load_profile', methods=['GET'])
@login_required
def load_profile():
    time.sleep(0.2)
    count = request.args.get('count', 0, type=int)

    try:
        recipe_ids = cache.get(f"user:{current_user.id}:profile")
        res = Recipe.query.filter(Recipe.id.in_(recipe_ids[count: count + quantity]))
        res = res[count: count + quantity]
        data = {}
        for stuff in res:
            first_image = stuff.images.first()
            image_url = url_for('views.serve_image', filename=first_image.filename) if first_image else url_for('static', filename='images/food_image_empty.png')
            data[stuff.id] = {
                'name': stuff.name,
                'image_url': image_url
            }
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
        
        print(recipe.name)
        # Handle steps
        steps = bleach.clean(request.form.get("Instructions"))
        recipe.steps = steps  # This will now be a |-separated string of steps
        
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
        tags = {tag.strip() for tag in set(request.form.get('TagsInput', '').split(',')) if tag.strip()}
        ingredients = {ingredient.strip() for ingredient in set(request.form.get('IngredientsInput', '').split(',')) if ingredient.strip()}
        # Fetch existing tags and ingredients in one query
        existing_tags = {tag.name: tag for tag in Tag.query.filter(Tag.name.in_(tags)).all()}
        existing_ingredients = {ingredient.name: ingredient for ingredient in Ingredient.query.filter(Ingredient.name.in_(ingredients)).all()}

        # Process tags
        for tag_name in tags:
            tag = existing_tags.get(tag_name)
            if not tag:
                tag = Tag(name=tag_name)
                db.session.add(tag)
            recipe.tags.append(tag)

        # Process ingredients
        for ingredient_name in ingredients:
            ingredient = existing_ingredients.get(ingredient_name)
            if not ingredient:
                ingredient = Ingredient(name=ingredient_name)
                db.session.add(ingredient)
            recipe.ingredients.append(ingredient)


        steps = recipe.steps.split('|')
        steps = [s.strip() for s in steps]
        text_data = f"{recipe.name} {recipe.ingredients} {recipe.tags or ''} {recipe.desc}. {'. '.join(steps)}"
        
        # Generate embedding for the recipe
        embedding = model.encode(text_data)
        recipe.embedding = embedding.tolist()

        user_search_cache_key = f"user:{current_user.id}:search_result"
        user_profile_cache_key = f"user:{current_user.id}:profile"
        # Use delete_many for efficient multiple key deletion
        cache.delete_many([
            user_search_cache_key,
            user_profile_cache_key,
            "all_tags",
            "all_ingredients",
            "all_recipes_embeddings"
        ])
        #Commit changes to database
        db.session.commit()

        add_recipe_to_faiss(recipe=recipe)

        return redirect(url_for('views.get_recipe', meal_id=recipe.id))
    
    # GET request
    recipe_id = request.args.get('recipe_id')
    if not recipe_id:
        return render_template("post_recipe_form.html", user=current_user, recipe=[], tags=cache.get("all_tags"), ingredients=cache.get("all_ingredients"))
        
    # Updating existing recipe
    recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
    if not recipe:
        abort(403)  # Forbidden if the recipe doesn't exist or doesn't belong to the user
    existing_images = Image.query.filter_by(recipe_id=recipe.id).all()
    existing_video = Video.query.filter_by(recipe_id=recipe.id).first()
    return render_template("post_recipe_form.html", user=current_user, recipe=recipe, tags=cache.get("all_tags"), ingredients=cache.get("all_ingredients"), existing_images=existing_images, existing_video=existing_video)

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
    
    user_search_cache_key = f"user:{current_user.id}:search_result"
    user_profile_cache_key = f"user:{current_user.id}:profile"
    # Use delete_many for efficient multiple key deletion
    cache.delete_many([
        user_search_cache_key,
        user_profile_cache_key,
        "all_tags",
        "all_ingredients"
    ])
    return jsonify({}) 


