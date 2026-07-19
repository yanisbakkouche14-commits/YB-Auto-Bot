from voitures import voitures
import atexit
import importlib.util
import logging
import os
import tempfile
import time as time_module
from pathlib import Path
from datetime import datetime, time, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from config import TOKEN

from scanner.autoscout import (
    analyser_lien as analyser_lien_autoscout,
    rechercher_voitures
)

from database.database import (
    activer_scanner_global,
    ajouter_favori,
    ajouter_annonce,
    ajouter_surveillance,
    alerte_baisse_favori_deja_envoyee,
    analyser_pression_vendeur,
    avancer_lot_scanner_global,
    bilan_business,
    dashboard_resume,
    desactiver_scanner_global,
    enregistrer_alerte_baisse_favori,
    enregistrer_message_business,
    enregistrer_opportunite,
    enregistrer_opportunite_globale_envoyee,
    enregistrer_statistiques_scan,
    formater_filtres,
    lister_favoris,
    lister_favoris_actifs,
    lister_chat_ids_surveillance,
    lister_scanners_globaux_actifs,
    lister_surveillances,
    message_business_deja_envoye,
    mettre_a_jour_analyse_annonce,
    mettre_a_jour_favori,
    nombre_alertes_baisse_favori,
    obtenir_favori,
    obtenir_favori_par_id,
    opportunite_globale_deja_envoyee,
    signature_opportunite_globale,
    signature_alerte_baisse_favori,
    statut_scanner_global,
    stats_modele,
    stats_sources,
    supprimer_favori,
    supprimer_favori_par_id,
    supprimer_surveillance,
    top_opportunites
)

from ai.analyse import analyser_annonce
from ai.marche import analyser_marche
from business.business_score import (
    calculer_business_score,
    formater_business_score,
    donnees_business,
    identifiant_modele,
)
from business.negociation import calculer_negociation
from business.mecanique import analyser_mecanique
from business.dashboard import (
    formater_dashboard,
    formater_sources,
    formater_stats_modele,
    formater_top,
)
from scanner.deuxiememain import (
    analyser_lien as analyser_lien_2ememain,
    rechercher_voitures as rechercher_2ememain
)
from scanner.aggregateur import rechercher_partout
from scanner.marketplace import (
    etat_marketplace,
    marquer_notification_panne_envoyee,
    marquer_notification_retour_envoyee,
    panne_a_notifier,
    rechercher_voitures as rechercher_marketplace,
    retour_a_notifier,
    tester_sante,
)
from user_settings import (
    basculer_alertes,
    definir_alertes,
    lister_alertes as lister_alertes_utilisateur,
    modifier_annee as modifier_annee_utilisateur,
    modifier_benefice_min,
    modifier_budget as modifier_budget_utilisateur,
    modifier_budget_min,
    modifier_frequence_scan,
    modifier_km as modifier_km_utilisateur,
    modifier_pays,
    modifier_score_min,
    obtenir_parametres,
    supprimer_alerte as supprimer_alerte_utilisateur,
    supprimer_toutes_alertes,
)


SCORE_ALERTE_MINIMUM = 80
BENEFICE_ALERTE_MINIMUM = 2500
MAX_ALERTES_PAR_RECHERCHE = 5
FUSEAU_HORAIRE = ZoneInfo("Europe/Brussels")
HEURE_MESSAGE_BUSINESS = time(8, 0, tzinfo=FUSEAU_HORAIRE)
CHEMIN_VERROU_INSTANCE = os.getenv(
    "YB_AUTO_BOT_LOCK",
    os.path.join(tempfile.gettempdir(), "yb_auto_bot.lock")
)
CHEMIN_CONFIG_VEHICULES_BUSINESS = (
    Path(__file__).resolve().parent / "config" / "vehicules_business.py"
)
scan_en_cours = False
scan_global_en_cours = False
verification_favoris_en_cours = False
INTERVALLE_VERIFICATION_FAVORIS_SECONDES = 3 * 60 * 60
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


def charger_config_vehicules_business():
    spec = importlib.util.spec_from_file_location(
        "vehicules_business_config",
        CHEMIN_CONFIG_VEHICULES_BUSINESS
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONFIG_VEHICULES_BUSINESS = charger_config_vehicules_business()
VEHICULES_BUSINESS = CONFIG_VEHICULES_BUSINESS.VEHICULES_BUSINESS
LOTS_VEHICULES_BUSINESS = list(VEHICULES_BUSINESS.items())
PRIX_MAX_GLOBAL = CONFIG_VEHICULES_BUSINESS.PRIX_MAX_GLOBAL
MAX_OPPORTUNITES_SCAN_GLOBAL = (
    CONFIG_VEHICULES_BUSINESS.MAX_OPPORTUNITES_SCAN_GLOBAL
)
INTERVALLE_SCAN_GLOBAL_SECONDES = (
    CONFIG_VEHICULES_BUSINESS.INTERVALLE_SCAN_GLOBAL_SECONDES
)

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


MENU_PRINCIPAL_ACTIONS = [
    [("🏠 Accueil", "menu:home")],
    [("🔗 Analyser une annonce", "analysis:ask_link")],
    [("🔥 Scanner Business", "menu:scanner"), ("🌍 Scanner Europe", "menu:europe")],
    [("🛒 Facebook Marketplace", "menu:marketplace"), ("⭐ Opportunités", "menu:opportunities")],
    [("❤️ Favoris", "menu:favorites"), ("📊 Tableau de bord", "menu:dashboard")],
    [("⚙️ Paramètres", "menu:settings"), ("ℹ️ Aide", "menu:help")],
]

MENU_PRINCIPAL_BOUTONS = [
    [libelle for libelle, _callback_data in ligne]
    for ligne in MENU_PRINCIPAL_ACTIONS
]


def clavier_principal():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(libelle, callback_data=callback_data)
            for libelle, callback_data in ligne
        ]
        for ligne in MENU_PRINCIPAL_ACTIONS
    ])


def clavier_principal_reponse():
    return ReplyKeyboardMarkup(
        MENU_PRINCIPAL_BOUTONS,
        resize_keyboard=True
    )


def clavier_retour_accueil():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")]
    ])


def clavier_scanner_business():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Activer", callback_data="scanner:enable"),
            InlineKeyboardButton("⛔ Désactiver", callback_data="scanner:disable"),
        ],
        [
            InlineKeyboardButton("📊 Statut", callback_data="scanner:status"),
            InlineKeyboardButton("🚀 Lancer maintenant", callback_data="scanner:run"),
        ],
        [InlineKeyboardButton("⚙️ Paramètres", callback_data="scanner:settings")],
        [InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")],
    ])


def clavier_opportunites():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 Top 10 aujourd'hui", callback_data="opp:top_today")],
        [InlineKeyboardButton("🔥 Top de la semaine", callback_data="opp:top_week")],
        [InlineKeyboardButton("🚨 Dernières alertes", callback_data="opp:last_alerts")],
        [InlineKeyboardButton("⏳ Vendeurs pressés", callback_data="opp:urgent_sellers")],
        [InlineKeyboardButton("📉 Baisses de prix", callback_data="opp:price_drops")],
        [InlineKeyboardButton("📈 Top ROI", callback_data="opp:top_roi")],
        [InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")],
    ])


def clavier_favoris():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❤️ Voir les favoris", callback_data="fav:list")],
        [InlineKeyboardButton("🗑️ Retirer un favori", callback_data="fav:delete")],
        [InlineKeyboardButton("🧹 Supprimer tous les favoris", callback_data="fav:delete_all")],
        [InlineKeyboardButton("📉 Vérifier les prix maintenant", callback_data="fav:check")],
        [InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")],
    ])


def clavier_analyse_annonce(est_favori=False):
    if est_favori:
        premiere_ligne = [
            InlineKeyboardButton("🗑 Retirer des favoris", callback_data="fav:remove_last")
        ]
    else:
        premiere_ligne = [
            InlineKeyboardButton("❤️ Ajouter aux favoris", callback_data="fav:add_last"),
            InlineKeyboardButton("📉 Suivre le prix", callback_data="fav:add_last"),
        ]

    return InlineKeyboardMarkup([
        premiere_ligne,
        [InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")],
    ])


def clavier_tableau_de_bord():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Vue générale", callback_data="dash:overview")],
        [InlineKeyboardButton("🔥 Top du jour", callback_data="dash:top_today")],
        [InlineKeyboardButton("📅 Top de la semaine", callback_data="dash:top_week")],
        [InlineKeyboardButton("🚗 Stats par modèle", callback_data="dash:stats_model_prompt")],
        [InlineKeyboardButton("📡 État des sources", callback_data="dash:sources")],
        [InlineKeyboardButton("❤️ Favoris", callback_data="menu:favorites")],
        [InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")],
    ])


def clavier_parametres():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Budget min", callback_data="settings:set:budget_min"),
            InlineKeyboardButton("💰 Budget max", callback_data="settings:set:budget_max"),
        ],
        [
            InlineKeyboardButton("🛣️ Km max", callback_data="settings:set:km_max"),
            InlineKeyboardButton("📅 Année min", callback_data="settings:set:annee_min"),
        ],
        [
            InlineKeyboardButton("⭐ Score min", callback_data="settings:set:score_min"),
            InlineKeyboardButton("💵 Bénéfice min", callback_data="settings:set:benefice_min"),
        ],
        [
            InlineKeyboardButton("🌍 Pays", callback_data="settings:set:pays"),
            InlineKeyboardButton("⏱️ Fréquence", callback_data="settings:set:frequence"),
        ],
        [InlineKeyboardButton("🔔 Activer / désactiver alertes", callback_data="settings:toggle_alertes")],
        [InlineKeyboardButton("🔎 Surveillances", callback_data="settings:surveillances")],
        [InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")],
    ])


def clavier_scanner_europe():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Rechercher un modèle", callback_data="europe:search")],
        [
            InlineKeyboardButton("🇧🇪 Belgique", callback_data="europe:country:Belgique"),
            InlineKeyboardButton("🇩🇪 Allemagne", callback_data="europe:country:Allemagne"),
            InlineKeyboardButton("🇫🇷 France", callback_data="europe:country:France"),
        ],
        [
            InlineKeyboardButton("🇳🇱 Pays-Bas", callback_data="europe:country:Pays-Bas"),
            InlineKeyboardButton("🇱🇺 Luxembourg", callback_data="europe:country:Luxembourg"),
        ],
        [InlineKeyboardButton("📡 État des plateformes", callback_data="europe:sources")],
        [InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")],
    ])


def clavier_marketplace():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Rechercher un modèle", callback_data="marketplace:search")],
        [InlineKeyboardButton("📡 Statut Marketplace", callback_data="marketplace:status")],
        [InlineKeyboardButton("🔄 Retester la santé", callback_data="marketplace:retry")],
        [InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")],
    ])


def clavier_surveillance_liste(chat_id):
    lignes = []

    for index, surveillance in enumerate(lister_surveillances(chat_id)[:20], start=1):
        recherche, filtres = surveillance
        libelle = f"🗑 {index}. {recherche}"
        lignes.append([
            InlineKeyboardButton(
                libelle[:60],
                callback_data=f"surv:delete:{index - 1}"
            )
        ])

    if lignes:
        lignes.append([InlineKeyboardButton("🧹 Supprimer toutes les surveillances", callback_data="surv:delete_all")])

    lignes.append([
        InlineKeyboardButton("🔕 Alertes OFF", callback_data="surv:alerts_off"),
        InlineKeyboardButton("🔔 Alertes ON", callback_data="surv:alerts_on"),
    ])
    lignes.append([InlineKeyboardButton("⚙️ Paramètres", callback_data="menu:settings")])
    lignes.append([InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")])
    return InlineKeyboardMarkup(lignes)


def clavier_aide():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Explication des scores", callback_data="help:scores")],
        [InlineKeyboardButton("🔥 Business Score", callback_data="help:business_score")],
        [InlineKeyboardButton("❓ FAQ", callback_data="help:faq")],
        [InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")],
    ])


def texte_accueil():
    return (
        "🏠 Accueil\n\n"
        "Bienvenue sur YB Auto Bot.\n"
        "Utilise les boutons pour scanner le marché, suivre les opportunités "
        "et piloter tes alertes."
    )


def texte_scanner_business():
    return (
        "🔥 Scanner Business\n\n"
        "Le scanner global analyse automatiquement un lot de véhicules "
        "rentables toutes les 2 heures."
    )


def texte_scanner_europe():
    return (
        "🌍 Scanner Europe\n\n"
        "Recherche une annonce sur les plateformes Belgique + Europe, "
        "sans modifier le scanner /internet classique.\n\n"
        "Choisis un pays de préférence ou lance une recherche."
    )


def texte_marketplace():
    return (
        "🛒 Facebook Marketplace\n\n"
        "Marketplace fonctionne via le service local séparé. Si ton PC local "
        "ou la session Facebook ne sont pas disponibles, les autres plateformes "
        "continuent de fonctionner."
    )


def texte_opportunites():
    return (
        "⭐ Opportunités\n\n"
        "Retrouve ici les meilleures annonces, les alertes récentes, "
        "les vendeurs pressés et les baisses de prix."
    )


def texte_favoris():
    return (
        "❤️ Favoris\n\n"
        "Sauvegarde les annonces intéressantes, suis leurs prix et vérifie "
        "les baisses directement depuis ce menu."
    )


def texte_parametres():
    return "⚙️ Paramètres\n\nChoisis le réglage à modifier."


def formater_etat_marketplace():
    etat = etat_marketplace()
    erreur = etat.get("derniere_erreur") or "Aucune erreur récente."
    erreur_min = erreur.lower()

    if "session facebook expir" in erreur_min or "authentification" in erreur_min:
        statut = "Session Facebook expirée"
    elif "service local" in erreur_min or "indisponible" in erreur_min:
        statut = "Service local hors ligne"
    elif etat.get("desactive_temporairement"):
        statut = "Désactivé temporairement"
    else:
        statut = "Actif"

    return "\n".join([
        "🛒 ÉTAT FACEBOOK MARKETPLACE",
        "",
        f"Statut : {statut}",
        f"Dernière réussite : {etat.get('derniere_reussite') or 'Inconnue'}",
        f"Dernière erreur : {erreur}",
        f"Échecs consécutifs : {etat.get('echecs_consecutifs', 0)}",
    ])


def texte_aide():
    return (
        "ℹ️ Aide\n\n"
        "Choisis une rubrique pour comprendre les scores, le Business Score "
        "ou les questions fréquentes."
    )


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
    if prix in (None, "", "Inconnu"):
        return "Inconnu"

    if isinstance(prix, int):
        return f"{prix} €"

    return str(prix)


def reconnaitre_plateforme_lien(lien):
    try:
        domaine = urlparse(lien).netloc.lower()
    except ValueError:
        return None

    if "autoscout24" in domaine:
        return "autoscout24"

    if "2ememain" in domaine or "2dehands" in domaine:
        return "2ememain"

    return None


def lien_valide(lien):
    try:
        resultat = urlparse(lien)
    except ValueError:
        return False

    return resultat.scheme in {"http", "https"} and bool(resultat.netloc)


def analyser_lien_plateforme(lien):
    if not lien_valide(lien):
        raise ValueError("Lien invalide.")

    plateforme = reconnaitre_plateforme_lien(lien)

    if plateforme == "autoscout24":
        return analyser_lien_autoscout(lien)

    if plateforme == "2ememain":
        return analyser_lien_2ememain(lien)

    raise ValueError("Plateforme inconnue. Utilise un lien AutoScout24 ou 2ememain.")


def fiche_modele_business(voiture):
    donnees = donnees_business()
    modele_id = identifiant_modele(voiture, donnees)
    fiche = donnees.get("modeles", {}).get("modeles", {}).get(modele_id)
    return modele_id, fiche


def valeur_sourcee(champ, defaut="Inconnu"):
    if isinstance(champ, dict):
        return champ.get("valeur", defaut)

    if champ in (None, "", [], {}):
        return defaut

    return champ


def formater_lez(fiche):
    if not fiche:
        return "Inconnu"

    lez = fiche.get("lez", {})
    norme = valeur_sourcee(lez.get("norme_euro_minimale_conseillee"))
    risque = valeur_sourcee(lez.get("risque_lez_belgique"))
    impact = valeur_sourcee(lez.get("impact_revente"))

    return (
        f"Norme conseillée : {norme}\n"
        f"Risque Belgique : {risque}\n"
        f"Impact revente : {impact}"
    )


def formater_problemes_connus(fiche):
    if not fiche:
        return "Inconnu"

    pannes = fiche.get("mecanique", {}).get("pannes_frequentes", [])

    if not pannes:
        return "Inconnu"

    lignes = []

    for panne in pannes:
        lignes.append(str(valeur_sourcee(panne)))

    return "\n".join(f"- {ligne}" for ligne in lignes if ligne) or "Inconnu"


def formater_donnees_manquantes(voiture):
    champs = []

    for cle, libelle in (
        ("annee", "année"),
        ("kilometrage", "kilométrage"),
        ("prix", "prix"),
        ("carburant", "carburant"),
        ("boite", "boîte"),
    ):
        if voiture.get(cle) in (None, "", "Inconnu", "Inconnue"):
            champs.append(libelle)

    if not champs:
        return "Aucune donnée critique manquante."

    return "Données manquantes : " + ", ".join(champs) + "."


def formater_negociation(negociation):
    arguments = "\n".join(
        f"- {argument}"
        for argument in negociation.get("arguments", [])[:5]
    )

    if not arguments:
        arguments = "- Aucun argument spécifique détecté"

    return (
        f"🤝 Score négociation : {negociation['score_negociation']}/100\n"
        f"📈 Probabilité d'acceptation : {negociation['probabilite_acceptation']}%\n"
        f"🎯 Offre de départ : {formater_prix(negociation['offre_depart'])}\n"
        f"🤝 Prix conseillé : {formater_prix(negociation['prix_conseille'])}\n"
        f"⛔ Prix maximum : {formater_prix(negociation['prix_maximum'])}\n"
        f"💬 Verdict : {negociation['verdict']}\n"
        f"📌 Arguments :\n{arguments}"
    )


def formater_mecanique(mecanique):
    pannes = mecanique.get("pannes_connues") or []
    pannes_texte = "\n".join(f"- {panne}" for panne in pannes) or "- Inconnu"
    score_fiabilite = mecanique.get("score_fiabilite")
    score_mecanique = mecanique.get("score_mecanique")
    cout_moyen = mecanique.get("cout_reparation_moyen")
    marge_nette = mecanique.get("marge_nette_estimee")
    risque = mecanique.get("risque") or "inconnu"
    commentaire = mecanique.get("commentaire") or "Donnees mecaniques insuffisantes."

    return (
        "🔧 MÉCANIQUE\n\n"
        f"Fiabilité : {score_fiabilite if score_fiabilite is not None else 'Inconnu'}/10\n"
        f"Score mécanique : {score_mecanique}/10\n\n"
        "Pannes connues :\n"
        f"{pannes_texte}\n\n"
        f"Coût moyen : {formater_prix(cout_moyen)}\n"
        f"Marge nette estimée : {formater_prix(marge_nette)}\n\n"
        f"Verdict : Risque {risque}.\n"
        f"Commentaire : {commentaire}"
    )


def formater_analyse_lien(
    voiture,
    analyse,
    business_score,
    infos_vendeur,
    fiche,
    negociation,
    mecanique,
):
    infos_vendeur = infos_vendeur or {}
    score_vendeur = infos_vendeur.get("score", "Inconnu")
    verdict_vendeur = infos_vendeur.get("verdict", "aucun historique connu")
    baisse_totale = infos_vendeur.get("baisse_totale", 0)
    risques = analyse.get("risques") or []

    if isinstance(risques, str):
        risques = [risques] if risques else []

    niveau_risque = "Faible" if not risques else ", ".join(map(str, risques))

    return (
        "🔎 ANALYSE DE L'ANNONCE\n\n"
        f"🚗 {voiture.get('titre') or voiture.get('modele')}\n"
        f"🌐 Source : {voiture.get('source', 'Inconnu')}\n\n"
        f"💰 Prix affiché : {formater_prix(voiture.get('prix'))}\n"
        f"📊 Prix marché estimé : {formater_prix(analyse['prix_marche'])}\n"
        f"💵 Bénéfice brut estimé : +{formater_prix(analyse['benefice'])}\n"
        f"🎯 Prix de négociation conseillé : {formater_prix(negociation['prix_conseille'])}\n"
        f"⛔ Prix maximum à payer : {formater_prix(negociation['prix_maximum'])}\n\n"
        f"⭐ Score IA : {analyse['score']}/100\n"
        f"🔥 Business Score : {business_score['score']}/100\n"
        f"{business_score['etoiles']} {business_score['verdict']}\n"
        f"⚠️ Niveau de risque : {niveau_risque}\n\n"
        f"{formater_negociation(negociation)}\n\n"
        f"{formater_mecanique(mecanique)}\n\n"
        f"📅 Année : {voiture.get('annee', 'Inconnu')}\n"
        f"🛣️ Kilométrage : {extraire_kilometrage(voiture)}\n"
        f"⛽ Carburant : {voiture.get('carburant', 'Inconnu')}\n"
        f"⚙️ Boîte : {voiture.get('boite', 'Inconnue')}\n"
        f"📍 Localisation : {voiture.get('localisation') or voiture.get('ville', 'Inconnu')}\n\n"
        f"⏳ Vendeur pressé : {score_vendeur}/100 - {verdict_vendeur}\n"
        f"📉 Baisse totale connue : {formater_prix(baisse_totale)}\n\n"
        "🌍 Compatibilité LEZ\n"
        f"{formater_lez(fiche)}\n\n"
        "🧰 Problèmes connus\n"
        f"{formater_problemes_connus(fiche)}\n\n"
        f"📝 {formater_donnees_manquantes(voiture)}\n\n"
        f"🔗 {voiture.get('lien')}"
    )


def analyser_annonce_par_lien_detail(lien):
    voiture = analyser_lien_plateforme(lien)

    if voiture.get("prix") in (None, "", "Inconnu"):
        analyse = analyser_annonce(voiture)
    else:
        analyse = analyser_annonce(voiture)

    infos_vendeur = analyser_pression_vendeur(voiture["lien"])
    business_score = calculer_business_score(
        voiture,
        analyse,
        infos_vendeur,
        PRIX_MAX_GLOBAL
    )
    modele_id, fiche = fiche_modele_business(voiture)
    voiture["modele_id"] = modele_id
    negociation = calculer_negociation(
        voiture,
        analyse,
        infos_vendeur,
        infos_vendeur.get("score") if infos_vendeur else None
    )
    mecanique = analyser_mecanique(
        voiture.get("titre") or voiture.get("modele"),
        generation=voiture.get("generation"),
        moteur=voiture.get("moteur") or voiture.get("motorisation"),
        boite=voiture.get("boite"),
        annee=voiture.get("annee"),
        benefice_estime=analyse.get("benefice"),
    )

    texte = formater_analyse_lien(
        voiture,
        analyse,
        business_score,
        infos_vendeur,
        fiche,
        negociation,
        mecanique,
    )

    return {
        "texte": texte,
        "voiture": voiture,
        "analyse": analyse,
        "business_score": business_score,
        "infos_vendeur": infos_vendeur,
        "fiche": fiche,
        "negociation": negociation,
        "mecanique": mecanique,
    }


def analyser_annonce_par_lien(lien):
    return analyser_annonce_par_lien_detail(lien)["texte"]


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


def scanner_recherche_global(recherche):
    voitures = []
    erreurs = []

    plateformes = (
        ("AutoScout24", rechercher_voitures),
        ("2ememain", rechercher_2ememain),
    )

    for nom_plateforme, fonction_recherche in plateformes:
        debut = time_module.monotonic()

        try:
            voitures.extend(fonction_recherche(recherche))
        except Exception as erreur:
            erreurs.append(f"{nom_plateforme} / {recherche} : {erreur}")
            logger.warning(
                "Erreur scan global %s pour %s : %s",
                nom_plateforme,
                recherche,
                erreur
            )
        finally:
            duree = time_module.monotonic() - debut
            logger.info(
                "Scan global %s / %s terminé en %.2fs",
                nom_plateforme,
                recherche,
                duree
            )

    return voitures, erreurs


def dedupliquer_annonces_par_lien(voitures):
    annonces = {}

    for voiture in voitures:
        lien = voiture.get("lien")

        if not lien or lien in annonces:
            continue

        annonces[lien] = voiture

    return list(annonces.values())


def score_business_global(analyse, infos_vendeur, prix, prix_max):
    score_ia = min(analyse["score"], 100) * 0.40
    score_benefice = min(analyse["benefice"] / 5000, 1) * 100 * 0.30
    score_vendeur = (infos_vendeur["score"] if infos_vendeur else 0) * 0.15
    baisse_totale = infos_vendeur["baisse_totale"] if infos_vendeur else 0
    score_baisse = min(baisse_totale / 3000, 1) * 100 * 0.10

    if prix <= prix_max * 0.65:
        score_budget = 100 * 0.05
    elif prix <= prix_max:
        score_budget = 50 * 0.05
    else:
        score_budget = 0

    return int(round(
        min(
            score_ia
            + score_benefice
            + score_vendeur
            + score_baisse
            + score_budget,
            100
        )
    ))


def est_baisse_importante(infos_vendeur):
    if not infos_vendeur:
        return False

    return (
        infos_vendeur["baisse_totale"] >= 1000
        or infos_vendeur["nombre_baisses"] >= 2
    )


def analyser_scan_global(voitures, prix_max):
    opportunites = []

    for voiture in dedupliquer_annonces_par_lien(voitures):
        prix = extraire_nombre(voiture.get("prix"))

        if prix is None or prix > prix_max:
            continue

        analyse = analyser_annonce(voiture)
        est_nouvelle = ajouter_annonce(
            voiture.get("source", "AutoScout24"),
            voiture["modele"],
            prix,
            extraire_kilometrage(voiture),
            voiture.get("annee", "Inconnu"),
            voiture["lien"]
        )
        mettre_a_jour_analyse_annonce(
            voiture["lien"],
            analyse["score"],
            analyse["benefice"]
        )
        infos_vendeur = analyser_pression_vendeur(voiture["lien"])

        if analyse["score"] < 80 or analyse["benefice"] < 2000:
            continue

        if not est_nouvelle and not est_baisse_importante(infos_vendeur):
            continue

        voiture_score = dict(voiture)
        voiture_score["prix"] = prix
        business_score = calculer_business_score(
            voiture_score,
            analyse,
            infos_vendeur,
            prix_max
        )
        negociation = calculer_negociation(
            voiture_score,
            analyse,
            infos_vendeur,
            infos_vendeur.get("score") if infos_vendeur else None
        )

        opportunites.append({
            "voiture": voiture,
            "analyse": analyse,
            "infos_vendeur": infos_vendeur,
            "prix": prix,
            "score_business": business_score["score"],
            "business_score": business_score,
            "negociation": negociation,
            "est_nouvelle": est_nouvelle,
        })

    return sorted(
        opportunites,
        key=lambda item: (
            item["score_business"],
            item["analyse"]["score"],
            item["analyse"]["benefice"],
            item["infos_vendeur"]["score"] if item["infos_vendeur"] else 0,
            item["infos_vendeur"]["baisse_totale"] if item["infos_vendeur"] else 0,
            -item["prix"],
            item["infos_vendeur"]["jours_depuis_detection"]
            if item["infos_vendeur"] else 0,
        ),
        reverse=True
    )


def enregistrer_opportunite_depuis_resultat(chat_id, voiture, analyse, infos_vendeur, business_score, negociation):
    if chat_id is None:
        return False

    baisse = infos_vendeur.get("baisse_totale", 0) if infos_vendeur else 0
    score_vendeur = infos_vendeur.get("score") if infos_vendeur else None

    return enregistrer_opportunite(
        chat_id=chat_id,
        lien=voiture.get("lien"),
        modele=voiture.get("titre") or voiture.get("modele"),
        source=voiture.get("source"),
        prix=voiture.get("prix"),
        benefice=analyse.get("benefice"),
        score_business=business_score.get("score"),
        score_negociation=negociation.get("score_negociation"),
        score_vendeur_presse=score_vendeur,
        baisse_prix=baisse,
    )


def opportunites_globales_non_envoyees(chat_id, opportunites):
    nouvelles = []

    for opportunite in opportunites:
        infos_vendeur = opportunite["infos_vendeur"]
        baisse_totale = infos_vendeur["baisse_totale"] if infos_vendeur else 0
        signature = signature_opportunite_globale(
            opportunite["voiture"]["lien"],
            opportunite["prix"],
            opportunite["score_business"],
            baisse_totale
        )

        if opportunite_globale_deja_envoyee(
            chat_id,
            opportunite["voiture"]["lien"],
            signature
        ):
            continue

        opportunite["signature"] = signature
        nouvelles.append(opportunite)

    return nouvelles


def formater_resume_scanner_global(nom_lot, opportunites, erreurs):
    blocs = [
        "🔥 TOP OPPORTUNITÉS DU MARCHÉ\n\n"
        f"Lot scanné : {nom_lot.replace('_', ' ')}\n"
        f"Opportunités retenues : {len(opportunites)}\n"
    ]

    if erreurs:
        blocs.append(
            "\n⚠️ Erreurs partielles :\n"
            + "\n".join(f"- {erreur}" for erreur in erreurs[:5])
            + "\n"
        )

    medailles = ["🥇", "🥈", "🥉"]

    for index, opportunite in enumerate(opportunites, start=1):
        voiture = opportunite["voiture"]
        analyse = opportunite["analyse"]
        infos_vendeur = opportunite["infos_vendeur"] or {}
        business_score = opportunite.get("business_score")
        medaille = medailles[index - 1] if index <= 3 else f"{index}."
        baisse = infos_vendeur.get("baisse_totale", 0)
        score_vendeur = infos_vendeur.get("score", 0)
        verdict_score = ""

        if business_score:
            verdict_score = (
                f"{business_score['etoiles']} {business_score['verdict']}\n"
            )

        blocs.append(
            "\n"
            f"{medaille} {voiture['modele']}\n"
            f"💰 Prix : {formater_prix(opportunite['prix'])}\n"
            f"💵 Bénéfice estimé : +{formater_prix(analyse['benefice'])}\n"
            f"⭐ Score business : {opportunite['score_business']}/100\n"
            f"{verdict_score}"
            f"📉 Baisse : {formater_prix(baisse)}\n"
            f"⏳ Vendeur pressé : {score_vendeur}/100\n"
            f"🔗 {voiture['lien']}\n"
        )

        if business_score:
            blocs.append(formater_business_score(business_score) + "\n")

    return "".join(blocs)


def analyser_et_enregistrer(voitures, filtres=None, chat_id=None):
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
        business_score = calculer_business_score(
            voiture,
            analyse,
            infos_vendeur,
            PRIX_MAX_GLOBAL
        )
        negociation = calculer_negociation(
            voiture,
            analyse,
            infos_vendeur,
            infos_vendeur.get("score") if infos_vendeur else None
        )

        if est_nouvelle and respecte_filtres(voiture, analyse, filtres):
            alertes.append({
                "voiture": voiture,
                "analyse": analyse,
                "business_score": business_score,
                "negociation": negociation,
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

        if respecte_filtres(voiture, analyse, filtres):
            enregistrer_opportunite_depuis_resultat(
                chat_id,
                voiture,
                analyse,
                infos_vendeur,
                business_score,
                negociation,
            )

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
            "business_score": business_score,
            "negociation": negociation,
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

    resultat = analyser_et_enregistrer(
        voitures,
        chat_id=update.effective_chat.id
    )
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


def formater_repartition_plateformes(plateformes):
    lignes = []

    for nom, total in plateformes.items():
        lignes.append(f"- {nom} : {total}")

    return "\n".join(lignes) if lignes else "- Aucune plateforme"


def formater_comparaison_europe(comparaison):
    belgique = comparaison.get("belgique")
    allemagne = comparaison.get("allemagne")
    difference = comparaison.get("difference")

    if belgique is None or allemagne is None or difference is None:
        return "Comparaison Belgique / Allemagne : données insuffisantes"

    return (
        f"Belgique : {formater_prix(belgique)}\n"
        f"Allemagne : {formater_prix(allemagne)}\n"
        f"Différence : {formater_prix(difference)}"
    )


def formater_resultat_europe(resultat):
    annonces = resultat["annonces"]
    erreurs = resultat.get("erreurs") or {}
    pays = ", ".join(resultat.get("pays") or ["Inconnu"])
    blocs = [
        "🌍 SCAN MULTI-PLATEFORMES",
        "",
        f"Recherche : {resultat['modele']}",
        f"Total : {resultat['total']} annonces",
        f"Total brut : {resultat['total_brut']}",
        f"Doublons forts retirés : {resultat['doublons']}",
        "",
        "Répartition :",
        formater_repartition_plateformes(resultat["plateformes"]),
        "",
        f"Pays détectés : {pays}",
        "",
        formater_comparaison_europe(resultat["comparaison"]),
    ]

    if erreurs:
        blocs.extend([
            "",
            "⚠️ Plateformes en erreur :",
            *[f"- {nom} : {erreur}" for nom, erreur in erreurs.items()],
        ])

    if not annonces:
        blocs.extend(["", "Aucune annonce exploitable trouvée."])
        return "\n".join(blocs)

    top = []

    for annonce in annonces:
        try:
            analyse = analyser_annonce(annonce)
        except Exception:
            analyse = {"score": 0, "benefice": 0}

        top.append((annonce, analyse))

    top = sorted(
        top,
        key=lambda item: (
            item[1].get("score", 0),
            item[1].get("benefice", 0)
        ),
        reverse=True
    )[:5]

    blocs.extend(["", "🔥 Top 5 opportunités :"])

    for index, (annonce, analyse) in enumerate(top, start=1):
        blocs.append(
            "\n".join([
                f"{index}. {annonce.get('titre') or annonce.get('modele')}",
                f"🌐 {annonce.get('source')} - {annonce.get('pays', 'Inconnu')}",
                f"💰 Prix : {formater_prix(annonce.get('prix'))}",
                f"📅 Année : {annonce.get('annee', 'Inconnu')}",
                f"🛣️ Km : {annonce.get('kilometrage', 'Inconnu')}",
                f"⭐ Score : {analyse.get('score', 0)}/100",
                f"💵 Bénéfice estimé : +{formater_prix(analyse.get('benefice'))}",
                f"🔗 {annonce.get('lien')}",
            ])
        )

    return "\n\n".join(blocs)


async def europe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("❌ Utilisation : /europe Golf GTI")
        return

    modele = " ".join(context.args).strip()
    await update.message.reply_text("🌍 Scan Europe en cours...")
    resultat = rechercher_partout(modele)
    texte = formater_resultat_europe(resultat)

    for message in decouper_messages([texte], limite=3900):
        await update.message.reply_text(message)


def formater_resultat_marketplace(modele, annonces):
    logger.info(
        "Marketplace formatage debut: modele=%s nombre_recu=%s type=%s",
        modele,
        len(annonces) if annonces is not None else None,
        type(annonces).__name__,
    )
    etat = etat_marketplace()
    derniere_erreur = etat.get("derniere_erreur") or ""
    blocs = [
        "🛒 FACEBOOK MARKETPLACE",
        "",
        f"Recherche : {modele}",
        f"Total : {len(annonces)} annonces",
        "",
    ]

    if not annonces:
        if (
            "authentification" in derniere_erreur.lower()
            or "session facebook expir" in derniere_erreur.lower()
        ):
            blocs.append(
                derniere_erreur
            )
            texte = "\n".join(blocs)
            logger.info(
                "Marketplace formatage fin: annonces_utilisees=0 "
                "taille_message=%s decoupage_telegram=%s",
                len(texte),
                len(texte) > 3900,
            )
            return texte

        blocs.append(
            "Aucune annonce exploitable trouvée ou Marketplace temporairement indisponible."
        )
        texte = "\n".join(blocs)
        logger.info(
            "Marketplace formatage fin: annonces_utilisees=0 "
            "taille_message=%s decoupage_telegram=%s",
            len(texte),
            len(texte) > 3900,
        )
        return texte

    top = []

    for annonce in annonces:
        try:
            analyse = analyser_annonce(annonce)
        except Exception:
            analyse = {"score": 0, "benefice": 0}

        top.append((annonce, analyse))

    top = sorted(
        top,
        key=lambda item: (
            item[1].get("score", 0),
            item[1].get("benefice", 0)
        ),
        reverse=True
    )[:5]

    blocs.append("🔥 Top annonces :")

    for index, (annonce, analyse) in enumerate(top, start=1):
        blocs.append(
            "\n".join([
                f"{index}. {annonce.get('titre') or annonce.get('modele')}",
                f"📍 {annonce.get('ville', 'Belgique')}",
                f"💰 Prix : {formater_prix(annonce.get('prix'))}",
                f"📅 Année : {annonce.get('annee', 'Inconnu')}",
                f"🛣️ Km : {annonce.get('kilometrage', 'Inconnu')}",
                f"⭐ Score : {analyse.get('score', 0)}/100",
                f"💵 Bénéfice estimé : +{formater_prix(analyse.get('benefice'))}",
                f"🔗 {annonce.get('lien')}",
            ])
        )

    texte = "\n\n".join(blocs)
    logger.info(
        "Marketplace formatage fin: annonces_utilisees=%s taille_message=%s "
        "decoupage_telegram=%s",
        len(top),
        len(texte),
        len(texte) > 3900,
    )
    return texte


def source_marketplace_etat():
    etat = etat_marketplace()
    statut = (
        "désactivé temporairement"
        if etat["desactive_temporairement"]
        else "actif"
    )

    return {
        "source": "Facebook Marketplace",
        "annonces_recuperees": 0,
        "annonces_pertinentes": 0,
        "bonnes_affaires": 0,
        "erreurs": etat["echecs_consecutifs"],
        "temps_moyen": None,
        "derniere_reussite": etat["derniere_reussite"],
        "dernier_echec": etat["derniere_erreur"],
        "statut": statut,
        "echecs_consecutifs": etat["echecs_consecutifs"],
    }


async def marketplace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("❌ Utilisation : /marketplace Golf GTI")
        return

    modele = " ".join(context.args).strip()
    await update.message.reply_text("🛒 Scan Facebook Marketplace en cours...")
    annonces = rechercher_marketplace(modele)
    logger.info(
        "Marketplace commande apres recherche: modele=%s len=%s type=%s",
        modele,
        len(annonces) if annonces is not None else None,
        type(annonces).__name__,
    )
    logger.info(
        "Marketplace commande avant formatage: modele=%s len=%s",
        modele,
        len(annonces) if annonces is not None else None,
    )
    texte = formater_resultat_marketplace(modele, annonces)

    messages = decouper_messages([texte], limite=3900)
    logger.info(
        "Marketplace commande decoupage Telegram: messages=%s longueurs=%s",
        len(messages),
        [len(message) for message in messages],
    )

    for message in messages:
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

            resultat = analyser_et_enregistrer(voitures, chat_id=chat_id)
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

            resultat = analyser_et_enregistrer(voitures, filtres, chat_id)
            toutes_les_alertes = resultat["alertes"]
            meilleure_alerte = toutes_les_alertes[0] if toutes_les_alertes else None

            enregistrer_statistiques_scan(
                chat_id=chat_id,
                recherche=recherche,
                annonces_analysees=len(voitures),
                nouvelles_annonces=resultat["nouvelles"],
                bonnes_affaires=len(toutes_les_alertes),
                alertes_envoyees=min(
                    len(toutes_les_alertes),
                    MAX_ALERTES_PAR_RECHERCHE
                ),
                meilleur_modele=(
                    meilleure_alerte["voiture"]["modele"]
                    if meilleure_alerte else None
                ),
                meilleur_benefice=(
                    meilleure_alerte["analyse"]["benefice"]
                    if meilleure_alerte else None
                ),
                meilleur_score_business=(
                    meilleure_alerte.get("business_score", {}).get("score")
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


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        generer_tableau_de_bord(update.effective_chat.id),
        reply_markup=clavier_tableau_de_bord()
    )


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = generer_top(
        update.effective_chat.id,
        jours=1,
        limite=5,
        tri="score_business",
        titre="🔥 Top 5 opportunités du jour"
    )

    for message in decouper_messages([texte], limite=3900):
        await update.message.reply_text(message, reply_markup=clavier_opportunites())


async def stats_modele_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text(
            "❌ Utilisation : /stats_modele <modèle>"
        )
        return

    modele = " ".join(context.args).strip()
    texte = formater_stats_modele(
        stats_modele(update.effective_chat.id, modele)
    )
    await update.message.reply_text(texte, reply_markup=clavier_tableau_de_bord())


def _chat_id(update):
    return update.effective_user.id


def _format_valeur_parametre(valeur, suffixe=""):
    if valeur in (None, ""):
        return "Non défini"

    texte = f"{int(valeur):,}".replace(",", " ")
    return f"{texte}{suffixe}"


def _format_liste_parametre(valeurs):
    if not valeurs:
        return "Non défini"

    return ", ".join(str(valeur) for valeur in valeurs)


def formater_parametres_utilisateur(chat_id):
    parametres = obtenir_parametres(chat_id)
    alertes = parametres.get("alertes", [])
    alertes_activees = parametres.get("alertes_activees", True)
    lignes_alertes = []

    for index, alerte in enumerate(alertes, start=1):
        texte = alerte.get("texte") or "Alerte"
        lignes_alertes.append(f"{alerte.get('id', index)}. {texte}")

    if not lignes_alertes:
        lignes_alertes.append("Aucune alerte active.")

    return "\n".join([
        "⚙️ MES PARAMÈTRES",
        "",
        f"Budget min : {_format_valeur_parametre(parametres.get('budget_min'), ' €')}",
        f"Budget max : {_format_valeur_parametre(parametres.get('budget_max'), ' €')}",
        f"Km max : {_format_valeur_parametre(parametres.get('km_max'), ' km')}",
        f"Année min : {_format_valeur_parametre(parametres.get('annee_min'))}",
        f"Score min : {_format_valeur_parametre(parametres.get('score_min'), '/100')}",
        f"Bénéfice min : {_format_valeur_parametre(parametres.get('benefice_min'), ' €')}",
        f"Pays : {_format_liste_parametre(parametres.get('pays'))}",
        f"Fréquence scan : toutes les {_format_valeur_parametre(parametres.get('frequence_scan_heures'))} h",
        f"Alertes : {'activées' if alertes_activees else 'désactivées'}",
        "",
        "Alertes actives :",
        *lignes_alertes,
    ])


def formater_surveillance_liste(chat_id):
    surveillances = lister_surveillances(chat_id)

    if not surveillances:
        return "🔔 MES SURVEILLANCES\n\nAucune recherche surveillée."

    lignes = ["🔔 MES SURVEILLANCES", ""]

    for index, (recherche, filtres) in enumerate(surveillances, start=1):
        lignes.extend([
            f"{index}. {recherche}",
            f"Filtres : {formater_filtres(filtres)}",
            "Date : non disponible",
            "",
        ])

    return "\n".join(lignes).strip()


def supprimer_toutes_surveillances(chat_id):
    total = 0

    for recherche, filtres in list(lister_surveillances(chat_id)):
        if supprimer_surveillance(recherche, chat_id, filtres):
            total += 1

    return total


PARAMETRES_SAISIE = {
    "budget_min": {
        "invite": "💰 Envoie le budget minimum en euros, par exemple : 5000.",
        "nom": "Budget minimum",
    },
    "budget_max": {
        "invite": "💰 Envoie le budget maximum en euros, par exemple : 15000.",
        "nom": "Budget maximum",
    },
    "km_max": {
        "invite": "🛣️ Envoie le kilométrage maximum, par exemple : 120000.",
        "nom": "Kilométrage maximum",
    },
    "annee_min": {
        "invite": "📅 Envoie l'année minimale, par exemple : 2017.",
        "nom": "Année minimale",
    },
    "score_min": {
        "invite": "⭐ Envoie le score minimum entre 0 et 100, par exemple : 80.",
        "nom": "Score minimum",
    },
    "benefice_min": {
        "invite": "💵 Envoie le bénéfice minimum en euros, par exemple : 2500.",
        "nom": "Bénéfice minimum",
    },
    "pays": {
        "invite": "🌍 Envoie les pays séparés par des virgules, par exemple : Belgique, Allemagne.",
        "nom": "Pays",
    },
    "frequence": {
        "invite": "⏱️ Envoie la fréquence en heures entre 1 et 24, par exemple : 2.",
        "nom": "Fréquence du scan",
    },
}


def appliquer_parametre_utilisateur(chat_id, champ, valeur):
    if champ == "budget_min":
        return modifier_budget_min(chat_id, int(valeur))
    if champ == "budget_max":
        return modifier_budget_utilisateur(chat_id, int(valeur))
    if champ == "km_max":
        return modifier_km_utilisateur(chat_id, int(valeur))
    if champ == "annee_min":
        annee = int(valeur)
        if annee < 1950 or annee > datetime.now().year + 1:
            raise ValueError("Année invalide.")
        return modifier_annee_utilisateur(chat_id, annee)
    if champ == "score_min":
        return modifier_score_min(chat_id, int(valeur))
    if champ == "benefice_min":
        return modifier_benefice_min(chat_id, int(valeur))
    if champ == "pays":
        return modifier_pays(chat_id, valeur)
    if champ == "frequence":
        return modifier_frequence_scan(chat_id, int(valeur))

    raise ValueError("Paramètre inconnu.")


async def modifier_budget_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Utilisation : /modifier_budget 15000")
        return

    try:
        parametres = modifier_budget_utilisateur(_chat_id(update), context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Budget invalide. Exemple : /modifier_budget 15000")
        return

    await update.message.reply_text(
        f"✅ Budget max mis à jour : {_format_valeur_parametre(parametres['budget_max'], ' €')}"
    )


async def voir_budget_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parametres = obtenir_parametres(_chat_id(update))
    await update.message.reply_text(
        f"Budget max : {_format_valeur_parametre(parametres.get('budget_max'), ' €')}"
    )


async def modifier_km_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Utilisation : /modifier_km 120000")
        return

    try:
        parametres = modifier_km_utilisateur(_chat_id(update), context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Kilométrage invalide. Exemple : /modifier_km 120000")
        return

    await update.message.reply_text(
        f"✅ Kilométrage max mis à jour : {_format_valeur_parametre(parametres['km_max'])}"
    )


async def voir_km_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parametres = obtenir_parametres(_chat_id(update))
    await update.message.reply_text(
        f"Km max : {_format_valeur_parametre(parametres.get('km_max'))}"
    )


async def modifier_annee_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Utilisation : /modifier_annee 2017")
        return

    try:
        annee = int(context.args[0])
        if annee < 1950 or annee > datetime.now().year + 1:
            raise ValueError
        parametres = modifier_annee_utilisateur(_chat_id(update), annee)
    except ValueError:
        await update.message.reply_text("❌ Année invalide. Exemple : /modifier_annee 2017")
        return

    await update.message.reply_text(
        f"✅ Année minimale mise à jour : {parametres['annee_min']}"
    )


async def voir_annee_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parametres = obtenir_parametres(_chat_id(update))
    await update.message.reply_text(
        f"Année min : {_format_valeur_parametre(parametres.get('annee_min'))}"
    )


async def mes_alertes_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alertes = lister_alertes_utilisateur(_chat_id(update))

    if not alertes:
        await update.message.reply_text("Aucune alerte active.")
        return

    lignes = ["🔔 MES ALERTES", ""]
    lignes.extend(
        f"{alerte.get('id')}. {alerte.get('texte') or 'Alerte'}"
        for alerte in alertes
    )
    await update.message.reply_text("\n".join(lignes))


async def supprimer_alerte_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Utilisation : /supprimer_alerte 3")
        return

    try:
        supprimee = supprimer_alerte_utilisateur(_chat_id(update), context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID d'alerte invalide. Exemple : /supprimer_alerte 3")
        return

    if supprimee:
        await update.message.reply_text("✅ Alerte supprimée.")
    else:
        await update.message.reply_text("Aucune alerte trouvée avec cet ID.")


async def supprimer_toutes_alertes_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = supprimer_toutes_alertes(_chat_id(update))
    await update.message.reply_text(f"✅ {total} alerte(s) supprimée(s).")


async def mes_parametres_commande(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(formater_parametres_utilisateur(_chat_id(update)))


async def analyser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text(
            "❌ Utilisation : /analyser <lien AutoScout24 ou 2ememain>"
        )
        return

    lien = " ".join(context.args).strip()
    await update.message.reply_text("🔎 Analyse de l'annonce en cours...")

    try:
        resultat = analyser_annonce_par_lien_detail(lien)
        texte = resultat["texte"]
        context.user_data["derniere_analyse_annonce"] = resultat
    except ValueError as erreur:
        texte = f"❌ {erreur}"
    except RuntimeError as erreur:
        texte = f"❌ Impossible de récupérer l'annonce.\n{erreur}"
    except Exception as erreur:
        logger.exception("Erreur pendant /analyser")
        texte = (
            "❌ Impossible d'analyser cette annonce. "
            f"Détail : {erreur}"
        )

    messages = decouper_messages([texte], limite=3900)

    for index, message in enumerate(messages):
        kwargs = {}

        if index == len(messages) - 1 and "resultat" in locals():
            est_favori = obtenir_favori(
                update.effective_chat.id,
                resultat["voiture"]["lien"]
            )
            kwargs["reply_markup"] = clavier_analyse_annonce(bool(est_favori))

        await update.message.reply_text(message, **kwargs)


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


def ajouter_favori_depuis_analyse(chat_id, resultat):
    voiture = resultat["voiture"]
    business_score = resultat["business_score"]
    negociation = resultat["negociation"]

    return ajouter_favori(
        chat_id=chat_id,
        lien=voiture["lien"],
        modele=voiture.get("titre") or voiture.get("modele"),
        prix=voiture.get("prix"),
        prix_initial=voiture.get("prix"),
        score_business=business_score["score"],
        score_negociation=negociation["score_negociation"],
    )


def formater_liste_favoris(chat_id):
    favoris = lister_favoris(chat_id)

    if not favoris:
        return "❤️ Favoris\n\nAucun favori actif pour le moment."

    lignes = ["❤️ Favoris actifs\n"]

    for index, favori in enumerate(favoris, start=1):
        lignes.append(
            f"{index}. {favori.get('modele') or 'Annonce'}\n"
            f"💰 Prix : {formater_prix(favori.get('prix'))}\n"
            f"🔥 Business Score : {favori.get('score_business') or 'Inconnu'}/100\n"
            f"🤝 Négociation : {favori.get('score_negociation') or 'Inconnu'}/100\n"
            f"🔗 {favori.get('lien')}\n"
        )

    return "\n".join(lignes)


def clavier_liste_favoris(chat_id):
    lignes = []

    for favori in lister_favoris(chat_id)[:10]:
        libelle = f"🗑 {favori.get('modele') or favori['id']}"
        lignes.append([
            InlineKeyboardButton(
                libelle[:60],
                callback_data=f"fav:remove_id:{favori['id']}"
            )
        ])

    lignes.append([InlineKeyboardButton("📉 Vérifier les prix maintenant", callback_data="fav:check")])
    lignes.append([InlineKeyboardButton("🏠 Accueil", callback_data="menu:home")])
    return InlineKeyboardMarkup(lignes)


def baisse_declenche_alerte(favori, nouveau_prix):
    ancien_prix = extraire_nombre(favori.get("prix"))
    nouveau_prix = extraire_nombre(nouveau_prix)

    if ancien_prix is None or nouveau_prix is None:
        return False

    variation = nouveau_prix - ancien_prix

    if variation >= 0:
        return False

    baisse = abs(variation)
    pourcentage = (baisse / ancien_prix) * 100 if ancien_prix else 0

    return (
        baisse >= 500
        or pourcentage >= 3
        or nombre_alertes_baisse_favori(
            favori["chat_id"],
            favori["lien"]
        ) > 0
    )


def formater_alerte_baisse_favori(favori, voiture, negociation, ancien_prix):
    nouveau_prix = extraire_nombre(voiture.get("prix")) or 0
    baisse = int(ancien_prix - nouveau_prix)
    pourcentage = (baisse / ancien_prix) * 100 if ancien_prix else 0

    return (
        "📉 BAISSE DE PRIX\n\n"
        f"🚗 {voiture.get('titre') or voiture.get('modele')}\n"
        f"Ancien prix : {formater_prix(int(ancien_prix))}\n"
        f"Nouveau prix : {formater_prix(int(nouveau_prix))}\n"
        f"Baisse : {formater_prix(baisse)} (-{pourcentage:.1f} %)\n\n"
        f"💬 Nouveau score négociation : {negociation['score_negociation']}/100\n"
        f"🎯 Offre conseillée : {formater_prix(negociation['prix_conseille'])}\n"
        f"🔗 {favori['lien']}"
    )


def analyser_favori_pour_prix(favori):
    voiture = analyser_lien_plateforme(favori["lien"])
    analyse = analyser_annonce(voiture)
    business_score = calculer_business_score(
        voiture,
        analyse,
        None,
        PRIX_MAX_GLOBAL
    )
    negociation = calculer_negociation(voiture, analyse)
    return voiture, analyse, business_score, negociation


async def verifier_favoris_actifs(bot=None, chat_id_filtre=None):
    alertes = []

    for favori in lister_favoris_actifs():
        if chat_id_filtre is not None and favori["chat_id"] != chat_id_filtre:
            continue

        try:
            voiture, _analyse, business_score, negociation = analyser_favori_pour_prix(
                favori
            )
        except Exception as erreur:
            logger.warning(
                "Erreur vérification favori %s : %s",
                favori.get("lien"),
                erreur
            )
            continue

        ancien_prix = extraire_nombre(favori.get("prix"))
        nouveau_prix = extraire_nombre(voiture.get("prix"))

        if ancien_prix is None or nouveau_prix is None:
            mettre_a_jour_favori(
                favori["chat_id"],
                favori["lien"],
                prix=nouveau_prix,
                score_business=business_score["score"],
                score_negociation=negociation["score_negociation"],
                modele=voiture.get("titre") or voiture.get("modele"),
            )
            continue

        variation = int(nouveau_prix - ancien_prix)
        signature = signature_alerte_baisse_favori(
            favori["chat_id"],
            favori["lien"],
            int(nouveau_prix)
        )

        doit_alerter = (
            baisse_declenche_alerte(favori, nouveau_prix)
            and not alerte_baisse_favori_deja_envoyee(signature)
        )

        mettre_a_jour_favori(
            favori["chat_id"],
            favori["lien"],
            prix=nouveau_prix,
            score_business=business_score["score"],
            score_negociation=negociation["score_negociation"],
            modele=voiture.get("titre") or voiture.get("modele"),
        )

        if not doit_alerter:
            continue

        enregistrer_alerte_baisse_favori(
            favori["chat_id"],
            favori["lien"],
            int(ancien_prix),
            int(nouveau_prix),
            variation,
            signature,
        )
        texte = formater_alerte_baisse_favori(
            favori,
            voiture,
            negociation,
            ancien_prix
        )
        alertes.append({
            "chat_id": favori["chat_id"],
            "texte": texte,
            "signature": signature,
        })

        if bot is not None:
            await bot.send_message(chat_id=favori["chat_id"], text=texte)

    return alertes


async def scanner_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if activer_scanner_global(chat_id, PRIX_MAX_GLOBAL):
        await update.message.reply_text(
            "✅ Scanner Business global activé.\n"
            "Un lot de véhicules sera analysé toutes les 2 heures."
        )
    else:
        await update.message.reply_text(
            "ℹ️ Scanner Business global déjà actif."
        )


async def stop_scanner_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if desactiver_scanner_global(chat_id):
        await update.message.reply_text(
            "🛑 Scanner Business global désactivé."
        )
    else:
        await update.message.reply_text(
            "ℹ️ Scanner Business global déjà inactif."
        )


async def statut_scanner_global_commande(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    statut = statut_scanner_global(update.effective_chat.id)

    if not statut or not statut["actif"]:
        await update.message.reply_text(
            "Scanner Business global : inactif."
        )
        return

    nom_lot, vehicules = LOTS_VEHICULES_BUSINESS[
        statut["prochain_lot_index"] % len(LOTS_VEHICULES_BUSINESS)
    ]
    await update.message.reply_text(
        "Scanner Business global : actif.\n"
        f"Prochain lot : {nom_lot.replace('_', ' ')} "
        f"({len(vehicules)} recherches)\n"
        f"Prix maximum : {formater_prix(statut['prix_max'] or PRIX_MAX_GLOBAL)}"
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


async def verifier_favoris_job(context: ContextTypes.DEFAULT_TYPE):
    global verification_favoris_en_cours

    if verification_favoris_en_cours:
        logger.info("Vérification favoris déjà en cours, passage ignoré.")
        return

    verification_favoris_en_cours = True

    try:
        await verifier_favoris_actifs(context.bot)
    finally:
        verification_favoris_en_cours = False


async def scan_global_business(context: ContextTypes.DEFAULT_TYPE):
    global scan_global_en_cours

    if scan_global_en_cours:
        logger.info("Scan global déjà en cours, passage ignoré.")
        return

    scan_global_en_cours = True
    debut_scan = time_module.monotonic()

    try:
        scanners_actifs = lister_scanners_globaux_actifs()

        for scanner in scanners_actifs:
            chat_id = scanner["chat_id"]
            prix_max = scanner["prix_max"] or PRIX_MAX_GLOBAL
            index_lot = scanner["prochain_lot_index"] % len(LOTS_VEHICULES_BUSINESS)
            nom_lot, vehicules = LOTS_VEHICULES_BUSINESS[index_lot]
            voitures = []
            erreurs = []

            for recherche in vehicules:
                voitures_recherche, erreurs_recherche = scanner_recherche_global(
                    recherche
                )
                voitures.extend(voitures_recherche)
                erreurs.extend(erreurs_recherche)

            voitures = dedupliquer_annonces_par_lien(voitures)
            opportunites = analyser_scan_global(voitures, prix_max)
            opportunites = opportunites_globales_non_envoyees(
                chat_id,
                opportunites
            )[:MAX_OPPORTUNITES_SCAN_GLOBAL]

            if opportunites:
                message = formater_resume_scanner_global(
                    nom_lot,
                    opportunites,
                    erreurs
                )

                for morceau in decouper_messages([message], limite=3900):
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=morceau
                    )

                for opportunite in opportunites:
                    infos_vendeur = opportunite["infos_vendeur"]
                    baisse_totale = (
                        infos_vendeur["baisse_totale"]
                        if infos_vendeur else 0
                    )
                    enregistrer_opportunite_depuis_resultat(
                        chat_id,
                        opportunite["voiture"],
                        opportunite["analyse"],
                        infos_vendeur,
                        opportunite["business_score"],
                        opportunite["negociation"],
                    )
                    enregistrer_opportunite_globale_envoyee(
                        chat_id,
                        opportunite["voiture"]["lien"],
                        opportunite["prix"],
                        opportunite["score_business"],
                        baisse_totale,
                        opportunite["signature"]
                    )

            avancer_lot_scanner_global(
                chat_id,
                len(LOTS_VEHICULES_BUSINESS)
            )

    finally:
        duree = time_module.monotonic() - debut_scan
        logger.info("Scan global terminé en %.2fs", duree)
        scan_global_en_cours = False


async def executer_scan_global_pour_scanners(context, scanners_actifs):
    debut_scan = time_module.monotonic()

    try:
        for scanner in scanners_actifs:
            chat_id = scanner["chat_id"]
            prix_max = scanner["prix_max"] or PRIX_MAX_GLOBAL
            index_lot = scanner["prochain_lot_index"] % len(LOTS_VEHICULES_BUSINESS)
            nom_lot, vehicules = LOTS_VEHICULES_BUSINESS[index_lot]
            voitures = []
            erreurs = []

            for recherche in vehicules:
                voitures_recherche, erreurs_recherche = scanner_recherche_global(
                    recherche
                )
                voitures.extend(voitures_recherche)
                erreurs.extend(erreurs_recherche)

            voitures = dedupliquer_annonces_par_lien(voitures)
            opportunites = analyser_scan_global(voitures, prix_max)
            opportunites = opportunites_globales_non_envoyees(
                chat_id,
                opportunites
            )[:MAX_OPPORTUNITES_SCAN_GLOBAL]

            if opportunites:
                message = formater_resume_scanner_global(
                    nom_lot,
                    opportunites,
                    erreurs
                )

                for morceau in decouper_messages([message], limite=3900):
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=morceau
                    )

                for opportunite in opportunites:
                    infos_vendeur = opportunite["infos_vendeur"]
                    baisse_totale = (
                        infos_vendeur["baisse_totale"]
                        if infos_vendeur else 0
                    )
                    enregistrer_opportunite_depuis_resultat(
                        chat_id,
                        opportunite["voiture"],
                        opportunite["analyse"],
                        infos_vendeur,
                        opportunite["business_score"],
                        opportunite["negociation"],
                    )
                    enregistrer_opportunite_globale_envoyee(
                        chat_id,
                        opportunite["voiture"]["lien"],
                        opportunite["prix"],
                        opportunite["score_business"],
                        baisse_totale,
                        opportunite["signature"]
                    )

            avancer_lot_scanner_global(
                chat_id,
                len(LOTS_VEHICULES_BUSINESS)
            )

    finally:
        duree = time_module.monotonic() - debut_scan
        logger.info("Scan global terminé en %.2fs", duree)


async def executer_scan_global_avec_verrou(context, scanners_actifs):
    global scan_global_en_cours

    if scan_global_en_cours:
        return False

    scan_global_en_cours = True

    try:
        await executer_scan_global_pour_scanners(context, scanners_actifs)
        return True
    finally:
        scan_global_en_cours = False


async def scan_global_business(context: ContextTypes.DEFAULT_TYPE):
    scanners_actifs = lister_scanners_globaux_actifs()
    lancement = await executer_scan_global_avec_verrou(context, scanners_actifs)

    if not lancement:
        logger.info("Scan global déjà en cours, passage ignoré.")


async def lancer_scan_global_pour_chat(chat_id, bot):
    statut = statut_scanner_global(chat_id)

    if not statut or not statut["actif"]:
        return "inactive"

    contexte = type("ScanGlobalContext", (), {"bot": bot})()
    lancement = await executer_scan_global_avec_verrou(
        contexte,
        [{
            "chat_id": chat_id,
            "prix_max": statut["prix_max"],
            "prochain_lot_index": statut["prochain_lot_index"],
        }]
    )

    return "started" if lancement else "busy"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        texte_accueil(),
        reply_markup=clavier_principal()
    )


async def afficher_menu_callback(query, texte, clavier):
    await query.edit_message_text(
        text=texte,
        reply_markup=clavier
    )


def generer_statut_scanner_global(chat_id):
    statut = statut_scanner_global(chat_id)

    if not statut or not statut["actif"]:
        return "Scanner Business global : inactif."

    nom_lot, vehicules = LOTS_VEHICULES_BUSINESS[
        statut["prochain_lot_index"] % len(LOTS_VEHICULES_BUSINESS)
    ]
    return (
        "Scanner Business global : actif.\n"
        f"Prochain lot : {nom_lot.replace('_', ' ')} "
        f"({len(vehicules)} recherches)\n"
        f"Prix maximum : {formater_prix(statut['prix_max'] or PRIX_MAX_GLOBAL)}"
    )


def generer_tableau_de_bord(chat_id):
    return formater_dashboard(dashboard_resume(chat_id))


def generer_top(chat_id, jours=1, limite=5, tri="score_business", titre=None):
    opportunites = top_opportunites(
        chat_id,
        jours=jours,
        limite=limite,
        tri=tri
    )
    return formater_top(titre or "🔥 Top opportunités", opportunites, limite)


async def interface_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if data == "menu:home":
        await afficher_menu_callback(query, texte_accueil(), clavier_principal())
    elif data == "menu:scanner":
        await afficher_menu_callback(query, texte_scanner_business(), clavier_scanner_business())
    elif data == "menu:europe":
        await afficher_menu_callback(query, texte_scanner_europe(), clavier_scanner_europe())
    elif data == "menu:marketplace":
        await afficher_menu_callback(query, texte_marketplace(), clavier_marketplace())
    elif data == "menu:opportunities":
        await afficher_menu_callback(query, texte_opportunites(), clavier_opportunites())
    elif data == "menu:favorites":
        await afficher_menu_callback(query, texte_favoris(), clavier_favoris())
    elif data == "menu:dashboard":
        await afficher_menu_callback(query, generer_tableau_de_bord(chat_id), clavier_tableau_de_bord())
    elif data == "menu:settings":
        await afficher_menu_callback(query, formater_parametres_utilisateur(chat_id), clavier_parametres())
    elif data == "menu:help":
        await afficher_menu_callback(query, texte_aide(), clavier_aide())
    elif data == "analysis:ask_link":
        context.user_data["attente_analyse_lien"] = True
        await afficher_menu_callback(
            query,
            "🔗 Colle le lien AutoScout24 ou 2ememain à analyser.",
            clavier_retour_accueil()
        )
    elif data == "scanner:enable":
        texte = (
            "✅ Scanner Business global activé."
            if activer_scanner_global(chat_id, PRIX_MAX_GLOBAL)
            else "ℹ️ Scanner Business global déjà actif."
        )
        await afficher_menu_callback(query, texte, clavier_scanner_business())
    elif data == "scanner:disable":
        texte = (
            "🛑 Scanner Business global désactivé."
            if desactiver_scanner_global(chat_id)
            else "ℹ️ Scanner Business global déjà inactif."
        )
        await afficher_menu_callback(query, texte, clavier_scanner_business())
    elif data == "scanner:status":
        await afficher_menu_callback(query, generer_statut_scanner_global(chat_id), clavier_scanner_business())
    elif data == "scanner:europe":
        await afficher_menu_callback(query, texte_scanner_europe(), clavier_scanner_europe())
    elif data == "scanner:marketplace":
        await afficher_menu_callback(query, texte_marketplace(), clavier_marketplace())
    elif data == "scanner:run":
        if scan_global_en_cours:
            await afficher_menu_callback(
                query,
                "⏳ Un scan est déjà en cours. Merci de patienter.",
                clavier_scanner_business()
            )
            return

        await afficher_menu_callback(
            query,
            "🚀 Scan global lancé. Les opportunités seront envoyées ici.",
            clavier_scanner_business()
        )
        resultat = await lancer_scan_global_pour_chat(chat_id, context.bot)

        if resultat == "busy":
            await context.bot.send_message(
                chat_id=chat_id,
                text="⏳ Un scan est déjà en cours. Merci de patienter."
            )
        elif resultat == "inactive":
            await context.bot.send_message(
                chat_id=chat_id,
                text="ℹ️ Active d'abord le Scanner Business global."
            )
    elif data == "scanner:settings":
        await afficher_menu_callback(query, formater_parametres_utilisateur(chat_id), clavier_parametres())
    elif data == "europe:search":
        context.user_data["attente_scan_europe"] = True
        await afficher_menu_callback(
            query,
            "🌍 Envoie le modèle à scanner en Europe, par exemple : Golf GTI.",
            clavier_scanner_europe()
        )
    elif data.startswith("europe:country:"):
        pays = data.rsplit(":", 1)[1]
        modifier_pays(chat_id, pays)
        await afficher_menu_callback(
            query,
            f"✅ Pays préféré mis à jour : {pays}\n\n{texte_scanner_europe()}",
            clavier_scanner_europe()
        )
    elif data == "europe:sources":
        await afficher_menu_callback(
            query,
            formater_sources(stats_sources() + [source_marketplace_etat()]),
            clavier_scanner_europe()
        )
    elif data == "marketplace:search":
        context.user_data["attente_scan_marketplace"] = True
        await afficher_menu_callback(
            query,
            "🛒 Envoie le modèle à rechercher sur Facebook Marketplace.",
            clavier_marketplace()
        )
    elif data == "marketplace:status":
        await afficher_menu_callback(query, formater_etat_marketplace(), clavier_marketplace())
    elif data == "marketplace:retry":
        tester_sante()
        await afficher_menu_callback(
            query,
            "🔄 Test de santé Marketplace effectué.\n\n" + formater_etat_marketplace(),
            clavier_marketplace()
        )
    elif data == "opp:top_week":
        await afficher_menu_callback(
            query,
            generer_top(chat_id, jours=7, limite=10, tri="score_business", titre="Top 10 cette semaine"),
            clavier_opportunites()
        )
    elif data == "opp:top_roi":
        await afficher_menu_callback(
            query,
            generer_top(chat_id, jours=30, limite=10, tri="roi", titre="Top ROI"),
            clavier_opportunites()
        )
    elif data == "opp:top_today":
        await afficher_menu_callback(
            query,
            generer_top(
                chat_id,
                jours=1,
                limite=10,
                tri="score_business",
                titre="🏆 Top 10 aujourd'hui"
            ),
            clavier_opportunites()
        )
    elif data == "opp:last_alerts":
        await afficher_menu_callback(
            query,
            generer_top(
                chat_id,
                jours=7,
                limite=10,
                tri="score_business",
                titre="🚨 Dernières alertes"
            ),
            clavier_opportunites()
        )
    elif data == "opp:urgent_sellers":
        await afficher_menu_callback(
            query,
            generer_top(
                chat_id,
                jours=30,
                limite=10,
                tri="vendeur",
                titre="⏳ Top vendeurs pressés"
            ),
            clavier_opportunites()
        )
    elif data == "opp:price_drops":
        await afficher_menu_callback(
            query,
            generer_top(
                chat_id,
                jours=30,
                limite=10,
                tri="baisse",
                titre="📉 Top baisses de prix"
            ),
            clavier_opportunites()
        )
    elif data == "fav:list":
        await afficher_menu_callback(
            query,
            formater_liste_favoris(chat_id),
            clavier_liste_favoris(chat_id)
        )
    elif data == "fav:delete":
        await afficher_menu_callback(
            query,
            "🗑 Retirer un favori\n\nChoisis un favori à retirer.",
            clavier_liste_favoris(chat_id)
        )
    elif data == "fav:add_last":
        resultat = context.user_data.get("derniere_analyse_annonce")

        if not resultat:
            await afficher_menu_callback(
                query,
                "ℹ️ Analyse d'abord une annonce avant de l'ajouter aux favoris.",
                clavier_favoris()
            )
            return

        ajoute = ajouter_favori_depuis_analyse(chat_id, resultat)
        texte = (
            "❤️ Annonce ajoutée aux favoris et suivie pour les baisses de prix."
            if ajoute
            else "ℹ️ Cette annonce est déjà dans tes favoris."
        )
        await afficher_menu_callback(
            query,
            texte,
            clavier_analyse_annonce(est_favori=True)
        )
    elif data == "fav:remove_last":
        resultat = context.user_data.get("derniere_analyse_annonce")

        if not resultat:
            await afficher_menu_callback(
                query,
                "ℹ️ Aucun favori récent à retirer.",
                clavier_favoris()
            )
            return

        retire = supprimer_favori(chat_id, resultat["voiture"]["lien"])
        texte = (
            "🗑 Annonce retirée des favoris."
            if retire
            else "ℹ️ Cette annonce n'était pas dans tes favoris actifs."
        )
        await afficher_menu_callback(
            query,
            texte,
            clavier_analyse_annonce(est_favori=False)
        )
    elif data.startswith("fav:remove_id:"):
        favori_id = int(data.rsplit(":", 1)[1])
        retire = supprimer_favori_par_id(chat_id, favori_id)
        texte = (
            "🗑 Favori retiré."
            if retire
            else "ℹ️ Favori introuvable ou déjà retiré."
        )
        await afficher_menu_callback(
            query,
            texte + "\n\n" + formater_liste_favoris(chat_id),
            clavier_liste_favoris(chat_id)
        )
    elif data == "fav:delete_all":
        favoris = list(lister_favoris(chat_id))
        total = 0

        for favori in favoris:
            if supprimer_favori_par_id(chat_id, favori["id"]):
                total += 1

        await afficher_menu_callback(
            query,
            f"🧹 {total} favori(s) retiré(s).\n\n" + formater_liste_favoris(chat_id),
            clavier_liste_favoris(chat_id)
        )
    elif data == "fav:check":
        await afficher_menu_callback(
            query,
            "📉 Vérification des favoris en cours...",
            clavier_favoris()
        )
        alertes = await verifier_favoris_actifs(context.bot, chat_id)

        if not alertes:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Aucune baisse de prix détectée sur tes favoris."
            )
    elif data in ("dash:summary", "dash:overview"):
        await afficher_menu_callback(query, generer_tableau_de_bord(chat_id), clavier_tableau_de_bord())
    elif data == "dash:top_today":
        await afficher_menu_callback(
            query,
            generer_top(
                chat_id,
                jours=1,
                limite=5,
                tri="score_business",
                titre="🔥 Top 5 du jour"
            ),
            clavier_tableau_de_bord()
        )
    elif data == "dash:top_week":
        await afficher_menu_callback(
            query,
            generer_top(
                chat_id,
                jours=7,
                limite=10,
                tri="score_business",
                titre="📅 Top 10 de la semaine"
            ),
            clavier_tableau_de_bord()
        )
    elif data == "dash:stats_model_prompt":
        context.user_data["attente_stats_modele"] = True
        await afficher_menu_callback(
            query,
            "🚗 Stats par modèle\n\nEnvoie le modèle à analyser, par exemple : golf, audi a3 ou bmw serie 1.",
            clavier_tableau_de_bord()
        )
    elif data == "dash:sources":
        await afficher_menu_callback(
            query,
            formater_sources(stats_sources() + [source_marketplace_etat()]),
            clavier_tableau_de_bord()
        )
    elif data.startswith("settings:set:"):
        champ = data.rsplit(":", 1)[1]
        definition = PARAMETRES_SAISIE.get(champ)

        if not definition:
            await afficher_menu_callback(query, "⚙️ Paramètre inconnu.", clavier_parametres())
            return

        context.user_data["attente_parametre"] = champ
        await afficher_menu_callback(query, definition["invite"], clavier_parametres())
    elif data == "settings:toggle_alertes":
        parametres = basculer_alertes(chat_id)
        etat = "activées" if parametres.get("alertes_activees", True) else "désactivées"
        await afficher_menu_callback(
            query,
            f"🔔 Alertes {etat}.\n\n" + formater_parametres_utilisateur(chat_id),
            clavier_parametres()
        )
    elif data == "settings:surveillances":
        await afficher_menu_callback(
            query,
            formater_surveillance_liste(chat_id),
            clavier_surveillance_liste(chat_id)
        )
    elif data.startswith("surv:delete:"):
        index = int(data.rsplit(":", 1)[1])
        surveillances = lister_surveillances(chat_id)

        if index < 0 or index >= len(surveillances):
            await afficher_menu_callback(
                query,
                "ℹ️ Surveillance introuvable.",
                clavier_surveillance_liste(chat_id)
            )
            return

        recherche, filtres = surveillances[index]
        supprimee = supprimer_surveillance(recherche, chat_id, filtres)
        texte = "🗑 Surveillance supprimée." if supprimee else "ℹ️ Surveillance introuvable."
        await afficher_menu_callback(
            query,
            texte + "\n\n" + formater_surveillance_liste(chat_id),
            clavier_surveillance_liste(chat_id)
        )
    elif data == "surv:delete_all":
        total = supprimer_toutes_surveillances(chat_id)
        await afficher_menu_callback(
            query,
            f"🧹 {total} surveillance(s) supprimée(s).\n\n" + formater_surveillance_liste(chat_id),
            clavier_surveillance_liste(chat_id)
        )
    elif data == "surv:alerts_off":
        definir_alertes(chat_id, False)
        await afficher_menu_callback(
            query,
            "🔕 Alertes désactivées.\n\n" + formater_parametres_utilisateur(chat_id),
            clavier_surveillance_liste(chat_id)
        )
    elif data == "surv:alerts_on":
        definir_alertes(chat_id, True)
        await afficher_menu_callback(
            query,
            "🔔 Alertes activées.\n\n" + formater_parametres_utilisateur(chat_id),
            clavier_surveillance_liste(chat_id)
        )
    elif data == "help:scores":
        await afficher_menu_callback(query, "⭐ Scores\n\nLe score IA évalue la qualité de l'annonce selon le prix, la marge et le contexte véhicule.", clavier_aide())
    elif data == "help:business_score":
        await afficher_menu_callback(query, "🔥 Business Score V2\n\nScore d'investissement sur 100 basé sur le score IA, la marge, le vendeur pressé, l'historique des prix, le budget, le prix marché, la liquidité, le risque, la fiabilité, la LEZ, la popularité, les réparations et la disponibilité des pièces.", clavier_aide())
    elif data == "help:faq":
        await afficher_menu_callback(query, "❓ FAQ\n\nLes anciennes commandes restent disponibles, mais l'utilisation principale se fait maintenant avec les boutons.", clavier_aide())


async def gerer_reply_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = (update.message.text or "").strip()

    if context.user_data.get("attente_parametre"):
        champ = context.user_data.pop("attente_parametre", None)
        definition = PARAMETRES_SAISIE.get(champ, {"nom": "Paramètre"})

        try:
            appliquer_parametre_utilisateur(update.effective_chat.id, champ, texte)
        except (TypeError, ValueError):
            await update.message.reply_text(
                f"❌ Valeur invalide pour {definition['nom']}.\n"
                f"{definition.get('invite', '')}",
                reply_markup=clavier_parametres()
            )
            return

        await update.message.reply_text(
            f"✅ {definition['nom']} mis à jour.\n\n"
            + formater_parametres_utilisateur(update.effective_chat.id),
            reply_markup=clavier_parametres()
        )
        return

    if context.user_data.get("attente_stats_modele"):
        context.user_data.pop("attente_stats_modele", None)
        stats = stats_modele(update.effective_chat.id, texte)
        await update.message.reply_text(
            formater_stats_modele(stats),
            reply_markup=clavier_tableau_de_bord()
        )
        return

    if context.user_data.get("attente_scan_europe"):
        context.user_data.pop("attente_scan_europe", None)
        await update.message.reply_text("🌍 Scan Europe en cours...")
        resultat = rechercher_partout(texte)
        reponse = formater_resultat_europe(resultat)

        for message in decouper_messages([reponse], limite=3900):
            await update.message.reply_text(message, reply_markup=clavier_scanner_business())
        return

    if context.user_data.get("attente_scan_marketplace"):
        context.user_data.pop("attente_scan_marketplace", None)
        await update.message.reply_text("🛒 Scan Facebook Marketplace en cours...")
        annonces = rechercher_marketplace(texte)
        logger.info(
            "Marketplace bouton apres recherche: modele=%s len=%s type=%s",
            texte,
            len(annonces) if annonces is not None else None,
            type(annonces).__name__,
        )
        logger.info(
            "Marketplace bouton avant formatage: modele=%s len=%s",
            texte,
            len(annonces) if annonces is not None else None,
        )
        reponse = formater_resultat_marketplace(texte, annonces)

        messages = decouper_messages([reponse], limite=3900)
        logger.info(
            "Marketplace bouton decoupage Telegram: messages=%s longueurs=%s",
            len(messages),
            [len(message) for message in messages],
        )

        for message in messages:
            await update.message.reply_text(message, reply_markup=clavier_scanner_business())
        return

    if context.user_data.get("attente_analyse_lien"):
        context.user_data.pop("attente_analyse_lien", None)
        await update.message.reply_text("🔎 Analyse de l'annonce en cours...")

        try:
            resultat_analyse = analyser_annonce_par_lien_detail(texte)
            resultat = resultat_analyse["texte"]
            context.user_data["derniere_analyse_annonce"] = resultat_analyse
        except ValueError as erreur:
            resultat = f"❌ {erreur}"
        except RuntimeError as erreur:
            resultat = f"❌ Impossible de récupérer l'annonce.\n{erreur}"
        except Exception as erreur:
            logger.exception("Erreur pendant l'analyse par bouton")
            resultat = (
                "❌ Impossible d'analyser cette annonce. "
                f"Détail : {erreur}"
            )

        messages = decouper_messages([resultat], limite=3900)

        for index, message in enumerate(messages):
            kwargs = {}

            if index == len(messages) - 1 and "resultat_analyse" in locals():
                est_favori = obtenir_favori(
                    update.effective_chat.id,
                    resultat_analyse["voiture"]["lien"]
                )
                kwargs["reply_markup"] = clavier_analyse_annonce(bool(est_favori))

            await update.message.reply_text(message, **kwargs)
        return

    if texte == "🏠 Accueil":
        await update.message.reply_text(texte_accueil(), reply_markup=clavier_principal())
    elif texte == "🔗 Analyser une annonce":
        context.user_data["attente_analyse_lien"] = True
        await update.message.reply_text(
            "🔗 Colle le lien AutoScout24 ou 2ememain à analyser.",
            reply_markup=clavier_retour_accueil()
        )
    elif texte == "🔥 Scanner Business":
        await update.message.reply_text(texte_scanner_business(), reply_markup=clavier_scanner_business())
    elif texte == "🌍 Scanner Europe":
        await update.message.reply_text(texte_scanner_europe(), reply_markup=clavier_scanner_europe())
    elif texte == "🛒 Facebook Marketplace":
        await update.message.reply_text(texte_marketplace(), reply_markup=clavier_marketplace())
    elif texte == "⭐ Opportunités":
        await update.message.reply_text(texte_opportunites(), reply_markup=clavier_opportunites())
    elif texte == "❤️ Favoris":
        await update.message.reply_text(texte_favoris(), reply_markup=clavier_favoris())
    elif texte == "📊 Tableau de bord":
        await update.message.reply_text(generer_tableau_de_bord(update.effective_chat.id), reply_markup=clavier_tableau_de_bord())
    elif texte == "⚙️ Paramètres":
        await update.message.reply_text(formater_parametres_utilisateur(update.effective_chat.id), reply_markup=clavier_parametres())
    elif texte == "ℹ️ Aide":
        await update.message.reply_text(texte_aide(), reply_markup=clavier_aide())


def chat_ids_notifications_marketplace():
    chat_ids = set(lister_chat_ids_surveillance())

    for scanner in lister_scanners_globaux_actifs():
        chat_ids.add(scanner["chat_id"])

    return sorted(chat_ids)


async def verifier_sante_marketplace(context: ContextTypes.DEFAULT_TYPE):
    tester_sante()
    chat_ids = chat_ids_notifications_marketplace()

    if panne_a_notifier():
        for chat_id in chat_ids:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "⚠️ Facebook Marketplace est temporairement indisponible.\n"
                    "Les autres plateformes restent actives."
                )
            )

        marquer_notification_panne_envoyee()

    if retour_a_notifier():
        for chat_id in chat_ids:
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Facebook Marketplace est de nouveau disponible."
            )

        marquer_notification_retour_envoyee()


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
    job_queue.run_repeating(
        scan_global_business,
        interval=INTERVALLE_SCAN_GLOBAL_SECONDES,
        first=INTERVALLE_SCAN_GLOBAL_SECONDES
    )
    job_queue.run_repeating(
        verifier_favoris_job,
        interval=INTERVALLE_VERIFICATION_FAVORIS_SECONDES,
        first=INTERVALLE_VERIFICATION_FAVORIS_SECONDES
    )
    job_queue.run_repeating(
        verifier_sante_marketplace,
        interval=3600,
        first=3600
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
    app.add_handler(CommandHandler("europe", europe))
    app.add_handler(CommandHandler("marketplace", marketplace))
    app.add_handler(CommandHandler("surveille", surveille))
    app.add_handler(CommandHandler("surveillances", surveillances))
    app.add_handler(CommandHandler("stop_surveillance", stop_surveillance))
    app.add_handler(CommandHandler("business", business))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("stats_modele", stats_modele_commande))
    app.add_handler(CommandHandler("modifier_budget", modifier_budget_commande))
    app.add_handler(CommandHandler("voir_budget", voir_budget_commande))
    app.add_handler(CommandHandler("modifier_km", modifier_km_commande))
    app.add_handler(CommandHandler("voir_km", voir_km_commande))
    app.add_handler(CommandHandler("modifier_annee", modifier_annee_commande))
    app.add_handler(CommandHandler("voir_annee", voir_annee_commande))
    app.add_handler(CommandHandler("mes_alertes", mes_alertes_commande))
    app.add_handler(CommandHandler("supprimer_alerte", supprimer_alerte_commande))
    app.add_handler(CommandHandler(
        "supprimer_toutes_les_alertes",
        supprimer_toutes_alertes_commande
    ))
    app.add_handler(CommandHandler("mes_parametres", mes_parametres_commande))
    app.add_handler(CommandHandler("analyser", analyser))
    app.add_handler(CommandHandler("historique", historique))
    app.add_handler(CommandHandler("scanner_global", scanner_global))
    app.add_handler(CommandHandler("stop_scanner_global", stop_scanner_global))
    app.add_handler(CommandHandler(
        "statut_scanner_global",
        statut_scanner_global_commande
    ))
    app.add_handler(CallbackQueryHandler(interface_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gerer_reply_keyboard))
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
