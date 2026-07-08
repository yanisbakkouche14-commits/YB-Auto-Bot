def analyser_marche(voitures):

    prix = []

    for voiture in voitures:

        try:
            p = int(
                str(voiture["prix"])
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
            "moyenne": 0,
            "mediane": 0,
            "minimum": 0,
            "maximum": 0,
            "nombre": 0
        }

    prix.sort()

    moyenne = int(sum(prix) / len(prix))

    mediane = prix[len(prix)//2]

    return {
        "moyenne": moyenne,
        "mediane": mediane,
        "minimum": min(prix),
        "maximum": max(prix),
        "nombre": len(prix)
    }