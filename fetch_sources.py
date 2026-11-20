import re
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

# En-tête "navigateur" pour éviter les blocages
HEADERS = {"User-Agent": "Mozilla/5.0 (agent-veille; contact: perso)"}

# Nombre de jours en arrière pris en compte (2 envois par semaine)
JOURS_VEILLE = 4

# Nombre max d'articles gardés par source
MAX_PAR_SOURCE = 5

# Sources par domaine
SOURCES = {
    "Data engineering / BI": [
        "https://www.dataengineeringweekly.com/feed",
    ],
    "Agents IA / LLM": [
        "https://simonwillison.net/atom/everything/",
        "https://huggingface.co/blog/feed.xml",
    ],
    "Vision par ordinateur": [
        "https://export.arxiv.org/api/query?search_query=cat:cs.CV&sortBy=submittedDate&sortOrder=descending&max_results=10",
    ],
    "Robotique / voiture autonome": [
        "https://export.arxiv.org/api/query?search_query=cat:cs.RO+AND+abs:autonomous+AND+abs:driving&sortBy=submittedDate&sortOrder=descending&max_results=10",
    ],
}


def nettoyer_html(texte):
    """Retire les balises HTML et raccourcit le résumé."""
    texte = re.sub(r"<[^>]+>", " ", texte or "")
    texte = re.sub(r"\s+", " ", texte).strip()
    return texte[:500]


def date_article(entry):
    """Renvoie la date de publication de l'article (ou None)."""
    date_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if date_struct is None:
        return None
    return datetime.fromtimestamp(time.mktime(date_struct), tz=timezone.utc)


def lire_flux(url):
    """Télécharge un flux et renvoie ses entrées (liste vide si échec)."""
    try:
        reponse = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as erreur:
        print(f"[ERREUR] {url} -> {erreur}")
        return []

    if reponse.status_code != 200:
        print(f"[ERREUR] {url} -> code HTTP {reponse.status_code}")
        return []

    flux = feedparser.parse(reponse.content)
    if not flux.entries:
        print(f"[VIDE] {url} -> flux lu mais aucun article")
    return flux.entries


def recuperer_articles():
    """Parcourt toutes les sources et renvoie la liste des articles récents."""
    limite = datetime.now(timezone.utc) - timedelta(days=JOURS_VEILLE)
    articles = []

    for domaine, urls in SOURCES.items():
        for url in urls:
            entries = lire_flux(url)

            gardes = 0
            for entry in entries:
                date = date_article(entry)
                if date is not None and date < limite:
                    continue

                articles.append({
                    "domaine": domaine,
                    "titre": " ".join(entry.get("title", "").split()),
                    "lien": entry.get("link", ""),
                    "resume": nettoyer_html(entry.get("summary", "")),
                    "date": date.strftime("%d/%m/%Y") if date else "inconnue",
                })

                gardes += 1
                if gardes >= MAX_PAR_SOURCE:
                    break

            # Pause pour respecter les limites d'arXiv
            if "arxiv" in url:
                time.sleep(3)

    return articles


if __name__ == "__main__":
    articles = recuperer_articles()

    print(f"\n{len(articles)} articles récupérés\n")
    for domaine in SOURCES:
        print(f"=== {domaine} ===")
        for a in articles:
            if a["domaine"] == domaine:
                print(f"- [{a['date']}] {a['titre']}")
        print()
