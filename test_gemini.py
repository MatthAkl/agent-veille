import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Charge les variables du fichier .env
load_dotenv()

# Initialise le modèle Gemini
llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL"),
    temperature=0.3,
)

# Envoie une question de test
reponse = llm.invoke("Explique en 2 phrases ce qu'est LangGraph.")

print(reponse.text)
