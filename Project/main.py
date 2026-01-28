import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, render_template, jsonify
import pandas as pd
import ast

app = Flask(__name__)

dataframe = pd.read_csv('povarenok_recipes_cleaned.csv')
dataframe['ingredients'] = dataframe['ingredients'].apply(
    ast.literal_eval)


all_ingredients = set()
for recipe_ingredients in dataframe['ingredients']:
    all_ingredients.update(recipe_ingredients.keys())  # Добавляем ключи (ингредиенты) в множество
all_ingredients = {ingredient.lower() for ingredient in all_ingredients}


# Функция для парсинга данных о блюде (калории, белки, жиры, углеводы и калории на 100 г)
def fetch_recipe_info(url):
    try:
        response = requests.get(url) # Отправляем GET-запрос на страницу рецепта
        response.raise_for_status()  # Проверяем успешность запроса (если ошибка — выбрасывается исключение)
        # Парсим HTML-страницу с использованием BeautifulSoup
        soup = BeautifulSoup(response.text, 'lxml')  # Используем lxml для ускоренного парсинга

        nutrition_block = soup.find("div", itemprop="nutrition")  #  блок с питательной ценностью
        if not nutrition_block:
            return {
                "calories": "N/A",
                "proteins": "N/A",
                "fats": "N/A",
                "carbs": "N/A",
                "calories100g": "N/A",
                "weight": "N/A"
            }

        # Извлекаем данные из блока
        calories = nutrition_block.find("strong", itemprop="calories")
        protein = nutrition_block.find("strong", itemprop="proteinContent")
        fat = nutrition_block.find("strong", itemprop="fatContent")
        carbs = nutrition_block.find("strong", itemprop="carbohydrateContent")

        calories_100g = "N/A"
        row_with_100g = nutrition_block.find("strong", string="100 г блюда")
        if row_with_100g:
            calories_100g_td = row_with_100g.find_parent("tr").find_next_sibling("tr").find("strong")
            calories_100g = calories_100g_td.text.strip() if calories_100g_td else "N/A"

        # Возвращаем извлеченные данные
        return {
            "calories": calories.text.strip() if calories else "нема",
            "proteins": protein.text.strip() if protein else "нема",
            "fats": fat.text.strip() if fat else "тютю",
            "carbs": carbs.text.strip() if carbs else "нема",
            "calories100g": calories_100g
        }
    except Exception as e:
        print(f"Ошибка при парсинге {url}: {e}")
        return {
            "calories": "N/A",
            "proteins": "N/A",
            "fats": "N/A",
            "carbs": "N/A",
            "calories100g": "N/A"
        }


# Функция для параллельной загрузки данных о рецептах
def fetch_recipe_info_parallel(urls):
    with ThreadPoolExecutor() as executor:  # Создаем пул потоков для параллельной загрузки
        results = list(executor.map(fetch_recipe_info, urls))  # Используем executor.map для параллельной загрузки данных
    return results


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/check-ingredient", methods=["POST"])
def check_ingredient():
    ingredient = request.json.get("ingredient", "").strip().lower()
    if ingredient in all_ingredients:
        return jsonify({"status": "found", "ingredient": ingredient})
    return jsonify({"status": "not_found", "ingredient": ingredient})



@app.route("/get-recipes", methods=["POST"])
def get_recipes():
    # Получаем список ингредиентов от пользователя
    user_ingredients = request.json.get("ingredients", [])

    if not user_ingredients:
        return jsonify({"error": "Ингредиенты не были предоставлены. Пожалуйста, добавьте хотя бы один продукт."}), 400


    user_ingredients = {ingredient.lower() for ingredient in user_ingredients}

    # Функция для подсчета совпадений ингредиентов
    def count_matches(recipe_ingredients):
        recipe_ingredients = {ingredient.lower(): amount for ingredient, amount in
                              recipe_ingredients.items()}
        matches = set(user_ingredients) & set(recipe_ingredients.keys())
        return len(matches)

    # Функция для проверки точного совпадения ингредиентов
    def is_exact_match(recipe_ingredients):
        recipe_ingredients = {ingredient.lower(): amount for ingredient, amount in recipe_ingredients.items()}
        if set(user_ingredients) != set(recipe_ingredients.keys()):
            return False
        return True

    # Добавляем новые колонки в датафрейм для хранения информации о совпадениях
    dataframe['num_ingredients'] = dataframe['ingredients'].apply(lambda x: len(x.keys()))
    dataframe['matches'] = dataframe['ingredients'].apply(count_matches)  # Количество совпадений
    dataframe['exact_match'] = dataframe['ingredients'].apply(is_exact_match)  # Точное совпадение
    dataframe['diference'] = dataframe['num_ingredients'] - dataframe['matches']

    # Сортируем рецепты по точному совпадению, совпадениям и разнице
    sorted_recipes = dataframe.sort_values(by=['exact_match', 'matches', 'diference'], ascending=[False, False, True])
    top_recipes = sorted_recipes.head(5)


    recipe_urls = top_recipes['url'].tolist()
    recipe_info = fetch_recipe_info_parallel(recipe_urls)

    # Формируем ответ с результатами
    response = []
    for i, row in enumerate(top_recipes.iterrows()):
        row = row[1]  # Получаем строку
        recipe_info_data = recipe_info[i]
        match_info = f"{row['matches']} из {len(row['ingredients'])} ингредиентов"
        response.append({
            'name': row['name'],
            'url': row['url'],
            'match_info': match_info,
            **recipe_info_data  # Добавляем данные о питательной ценности (калории, белки, жиры и т.д.)
        })

    return jsonify(response)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=9000, debug=True)
