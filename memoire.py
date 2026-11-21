import json
import os
from datetime import datetime

# Fichier qui garde la trace des articles déjà envoyés
FICHIER_HISTORIQUE = "historique.json"

# Nombre max d'entrées conservées (les plus anciennes sont supprimées)
MAX_ENTREES = 1000


def charger_historique():
    """Renvoie la liste des articles déjà envoyés."""
    if not os.path.exists(FICHIER_HISTORIQUE):
        return []

    with open(FICHIER_HISTORIQUE, encoding="utf-8") as f:
        return json.load(f)


def liens_deja_envoyes():
    """Renvoie l'ensemble des liens déjà envoyés."""
    return {entree["lien"] for entree in charger_historique()}


def enregistrer_envoi(articles):
    """Ajoute les articles envoyés à l'historique."""
    historique = charger_historique()
    date_envoi = datetime.now().strftime("%Y-%m-%d")

    for a in articles:
        historique.append({
            "lien": a["lien"],
            "titre": a["titre"],
            "domaine": a["domaine"],
            "date_envoi": date_envoi,
        })

    # Garde seulement les entrées les plus récentes
    historique = historique[-MAX_ENTREES:]

    with open(FICHIER_HISTORIQUE, "w", encoding="utf-8") as f:
        json.dump(historique, f, ensure_ascii=False, indent=2)

    print(f"[memoriser] {len(articles)} articles ajoutés à l'historique ({len(historique)} au total)")
