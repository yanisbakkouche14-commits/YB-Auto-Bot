from voitures import voitures
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TOKEN

from scanner.autoscout import rechercher_voitures
from database.database import ajouter_annonce
from ai.analyse import analyser_annonce


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚗 Bienvenue sur YB Auto Bot\n\n"
        "Je vais t'aider à trouver les meilleures affaires automobiles."
    )


async def aide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Commandes disponibles\n\n"
        "/start\n"
        "/aide\n"
        "/sites\n"
        "/recherche golf\n"
        "/internet golf"
    )


async def sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌍 Sites surveillés\n\n"
        "✅ AutoScout24\n"
        "✅ 2ememain\n"
        "⏳ Facebook Marketplace"
    )


async def recherche(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) == 0:
        await update.message.reply_text(
            "❌ Utilisation : /recherche Golf"
        )
        return

    recherche_utilisateur = " ".join(context.args).lower()

    texte = "🚗 Résultats trouvés\n\n"

    trouve = False

    for voiture in voitures:

        if recherche_utilisateur not in voiture["modele"].lower():
            continue

        profit = voiture["revente"] - voiture["prix"]

        ajouter_annonce(
            voiture["modele"],
            voiture["prix"],
            voiture["ville"],
            voiture["modele"]
        )

        texte += (
            f"🚘 {voiture['modele']}\n"
            f"💰 Prix : {voiture['prix']} €\n"
            f"📍 Ville : {voiture['ville']}\n"
            f"📈 Revente : {voiture['revente']} €\n"
            f"💵 Profit : +{profit} €\n\n"
        )

        trouve = True

    if not trouve:
        texte = "❌ Aucune voiture trouvée."

    await update.message.reply_text(texte)
async def internet(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) == 0:
        await update.message.reply_text(
            "❌ Utilisation : /internet Golf"
        )
        return

    modele = " ".join(context.args)

    await update.message.reply_text(
        "🔎 Recherche sur AutoScout24..."
    )

    voitures = rechercher_voitures(modele)

    if len(voitures) == 0:
        await update.message.reply_text(
            "❌ Aucune annonce trouvée."
        )
        return

    texte = "🌍 Annonces trouvées\n\n"

    for voiture in voitures:

        analyse = analyser_annonce(voiture)

        kilometrage = voiture.get("kilometrage", "Inconnu")

        if isinstance(kilometrage, dict):
            kilometrage = kilometrage.get("value", "Inconnu")

        texte += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🚗 {voiture['modele']}\n\n"

            f"💰 Prix affiché : {voiture['prix']}\n"
            f"📍 Ville : {voiture['ville']}\n"
            f"📅 Année : {voiture.get('annee', 'Inconnue')}\n"
            f"🛣️ Kilométrage : {kilometrage} km\n"
            f"⛽ Carburant : {voiture.get('carburant', 'Inconnu')}\n"
            f"⚙️ Boîte : {voiture.get('boite', 'Inconnue')}\n\n"

            f"📊 Valeur estimée : {analyse['prix_marche']} €\n\n"

            f"🎯 Commence à négocier : {analyse['offre_depart']} €\n"
            f"🤝 Prix conseillé : {analyse['prix_conseille']} €\n"
            f"⛔ Ne dépasse jamais : {analyse['prix_max']} €\n\n"

            f"💵 Bénéfice estimé : +{analyse['benefice']} €\n"
            f"⭐ Score : {analyse['score']}/100\n"
            f"💡 Conseil : {analyse['conseil']}\n\n"

            f"🔗 {voiture['lien']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )

    await update.message.reply_text(texte)   
app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("aide", aide))
app.add_handler(CommandHandler("sites", sites))
app.add_handler(CommandHandler("recherche", recherche))
app.add_handler(CommandHandler("internet", internet))

print("=" * 50)
print("🚗 YB AUTO BOT V2")
print("🤖 Assistant d'achat / revente automobile")
print("✅ Bot lancé avec succès !")
print("=" * 50)

app.run_polling()