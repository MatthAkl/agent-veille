import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()


def envoyer_mail(sujet, html, debug=False):
    """Envoie un mail HTML via le serveur SMTP de Gmail (port 587 + STARTTLS)."""
    expediteur = os.getenv("GMAIL_ADRESSE", "").strip()
    mot_de_passe = os.getenv("GMAIL_MOT_DE_PASSE_APP", "").replace(" ", "").strip('"').strip("'")
    destinataire = os.getenv("MAIL_DESTINATAIRE", "").strip() or expediteur

    # Vérifications avant l'envoi
    if not expediteur or not mot_de_passe:
        raise ValueError("GMAIL_ADRESSE ou GMAIL_MOT_DE_PASSE_APP manquant dans le .env")
    if len(mot_de_passe) != 16:
        raise ValueError(f"Le mot de passe d'application doit faire 16 caractères (actuellement {len(mot_de_passe)})")

    message = MIMEMultipart("alternative")
    message["Subject"] = sujet
    message["From"] = f"Agent de veille <{expediteur}>"
    message["To"] = destinataire

    # Version texte de secours, puis version HTML
    message.attach(MIMEText("Ta veille est disponible en version HTML.", "plain", "utf-8"))
    message.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as serveur:
        if debug:
            serveur.set_debuglevel(1)
        serveur.ehlo()
        serveur.starttls()
        serveur.ehlo()
        serveur.login(expediteur, mot_de_passe)
        serveur.send_message(message)

    print(f"[envoi] mail envoyé à {destinataire}")


# Test : envoie l'aperçu déjà généré, sans relancer Gemini
if __name__ == "__main__":
    with open("apercu_mail.html", encoding="utf-8") as f:
        html = f.read()

    envoyer_mail("Test - Ta veille tech", html, debug=True)
