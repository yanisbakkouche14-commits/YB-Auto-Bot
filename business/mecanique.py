import json
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parent / "data" / "mecanique.json"


def _charger_donnees():
    try:
        with DATA_PATH.open("r", encoding="utf-8") as fichier:
            return json.load(fichier)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"modeles": []}


def _normaliser(valeur):
    if valeur is None:
        return ""

    return str(valeur).lower().replace("é", "e").replace("è", "e").strip()


def _valeur_sourcee(champ, defaut=None):
    if isinstance(champ, dict) and "valeur" in champ:
        return champ.get("valeur", defaut)

    return champ if champ not in (None, "", [], {}) else defaut


def _texte_voiture(modele=None, generation=None, moteur=None, boite=None):
    morceaux = [modele, generation, moteur, boite]
    return " ".join(_normaliser(morceau) for morceau in morceaux if morceau)


def _correspondance(fiche, texte, generation=None):
    candidats = [
        fiche.get("id"),
        fiche.get("generation"),
        *fiche.get("alias", []),
    ]
    candidats = [_normaliser(candidat) for candidat in candidats if candidat]

    if generation:
        generation_normalisee = _normaliser(generation)
        if generation_normalisee and generation_normalisee in _normaliser(fiche.get("generation")):
            return True

    return any(candidat and candidat in texte for candidat in candidats)


def trouver_fiche_mecanique(modele, generation=None, moteur=None, boite=None):
    donnees = _charger_donnees()
    texte = _texte_voiture(modele, generation, moteur, boite)
    fiches = donnees.get("modeles", [])

    for fiche in fiches:
        if _correspondance(fiche, texte, generation):
            return fiche

    return None


def estimer_reparations(fiche=None, niveau="moyen"):
    if not fiche:
        return None

    couts = fiche.get("cout_estime") or {}
    cout = couts.get(niveau)

    if cout is None and niveau != "moyen":
        cout = couts.get("moyen")

    return cout


def calculer_marge_nette(benefice_estime, cout_reparation_moyen):
    try:
        benefice = int(benefice_estime)
    except (TypeError, ValueError):
        return None

    try:
        cout = int(cout_reparation_moyen)
    except (TypeError, ValueError):
        return None

    return benefice - max(cout, 0)


def _score_cout(cout):
    if cout is None:
        return None

    if cout <= 500:
        return 2
    if cout <= 1500:
        return 1.4
    if cout <= 3000:
        return 0.7

    return 0


def _score_age(annee):
    try:
        annee = int(annee)
    except (TypeError, ValueError):
        return None

    if annee >= 2020:
        return 1
    if annee >= 2016:
        return 0.7
    if annee >= 2012:
        return 0.4

    return 0.1


def _score_pannes(pannes):
    if not pannes:
        return None

    nombre = len(pannes)

    if nombre <= 2:
        return 0.7
    if nombre <= 5:
        return 0.3

    return 0


def _score_mecanique(fiche, cout_moyen, annee=None):
    if not fiche:
        return 5

    points = []
    maximum = 0
    fiabilite = _valeur_sourcee(fiche.get("score_fiabilite"))
    pieces = _valeur_sourcee(fiche.get("disponibilite_pieces"))

    if fiabilite is not None:
        points.append((max(0, min(float(fiabilite), 10)) / 10) * 4)
        maximum += 4

    score_cout = _score_cout(cout_moyen)
    if score_cout is not None:
        points.append(score_cout)
        maximum += 2

    if pieces is not None:
        points.append((max(0, min(float(pieces), 10)) / 10) * 2)
        maximum += 2

    score_pannes = _score_pannes(fiche.get("pannes_frequentes"))
    if score_pannes is not None:
        points.append(score_pannes)
        maximum += 1

    score_age = _score_age(annee)
    if score_age is not None:
        points.append(score_age)
        maximum += 1

    if not points or maximum <= 1:
        return 5

    return round(max(0, min((sum(points) / maximum) * 10, 10)), 1)


def _verdict_risque(score, risque_source):
    if risque_source and risque_source != "inconnu":
        return risque_source

    if score >= 7.5:
        return "faible"
    if score >= 5:
        return "moyen"

    return "eleve"


def analyser_mecanique(modele, generation=None, moteur=None, boite=None, annee=None, benefice_estime=None):
    fiche = trouver_fiche_mecanique(modele, generation, moteur, boite)
    cout_moyen = estimer_reparations(fiche, "moyen")
    score = _score_mecanique(fiche, cout_moyen, annee)
    marge_nette = calculer_marge_nette(benefice_estime, cout_moyen)

    if not fiche:
        return {
            "modele_reconnu": False,
            "generation": generation or "inconnu",
            "risque": "inconnu",
            "score_fiabilite": None,
            "score_mecanique": score,
            "cout_reparation_moyen": None,
            "marge_nette_estimee": marge_nette,
            "pannes_connues": [],
            "motorisations_recommandees": [],
            "motorisations_a_eviter": [],
            "boites_recommandees": [],
            "boites_a_risque": [],
            "disponibilite_pieces": None,
            "commentaire": "Donnees mecaniques insuffisantes pour ce modele.",
            "confiance": "faible",
            "source": [],
        }

    risque = _verdict_risque(score, fiche.get("niveau_risque"))

    return {
        "modele_reconnu": True,
        "generation": fiche.get("generation") or generation or "inconnu",
        "risque": risque,
        "score_fiabilite": _valeur_sourcee(fiche.get("score_fiabilite")),
        "score_mecanique": score,
        "cout_reparation_moyen": cout_moyen,
        "marge_nette_estimee": marge_nette,
        "pannes_connues": fiche.get("pannes_frequentes") or [],
        "motorisations_recommandees": fiche.get("motorisations_recommandees") or [],
        "motorisations_a_eviter": fiche.get("motorisations_a_eviter") or [],
        "boites_recommandees": fiche.get("boites_recommandees") or [],
        "boites_a_risque": fiche.get("boites_a_risque") or [],
        "disponibilite_pieces": _valeur_sourcee(fiche.get("disponibilite_pieces")),
        "commentaire": fiche.get("commentaire_metier") or "inconnu",
        "confiance": fiche.get("confiance") or "faible",
        "source": fiche.get("source") or [],
    }
