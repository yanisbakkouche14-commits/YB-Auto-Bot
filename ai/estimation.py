def calculer_prix_marche(prix):
    """
    Estimation provisoire.
    Plus tard, cette fonction utilisera les annonces similaires.
    """
    return int(prix * 1.12)


def calculer_offre_depart(prix):
    """
    Première offre à faire au vendeur.
    """
    return int(prix * 0.90)


def calculer_prix_conseille(prix):
    """
    Prix conseillé si le vendeur négocie.
    """
    return int(prix * 0.94)


def calculer_prix_max(prix):
    """
    Prix maximum à ne jamais dépasser.
    """
    return int(prix * 0.97)


def calculer_benefice(prix, prix_marche):
    return prix_marche - prix


def calculer_score(benefice):

    if benefice >= 4000:
        return 95, "🔥 À acheter rapidement"

    if benefice >= 2500:
        return 85, "🟢 Très bonne affaire"

    if benefice >= 1000:
        return 70, "🟡 Bonne affaire"

    return 50, "⚪ Prix correct"