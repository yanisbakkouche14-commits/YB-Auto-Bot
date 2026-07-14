import json
import re
import unicodedata
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.autoscout24.be"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/137.0 Safari/537.36"
    )
}

MARQUES = {
    "abarth": "abarth",
    "alfa": "alfa-romeo",
    "alfa romeo": "alfa-romeo",
    "alpina": "alpina",
    "alpine": "alpine",
    "aston martin": "aston-martin",
    "audi": "audi",
    "bentley": "bentley",
    "bmw": "bmw",
    "byd": "byd",
    "cadillac": "cadillac",
    "chevrolet": "chevrolet",
    "chrysler": "chrysler",
    "citroen": "citroen",
    "citroën": "citroen",
    "cupra": "cupra",
    "dacia": "dacia",
    "dodge": "dodge",
    "ds": "ds-automobiles",
    "ds automobiles": "ds-automobiles",
    "ferrari": "ferrari",
    "fiat": "fiat",
    "ford": "ford",
    "honda": "honda",
    "hyundai": "hyundai",
    "jaguar": "jaguar",
    "jeep": "jeep",
    "kia": "kia",
    "lamborghini": "lamborghini",
    "lancia": "lancia",
    "land rover": "land-rover",
    "lexus": "lexus",
    "lotus": "lotus",
    "mazda": "mazda",
    "mclaren": "mclaren",
    "mercedes": "mercedes-benz",
    "mercedes benz": "mercedes-benz",
    "mercedes-benz": "mercedes-benz",
    "mg": "mg",
    "mini": "mini",
    "mitsubishi": "mitsubishi",
    "nissan": "nissan",
    "opel": "opel",
    "peugeot": "peugeot",
    "polestar": "polestar",
    "porsche": "porsche",
    "renault": "renault",
    "rolls royce": "rolls-royce",
    "rolls-royce": "rolls-royce",
    "seat": "seat",
    "skoda": "skoda",
    "smart": "smart",
    "subaru": "subaru",
    "suzuki": "suzuki",
    "tesla": "tesla",
    "toyota": "toyota",
    "volkswagen": "volkswagen",
    "vw": "volkswagen",
    "volvo": "volvo",
}

MOTS_MODELE_IGNORES = {
    "classe",
    "class",
    "serie",
    "series",
    "série",
    "klasse",
}


def _normaliser(texte):
    texte = unicodedata.normalize("NFKD", texte.lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


def _slugifier(texte):
    texte = _normaliser(texte)
    return re.sub(r"\s+", "-", texte).strip("-")


def _decouper_recherche(recherche):
    recherche_normalisee = _normaliser(recherche)

    for marque in sorted(MARQUES, key=len, reverse=True):
        if recherche_normalisee == marque:
            return MARQUES[marque], []

        prefixe = marque + " "

        if recherche_normalisee.startswith(prefixe):
            modele = recherche_normalisee[len(prefixe):].split()
            return MARQUES[marque], modele

    return None, recherche_normalisee.split()


def _variantes_modele(mots_modele):
    mots = [mot for mot in mots_modele if mot not in MOTS_MODELE_IGNORES]

    if not mots:
        return []

    variantes = []

    def ajouter(mots_variant):
        slug = _slugifier(" ".join(mots_variant))

        if slug and slug not in variantes:
            variantes.append(slug)

    ajouter(mots)

    mots_sans_suffixes = []

    for mot in mots:
        match = re.fullmatch(r"(\d+)[a-z]+", mot)
        mots_sans_suffixes.append(match.group(1) if match else mot)

    ajouter(mots_sans_suffixes)
    ajouter(mots[:1])

    return variantes


def _construire_urls(modele):
    marque, mots_modele = _decouper_recherche(modele)
    variantes = _variantes_modele(mots_modele)
    urls = []

    if marque:
        if variantes:
            urls.extend(
                f"{BASE_URL}/fr/lst/{marque}/{variante}"
                "?sort=standard&desc=0&ustate=N%2CU&atype=C&cy=B"
                for variante in variantes
            )
        else:
            urls.append(
                f"{BASE_URL}/fr/lst/{marque}"
                "?sort=standard&desc=0&ustate=N%2CU&atype=C&cy=B"
            )

    else:
        urls.append(
            f"{BASE_URL}/fr/lst"
            f"?sort=standard&desc=0&ustate=N%2CU&atype=C&cy=B&q={quote_plus(modele)}"
        )

        for variante in variantes:
            urls.extend(
                f"{BASE_URL}/fr/lst/{marque_autoscout}/{variante}"
                "?sort=standard&desc=0&ustate=N%2CU&atype=C&cy=B"
                for marque_autoscout in sorted(set(MARQUES.values()))
            )

    return urls


def _construire_url(modele):
    return _construire_urls(modele)[0]


def _mots_pertinents(recherche):
    _, mots_modele = _decouper_recherche(recherche)
    mots = [
        mot
        for mot in mots_modele
        if mot not in MOTS_MODELE_IGNORES
    ]

    if not mots:
        mots = _normaliser(recherche).split()

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
        re.search(rf"\b{re.escape(mot)}\b", titre_normalise)
        for mot in mots_courts
    )


def _extraire_kilometrage(kilometrage):
    if isinstance(kilometrage, dict):
        return kilometrage.get("value", "Inconnu")

    return kilometrage or "Inconnu"


def _extraire_annee(item):
    annee = item.get("vehicleModelDate")

    if annee:
        return annee

    return "Inconnu"


def _extraire_voitures(html, recherche):
    soup = BeautifulSoup(html, "html.parser")
    voitures = []

    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:

        if not script.string:
            continue

        try:
            data = json.loads(script.string)
        except (TypeError, json.JSONDecodeError):
            continue

        if "@graph" not in data:
            continue

        for obj in data["@graph"]:

            if obj.get("@type") != "SearchResultsPage":
                continue

            annonces = obj.get("mainEntity", {}).get("itemListElement", [])

            for annonce in annonces:

                item = annonce.get("item", {})
                offers = item.get("offers", {})

                nom = item.get("name", "")
                prix = offers.get("price", "Inconnu")

                if (
                    not nom
                    or not isinstance(prix, int)
                    or not _titre_correspond(recherche, nom)
                ):
                    continue

                seller = offers.get("seller", {})
                address = seller.get("address", {})

                ville = address.get("addressLocality", "Belgique")
                lien_annonce = offers.get("url", "")

                if lien_annonce.startswith("http"):
                    lien = lien_annonce
                else:
                    lien = BASE_URL + lien_annonce

                voitures.append({
                    "modele": nom,
                    "prix": prix,
                    "ville": ville,
                    "source": "AutoScout24",
                    "annee": _extraire_annee(item),
                    "kilometrage": _extraire_kilometrage(
                        item.get("mileageFromOdometer")
                    ),
                    "carburant": item.get("fuelType", "Inconnu"),
                    "boite": item.get("vehicleTransmission", "Inconnue"),
                    "lien": lien
                })

    return voitures


def _liste_json_ld(soup):
    objets = []

    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue

        try:
            data = json.loads(script.string)
        except (TypeError, json.JSONDecodeError):
            continue

        if isinstance(data, list):
            objets.extend(data)
        else:
            objets.append(data)

    return objets


def _aplatir_json_ld(objet):
    if isinstance(objet, dict):
        yield objet

        for valeur in objet.values():
            yield from _aplatir_json_ld(valeur)
    elif isinstance(objet, list):
        for item in objet:
            yield from _aplatir_json_ld(item)


def _premiere_valeur(*valeurs, defaut="Inconnu"):
    for valeur in valeurs:
        if valeur not in (None, "", [], {}):
            return valeur

    return defaut


def _extraire_prix_offre(offers):
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    if not isinstance(offers, dict):
        return "Inconnu"

    prix = offers.get("price") or offers.get("priceSpecification", {}).get("price")

    if isinstance(prix, int):
        return prix

    chiffres = re.sub(r"\D", "", str(prix or ""))
    return int(chiffres) if chiffres else "Inconnu"


def _extraire_adresse(offers):
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    seller = offers.get("seller", {}) if isinstance(offers, dict) else {}
    address = seller.get("address", {}) if isinstance(seller, dict) else {}

    if isinstance(address, dict):
        return _premiere_valeur(
            address.get("addressLocality"),
            address.get("addressRegion"),
            defaut="Belgique"
        )

    return "Belgique"


def analyser_lien(lien):
    try:
        reponse = requests.get(lien, headers=HEADERS, timeout=15)
        reponse.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"AutoScout24 inaccessible: {e}") from e

    soup = BeautifulSoup(reponse.text, "html.parser")
    objets = list(_aplatir_json_ld(_liste_json_ld(soup)))
    vehicule = next(
        (
            obj for obj in objets
            if obj.get("@type") in {"Car", "Vehicle", "Product"}
        ),
        {}
    )

    offers = vehicule.get("offers", {}) if isinstance(vehicule, dict) else {}
    titre = _premiere_valeur(
        vehicule.get("name") if isinstance(vehicule, dict) else None,
        soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else None,
        soup.title.get_text(" ", strip=True) if soup.title else None
    )
    description = _premiere_valeur(
        vehicule.get("description") if isinstance(vehicule, dict) else None,
        soup.find("meta", attrs={"name": "description"}).get("content")
        if soup.find("meta", attrs={"name": "description"}) else None,
        defaut=""
    )
    marque = vehicule.get("brand", {}) if isinstance(vehicule, dict) else {}

    if isinstance(marque, dict):
        marque = marque.get("name")

    kilometrage = _extraire_kilometrage(
        vehicule.get("mileageFromOdometer") if isinstance(vehicule, dict) else None
    )
    annee = _extraire_annee(vehicule) if isinstance(vehicule, dict) else "Inconnu"

    return {
        "marque": _premiere_valeur(marque),
        "modele": _premiere_valeur(
            vehicule.get("model") if isinstance(vehicule, dict) else None,
            titre
        ),
        "annee": annee,
        "kilometrage": kilometrage,
        "carburant": _premiere_valeur(
            vehicule.get("fuelType") if isinstance(vehicule, dict) else None
        ),
        "boite": _premiere_valeur(
            vehicule.get("vehicleTransmission") if isinstance(vehicule, dict) else None,
            defaut="Inconnue"
        ),
        "prix": _extraire_prix_offre(offers),
        "titre": titre,
        "description": description,
        "ville": _extraire_adresse(offers),
        "localisation": _extraire_adresse(offers),
        "source": "AutoScout24",
        "lien": lien,
    }


def rechercher_voitures(modele):

    for url in _construire_urls(modele):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)

            if r.status_code == 404:
                continue

            r.raise_for_status()

            voitures = _extraire_voitures(r.text, modele)

            if voitures:
                return voitures

        except requests.exceptions.RequestException as e:
            print(f"Erreur AutoScout24: {e}")

    return []
