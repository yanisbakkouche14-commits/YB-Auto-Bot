def formater_prix(prix):
    if isinstance(prix, int):
        return f"{prix} €"

    if isinstance(prix, float):
        return f"{round(prix)} €"

    return "Inconnu" if prix in (None, "") else str(prix)


def formater_dashboard(donnees):
    meilleure = donnees.get("meilleure_opportunite")

    if meilleure:
        texte_meilleure = (
            f"{meilleure['modele']} | "
            f"+{formater_prix(meilleure['benefice'])} | "
            f"{meilleure['score_business'] or 0}/100"
        )
    else:
        texte_meilleure = "Aucune opportunité enregistrée"

    return (
        "📊 TABLEAU DE BORD\n\n"
        "📈 Activité\n"
        f"- Annonces analysées : {donnees['annonces_total']}\n"
        f"- Nouvelles aujourd'hui : {donnees['nouvelles_aujourdhui']}\n"
        f"- Bonnes affaires aujourd'hui : {donnees['bonnes_affaires_aujourdhui']}\n"
        f"- Alertes envoyées aujourd'hui : {donnees['alertes_aujourdhui']}\n\n"
        "🎯 Business\n"
        f"- Marge potentielle du jour : {formater_prix(donnees['marge_potentielle_jour'])}\n"
        f"- Business Score moyen : {donnees['business_score_moyen_jour']}/100\n"
        f"- Meilleure opportunité : {texte_meilleure}\n\n"
        "⚙️ Suivi\n"
        f"- Favoris actifs : {donnees['favoris_actifs']}\n"
        f"- Surveillances actives : {donnees['surveillances_actives']}\n"
        f"- Scanner global : {'actif' if donnees['scanner_global_actif'] else 'inactif'}\n"
        f"- Dernier scan : {donnees['dernier_scan'] or 'Aucun scan'}"
    )


def formater_opportunite(opportunite, index):
    baisse = opportunite.get("baisse_prix") or 0

    return (
        f"{index}. {opportunite.get('modele') or 'Annonce'}\n"
        f"🌐 Source : {opportunite.get('source') or 'Inconnu'}\n"
        f"💰 Prix : {formater_prix(opportunite.get('prix'))}\n"
        f"💵 Bénéfice : +{formater_prix(opportunite.get('benefice'))}\n"
        f"🔥 Business Score : {opportunite.get('score_business') or 0}/100\n"
        f"🤝 Négociation : {opportunite.get('score_negociation') or 'Inconnu'}/100\n"
        f"⏳ Vendeur pressé : {opportunite.get('score_vendeur_presse') or 'Inconnu'}/100\n"
        f"📉 Baisse : {formater_prix(baisse)}\n"
        f"🔗 {opportunite.get('lien')}\n"
    )


def formater_top(titre, opportunites, limite=None):
    if limite:
        opportunites = opportunites[:limite]

    if not opportunites:
        return f"{titre}\n\nAucune opportunité enregistrée pour cette période."

    blocs = [titre, ""]

    for index, opportunite in enumerate(opportunites, start=1):
        blocs.append(formater_opportunite(opportunite, index))

    return "\n".join(blocs)


def formater_stats_modele(stats):
    if stats["nombre"] == 0:
        return (
            f"🚗 Stats modèle : {stats['modele']}\n\n"
            "Aucune donnée disponible pour ce modèle."
        )

    meilleure = stats["meilleure_annonce"]
    texte_meilleure = (
        f"{meilleure['modele']} | "
        f"+{formater_prix(meilleure['benefice'])} | "
        f"{meilleure['score_business'] or 0}/100\n"
        f"{meilleure['lien']}"
    )

    return (
        f"🚗 Stats modèle : {stats['modele']}\n\n"
        f"- Annonces analysées : {stats['nombre']}\n"
        f"- Prix moyen : {formater_prix(stats['prix_moyen'])}\n"
        f"- Prix médian : {formater_prix(stats['prix_median'])}\n"
        f"- Prix minimum : {formater_prix(stats['prix_min'])}\n"
        f"- Prix maximum : {formater_prix(stats['prix_max'])}\n"
        f"- Bénéfice moyen : +{formater_prix(stats['benefice_moyen'])}\n"
        f"- Business Score moyen : {stats['score_business_moyen']}/100\n"
        f"- Bonnes affaires : {stats['bonnes_affaires']}\n"
        f"- Baisses détectées : {stats['nombre_baisses']}\n"
        f"- Période : {stats['periode_debut']} → {stats['periode_fin']}\n\n"
        f"🏆 Meilleure annonce\n{texte_meilleure}"
    )


def formater_sources(sources):
    if not sources:
        return "📡 État des sources\n\nAucune donnée source disponible."

    blocs = ["📡 État des sources", ""]

    for source in sources:
        lignes = [
            f"🌐 {source['source']}",
            f"- Annonces récupérées : {source['annonces_recuperees']}",
            f"- Annonces pertinentes : {source['annonces_pertinentes']}",
            f"- Bonnes affaires : {source['bonnes_affaires']}",
            f"- Erreurs : {source['erreurs']}",
            f"- Temps moyen : {source['temps_moyen'] or 'Inconnu'} s",
            f"- Dernière réussite : {source['derniere_reussite'] or 'Inconnu'}",
            f"- Dernier échec : {source['dernier_echec'] or 'Inconnu'}",
        ]

        if "statut" in source:
            lignes.append(f"- Statut : {source['statut']}")

        if "echecs_consecutifs" in source:
            lignes.append(
                f"- Échecs consécutifs : {source['echecs_consecutifs']}"
            )

        blocs.append("\n".join(lignes))

    return "\n\n".join(blocs)
