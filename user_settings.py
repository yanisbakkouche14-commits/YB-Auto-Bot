import json
from pathlib import Path


CHEMIN_SETTINGS = Path(__file__).resolve().parent / "data" / "user_settings.json"

PARAMETRES_DEFAUT = {
    "budget_max": None,
    "km_max": None,
    "annee_min": None,
    "alertes": [],
}


def _charger_tous():
    if not CHEMIN_SETTINGS.exists():
        return {}

    try:
        with CHEMIN_SETTINGS.open("r", encoding="utf-8") as fichier:
            donnees = json.load(fichier)
    except (json.JSONDecodeError, OSError):
        return {}

    return donnees if isinstance(donnees, dict) else {}


def _sauvegarder_tous(donnees):
    CHEMIN_SETTINGS.parent.mkdir(parents=True, exist_ok=True)

    with CHEMIN_SETTINGS.open("w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2, sort_keys=True)


def _normaliser_parametres(parametres):
    normalises = PARAMETRES_DEFAUT.copy()

    if isinstance(parametres, dict):
        normalises.update({
            cle: parametres.get(cle, valeur)
            for cle, valeur in PARAMETRES_DEFAUT.items()
        })

    if not isinstance(normalises["alertes"], list):
        normalises["alertes"] = []

    return normalises


def obtenir_parametres(chat_id):
    donnees = _charger_tous()
    cle = str(chat_id)
    parametres = _normaliser_parametres(donnees.get(cle))

    if cle not in donnees:
        donnees[cle] = parametres
        _sauvegarder_tous(donnees)

    return parametres


def modifier_budget(chat_id, montant):
    return _modifier_entier(chat_id, "budget_max", montant)


def modifier_km(chat_id, valeur):
    return _modifier_entier(chat_id, "km_max", valeur)


def modifier_annee(chat_id, annee):
    return _modifier_entier(chat_id, "annee_min", annee)


def _modifier_entier(chat_id, champ, valeur):
    nombre = int(valeur)

    if nombre < 0:
        raise ValueError("La valeur doit être positive.")

    donnees = _charger_tous()
    cle = str(chat_id)
    parametres = _normaliser_parametres(donnees.get(cle))
    parametres[champ] = nombre
    donnees[cle] = parametres
    _sauvegarder_tous(donnees)
    return parametres


def ajouter_alerte(chat_id, texte):
    donnees = _charger_tous()
    cle = str(chat_id)
    parametres = _normaliser_parametres(donnees.get(cle))
    alertes = parametres["alertes"]
    nouvel_id = max([alerte.get("id", 0) for alerte in alertes] or [0]) + 1
    alerte = {"id": nouvel_id, "texte": str(texte).strip()}
    alertes.append(alerte)
    donnees[cle] = parametres
    _sauvegarder_tous(donnees)
    return alerte


def lister_alertes(chat_id):
    return obtenir_parametres(chat_id)["alertes"]


def supprimer_alerte(chat_id, alerte_id):
    donnees = _charger_tous()
    cle = str(chat_id)
    parametres = _normaliser_parametres(donnees.get(cle))
    avant = len(parametres["alertes"])
    parametres["alertes"] = [
        alerte
        for alerte in parametres["alertes"]
        if alerte.get("id") != int(alerte_id)
    ]
    donnees[cle] = parametres
    _sauvegarder_tous(donnees)
    return len(parametres["alertes"]) < avant


def supprimer_toutes_alertes(chat_id):
    donnees = _charger_tous()
    cle = str(chat_id)
    parametres = _normaliser_parametres(donnees.get(cle))
    total = len(parametres["alertes"])
    parametres["alertes"] = []
    donnees[cle] = parametres
    _sauvegarder_tous(donnees)
    return total
