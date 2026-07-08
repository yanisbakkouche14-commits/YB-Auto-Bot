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

    # Estimation provisoire du marché
    prix_marche = int(prix * 1.12)

    benefice = prix_marche - prix

    # Calcul des prix de négociation
    offre_depart = int(prix * 0.90)
    prix_conseille = int(prix * 0.94)
    prix_max = int(prix * 0.97)

    score = 50
    conseil = "Prix correct"

    if benefice >= 1000:
        score = 70
        conseil = "Bonne affaire"

    if benefice >= 2500:
        score = 85
        conseil = "Très bonne affaire"

    if benefice >= 4000:
        score = 95
        conseil = "À acheter rapidement"

    return {
        "score": score,
        "benefice": benefice,
        "prix_marche": prix_marche,
        "conseil": conseil,
        "offre_depart": offre_depart,
        "prix_conseille": prix_conseille,
        "prix_max": prix_max
    }