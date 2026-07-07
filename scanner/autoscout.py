import requests
import json
from bs4 import BeautifulSoup


def rechercher_voitures(modele):

    modele_recherche = modele

    url = (
        "https://www.autoscout24.be/fr/lst"
        f"?sort=standard&desc=0&ustate=N%2CU&atype=C&cy=B&q={modele}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/137.0 Safari/537.36"
        )
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        voitures = []

        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:

            if not script.string:
                continue

            try:
                data = json.loads(script.string)
            except Exception:
                continue

            if "@graph" not in data:
                continue

            for obj in data["@graph"]:

                if obj.get("@type") != "SearchResultsPage":
                    continue

                annonces = obj.get("mainEntity", {}).get("itemListElement", [])

                for annonce in annonces:

                    item = annonce.get("item", {})

                    nom = item.get("name", "")

                    if modele_recherche.lower() not in nom.lower():
                        continue

                    offers = item.get("offers", {})

                    prix = offers.get("price", "Non indiqué")

                    seller = offers.get("seller", {})
                    address = seller.get("address", {})

                    ville = address.get("addressLocality", "Belgique")

                    lien = (
                        "https://www.autoscout24.be"
                        + offers.get("url", "")
                    )

                    kilometrage = item.get("mileageFromOdometer", {})

                    if isinstance(kilometrage, dict):
                        kilometrage = kilometrage.get("value", "Inconnu")

                    voitures.append({
                        "modele": nom,
                        "prix": f"{prix} €",
                        "ville": ville,
                        "annee": item.get("vehicleModelDate", "Inconnue"),
                        "kilometrage": kilometrage,
                        "carburant": item.get("fuelType", "Inconnu"),
                        "boite": item.get("vehicleTransmission", "Inconnue"),
                        "lien": lien
                    })

        return voitures

    except Exception as e:
        print(e)
        return []