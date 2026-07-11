from voitures import voitures
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TOKEN

from scanner.autoscout import rechercher_voitures

from database.database import (
    ajouter_annonce,
    ajouter_surveillance,
    lister_surveillances,
    supprimer_surveillance
)

from ai.analyse import analyser_annonce
from ai.marche import analyser_marche
from scanner.deuxiememain import rechercher_voitures as rechercher_2ememain


SCORE_ALERTE_MINIMUM = 80
BENEFICE_ALERTE_MINIMUM = 2500
MAX_ALERTES_PAR_RECHERCHE = 5
scan_en_cours = False


def formater_prix(prix):
    if isinstance(prix, int):
        return f"{prix} €"

    return str(prix)


def decouper_messages(blocs, limite=3900):
    messages = []
    message = ""

    for bloc in blocs:
        if len(bloc) > limite:
            if message:
                messages.append(message)
                message = ""

            for debut in range(0, len(bloc), limite):
                messages.append(bloc[debut:debut + limite])

            continue

        if message and len(message) + len(bloc) > limite:
            messages.append(message)
            message = bloc
        else:
            message += bloc

    if message:
        messages.append(message)

    return messages


def formater_alerte(voiture, analyse, kilometrage):
    return (
        "🚨 NOUVELLE BONNE AFFAIRE\n\n"

        f"🚗 {voiture['modele']}\n"
        f"🌐 {voiture.get('source', 'AutoScout24')}\n\n"

        f"💰 Prix : {formater_prix(voiture['prix'])}\n"
        f"📊 Valeur estimée : {formater_prix(analyse['prix_marche'])}\n"
        f"💵 Bénéfice potentiel : +{formater_prix(analyse['benefice'])}\n"
        f"⭐ Score : {analyse['score']}/100\n\n"

        f"📅 Année : {voiture.get('annee', 'Inconnue')}\n"
        f"🛣️ Kilométrage : {kilometrage}\n"
        f"📍 Ville : {voiture['ville']}\n\n"

        f"🔗 {voiture['lien']}"
    )


def est_bonne_affaire(analyse):
    return (
        analyse["score"] >= SCORE_ALERTE_MINIMUM
        and analyse["benefice"] >= BENEFICE_ALERTE_MINIMUM
    )


def extraire_kilometrage(voiture):
    kilometrage = voiture.get("kilometrage", "Inconnu")

    if isinstance(kilometrage, dict):
        kilometrage = kilometrage.get(
            "value",
            "Inconnu"
        )

    return kilometrage


def scanner_recherche(recherche):
    voitures = []
    erreurs = []

    try:
        voitures.extend(rechercher_voitures(recherche))
    except Exception as e:
        erreurs.append(f"AutoScout24 : {e}")

    try:
        voitures.extend(rechercher_2ememain(recherche))
    except Exception as e:
        erreurs.append(f"2ememain : {e}")

    return voitures, erreurs


def analyser_et_enregistrer(voitures):
    annonces_analysees = []
    alertes = []
    nouvelles_annonces = 0
    annonces_connues = 0

    for voiture in voitures:

        analyse = analyser_annonce(voiture)
        kilometrage = extraire_kilometrage(voiture)

        est_nouvelle = ajouter_annonce(
            voiture.get("source", "AutoScout24"),
            voiture["modele"],
            voiture["prix"],
            kilometrage,
            voiture.get("annee", "Inconnu"),
            voiture["lien"]
        )

        if est_nouvelle:
            nouvelles_annonces += 1
        else:
            annonces_connues += 1

        if est_nouvelle and est_bonne_affaire(analyse):
            alertes.append({
                "voiture": voiture,
                "analyse": analyse,
                "kilometrage": kilometrage,
                "texte": formater_alerte(voiture, analyse, kilometrage)
            })

        bloc = (

            f"🚗 {voiture['modele']}\n"
            f"🌐 Source : {voiture.get('source', 'AutoScout24')}\n\n"

            f"💰 Prix affiché : {formater_prix(voiture['prix'])}\n"

            f"📍 Ville : {voiture['ville']}\n"

            f"📅 Année : {voiture.get('annee', 'Inconnue')}\n"

            f"🛣️ Kilométrage : {kilometrage} km\n"

            f"⛽ Carburant : {voiture.get('carburant', 'Inconnu')}\n"

            f"⚙️ Boîte : {voiture.get('boite', 'Inconnue')}\n\n"

            f"📊 Valeur estimée : {formater_prix(analyse['prix_marche'])}\n"

            f"🎯 Offre de départ : {formater_prix(analyse['offre_depart'])}\n"

            f"🤝 Prix conseillé : {formater_prix(analyse['prix_conseille'])}\n"

            f"⛔ Maximum : {formater_prix(analyse['prix_max'])}\n\n"

            f"💵 Bénéfice estimé : +{formater_prix(analyse['benefice'])}\n"

            f"⭐ Score : {analyse['score']}/100\n"

            f"💡 {analyse['conseil']}\n\n"

            f"🔗 {voiture['lien']}\n"

            "━━━━━━━━━━━━━━━━━━━━\n\n"

        )

        annonces_analysees.append({
            "voiture": voiture,
            "analyse": analyse,
            "bloc": bloc
        })

    alertes = sorted(
        alertes,
        key=lambda item: (
            item["analyse"]["score"],
            item["analyse"]["benefice"]
        ),
        reverse=True
    )

    return {
        "annonces": annonces_analysees,
        "alertes": alertes,
        "nouvelles": nouvelles_annonces,
        "connues": annonces_connues
    }


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

            f"💰 Prix : {formater_prix(voiture['prix'])}\n"

            f"📍 Ville : {voiture['ville']}\n"

            f"📈 Revente : {formater_prix(voiture['revente'])}\n"

            f"💵 Profit : +{formater_prix(profit)}\n\n"

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

    voitures, erreurs = scanner_recherche(modele)

    if len(voitures) == 0:

        await update.message.reply_text(
            "❌ Aucune annonce trouvée."
        )
        return

    marche = analyser_marche(voitures)

    resultat = analyser_et_enregistrer(voitures)
    annonces_analysees = resultat["annonces"]
    alertes = resultat["alertes"]
    nouvelles_annonces = resultat["nouvelles"]
    annonces_connues = resultat["connues"]

    meilleures_annonces = sorted(
        annonces_analysees,
        key=lambda item: (
            item["analyse"]["score"],
            item["analyse"]["benefice"]
        ),
        reverse=True
    )[:10]

    texte_erreurs = ""

    if erreurs:
        texte_erreurs = (
            "\n⚠️ Erreurs :\n"
            + "\n".join(f"- {erreur}" for erreur in erreurs)
            + "\n"
        )

    resume = (
        "📊 ANALYSE DU MARCHÉ\n\n"

        f"🚗 Annonces trouvées : {len(voitures)}\n"

        f"🆕 Nouvelles annonces : {nouvelles_annonces}\n"

        f"📌 Déjà connues : {annonces_connues}\n"

        f"⭐ Annonces présentées : {len(meilleures_annonces)}\n"

        f"💰 Prix moyen : {formater_prix(marche['moyenne'])}\n"

        f"📈 Prix médian : {formater_prix(marche['mediane'])}\n"

        f"📉 Fourchette : {formater_prix(marche['minimum'])} → {formater_prix(marche['maximum'])}\n"

        f"{texte_erreurs}"

        "\n━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    await update.message.reply_text(resume)

    alertes = sorted(
        alertes,
        key=lambda item: (
            item["analyse"]["score"],
            item["analyse"]["benefice"]
        ),
        reverse=True
    )[:5]

    if alertes:
        for alerte in alertes:
            await update.message.reply_text(alerte["texte"])
    else:
        await update.message.reply_text(
            "Aucune nouvelle bonne affaire détectée."
        )

    for message in decouper_messages(
        [annonce["bloc"] for annonce in meilleures_annonces]
    ):
        await update.message.reply_text(message)


async def surveille(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) == 0:
        await update.message.reply_text(
            "❌ Utilisation : /surveille golf gti"
        )
        return

    recherche = " ".join(context.args)
    chat_id = update.effective_chat.id

    if ajouter_surveillance(recherche, chat_id):
        await update.message.reply_text(
            f"✅ Surveillance ajoutée : {recherche.lower()}"
        )
    else:
        await update.message.reply_text(
            f"ℹ️ Surveillance déjà active : {recherche.lower()}"
        )


async def surveillances(update: Update, context: ContextTypes.DEFAULT_TYPE):

    recherches = lister_surveillances(update.effective_chat.id)

    if not recherches:
        await update.message.reply_text(
            "Aucune recherche surveillée."
        )
        return

    texte = "🔎 Recherches surveillées\n\n"
    texte += "\n".join(f"- {recherche}" for recherche in recherches)

    await update.message.reply_text(texte)


async def stop_surveillance(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) == 0:
        await update.message.reply_text(
            "❌ Utilisation : /stop_surveillance golf gti"
        )
        return

    recherche = " ".join(context.args)
    chat_id = update.effective_chat.id

    if supprimer_surveillance(recherche, chat_id):
        await update.message.reply_text(
            f"🛑 Surveillance supprimée : {recherche.lower()}"
        )
    else:
        await update.message.reply_text(
            f"ℹ️ Aucune surveillance trouvée : {recherche.lower()}"
        )


async def scan_surveillances(context: ContextTypes.DEFAULT_TYPE):

    global scan_en_cours

    if scan_en_cours:
        print("Scan automatique déjà en cours, passage ignoré.")
        return

    scan_en_cours = True

    try:
        surveillances_actives = lister_surveillances()

        for recherche, chat_id in surveillances_actives:
            voitures, erreurs = scanner_recherche(recherche)

            if not voitures:
                if erreurs:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"⚠️ Surveillance {recherche}\n"
                            + "\n".join(erreurs)
                        )
                    )
                continue

            resultat = analyser_et_enregistrer(voitures)
            alertes = resultat["alertes"][:MAX_ALERTES_PAR_RECHERCHE]

            for alerte in alertes:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=alerte["texte"]
                )

    finally:
        scan_en_cours = False


def planifier_scan(app):
    job_queue = getattr(app, "job_queue", None)

    if job_queue is None:
        print(
            "JobQueue indisponible : installez python-telegram-bot[job-queue] "
            "pour activer la surveillance automatique."
        )
        return False

    job_queue.run_repeating(
        scan_surveillances,
        interval=3600,
        first=3600
    )
    return True


app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("aide", aide))
app.add_handler(CommandHandler("sites", sites))
app.add_handler(CommandHandler("recherche", recherche))
app.add_handler(CommandHandler("internet", internet))
app.add_handler(CommandHandler("surveille", surveille))
app.add_handler(CommandHandler("surveillances", surveillances))
app.add_handler(CommandHandler("stop_surveillance", stop_surveillance))

planifier_scan(app)

print("=" * 60)
print("🚗 YB AUTO BOT")
print("🤖 Assistant intelligent d'achat / revente automobile")
print("📊 Analyse du marché activée")
print("✅ Bot lancé avec succès !")
print("=" * 60)

app.run_polling()
