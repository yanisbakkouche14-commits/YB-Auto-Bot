from voitures import voitures
import atexit
import logging
import os
import tempfile
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.error import Conflict
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TOKEN

from scanner.autoscout import rechercher_voitures

from database.database import (
    ajouter_annonce,
    ajouter_surveillance,
    analyser_pression_vendeur,
    bilan_business,
    enregistrer_message_business,
    enregistrer_statistiques_scan,
    formater_filtres,
    lister_chat_ids_surveillance,
    lister_surveillances,
    message_business_deja_envoye,
    mettre_a_jour_analyse_annonce,
    supprimer_surveillance
)

from ai.analyse import analyser_annonce
from ai.marche import analyser_marche
from scanner.deuxiememain import rechercher_voitures as rechercher_2ememain


SCORE_ALERTE_MINIMUM = 80
BENEFICE_ALERTE_MINIMUM = 2500
MAX_ALERTES_PAR_RECHERCHE = 5
FUSEAU_HORAIRE = ZoneInfo("Europe/Brussels")
HEURE_MESSAGE_BUSINESS = time(8, 0, tzinfo=FUSEAU_HORAIRE)
CHEMIN_VERROU_INSTANCE = os.getenv(
    "YB_AUTO_BOT_LOCK",
    os.path.join(tempfile.gettempdir(), "yb_auto_bot.lock")
)
scan_en_cours = False
FILTRES_SURVEILLANCE = {
    "prix_min",
    "prix_max",
    "km_max",
    "annee_min",
    "carburant",
    "boite",
    "score_min",
    "benefice_min",
    "source",
}
FILTRES_NUMERIQUES = {
    "prix_min",
    "prix_max",
    "km_max",
    "annee_min",
    "score_min",
    "benefice_min",
}

PHRASES_BUSINESS = [
    "La marge se construit avant l'achat, pas après la vente.",
    "Chaque annonce analysée te rapproche d'une vraie opportunité.",
    "La discipline bat l'intuition quand les chiffres sont bons.",
    "Un bon deal commence par un prix d'achat maîtrisé.",
    "Le marché récompense ceux qui comparent avant d'agir.",
    "Acheter trop cher transforme une bonne voiture en mauvais business.",
    "La patience est une stratégie quand elle protège ta marge.",
    "Un refus intelligent vaut mieux qu'un achat émotionnel.",
    "Le profit se cache souvent dans les annonces que les autres ignorent.",
    "La régularité crée plus d'opportunités que les coups de chance.",
    "Une bonne affaire doit survivre aux chiffres, pas seulement à l'envie.",
    "Cherche la décote, protège la trésorerie, laisse parler la marge.",
    "Le meilleur achat est celui que tu peux revendre sereinement.",
    "Le volume d'analyse donne de la précision au jugement.",
    "Une annonce moyenne au bon prix peut battre une belle annonce trop chère.",
    "Le marché change vite, la méthode doit rester stable.",
    "Les meilleures opportunités aiment les décisions préparées.",
    "Un business solide commence par des critères clairs.",
    "La donnée transforme une intuition en avantage.",
    "Chaque scan est une négociation commencée en silence.",
    "La marge minimale n'est pas un détail, c'est une protection.",
    "Un prix bas n'est utile que si le risque est compris.",
    "La vitesse compte, mais la lucidité compte davantage.",
    "Les bons acheteurs savent attendre sans dormir.",
    "Une opportunité ratée coûte moins cher qu'une mauvaise décision.",
    "Les chiffres froids évitent les erreurs chaudes.",
    "Un deal propre laisse de la place pour l'imprévu.",
    "La meilleure annonce du jour est celle qui respecte tes règles.",
    "Le suivi quotidien transforme le marché en terrain connu.",
    "Le vrai levier, c'est d'acheter quand la marge est déjà visible.",
]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger("yb_auto_bot")


def processus_actif(pid):
    if not pid or pid <= 0:
        return False

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def liberer_verrou_instance(chemin_verrou=CHEMIN_VERROU_INSTANCE):
    try:
        with open(chemin_verrou, "r", encoding="utf-8") as fichier:
            pid_verrou = int(fichier.read().strip() or 0)
    except (FileNotFoundError, OSError, ValueError):
        return

    if pid_verrou != os.getpid():
        return

    try:
        os.remove(chemin_verrou)
        logger.info("Verrou mono-instance libéré : %s", chemin_verrou)
    except FileNotFoundError:
        pass
    except OSError as erreur:
        logger.warning(
            "Impossible de libérer le verrou mono-instance %s : %s",
            chemin_verrou,
            erreur
        )


def acquerir_verrou_instance(chemin_verrou=CHEMIN_VERROU_INSTANCE):
    while True:
        try:
            descripteur = os.open(
                chemin_verrou,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY
            )
        except FileExistsError:
            try:
                with open(chemin_verrou, "r", encoding="utf-8") as fichier:
                    pid_verrou = int(fichier.read().strip() or 0)
            except (OSError, ValueError):
                pid_verrou = 0

            if processus_actif(pid_verrou):
                raise RuntimeError(
                    "Une instance locale du bot semble déjà active "
                    f"(pid={pid_verrou}, verrou={chemin_verrou})."
                )

            logger.warning(
                "Verrou mono-instance obsolète supprimé : %s",
                chemin_verrou
            )
            try:
                os.remove(chemin_verrou)
            except FileNotFoundError:
                pass
            continue

        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            fichier.write(str(os.getpid()))

        atexit.register(liberer_verrou_instance, chemin_verrou)
        logger.info("Verrou mono-instance acquis : %s", chemin_verrou)
        return chemin_verrou


def formater_prix(prix):
    if isinstance(prix, int):
        return f"{prix} €"

    return str(prix)


def extraire_recherche_et_filtres(args):
    position_premier_filtre = None

    for index, argument in enumerate(args):
        if "=" in argument:
            position_premier_filtre = index
            break

    if position_premier_filtre is None:
        recherche_args = args
        filtre_args = []
    else:
        recherche_args = args[:position_premier_filtre]
        filtre_args = args[position_premier_filtre:]

    recherche = " ".join(recherche_args).strip()

    if not recherche:
        return None, None, "la recherche véhicule est obligatoire"

    filtres = {}

    for argument in filtre_args:
        if "=" not in argument:
            return None, None, f"filtre invalide : {argument}"

        cle, valeur = argument.split("=", 1)
        cle = cle.strip().lower()
        valeur = valeur.strip()

        if cle not in FILTRES_SURVEILLANCE:
            return None, None, f"filtre inconnu : {cle}"

        if not valeur:
            return None, None, f"valeur manquante pour {cle}"

        if cle in FILTRES_NUMERIQUES:
            try:
                valeur = int(valeur)
            except ValueError:
                return None, None, f"valeur numérique invalide pour {cle}"

            if valeur < 0:
                return None, None, f"valeur négative invalide pour {cle}"
        else:
            valeur = valeur.lower()

        filtres[cle] = valeur

    return recherche, filtres, None


def extraire_nombre(valeur):
    if isinstance(valeur, int):
        return valeur

    if isinstance(valeur, dict):
        return extraire_nombre(valeur.get("value"))

    if valeur is None:
        return None

    chiffres = "".join(caractere for caractere in str(valeur) if caractere.isdigit())

    if not chiffres:
        return None

    return int(chiffres)


def valeur_texte(voiture, cle, defaut=""):
    return str(voiture.get(cle, defaut) or defaut).strip().lower()


def date_locale_bruxelles():
    return datetime.now(FUSEAU_HORAIRE).date()


def phrase_business_du_jour(date_jour=None):
    date_jour = date_jour or date_locale_bruxelles()
    index = date_jour.toordinal() % len(PHRASES_BUSINESS)
    return PHRASES_BUSINESS[index]


def formater_benefice(benefice):
    if benefice is None:
        return "Inconnu"

    return f"+{formater_prix(benefice)}"


def formater_infos_vendeur_presse(infos):
    if not infos:
        return ""

    return (
        "\n\n📉 Historique prix\n"
        f"- Baisses : {infos['nombre_baisses']}\n"
        f"- Baisse totale : {formater_prix(infos['baisse_totale'])} "
        f"({infos['baisse_pourcentage']}%)\n"
        f"- Ancienneté : {infos['jours_depuis_detection']} jours\n"
        f"- Vendeur pressé : {infos['score']}/100 "
        f"({infos['verdict']})"
    )


def formater_alerte_prix(infos):
    annonce = infos["annonce"]

    return (
        "📉 ALERTE PRIX / VENDEUR\n\n"
        f"🚗 {annonce.get('modele') or annonce.get('titre')}\n"
        f"💰 Prix initial : {formater_prix(infos['prix_initial'])}\n"
        f"💰 Prix actuel : {formater_prix(infos['prix_actuel'])}\n"
        f"📉 Baisse totale : {formater_prix(infos['baisse_totale'])} "
        f"({infos['baisse_pourcentage']}%)\n"
        f"🔁 Nombre de baisses : {infos['nombre_baisses']}\n"
        f"⏳ Ancienneté : {infos['jours_depuis_detection']} jours\n"
        f"🎯 Score vendeur pressé : {infos['score']}/100\n"
        f"🧭 Verdict : {infos['verdict']}\n\n"
        f"💬 Conseil : {infos['conseil']}\n\n"
        f"🔗 {annonce.get('lien')}"
    )


def formater_historique(infos):
    if infos is None:
        return "❌ Aucune annonce trouvée pour cet identifiant ou ce lien."

    annonce = infos["annonce"]
    lignes_historique = []

    for changement in infos["historique"]:
        sens = "baisse" if changement["variation"] < 0 else "hausse"
        lignes_historique.append(
            f"- {changement['date_changement']} : "
            f"{formater_prix(changement['ancien_prix'])} → "
            f"{formater_prix(changement['nouveau_prix'])} "
            f"({sens} {formater_prix(abs(changement['variation']))})"
        )

    if not lignes_historique:
        lignes_historique.append("- Aucun changement de prix enregistré.")

    return (
        "📉 HISTORIQUE PRIX\n\n"
        f"🚗 {annonce.get('modele') or annonce.get('titre')}\n"
        f"🔗 {annonce.get('lien')}\n\n"
        f"💰 Prix initial : {formater_prix(infos['prix_initial'])}\n"
        f"💰 Prix actuel : {formater_prix(infos['prix_actuel'])}\n\n"
        "📋 Changements :\n"
        + "\n".join(lignes_historique)
        + "\n\n"
        f"📉 Baisse totale : {formater_prix(infos['baisse_totale'])} "
        f"({infos['baisse_pourcentage']}%)\n"
        f"🔁 Nombre de baisses : {infos['nombre_baisses']}\n"
        f"⏳ Depuis première détection : "
        f"{infos['jours_depuis_detection']} jours\n"
        f"🎯 Score vendeur pressé : {infos['score']}/100\n"
        f"🧭 Verdict : {infos['verdict']}\n\n"
        f"💬 Conseil : {infos['conseil']}"
    )


def generer_message_business(chat_id, date_jour=None):
    date_jour = date_jour or date_locale_bruxelles()
    date_hier = date_jour - timedelta(days=1)
    bilan = bilan_business(date_hier.isoformat(), chat_id)

    if bilan["annonces_analysees"] == 0:
        meilleure_opportunite = "Aucune donnée disponible hier"
    elif bilan["meilleur_modele"]:
        meilleure_opportunite = (
            f"{bilan['meilleur_modele']} "
            f"{formater_benefice(bilan['meilleur_benefice'])}"
        )
    else:
        meilleure_opportunite = "Aucune bonne affaire détectée"

    return (
        "☀️ Bonjour !\n\n"
        "💬 Citation du jour :\n"
        f"\"{phrase_business_du_jour(date_jour)}\"\n\n"
        "📈 Bilan d'hier :\n"
        f"- {bilan['annonces_analysees']} annonces analysées\n"
        f"- {bilan['nouvelles_annonces']} nouvelles annonces\n"
        f"- {bilan['bonnes_affaires']} bonnes affaires détectées\n"
        f"- Meilleure opportunité : {meilleure_opportunite}\n\n"
        "🎯 Objectif du jour :\n"
        "Trouver au moins une annonce avec une marge supérieure à 2 500 €."
    )


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


def est_bonne_affaire(analyse, filtres=None):
    filtres = filtres or {}
    score_min = filtres.get("score_min", SCORE_ALERTE_MINIMUM)
    benefice_min = filtres.get("benefice_min", BENEFICE_ALERTE_MINIMUM)

    return (
        analyse["score"] >= score_min
        and analyse["benefice"] >= benefice_min
    )


def extraire_kilometrage(voiture):
    kilometrage = voiture.get("kilometrage", "Inconnu")

    if isinstance(kilometrage, dict):
        kilometrage = kilometrage.get(
            "value",
            "Inconnu"
        )

    return kilometrage


def respecte_filtres(voiture, analyse, filtres=None):
    filtres = filtres or {}
    prix = extraire_nombre(voiture.get("prix"))
    kilometrage = extraire_nombre(extraire_kilometrage(voiture))
    annee = extraire_nombre(voiture.get("annee"))

    if "prix_min" in filtres and (prix is None or prix < filtres["prix_min"]):
        return False

    if "prix_max" in filtres and (prix is None or prix > filtres["prix_max"]):
        return False

    if "km_max" in filtres and (
        kilometrage is None or kilometrage > filtres["km_max"]
    ):
        return False

    if "annee_min" in filtres and (
        annee is None or annee < filtres["annee_min"]
    ):
        return False

    if "carburant" in filtres:
        carburant = valeur_texte(voiture, "carburant")
        if filtres["carburant"] not in carburant:
            return False

    if "boite" in filtres:
        boite = valeur_texte(voiture, "boite")
        if filtres["boite"] not in boite:
            return False

    if "source" in filtres:
        source = valeur_texte(voiture, "source")
        filtre_source = filtres["source"]
        if filtre_source not in source and source not in filtre_source:
            return False

    return est_bonne_affaire(analyse, filtres)


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


def analyser_et_enregistrer(voitures, filtres=None):
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

        mettre_a_jour_analyse_annonce(
            voiture["lien"],
            analyse["score"],
            analyse["benefice"]
        )

        infos_vendeur = analyser_pression_vendeur(voiture["lien"])

        if est_nouvelle and respecte_filtres(voiture, analyse, filtres):
            alertes.append({
                "voiture": voiture,
                "analyse": analyse,
                "kilometrage": kilometrage,
                "texte": (
                    formater_alerte(voiture, analyse, kilometrage)
                    + formater_infos_vendeur_presse(infos_vendeur)
                )
            })
        elif (
            not est_nouvelle
            and infos_vendeur
            and infos_vendeur["alerte_speciale"]
        ):
            alertes.append({
                "voiture": voiture,
                "analyse": analyse,
                "kilometrage": kilometrage,
                "texte": formater_alerte_prix(infos_vendeur)
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


async def surveille(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) == 0:
        await update.message.reply_text(
            "âŒ Utilisation : /surveille golf gti prix_max=22000"
        )
        return

    recherche, filtres, erreur = extraire_recherche_et_filtres(context.args)

    if erreur:
        await update.message.reply_text(f"âŒ Filtre invalide : {erreur}")
        return

    chat_id = update.effective_chat.id

    if ajouter_surveillance(recherche, chat_id, filtres):
        await update.message.reply_text(
            f"âœ… Surveillance ajoutÃ©e : {recherche.lower()}\n"
            f"Filtres : {formater_filtres(filtres)}"
        )
    else:
        await update.message.reply_text(
            f"â„¹ï¸ Surveillance dÃ©jÃ  active : {recherche.lower()}\n"
            f"Filtres : {formater_filtres(filtres)}"
        )


async def surveillances(update: Update, context: ContextTypes.DEFAULT_TYPE):

    recherches = lister_surveillances(update.effective_chat.id)

    if not recherches:
        await update.message.reply_text(
            "Aucune recherche surveillÃ©e."
        )
        return

    texte = "ðŸ”Ž Recherches surveillÃ©es\n\n"
    texte += "\n".join(
        f"- {recherche} ({formater_filtres(filtres)})"
        for recherche, filtres in recherches
    )

    await update.message.reply_text(texte)


async def stop_surveillance(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) == 0:
        await update.message.reply_text(
            "âŒ Utilisation : /stop_surveillance golf gti prix_max=22000"
        )
        return

    recherche, filtres, erreur = extraire_recherche_et_filtres(context.args)

    if erreur:
        await update.message.reply_text(f"âŒ Filtre invalide : {erreur}")
        return

    chat_id = update.effective_chat.id

    if supprimer_surveillance(recherche, chat_id, filtres):
        await update.message.reply_text(
            f"ðŸ›‘ Surveillance supprimÃ©e : {recherche.lower()}\n"
            f"Filtres : {formater_filtres(filtres)}"
        )
    else:
        await update.message.reply_text(
            f"â„¹ï¸ Aucune surveillance trouvÃ©e : {recherche.lower()}\n"
            f"Filtres : {formater_filtres(filtres)}"
        )


async def scan_surveillances(context: ContextTypes.DEFAULT_TYPE):

    global scan_en_cours

    if scan_en_cours:
        print("Scan automatique dÃ©jÃ  en cours, passage ignorÃ©.")
        return

    scan_en_cours = True

    try:
        surveillances_actives = lister_surveillances()

        for recherche, chat_id, filtres in surveillances_actives:
            voitures, erreurs = scanner_recherche(recherche)

            if not voitures:
                if erreurs:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"âš ï¸ Surveillance {recherche} "
                            f"({formater_filtres(filtres)})\n"
                            + "\n".join(erreurs)
                        )
                    )
                continue

            resultat = analyser_et_enregistrer(voitures, filtres)
            toutes_les_alertes = resultat["alertes"]
            meilleure_alerte = toutes_les_alertes[0] if toutes_les_alertes else None

            enregistrer_statistiques_scan(
                chat_id=chat_id,
                recherche=recherche,
                annonces_analysees=len(voitures),
                nouvelles_annonces=resultat["nouvelles"],
                bonnes_affaires=len(toutes_les_alertes),
                meilleur_modele=(
                    meilleure_alerte["voiture"]["modele"]
                    if meilleure_alerte else None
                ),
                meilleur_benefice=(
                    meilleure_alerte["analyse"]["benefice"]
                    if meilleure_alerte else None
                ),
                date_scan=datetime.now(FUSEAU_HORAIRE).isoformat(
                    timespec="seconds"
                )
            )

            alertes = toutes_les_alertes[:MAX_ALERTES_PAR_RECHERCHE]

            for alerte in alertes:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=alerte["texte"]
                )

    finally:
        scan_en_cours = False


async def business(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        generer_message_business(update.effective_chat.id)
    )


async def historique(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text(
            "❌ Utilisation : /historique <lien ou identifiant>"
        )
        return

    identifiant = " ".join(context.args).strip()
    await update.message.reply_text(
        formater_historique(analyser_pression_vendeur(identifiant))
    )


async def envoyer_messages_business(context: ContextTypes.DEFAULT_TYPE):
    date_envoi = date_locale_bruxelles()

    for chat_id in lister_chat_ids_surveillance():
        if message_business_deja_envoye(chat_id, date_envoi.isoformat()):
            continue

        texte = generer_message_business(chat_id, date_envoi)

        await context.bot.send_message(
            chat_id=chat_id,
            text=texte
        )

        enregistrer_message_business(chat_id, date_envoi.isoformat())


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
    job_queue.run_daily(
        envoyer_messages_business,
        time=HEURE_MESSAGE_BUSINESS
    )
    return True


async def gerer_erreur_telegram(update, context):
    erreur = context.error

    if isinstance(erreur, Conflict):
        logger.error(
            "Conflit Telegram getUpdates détecté. "
            "Une autre instance utilise probablement le même token.",
            exc_info=(type(erreur), erreur, erreur.__traceback__)
        )
        return

    logger.error(
        "Erreur Telegram non gérée pendant le traitement d'une update.",
        exc_info=(type(erreur), erreur, erreur.__traceback__)
    )


def main():
    acquerir_verrou_instance()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("aide", aide))
    app.add_handler(CommandHandler("sites", sites))
    app.add_handler(CommandHandler("recherche", recherche))
    app.add_handler(CommandHandler("internet", internet))
    app.add_handler(CommandHandler("surveille", surveille))
    app.add_handler(CommandHandler("surveillances", surveillances))
    app.add_handler(CommandHandler("stop_surveillance", stop_surveillance))
    app.add_handler(CommandHandler("business", business))
    app.add_handler(CommandHandler("historique", historique))
    app.add_error_handler(gerer_erreur_telegram)

    planifier_scan(app)

    print("=" * 60)
    print("🚗 YB AUTO BOT")
    print("🤖 Assistant intelligent d'achat / revente automobile")
    print("📊 Analyse du marché activée")
    print("✅ Bot lancé avec succès !")
    print("=" * 60)

    try:
        app.run_polling()
    except Conflict:
        logger.error(
            "telegram.error.Conflict pendant run_polling(). "
            "Le bot ne masque pas cette erreur : vérifiez qu'un seul service, "
            "un seul replica, aucun ancien projet et aucun bot local n'utilisent "
            "le même token Telegram.",
            exc_info=True
        )
        raise
    finally:
        liberer_verrou_instance()


if __name__ == "__main__":
    main()
