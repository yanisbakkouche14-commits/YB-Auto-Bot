def comparer_annonces(modele, annonces):
    """
    Compare plusieurs annonces similaires
    et calcule un prix moyen.

    Cette première version est simple.
    Elle sera améliorée par la suite.
    """

    prix = []

    for annonce in annonces:

        try:
            p = int(
                str(annonce["prix"])
                .replace("€", "")
                .replace(" ", "")
                .replace(".", "")
                .replace(",", "")
            )

            prix.append(p)

        except:
            continue

    if len(prix) == 0:
        return {
            "prix_moyen": 0,
            "prix_median": 0,
            "nombre_annonces": 0
        }

    prix.sort()

    moyenne = int(sum(prix) / len(prix))

    mediane = prix[len(prix)//2]

    return {
        "prix_moyen": moyenne,
        "prix_median": mediane,
        "nombre_annonces": len(prix)
    }