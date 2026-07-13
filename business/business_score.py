import json
import math
import re
import unicodedata
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "data"

PONDERATIONS = {
    "score_ia": 25,
    "benefice": 20,
    "vendeur_presse": 10,
    "historique_prix": 8,
    "anciennete": 5,
    "budget": 5,
    "prix_marche": 7,
    "liquidite": 5,
    "risque": 5,
    "reparations": 3,
    "fiabilite": 3,
    "lez": 2,
    "popularite": 1,
    "pieces": 1,
}

DETAILS_AFFICHAGE = {
    "score_ia": ("Score IA", 30),
    "benefice": ("Bénéfice", 30),
    "liquidite": ("Liquidité", 10),
    "fiabilite": ("Fiabilité", 10),
    "lez": ("LEZ", 5),
    "popularite": ("Popularité", 10),
    "vendeur_presse": ("Vendeur pressé", 10),
    "reparations": ("Réparations", 5),
    "risque": ("Risque", 10),
}

_CACHE_DONNEES = None


def charger_donnees(data_dir=DATA_DIR):
    donnees = {}

    for chemin in sorted(Path(data_dir).glob("*.json")):
        nom = chemin.stem

        try:
            with chemin.open("r", encoding="utf-8") as fichier:
                donnees[nom] = json.load(fichier)
        except (OSError, json.JSONDecodeError):
            donnees[nom] = {}

    return donnees


def donnees_business():
    global _CACHE_DONNEES

    if _CACHE_DONNEES is None:
        _CACHE_DONNEES = charger_donnees()

    return _CACHE_DONNEES


def normaliser_texte(valeur):
    texte = str(valeur or "").lower().strip()
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(caractere for caractere in texte if not unicodedata.combining(caractere))
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


def identifiant_modele(voiture, donnees=None):
    donnees = donnees or donnees_business()
    candidats = [
        voiture.get("modele"),
        voiture.get("titre"),
        voiture.get("recherche"),
    ]

    alias_global = {}
    modeles_connus = set()

    for contenu in donnees.values():
        if not isinstance(contenu, dict):
            continue

        alias_global.update({
            normaliser_texte(alias): identifiant
            for alias, identifiant in contenu.get("alias", {}).items()
        })
        modeles_connus.update(contenu.get("modeles", {}).keys())

        for identifiant, fiche in contenu.get("modeles", {}).items():
            if not isinstance(fiche, dict):
                continue

            alias = (
                fiche.get("identite", {})
                .get("alias", {})
                .get("valeur", [])
            )

            for libelle in alias:
                alias_global[normaliser_texte(libelle)] = identifiant

    for candidat in candidats:
        texte = normaliser_texte(candidat)

        if not texte:
            continue

        if texte in alias_global:
            return alias_global[texte]

        identifiant = texte.replace(" ", "_")

        if identifiant in modeles_connus:
            return identifiant

        for alias, identifiant_alias in sorted(alias_global.items(), key=lambda item: len(item[0]), reverse=True):
            if alias and alias in texte:
                return identifiant_alias

    return normaliser_texte(candidats[0]).replace(" ", "_") or "modele_inconnu"


def valeur_modele(nom_critere, identifiant, donnees):
    contenu = donnees.get(nom_critere, {})

    if not isinstance(contenu, dict):
        return None, True

    modeles = contenu.get("modeles", {})

    if identifiant in modeles:
        return modeles[identifiant], False

    if "default" in contenu:
        return contenu["default"], True

    return None, True


def borner(valeur, minimum=0, maximum=100):
    return max(minimum, min(maximum, valeur))


def nombre(valeur):
    if valeur is None:
        return None

    if isinstance(valeur, (int, float)):
        return float(valeur)

    chiffres = re.sub(r"[^\d]", "", str(valeur))
    return float(chiffres) if chiffres else None


def sous_score_score_ia(analyse):
    return borner(float(analyse.get("score") or 0), 0, 100)


def sous_score_benefice(analyse):
    benefice = float(analyse.get("benefice") or 0)
    return borner((benefice / 5000) * 100, 0, 100)


def sous_score_vendeur(infos_vendeur):
    if not infos_vendeur:
        return None

    return borner(float(infos_vendeur.get("score") or 0), 0, 100)


def sous_score_historique(infos_vendeur):
    if not infos_vendeur:
        return None

    baisse_totale = float(infos_vendeur.get("baisse_totale") or 0)
    nombre_baisses = int(infos_vendeur.get("nombre_baisses") or 0)
    score_baisse = min(baisse_totale / 3000, 1) * 60
    score_frequence = min(nombre_baisses / 3, 1) * 40
    return borner(score_baisse + score_frequence, 0, 100)


def sous_score_anciennete(infos_vendeur):
    if not infos_vendeur:
        return None

    jours = int(infos_vendeur.get("jours_depuis_detection") or 0)

    if jours <= 2:
        return 80
    if jours <= 10:
        return 100
    if jours <= 25:
        return 70
    if jours <= 45:
        return 45

    return 25


def sous_score_budget(prix, prix_max):
    prix = nombre(prix)
    prix_max = nombre(prix_max)

    if prix is None or not prix_max:
        return None

    ratio = prix / prix_max

    if ratio <= 0.65:
        return 100
    if ratio <= 0.85:
        return 80
    if ratio <= 1:
        return 55

    return 0


def sous_score_prix_marche(prix, analyse):
    prix = nombre(prix)
    prix_marche = nombre(analyse.get("prix_marche") or analyse.get("estimation"))

    if prix is None or not prix_marche:
        return None

    ecart = (prix_marche - prix) / prix_marche

    if ecart >= 0.20:
        return 100
    if ecart >= 0.12:
        return 85
    if ecart >= 0.06:
        return 70
    if ecart >= 0:
        return 50

    return 20


def sous_score_risque(analyse):
    risques = analyse.get("risques") or []

    if isinstance(risques, str):
        risques = [risques] if risques else []

    score = 100 - min(len(risques) * 25, 100)
    return borner(score, 0, 100)


def sous_score_json(nom_critere, identifiant, donnees):
    valeur, manque = valeur_modele(nom_critere, identifiant, donnees)

    if valeur is None:
        return None, manque

    return borner(float(valeur) * 10, 0, 100), manque


def sous_score_pieces(donnees_json):
    reparations = donnees_json.get("reparations")
    popularite = donnees_json.get("popularite")

    if reparations is None and popularite is None:
        return None

    valeurs = [valeur for valeur in (reparations, popularite) if valeur is not None]
    return sum(valeurs) / len(valeurs)


def points_detail(sous_score, maximum):
    if sous_score is None:
        return None

    return int(round((sous_score / 100) * maximum))


def verdict(score):
    if score >= 90:
        return "★★★★★", "ACHETER IMMÉDIATEMENT"
    if score >= 75:
        return "★★★★☆", "Très bonne affaire"
    if score >= 60:
        return "★★★☆☆", "Bonne opportunité"
    if score >= 40:
        return "★★☆☆☆", "À surveiller"

    return "★☆☆☆☆", "À éviter"


def calculer_business_score(voiture, analyse, infos_vendeur=None, prix_max=None):
    donnees = donnees_business()
    identifiant = identifiant_modele(voiture, donnees)
    prix = voiture.get("prix")
    donnees_manquantes = []
    scores = {
        "score_ia": sous_score_score_ia(analyse),
        "benefice": sous_score_benefice(analyse),
        "vendeur_presse": sous_score_vendeur(infos_vendeur),
        "historique_prix": sous_score_historique(infos_vendeur),
        "anciennete": sous_score_anciennete(infos_vendeur),
        "budget": sous_score_budget(prix, prix_max),
        "prix_marche": sous_score_prix_marche(prix, analyse),
        "risque": sous_score_risque(analyse),
    }

    scores_json = {}

    for critere, contenu in donnees.items():
        if critere in {"index", "modeles"} or not isinstance(contenu, dict):
            continue

        if "modeles" not in contenu and "default" not in contenu:
            continue

        scores_json[critere], manque = sous_score_json(critere, identifiant, donnees)

        if manque:
            donnees_manquantes.append(critere)

    scores.update(scores_json)
    scores["pieces"] = sous_score_pieces(scores_json)

    total = 0
    poids_total = 0

    for critere, poids in PONDERATIONS.items():
        sous_score = scores.get(critere)

        if sous_score is None:
            donnees_manquantes.append(critere)
            continue

        total += sous_score * poids
        poids_total += poids

    score = int(round(total / poids_total)) if poids_total else 0
    score = int(borner(score, 0, 100))
    etoiles, libelle_verdict = verdict(score)

    details = {}

    for critere, (libelle, maximum) in DETAILS_AFFICHAGE.items():
        details[critere] = {
            "label": libelle,
            "points": points_detail(scores.get(critere), maximum),
            "max": maximum,
        }

    return {
        "score": score,
        "etoiles": etoiles,
        "verdict": libelle_verdict,
        "details": details,
        "scores": scores,
        "modele_id": identifiant,
        "donnees_manquantes": sorted(set(donnees_manquantes)),
    }


def formater_business_score(resultat):
    lignes = [
        "Business Score :",
        "",
        f"{resultat['score']}/100",
        "",
        f"{resultat['etoiles']}",
        resultat["verdict"],
        "",
    ]

    for cle in (
        "score_ia",
        "benefice",
        "liquidite",
        "fiabilite",
        "lez",
        "popularite",
        "vendeur_presse",
        "reparations",
        "risque",
    ):
        detail = resultat["details"][cle]
        points = detail["points"]
        valeur = "Inconnu" if points is None else str(points)
        lignes.append(f"{detail['label']} : {valeur}/{detail['max']}")

    return "\n".join(lignes)
