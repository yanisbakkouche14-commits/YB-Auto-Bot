import os


TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError(
        "Token Telegram manquant. Définissez TELEGRAM_TOKEN dans l'environnement."
    )
