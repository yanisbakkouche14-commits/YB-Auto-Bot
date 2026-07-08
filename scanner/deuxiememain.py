import requests
from bs4 import BeautifulSoup


def rechercher_voitures(modele):

    url = f"https://www.2ememain.be/l/auto-s/q/{modele}/"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    voitures = []

    try:

        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        annonces = soup.find_all("li")

        for annonce in annonces[:30]:

            texte = annonce.get_text(" ", strip=True)

            if modele.lower() not in texte.lower():
                continue

            prix = "Inconnu"

            for mot in texte.split():

                mot = mot.replace(".", "").replace(",", "")

                if mot.isdigit() and int(mot) > 500:
                    prix = mot + " €"
                    break

            lien = ""

            a = annonce.find("a")

            if a and a.get("href"):

                href = a["href"]

                if href.startswith("/"):
                    lien = "https://www.2ememain.be" + href
                else:
                    lien = href

            voitures.append({
                "modele": texte[:120],
                "prix": prix,
                "ville": "Belgique",
                "annee": "Inconnue",
                "kilometrage": "Inconnu",
                "carburant": "Inconnu",
                "boite": "Inconnue",
                "lien": lien,
                "source": "2ememain"
            })

    except Exception as e:
        print(e)

    return voitures