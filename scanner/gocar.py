import re
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.gocar.be"
MAX_ANNONCES = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/137.0 Safari/537.36"
    )
}


def _construire_url(modele):
    return f"{BASE_URL}/fr/voitures/search?keyword={quote_plus(modele)}"


def _extraire_nombre(texte):
    if not texte:
        return "Inconnu"

    valeur = re.sub(r"\D", "", texte)
    return int(valeur) if valeur else "Inconnu"


def _extraire_prix(texte):
    if not texte:
        return "Inconnu"

    match = re.search(
        r"(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6})\s*(?:€|eur|â‚¬)|(?:€|eur|â‚¬)\s*(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6})",
        texte,
        re.IGNORECASE
    )

    if not match:
        candidats = re.findall(
            r"(?<!\d)(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6})(?!\d)",
            re.sub(r"\b(19|20)\d{2}\b", "", texte)
        )

        for candidat in candidats:
            prix = _extraire_nombre(candidat)

            if isinstance(prix, int) and prix >= 500:
                return prix

        return "Inconnu"

    return _extraire_nombre(match.group(1) or match.group(2))


def _extraire_annee(texte):
    match = re.search(r"\b(19|20)\d{2}\b", texte or "")
    return match.group(0) if match else "Inconnu"


def _extraire_kilometrage(texte):
    matchs = re.findall(
        r"(?<!\d)(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6})\s*km",
        texte or "",
        re.IGNORECASE
    )

    if not matchs:
        return "Inconnu"

    return _extraire_nombre(matchs[-1])


def _cartes(soup):
    selecteurs = (
        "[data-testid*='car']",
        "article",
        ".vehicle-card",
        ".car-card",
        ".result-card",
        "a[href*='/fr/voitures/']",
    )
    cartes = []

    for selecteur in selecteurs:
        for element in soup.select(selecteur):
            if element not in cartes:
                cartes.append(element)

    return cartes


def rechercher_voitures(modele, limite=MAX_ANNONCES):
    url = _construire_url(modele)

    try:
        reponse = requests.get(url, headers=HEADERS, timeout=15)
        reponse.raise_for_status()
    except requests.exceptions.Timeout as erreur:
        raise RuntimeError(f"Gocar timeout: {erreur}") from erreur
    except requests.exceptions.RequestException as erreur:
        raise RuntimeError(f"Gocar inaccessible: {erreur}") from erreur

    soup = BeautifulSoup(reponse.text, "html.parser")
    annonces = []
    liens_vus = set()

    for carte in _cartes(soup):
        lien_element = carte if carte.name == "a" else carte.select_one("a[href]")
        lien = urljoin(BASE_URL, lien_element.get("href")) if lien_element else ""

        texte = carte.get_text(" ", strip=True)

        if not lien or len(texte) < 10:
            continue

        if lien in liens_vus:
            continue

        liens_vus.add(lien)

        titre_element = carte.select_one("h1, h2, h3, [class*='title']")
        titre = titre_element.get_text(" ", strip=True) if titre_element else texte[:90]
        prix = _extraire_prix(texte)

        if prix == "Inconnu" and not titre:
            continue

        annonces.append({
            "source": "Gocar",
            "pays": "Belgique",
            "modele": titre or modele,
            "titre": titre or modele,
            "prix": prix,
            "kilometrage": _extraire_kilometrage(texte),
            "annee": _extraire_annee(texte),
            "ville": "Belgique",
            "localisation": "Belgique",
            "lien": lien,
        })

        if len(annonces) >= limite:
            break

    return annonces
