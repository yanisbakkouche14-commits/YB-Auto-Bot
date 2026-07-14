import os
import re
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://suchen.mobile.de"
MAX_ANNONCES = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/137.0 Safari/537.36"
    ),
    "Accept-Language": "fr-BE,fr;q=0.9,de;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Referer": f"{BASE_URL}/",
}


def _construire_url(modele):
    return (
        f"{BASE_URL}/fahrzeuge/search.html"
        f"?dam=false&isSearchRequest=true&ms=&ref=quickSearch&s=Car&vc=Car"
        f"&q={quote_plus(modele)}"
    )


def _session():
    session = requests.Session()
    session.headers.update(HEADERS)

    cookie = os.getenv("MOBILEDE_COOKIE")
    if cookie:
        session.headers.update({"Cookie": cookie})

    return session


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


def _ville(texte):
    match = re.search(r"\b\d{5}\s+([A-Za-zÄÖÜäöüß\-\s]+)", texte or "")
    return match.group(1).strip() if match else "Allemagne"


def _cartes(soup):
    selecteurs = (
        "[data-testid='result-listing']",
        "[data-testid*='listing']",
        "article",
        ".cBox",
        "a[href*='/fahrzeuge/details.html']",
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
        reponse = _session().get(url, timeout=15)

        if reponse.status_code == 403:
            raise RuntimeError("Mobile.de protégée: accès HTTP 403")

        reponse.raise_for_status()
    except requests.exceptions.Timeout as erreur:
        raise RuntimeError(f"Mobile.de timeout: {erreur}") from erreur
    except RuntimeError:
        raise
    except requests.exceptions.RequestException as erreur:
        raise RuntimeError(f"Mobile.de inaccessible: {erreur}") from erreur

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

        titre_element = carte.select_one("h2, h3, [data-testid*='title']")
        titre = titre_element.get_text(" ", strip=True) if titre_element else texte[:90]

        annonces.append({
            "source": "Mobile.de",
            "pays": "Allemagne",
            "modele": titre or modele,
            "titre": titre or modele,
            "prix": _prix(texte),
            "kilometrage": _kilometrage(texte),
            "annee": _annee(texte),
            "ville": _ville(texte),
            "localisation": _ville(texte),
            "lien": lien,
        })

        if len(annonces) >= limite:
            break

    return annonces
