from ai.estimation import (
    calculer_prix_marche,
    calculer_offre_depart,
    calculer_prix_conseille,
    calculer_prix_max,
    calculer_benefice,
    calculer_score
)


def analyser_annonce(voiture):

    try:
        prix = int(
            str(voiture["prix"])
            .replace("€", "")
            .replace(" ", "")
            .replace(".", "")
            .replace(",", "")
        )

    except:
        return {
            "score": 0,
            "benefice": 0,
            "prix_marche": "Inconnu",
            "conseil": "Impossible d'analyser",
            "offre_depart": 0,
            "prix_conseille": 0,
            "prix_max": 0
        }

    prix_marche = calculer_prix_marche(prix)

    benefice = calculer_benefice(
        prix,
        prix_marche
    )

    offre_depart = calculer_offre_depart(prix)

    prix_conseille = calculer_prix_conseille(prix)

    prix_max = calculer_prix_max(prix)

    score, conseil = calculer_score(
        benefice
    )

    return {
        "score": score,
        "benefice": benefice,
        "prix_marche": prix_marche,
        "conseil": conseil,
        "offre_depart": offre_depart,
        "prix_conseille": prix_conseille,
        "prix_max": prix_max
    }