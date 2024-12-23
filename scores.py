import json
import time
import asyncio
import aiohttp
from flask import Flask, jsonify
from threading import Thread

# Configuration du logger pour enregistrer les erreurs
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Création de l'application Flask
app = Flask(__name__)

# Fonction pour convertir une cote fractionnelle en décimale
def fractional_to_decimal(fractional_value):
    try:
        numerator, denominator = map(int, fractional_value.split('/'))
        return (numerator / denominator) + 1
    except Exception as e:
        print(f"Erreur de conversion de la cote {fractional_value}: {e}")
        return None

# Fonction pour décoder les chaînes contenant des séquences Unicode échappées
def decode_unicode_string(input_string):
    try:
        return input_string.encode('utf-8').decode('unicode_escape')
    except Exception as e:
        print(f"Erreur de décodage de la chaîne : {e}")
        return input_string

# Fonction asynchrone pour récupérer les cotes d'un match via l'API
async def get_odds_for_match(session, match_id):
    url = f"https://www.sofascore.com/api/v1/event/{match_id}/odds/1/featured"
    
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                odds = {}

                if 'featured' in data:
                    featured_data = data['featured']
                    if 'default' in featured_data:
                        choices = featured_data['default']['choices']
                        for choice in choices:
                            if choice['name'] == '1':
                                odds['1'] = fractional_to_decimal(choice['fractionalValue'])
                            elif choice['name'] == 'X':
                                odds['X'] = fractional_to_decimal(choice['fractionalValue'])
                            elif choice['name'] == '2':
                                odds['2'] = fractional_to_decimal(choice['fractionalValue'])
                
                return odds
            else:
                print(f"Erreur lors de la récupération des données pour le match {match_id}. Code: {response.status}")
                return None
    except Exception as e:
        print(f"Erreur lors de la requête pour le match {match_id}: {e}")
        return None

# Fonction pour filtrer et sauvegarder les matchs avec leurs cotes
async def filter_and_save_matches():
    with open('foot.json', 'r', encoding='utf-8') as file:
        data = json.load(file)

    inprogress_matches = []
    notstarted_matches = []

    async with aiohttp.ClientSession() as session:

        async def filter_matches(matches, status):
            tasks = []
            for match in matches:
                if isinstance(match, dict):
                    if match.get("status") == status:
                        match_id = match["id"]
                        task = get_odds_for_match(session, match_id)
                        tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            
            for idx, match in enumerate(matches):
                if isinstance(match, dict) and match.get("status") == status and results[idx]:
                    match_data = {
                        "homeTeam": decode_unicode_string(match["homeTeam"]),
                        "awayTeam": decode_unicode_string(match["awayTeam"]),
                        "id": match["id"],
                        "odds": results[idx]
                    }
                    if status == "inprogress":
                        inprogress_matches.append(match_data)
                    elif status == "notstarted":
                        notstarted_matches.append(match_data)

        if isinstance(data, list):
            await filter_matches(data, "inprogress")
            await filter_matches(data, "notstarted")

        if "ongoing" in data:
            await filter_matches(data["ongoing"], "inprogress")

        if "upcoming" in data:
            await filter_matches(data["upcoming"], "notstarted")

    if inprogress_matches or notstarted_matches:
        with open('scores.json', 'w', encoding='utf-8') as file:
            json.dump({
                "inprogress": inprogress_matches,
                "notstarted": notstarted_matches
            }, file, ensure_ascii=False, indent=4)  # `ensure_ascii=False` pour conserver les caractères spéciaux
        print("Les matchs avec leurs cotes ont été enregistrés dans scores.json.")
    else:
        print("Aucun match correspondant n'a été trouvé.")

# Fonction principale pour exécuter la boucle asynchrone
async def main():
    while True:
        await filter_and_save_matches()
        await asyncio.sleep(1)  # Pause de 1 seconde avant la prochaine itération

# Route Flask pour récupérer les matchs en cours avec leurs cotes
@app.route('/live_matches', methods=['GET'])
def get_live_matches():
    try:
        with open('scores.json', 'r', encoding='utf-8') as file:
            live_matches = json.load(file)
        return jsonify(live_matches)
    except Exception as e:
        print(f"Erreur lors de la récupération des matchs en direct: {e}")
        return jsonify({"error": "Could not fetch live matches"}), 500

# Fonction pour lancer Flask sur le port 10000
def run_flask():
    app.run(host='0.0.0.0', port=10000)  # Lancer Flask sur le port 10000

if __name__ == "__main__":
    # Démarrer Flask dans un thread séparé pour ne pas bloquer la boucle asynchrone
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Lancer la boucle principale en mode asynchrone pour traiter les matchs
    asyncio.run(main())
