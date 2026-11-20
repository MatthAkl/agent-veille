import os
import re
from datetime import datetime
from typing import TypedDict

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

from fetch_sources import recuperer_articles
from envoi_mail import envoyer_mail

load_dotenv()

# ---------- Configuration ----------

def creer_llm(nom_modele):
    """Crée un client Gemini pour un modèle donné."""
    return ChatGoogleGenerativeAI(
        model=nom_modele,
        timeout=120,
        max_retries=1,
    )


# Modèles par ordre de préférence (lus dans le .env)
noms_modeles = [
    os.getenv("GEMINI_MODEL"),
    os.getenv("GEMINI_MODEL_SECOURS"),
    os.getenv("GEMINI_MODEL_SECOURS_2"),
]
noms_modeles = [nom for nom in noms_modeles if nom]
modeles = [creer_llm(nom) for nom in noms_modeles]

# Le premier modèle, avec bascule automatique vers les suivants en cas d'erreur
llm = modeles[0].with_fallbacks(modeles[1:])

# Relance d'un nœud en cas d'échec : 5 essais, pauses de 30 s, 60 s, puis 120 s max
RELANCE = RetryPolicy(
    max_attempts=5,
    initial_interval=30,
    backoff_factor=2,
    max_interval=120,
)

# Ton profil : domaines suivis et niveau dans chacun
PROFIL = {
    "Data engineering / BI": "intermédiaire",
    "Agents IA / LLM": "intermédiaire",
    "Vision par ordinateur": "intermédiaire",
    "Robotique / voiture autonome": "débutant",
}

# Nombre d'articles retenus par domaine
ARTICLES_PAR_DOMAINE = 2

# Style du mail
CSS = """
body { margin: 0; padding: 24px 0; background: #f4f5f7; font-family: Arial, Helvetica, sans-serif; color: #2b2b2b; }
.conteneur { max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.entete { background: #1f2a44; color: #ffffff; padding: 28px 32px; }
.entete h1 { margin: 0; font-size: 24px; }
.entete p { margin: 6px 0 0; font-size: 14px; color: #c9d1e3; }
.domaine { padding: 24px 32px; border-bottom: 1px solid #eeeeee; }
.domaine h2 { margin: 0 0 16px; font-size: 19px; color: #1f2a44; border-left: 4px solid #3b6fd8; padding-left: 10px; }
.article { margin: 0 0 18px; }
.article h3 { margin: 0 0 6px; font-size: 16px; color: #1f2a44; }
.article p { margin: 0 0 6px; font-size: 14px; line-height: 1.55; }
a { color: #3b6fd8; text-decoration: none; font-weight: bold; }
.exercice { background: #f0f5ff; border: 1px solid #d6e2fb; border-radius: 8px; padding: 16px 18px; margin-top: 8px; }
.exercice h3 { margin: 0 0 8px; font-size: 16px; color: #2b56b0; }
.exercice p, .exercice li { font-size: 14px; line-height: 1.55; }
pre { background: #1e1e1e; color: #f1f1f1; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 13px; }
.pied { padding: 20px 32px; text-align: center; font-size: 12px; color: #888888; }
"""


# ---------- État partagé entre les nœuds ----------

class EtatVeille(TypedDict):
    articles: list[dict]
    selection: list[dict]
    mail_html: str


# ---------- Nœuds du graphe ----------

def collecter(etat: EtatVeille):
    """Nœud 1 : récupère les articles récents de toutes les sources."""
    articles = recuperer_articles()
    print(f"[collecter] {len(articles)} articles récupérés")
    return {"articles": articles}


def selectionner(etat: EtatVeille):
    """Nœud 2 : garde les articles les plus utiles pour chaque domaine."""
    selection = []

    for domaine, niveau in PROFIL.items():
        candidats = [a for a in etat["articles"] if a["domaine"] == domaine]

        if not candidats:
            print(f"[selectionner] {domaine} : aucun article")
            continue

        # Pas besoin du LLM s'il y a peu d'articles
        if len(candidats) <= ARTICLES_PAR_DOMAINE:
            selection.extend(candidats)
            print(f"[selectionner] {domaine} : {len(candidats)} article(s) gardé(s) sans tri")
            continue

        print(f"[selectionner] {domaine} : tri de {len(candidats)} articles par Gemini...")

        liste = "\n".join(
            f"{i}. {a['titre']} : {a['resume'][:300]}"
            for i, a in enumerate(candidats)
        )

        prompt = f"""Tu aides un profil data (niveau {niveau} en "{domaine}") à faire sa veille.
Il cherche des sujets qui le font progresser concrètement et qu'il peut mettre en pratique.

Voici les articles disponibles :
{liste}

Choisis les {ARTICLES_PAR_DOMAINE} articles les plus utiles pour lui.
Évite les annonces de version mineure et les sujets trop anecdotiques.
Réponds uniquement avec les numéros séparés par une virgule, par exemple : 3, 0"""

        reponse = llm.invoke(prompt)
        numeros = [int(n) for n in re.findall(r"\d+", reponse.text)]

        gardes = 0
        for i in numeros:
            if 0 <= i < len(candidats) and gardes < ARTICLES_PAR_DOMAINE:
                selection.append(candidats[i])
                gardes += 1

        print(f"[selectionner] {domaine} : {gardes} article(s) retenu(s)")

    print(f"[selectionner] {len(selection)} articles retenus au total")
    return {"selection": selection}


def rediger(etat: EtatVeille):
    """Nœud 3 : rédige le contenu du mail en français (HTML structuré)."""
    print("[rediger] rédaction du mail par Gemini...")

    blocs = []
    for domaine, niveau in PROFIL.items():
        articles = [a for a in etat["selection"] if a["domaine"] == domaine]
        if not articles:
            continue

        texte = "\n".join(
            f"- Titre : {a['titre']}\n  Lien : {a['lien']}\n  Résumé source : {a['resume']}"
            for a in articles
        )
        blocs.append(f"## {domaine} (niveau {niveau})\n{texte}")

    contenu = "\n\n".join(blocs)

    prompt = f"""Tu rédiges un mail de veille personnalisé, entièrement en français.

Pour chaque domaine ci-dessous :
1. Pour chaque article : le titre traduit en français avec le titre original entre parenthèses,
   un résumé de 3 à 4 phrases qui explique pourquoi c'est important, et un lien "Lire l'article".
2. Un exercice pratique adapté au niveau indiqué (30 à 45 minutes), si possible en Python,
   en lien direct avec les articles. Pour un niveau débutant, explique les termes techniques.

Respecte exactement cette structure HTML pour chaque domaine :

<div class="domaine">
  <h2>Nom du domaine</h2>
  <div class="article">
    <h3>Titre en français (Titre original)</h3>
    <p>Résumé...</p>
    <p><a href="LIEN">Lire l'article</a></p>
  </div>
  <div class="exercice">
    <h3>Exercice pratique</h3>
    <p>Consignes...</p>
  </div>
</div>

Contraintes :
- Réponds uniquement avec ce HTML, sans balise html, head, body ni style.
- Pour du code dans un exercice, utilise <pre><code>...</code></pre>.
- Pas de bloc de code Markdown autour de la réponse.
- Style sobre, sans emojis.

Contenu :
{contenu}"""

    reponse = llm.invoke(prompt)
    html = reponse.text.strip()

    # Sécurité : retire un éventuel bloc ```html autour de la réponse
    html = html.removeprefix("```html").removeprefix("```").removesuffix("```").strip()

    print("[rediger] mail rédigé")
    return {"mail_html": html}


def envoyer(etat: EtatVeille):
    """Nœud 4 : met en page le mail, garde une copie locale et l'envoie."""
    page = construire_page(etat["mail_html"], len(etat["selection"]))

    # Copie locale pour pouvoir relire le mail
    with open("apercu_mail.html", "w", encoding="utf-8") as f:
        f.write(page)

    date = datetime.now().strftime("%d/%m/%Y")
    envoyer_mail(f"Ta veille tech du {date}", page)

    return {}


# ---------- Mise en page finale ----------

def construire_page(contenu_html, nb_articles):
    """Habille le contenu généré avec l'en-tête, le style et le pied de page."""
    date = datetime.now().strftime("%d/%m/%Y")

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ta veille du {date}</title>
<style>{CSS}</style>
</head>
<body>
<div class="conteneur">
  <div class="entete">
    <h1>Ta veille tech</h1>
    <p>{date} · {nb_articles} articles sélectionnés pour toi</p>
  </div>
  {contenu_html}
  <div class="pied">Généré automatiquement par ton agent de veille (LangGraph + Gemini)</div>
</div>
</body>
</html>"""


# ---------- Arête conditionnelle ----------

def apres_collecte(etat: EtatVeille):
    """S'il n'y a aucun article, on arrête le graphe."""
    if etat["articles"]:
        return "selectionner"
    return END


# ---------- Construction du graphe ----------

graphe = StateGraph(EtatVeille)

graphe.add_node("collecter", collecter)
graphe.add_node("selectionner", selectionner, retry_policy=RELANCE)
graphe.add_node("rediger", rediger, retry_policy=RELANCE)
graphe.add_node("envoyer", envoyer)

graphe.add_edge(START, "collecter")
graphe.add_conditional_edges("collecter", apres_collecte, ["selectionner", END])
graphe.add_edge("selectionner", "rediger")
graphe.add_edge("rediger", "envoyer")
graphe.add_edge("envoyer", END)

agent = graphe.compile()


# ---------- Lancement ----------

if __name__ == "__main__":
    print(f"Modèles utilisés (ordre de bascule) : {', '.join(noms_modeles)}")

    resultat = agent.invoke({"articles": [], "selection": [], "mail_html": ""})

    if not resultat["mail_html"]:
        print("Aucun article cette fois, pas de mail envoyé.")
    else:
        print("Veille terminée et envoyée.")
