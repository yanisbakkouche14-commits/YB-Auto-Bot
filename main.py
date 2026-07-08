from voitures import voitures
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TOKEN

from scanner.autoscout import rechercher_voitures

from database.database import ajouter_annonce

from ai.analyse import analyser_annonce
from ai.marche import analyser_marche


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(

        "🚗 Bienvenue sur YB Auto Bot\n\n"

        "🤖 Assistant intelligent d'achat / revente automobile\n\n"

        "Tape /aide pour voir toutes les commandes."

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

        "🌍 Plateformes surveillées\n\n"

        "✅ AutoScout24\n"

        "🚧 2ememain (bientôt)\n"

        "🚧 Facebook Marketplace (bientôt)"

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
        "🔎 Analyse du marché en cours..."
    )

    voitures = rechercher_voitures(modele)

    if len(voitures) == 0:

        await update.message.reply_text(
            "❌ Aucune annonce trouvée."
        )
        return

    marche = analyser_marche(voitures)

    texte = (
        "📊 ANALYSE DU MARCHÉ\n\n"

        f"🚗 Annonces analysées : {marche['nombre']}\n"

        f"💰 Prix moyen : {marche['moyenne']} €\n"

        f"📈 Prix médian : {marche['mediane']} €\n"

        f"📉 Fourchette : {marche['minimum']} € → {marche['maximum']} €\n"

        "\n━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    for voiture in voitures:

        analyse = analyser_annonce(voiture)

        kilometrage = voiture.get("kilometrage", "Inconnu")

        if isinstance(kilometrage, dict):
            kilometrage = kilometrage.get(
                "value",
                "Inconnu"
            )

        texte += (

            f"🚗 {voiture['modele']}\n\n"

            f"💰 Prix affiché : {voiture['prix']}\n"

            f"📍 Ville : {voiture['ville']}\n"

            f"📅 Année : {voiture.get('annee', 'Inconnue')}\n"

            f"🛣️ Kilométrage : {kilometrage} km\n"

            f"⛽ Carburant : {voiture.get('carburant', 'Inconnu')}\n"

            f"⚙️ Boîte : {voiture.get('boite', 'Inconnue')}\n\n"

            f"📊 Valeur estimée : {analyse['prix_marche']} €\n"

            f"🎯 Offre de départ : {analyse['offre_depart']} €\n"

            f"🤝 Prix conseillé : {analyse['prix_conseille']} €\n"

            f"⛔ Maximum : {analyse['prix_max']} €\n\n"

            f"💵 Bénéfice estimé : +{analyse['benefice']} €\n"

            f"⭐ Score : {analyse['score']}/100\n"

            f"💡 {analyse['conseil']}\n\n"

            f"🔗 {voiture['lien']}\n"

            "━━━━━━━━━━━━━━━━━━━━\n\n"

        )

    await update.message.reply_text(texte)
app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("aide", aide))
app.add_handler(CommandHandler("sites", sites))
app.add_handler(CommandHandler("recherche", recherche))
app.add_handler(CommandHandler("internet", internet))

print("=" * 60)
print("🚗 YB AUTO BOT")
print("🤖 Assistant intelligent d'achat / revente automobile")
print("📊 Analyse du marché activée")
print("✅ Bot lancé avec succès !")
print("=" * 60)

app.run_polling()