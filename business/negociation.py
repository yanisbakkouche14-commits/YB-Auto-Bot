import re


MOTS_CLES_NEGOCIATION = (
    "urgent",
    "a debattre",
    "à débattre",
    "prix a discuter",
    "prix à discuter",
    "depart",
    "départ",
    "besoin d'argent",
    "besoin d’argent",
    "premier arrive",
    "premier arrivé",
)

MOTS_CLES_DEFAUTS = (
    "defaut",
    "défaut",
    "reparation",
    "réparation",
    "a prevoir",
    "à prévoir",
    "griffe",
    "rayure",
    "bosse",
    "voyant",
    "embrayage",
    "distribution",
)


def _nombre(valeur):
    if valeur is None:
        return None

    if isinstance(valeur, (int, float)):
        return float(valeur)

    chiffres = re.sub(r"[^\d]", "", str(valeur))
    return float(chiffres) if chiffres else None


def _texte_annonce(voiture):
    return " ".join(
        str(voiture.get(cle) or "")
        for cle in ("titre", "modele", "description")
    ).lower()


def _verdict(score):
    if score >= 80:
        return "Négociation très favorable"
    if score >= 60:
        return "Négociation favorable"
    if score >= 40:
        return "Marge limitée"
    return "Peu de marge de négociation"


def _historique_valeur(historique, cle, defaut=0):
    if not historique:
        return defaut

    if isinstance(historique, dict):
        return historique.get(cle, defaut) or defaut

    return defaut


def _arguments_base(
    ecart_marche,
    benefice,
    jours,
    nombre_baisses,
    baisse_totale,
    score_vendeur,
    kilometrage,
    mots_cles,
    defauts,
):
    arguments = []

    if jours >= 21:
        arguments.append("Annonce en ligne depuis longtemps")
    elif jours >= 8:
        arguments.append("Annonce déjà visible depuis plusieurs jours")

    if nombre_baisses >= 2:
        arguments.append("Plusieurs baisses de prix détectées")
    elif nombre_baisses == 1:
        arguments.append("Une baisse de prix détectée")

    if baisse_totale >= 1000:
        arguments.append("Baisse totale significative")

    if ecart_marche > 0:
        arguments.append("Prix supérieur au marché estimé")

    if benefice < 2500:
        arguments.append("Marge limitée au prix affiché")

    if score_vendeur >= 70:
        arguments.append("Vendeur probablement pressé")

    if kilometrage and kilometrage >= 150000:
        arguments.append("Kilométrage élevé exploitable en négociation")

    if mots_cles:
        arguments.append("Mots-clés favorables détectés dans l'annonce")

    if defauts:
        arguments.append("Défauts ou réparations annoncés")

    if not arguments:
        arguments.append("Données limitées : estimation prudente")

    return arguments


def _borner(valeur, minimum=0, maximum=100):
    return max(minimum, min(maximum, valeur))


def _prix_coherents(prix_affiche, score, pression):
    remise_max = 0.04 + (score / 100) * 0.12 + (pression / 100) * 0.04
    remise_cible = remise_max * 0.65
    remise_depart = min(remise_max * 1.15, 0.22)

    prix_maximum = round(prix_affiche * (1 - remise_cible / 2), -2)
    prix_conseille = round(prix_affiche * (1 - remise_cible), -2)
    offre_depart = round(prix_affiche * (1 - remise_depart), -2)

    prix_maximum = int(max(0, min(prix_maximum, prix_affiche)))
    prix_conseille = int(max(0, min(prix_conseille, prix_maximum)))
    offre_depart = int(max(0, min(offre_depart, prix_conseille)))

    return offre_depart, prix_conseille, prix_maximum


def calculer_negociation(voiture, analyse, historique=None, score_vendeur=None):
    prix_affiche = _nombre(voiture.get("prix"))
    prix_marche = _nombre(
        analyse.get("prix_marche")
        or analyse.get("estimation")
    )
    benefice = _nombre(analyse.get("benefice")) or 0
    kilometrage = _nombre(voiture.get("kilometrage"))
    score_vendeur = _nombre(score_vendeur)

    if score_vendeur is None:
        score_vendeur = _historique_valeur(historique, "score", 0)

    nombre_baisses = int(_historique_valeur(historique, "nombre_baisses", 0))
    baisse_totale = _nombre(_historique_valeur(historique, "baisse_totale", 0)) or 0
    jours = int(_historique_valeur(historique, "jours_depuis_detection", 0))
    texte = _texte_annonce(voiture)
    mots_cles = any(mot in texte for mot in MOTS_CLES_NEGOCIATION)
    defauts = any(mot in texte for mot in MOTS_CLES_DEFAUTS)
    confiance = "moyenne"

    if not prix_affiche:
        return {
            "score_negociation": 0,
            "offre_depart": 0,
            "prix_conseille": 0,
            "prix_maximum": 0,
            "probabilite_acceptation": 0,
            "arguments": ["Prix affiché indisponible : estimation impossible"],
            "verdict": "Peu de marge de négociation",
            "confiance": "faible",
        }

    ecart_marche = 0
    if prix_marche:
        ecart_marche = (prix_affiche - prix_marche) / prix_marche
    else:
        confiance = "faible"

    score = 0
    score += _borner(ecart_marche * 100, 0, 25)
    score += _borner((benefice / 5000) * 15, 0, 15)
    score += min(nombre_baisses * 5, 10)
    score += _borner((baisse_totale / max(prix_affiche, 1)) * 100, 0, 10)
    score += _borner(score_vendeur * 0.15, 0, 15)

    if jours >= 30:
        score += 10
    elif jours >= 14:
        score += 7
    elif jours >= 7:
        score += 4

    if kilometrage and kilometrage >= 180000:
        score += 5
    elif kilometrage and kilometrage >= 120000:
        score += 3

    if mots_cles:
        score += 5

    if defauts:
        score += 5

    score = int(round(_borner(score, 0, 100)))
    pression = max(score_vendeur, score)
    offre_depart, prix_conseille, prix_maximum = _prix_coherents(
        prix_affiche,
        score,
        pression
    )
    probabilite = int(round(_borner(35 + score * 0.55 + score_vendeur * 0.2, 0, 95)))

    arguments = _arguments_base(
        ecart_marche,
        benefice,
        jours,
        nombre_baisses,
        baisse_totale,
        score_vendeur,
        kilometrage,
        mots_cles,
        defauts,
    )

    return {
        "score_negociation": score,
        "offre_depart": offre_depart,
        "prix_conseille": prix_conseille,
        "prix_maximum": prix_maximum,
        "probabilite_acceptation": probabilite,
        "arguments": arguments,
        "verdict": _verdict(score),
        "confiance": confiance,
    }
