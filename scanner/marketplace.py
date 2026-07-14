import logging
import os
import re
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.facebook.com"
SEARCH_URL = f"{BASE_URL}/marketplace/search/"
MAX_ANNONCES = 20
TIMEOUT = 10

logger = logging.getLogger(__name__)
_DESACTIVE = False

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/137.0 Safari/537.36"
    ),
    "Accept-Language": "fr-BE,fr;q=0.9,en;q=0.8",
}


def _session():
    session = requests.Session()
    session.headers.update(HEADERS)
    cookie = os.getenv("FACEBOOK_COOKIE")

    if cookie:
        session.headers.update({"Cookie": cookie})

    return session


def _construire_url(modele):
    return f"{SEARCH_URL}?query={quote_plus(modele)}&exact=false"


def _nombre(texte):
    valeur = re.sub(r"\D", "", texte or "")
    return int(valeur) if valeur else "Inconnu"


def _prix(texte):
    match = re.search(
        r"(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{3,6})\s*(?:€|eur|â‚¬)|"
        r"(?:€|eur|â‚¬)\s*(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{3,6})",
        texte or "",
        re.IGNORECASE
    )

    if not match:
        candidats = re.findall(
            r"(?<!\d)(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{3,6})(?!\d)",
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


def _ville(texte):
    villes = (
        "Bruxelles",
        "Charleroi",
        "Liège",
        "Liege",
        "Li?ge",
        "Namur",
        "Mons",
        "Anvers",
        "Antwerpen",
        "Gand",
        "Gent",
    )

    for ville in villes:
        if ville.lower() in (texte or "").lower():
            return "Liège" if ville == "Liege" else ville

    return "Belgique"


def _cartes(soup):
    selecteurs = (
        "a[href*='/marketplace/item/']",
        "[role='article']",
        "div[data-testid*='marketplace']",
    )
    cartes = []

    for selecteur in selecteurs:
        for element in soup.select(selecteur):
            if element not in cartes:
                cartes.append(element)

    return cartes


def _titre(carte, texte, modele):
    for selecteur in ("span[dir='auto']", "h2", "h3"):
        element = carte.select_one(selecteur)

        if element:
            titre = element.get_text(" ", strip=True)

            if titre and "€" not in titre:
                return titre[:120]

    lignes = [ligne.strip() for ligne in re.split(r"\s{2,}|\n|\r", texte) if ligne.strip()]

    for ligne in lignes:
        if "€" not in ligne and len(ligne) > 4:
            return ligne[:120]

    return modele


def rechercher_voitures(modele):
    global _DESACTIVE

    if _DESACTIVE:
        logger.warning("Facebook Marketplace desactive pour cette session.")
        return []

    url = _construire_url(modele)

    try:
        reponse = _session().get(url, timeout=TIMEOUT)
        reponse.raise_for_status()
    except requests.exceptions.Timeout as erreur:
        logger.warning("Facebook Marketplace timeout: %s", erreur)
        _DESACTIVE = True
        return []
    except requests.exceptions.RequestException as erreur:
        logger.warning("Facebook Marketplace inaccessible: %s", erreur)
        _DESACTIVE = True
        return []

    soup = BeautifulSoup(reponse.text, "html.parser")
    annonces = []
    liens_vus = set()

    for carte in _cartes(soup):
        lien_element = carte if carte.name == "a" else carte.select_one("a[href*='/marketplace/item/']")
        lien = urljoin(BASE_URL, lien_element.get("href")) if lien_element else ""
        texte = carte.get_text(" ", strip=True)

        if not lien or len(texte) < 8 or lien in liens_vus:
            continue

        liens_vus.add(lien)
        titre = _titre(carte, texte, modele)

        annonces.append({
            "source": "Facebook Marketplace",
            "pays": "Belgique",
            "modele": titre,
            "titre": titre,
            "prix": _prix(texte),
            "kilometrage": _kilometrage(texte),
            "annee": _annee(texte),
            "ville": _ville(texte),
            "localisation": _ville(texte),
            "lien": lien,
        })

        if len(annonces) >= MAX_ANNONCES:
            break

    return annonces
