import re
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.leparking.be"
MAX_ANNONCES = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/137.0 Safari/537.36"
    )
}


def _construire_url(modele):
    return f"{BASE_URL}/voiture-occasion/{quote_plus(modele)}.html"


def _nombre(texte):
    valeur = re.sub(r"\D", "", texte or "")
    return int(valeur) if valeur else "Inconnu"


def _prix(texte):
    match = re.search(
        r"(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6})\s*(?:€|eur|â‚¬)|(?:€|eur|â‚¬)\s*(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6})",
        texte or "",
        re.IGNORECASE
    )

    if not match:
        candidats = re.findall(
            r"(?<!\d)(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6})(?!\d)",
            re.sub(r"\b(19|20)\d{2}\b", "", texte or "")
        )

        for candidat in candidats:
            prix = _nombre(candidat)

            if isinstance(prix, int) and prix >= 500:
                return prix

        return "Inconnu"

    return _nombre(match.group(1) or match.group(2))


def _annee(texte):
    match = re.search(r"\b(19|20)\d{2}\b", texte or "")
    return match.group(0) if match else "Inconnu"


def _kilometrage(texte):
    matchs = re.findall(
        r"(?<!\d)(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6})\s*km",
        texte or "",
        re.IGNORECASE
    )
    return _nombre(matchs[-1]) if matchs else "Inconnu"


def _pays(texte):
    texte = (texte or "").lower()

    if "allemagne" in texte or "germany" in texte or "deutschland" in texte:
        return "Allemagne"

    if "belgique" in texte or "belgium" in texte:
        return "Belgique"

    if "france" in texte:
        return "France"

    return "Europe"


def _cartes(soup):
    selecteurs = (
        ".resultat",
        ".annonce",
        ".listing-item",
        "article",
        "a[href*='voiture-occasion']",
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
        raise RuntimeError(f"LeParking timeout: {erreur}") from erreur
    except requests.exceptions.RequestException as erreur:
        raise RuntimeError(f"LeParking inaccessible: {erreur}") from erreur

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

        titre_element = carte.select_one("h2, h3, .title, [class*='title']")
        titre = titre_element.get_text(" ", strip=True) if titre_element else texte[:90]
        pays = _pays(texte)

        annonces.append({
            "source": "LeParking",
            "pays": pays,
            "modele": titre or modele,
            "titre": titre or modele,
            "prix": _prix(texte),
            "kilometrage": _kilometrage(texte),
            "annee": _annee(texte),
            "ville": pays,
            "localisation": pays,
            "lien": lien,
        })

        if len(annonces) >= limite:
            break

    return annonces
