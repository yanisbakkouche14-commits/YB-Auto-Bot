import re
import unicodedata
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/137.0 Safari/537.36"
    )
}

MOTS_MODELE_IGNORES = {
    "classe",
    "class",
    "serie",
    "series",
    "série",
    "klasse",
}


def _construire_url(modele):
    return f"https://www.2ememain.be/l/autos/q/{quote_plus(modele)}/"


def _normaliser(texte):
    texte = unicodedata.normalize("NFKD", texte.lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


def _mots_pertinents(recherche):
    mots = [
        mot
        for mot in _normaliser(recherche).split()
        if mot not in MOTS_MODELE_IGNORES
    ]

    return mots


def _titre_correspond(recherche, titre):
    titre_normalise = _normaliser(titre)
    mots = _mots_pertinents(recherche)

    if not mots:
        return True

    mots_importants = [mot for mot in mots if len(mot) > 1 or mot.isdigit()]
    mots_courts = [mot for mot in mots if mot not in mots_importants]

    if mots_importants and not all(mot in titre_normalise for mot in mots_importants):
        return False

    return all(
        re.search(rf"\b{re.escape(mot)}", titre_normalise)
        for mot in mots_courts
    )


def _extraire_prix(texte):
    match = re.search(r"(?:€|â‚¬)\s*([\d\.\s]+)(?:,-)?", texte)

    if not match:
        return "Inconnu"

    prix = re.sub(r"\D", "", match.group(1))

    if not prix:
        return "Inconnu"

    return int(prix)


def _extraire_attributs(carte, titre):
    attributs = [
        element.get_text(" ", strip=True)
        for element in carte.select("span.hz-Attribute")
    ]

    annee = "Inconnu"
    kilometrage = "Inconnu"

    for attribut in attributs:
        if re.fullmatch(r"\d{4}", attribut):
            annee = attribut

        if "km" in attribut.lower():
            valeur = re.sub(r"\D", "", attribut)
            kilometrage = int(valeur) if valeur else "Inconnu"

    if annee == "Inconnu":
        match_annee = re.search(r"\b(19|20)\d{2}\b", titre)
        annee = match_annee.group(0) if match_annee else "Inconnu"

    if kilometrage == "Inconnu":
        match_km = re.search(r"(\d[\d\.\s]{2,})\s*km\b", titre, re.IGNORECASE)

        if match_km:
            valeur = re.sub(r"\D", "", match_km.group(1))
            kilometrage = int(valeur) if valeur else "Inconnu"

    return annee, kilometrage


def _premiere_valeur(*valeurs, defaut="Inconnu"):
    for valeur in valeurs:
        if valeur not in (None, "", [], {}):
            return valeur

    return defaut


def _extraire_meta(soup, nom):
    selecteurs = (
        {"property": nom},
        {"name": nom},
    )

    for attributs in selecteurs:
        element = soup.find("meta", attrs=attributs)

        if element and element.get("content"):
            return element["content"].strip()

    return None


def _extraire_prix_page(soup):
    for selecteur in (
        "[data-testid*='price']",
        ".Listing-price",
        ".hz-Listing-price",
    ):
        element = soup.select_one(selecteur)

        if element:
            prix = _extraire_prix(element.get_text(" ", strip=True))

            if isinstance(prix, int):
                return prix

    return _extraire_prix(soup.get_text(" ", strip=True))


def _extraire_attribut_texte(texte, libelles):
    bornes = (
        "Marque",
        "Carburant",
        "Fuel",
        "Boite",
        "BoÃ®te",
        "Transmission",
        "Localisation",
        "Ville",
        "KilomÃ©trage",
        "Kilometrage",
        "AnnÃ©e",
        "Annee",
    )

    for libelle in libelles:
        motif = (
            rf"{libelle}\s*[:\-]?\s*(.+?)"
            rf"(?=\s+(?:{'|'.join(bornes)})\s*[:\-]?|$)"
        )
        match = re.search(motif, texte, re.IGNORECASE)

        if match:
            valeur = match.group(1).strip()
            return re.split(r"\s{2,}|\n|\r", valeur)[0].strip()

    return "Inconnu"


def analyser_lien(lien):
    try:
        reponse = requests.get(lien, headers=HEADERS, timeout=15)
        reponse.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"2ememain inaccessible: {e}") from e

    soup = BeautifulSoup(reponse.text, "html.parser")
    titre = _premiere_valeur(
        _extraire_meta(soup, "og:title"),
        soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else None,
        soup.title.get_text(" ", strip=True) if soup.title else None
    )
    description = _premiere_valeur(
        _extraire_meta(soup, "og:description"),
        _extraire_meta(soup, "description"),
        defaut=""
    )
    texte = soup.get_text(" ", strip=True)
    annee, kilometrage = _extraire_attributs(soup, titre)

    return {
        "marque": _extraire_attribut_texte(texte, ("Marque",)),
        "modele": titre,
        "annee": annee,
        "kilometrage": kilometrage,
        "carburant": _extraire_attribut_texte(texte, ("Carburant", "Fuel")),
        "boite": _extraire_attribut_texte(
            texte,
            ("Boite", "BoÃ®te", "Transmission")
        ),
        "prix": _extraire_prix_page(soup),
        "titre": titre,
        "description": description,
        "ville": _premiere_valeur(
            _extraire_attribut_texte(texte, ("Localisation", "Ville")),
            defaut="Belgique"
        ),
        "localisation": _premiere_valeur(
            _extraire_attribut_texte(texte, ("Localisation", "Ville")),
            defaut="Belgique"
        ),
        "source": "2ememain",
        "lien": lien,
    }


def rechercher_voitures(modele):

    url = _construire_url(modele)
    voitures = []

    try:

        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        annonces = soup.select("li.hz-Listing.hz-Listing--list-item-cars")

        for annonce in annonces:

            titre_element = annonce.select_one(
                "span.ListingListViewContentCars_title__HRpz4"
            )

            lien_element = annonce.find("a", href=True)

            if not titre_element or not lien_element:
                continue

            titre = titre_element.get_text(" ", strip=True)
            lien = lien_element["href"]

            if (
                not titre
                or not lien.startswith("/v/autos/")
                or not _titre_correspond(modele, titre)
            ):
                continue

            texte = annonce.get_text(" ", strip=True)
            prix = _extraire_prix(texte)

            if not isinstance(prix, int):
                continue

            annee, kilometrage = _extraire_attributs(annonce, titre)

            voitures.append({
                "modele": titre,
                "prix": prix,
                "ville": "Belgique",
                "annee": annee,
                "kilometrage": kilometrage,
                "carburant": "Inconnu",
                "boite": "Inconnue",
                "lien": "https://www.2ememain.be" + lien,
                "source": "2ememain"
            })

    except requests.exceptions.RequestException as e:
        print(f"Erreur 2ememain: {e}")

    return voitures
