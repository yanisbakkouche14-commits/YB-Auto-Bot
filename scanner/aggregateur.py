import re
import unicodedata
from statistics import median

from scanner.autoscout import rechercher_voitures as rechercher_autoscout
from scanner.deuxiememain import rechercher_voitures as rechercher_deuxiememain
from scanner.gocar import rechercher_voitures as rechercher_gocar
from scanner.leparking import rechercher_voitures as rechercher_leparking
from scanner.mobilede import rechercher_voitures as rechercher_mobilede


PLATEFORMES = {
    "autoscout": rechercher_autoscout,
    "2ememain": rechercher_deuxiememain,
    "gocar": rechercher_gocar,
    "mobilede": rechercher_mobilede,
    "leparking": rechercher_leparking,
}


def _normaliser(valeur):
    texte = unicodedata.normalize("NFKD", str(valeur or "").lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


def _nombre(valeur):
    if isinstance(valeur, int):
        return valeur

    chiffres = re.sub(r"\D", "", str(valeur or ""))
    return int(chiffres) if chiffres else None


def _cle_forte(annonce):
    return {
        "titre": _normaliser(annonce.get("titre") or annonce.get("modele")),
        "prix": _nombre(annonce.get("prix")),
        "kilometrage": _nombre(annonce.get("kilometrage")),
        "annee": _normaliser(annonce.get("annee")),
        "ville": _normaliser(annonce.get("ville") or annonce.get("localisation")),
    }


def _doublon_fort(a, b):
    lien_a = a.get("lien")
    lien_b = b.get("lien")

    if lien_a and lien_b and lien_a == lien_b:
        return True

    cle_a = _cle_forte(a)
    cle_b = _cle_forte(b)
    champs_renseignes = [
        champ
        for champ in ("titre", "prix", "kilometrage", "annee", "ville")
        if cle_a[champ] not in (None, "") and cle_b[champ] not in (None, "")
    ]

    if lien_a and lien_b and lien_a != lien_b and len(champs_renseignes) < 5:
        return False

    correspondances = sum(1 for champ in champs_renseignes if cle_a[champ] == cle_b[champ])
    return len(champs_renseignes) >= 5 and correspondances == len(champs_renseignes)


def dedupliquer_annonces(liste):
    annonces_uniques = []
    doublons = 0

    for annonce in liste:
        if any(_doublon_fort(annonce, existante) for existante in annonces_uniques):
            doublons += 1
            continue

        annonces_uniques.append(annonce)

    return annonces_uniques, doublons


def statistiques_plateformes(resultats):
    plateformes = {
        nom: len(contenu.get("annonces", []))
        for nom, contenu in resultats.items()
    }
    erreurs = {
        nom: contenu.get("erreur")
        for nom, contenu in resultats.items()
        if contenu.get("erreur")
    }

    return {
        "total": sum(plateformes.values()),
        "plateformes": plateformes,
        "erreurs": erreurs,
    }


def _comparaison_pays(annonces):
    prix_belgique = [
        _nombre(annonce.get("prix"))
        for annonce in annonces
        if _normaliser(annonce.get("pays")) == "belgique"
    ]
    prix_allemagne = [
        _nombre(annonce.get("prix"))
        for annonce in annonces
        if _normaliser(annonce.get("pays")) == "allemagne"
    ]
    prix_belgique = [prix for prix in prix_belgique if prix]
    prix_allemagne = [prix for prix in prix_allemagne if prix]

    if not prix_belgique or not prix_allemagne:
        return {
            "belgique": None,
            "allemagne": None,
            "difference": None,
        }

    belgique = int(median(prix_belgique))
    allemagne = int(median(prix_allemagne))

    return {
        "belgique": belgique,
        "allemagne": allemagne,
        "difference": belgique - allemagne,
    }


def rechercher_partout(modele):
    resultats = {}
    annonces = []

    for nom, fonction in PLATEFORMES.items():
        try:
            annonces_plateforme = fonction(modele)[:20]
            resultats[nom] = {
                "annonces": annonces_plateforme,
                "erreur": None,
            }
            annonces.extend(annonces_plateforme)
        except Exception as erreur:
            resultats[nom] = {
                "annonces": [],
                "erreur": str(erreur),
            }

    annonces_uniques, doublons = dedupliquer_annonces(annonces)
    stats = statistiques_plateformes(resultats)

    return {
        "modele": modele,
        "annonces": annonces_uniques,
        "total": len(annonces_uniques),
        "total_brut": len(annonces),
        "doublons": doublons,
        "plateformes": stats["plateformes"],
        "erreurs": stats["erreurs"],
        "pays": sorted({
            annonce.get("pays", "Inconnu")
            for annonce in annonces_uniques
            if annonce.get("pays")
        }),
        "comparaison": _comparaison_pays(annonces_uniques),
        "resultats": resultats,
    }
