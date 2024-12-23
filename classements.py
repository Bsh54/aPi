import json
import asyncio
import aiohttp
import logging
from flask import Flask, jsonify

# Configuration du logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Créer une instance Flask
app = Flask(__name__)

# Fonction pour extraire les informations importantes des joueurs
def extract_player_info(player_data):
    return {
        "name": player_data["player"]["name"],
        "shortName": player_data["player"]["shortName"],
        "position": player_data["position"],
        "jerseyNumber": player_data["jerseyNumber"],
        "height": player_data["player"].get("height"),
        "nationality": player_data["player"]["country"]["name"],
        "marketValueCurrency": player_data["player"].get("marketValueCurrency"),
        "dateOfBirth": player_data["player"].get("dateOfBirthTimestamp"),
        "isSubstitute": player_data.get("substitute", False),
        "statistics": player_data.get("statistics", {})
    }

# Fonction asynchrone pour récupérer les lineups
async def get_lineup_data(session, match_id):
    url = f"https://www.sofascore.com/api/v1/event/{match_id}/lineups"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return {
                    "matchId": match_id,
                    "confirmed": data.get("confirmed"),
                    "homeTeam": [extract_player_info(player) for player in data["home"]["players"]],
                    "awayTeam": [extract_player_info(player) for player in data["away"]["players"]]
                }
            else:
                logging.warning(f"Erreur {response.status} pour le match {match_id}")
                return None
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des lineups pour le match {match_id}: {e}")
        return None

# Fonction pour traiter les matchs et organiser les résultats
async def process_matches(file_path):
    # Charger le fichier local
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    results = {"ongoing": [], "finished": [], "not_started": []}

    # Créer une session aiohttp pour les requêtes
    async with aiohttp.ClientSession() as session:
        tasks = []

        # Boucle infinie de 3 secondes
        while True:
            # Parcourir les matchs et créer des tâches selon leur statut
            for match in data.get("matches", []):
                match_id = match["id"]
                match_status = match["status"]

                # Préparer les données selon le statut
                if match_status in ["inprogress", "finished", "notstarted"]:
                    match_data = {
                        "id": match_id,
                        "homeTeam": match["homeTeam"],
                        "awayTeam": match["awayTeam"],
                        "startTime": match.get("startTime"),
                        "status": match_status
                    }

                    if match_status in ["inprogress", "finished"]:
                        results[match_status].append(match_data)
                        tasks.append(get_lineup_data(session, match_id))
                    elif match_status == "notstarted":
                        results["not_started"].append(match_data)

            # Attendre les résultats des tâches
            lineups = await asyncio.gather(*tasks, return_exceptions=True)
            lineups = [lineup for lineup in lineups if lineup]  # Supprimer les erreurs et résultats nuls

            # Associer les données de lineup aux matchs correspondants
            for match_list in [results["ongoing"], results["finished"]]:
                for match in match_list:
                    match_lineup = next((lineup for lineup in lineups if lineup["matchId"] == match["id"]), None)
                    if match_lineup:
                        match["lineup"] = match_lineup

            # Enregistrer les résultats dans classements.json
            with open("classements.json", "w", encoding="utf-8") as file:
                json.dump(results, file, ensure_ascii=False, indent=4)

            logging.info("Les données des matchs ont été enregistrées dans classements.json.")

            # Attendre 3 secondes avant de répéter la boucle
            await asyncio.sleep(3)

# Route Flask pour afficher les résultats
@app.route('/results', methods=['GET'])
async def get_results():
    with open('classements.json', 'r', encoding='utf-8') as file:
        results = json.load(file)
    return jsonify(results)

# Fonction principale
async def main():
    file_path = "foot.json"  # Chemin du fichier local
    await process_matches(file_path)

# Exécuter l'application Flask
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
    asyncio.run(main())
