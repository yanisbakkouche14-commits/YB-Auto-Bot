import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "marche_reel.db"
STATS_PATH = DATA_DIR / "statistiques_reelles.json"
TOP50_PATH = DATA_DIR / "marche_revente_belgique_top50.json"


def maintenant():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def nombre(valeur):
    if isinstance(valeur, int):
        return valeur

    if isinstance(valeur, float):
        return int(valeur)

    chiffres = "".join(caractere for caractere in str(valeur or "") if caractere.isdigit())
    return int(chiffres) if chiffres else None


def texte(valeur, defaut="Inconnu"):
    valeur = str(valeur or "").strip()
    return valeur if valeur else defaut


def connecter(db_path=DB_PATH):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connexion = sqlite3.connect(db_path)
    connexion.row_factory = sqlite3.Row
    return connexion


def initialiser_base(db_path=DB_PATH):
    with connecter(db_path) as connexion:
        connexion.executescript(
            """
            CREATE TABLE IF NOT EXISTS annonces_reelles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lien TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                modele_recherche TEXT NOT NULL,
                modele TEXT,
                titre TEXT,
                prix INTEGER,
                annee TEXT,
                kilometrage INTEGER,
                moteur TEXT,
                boite TEXT,
                ville TEXT,
                pays TEXT,
                date_decouverte TEXT NOT NULL,
                date_derniere_vue TEXT NOT NULL,
                date_disparition TEXT,
                duree_en_ligne_jours REAL,
                active INTEGER NOT NULL DEFAULT 1,
                observations INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS observations_reelles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                annonce_id INTEGER NOT NULL,
                date_observation TEXT NOT NULL,
                prix INTEGER,
                kilometrage INTEGER,
                annee TEXT,
                ville TEXT,
                FOREIGN KEY(annonce_id) REFERENCES annonces_reelles(id)
            );

            CREATE TABLE IF NOT EXISTS collectes_reelles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_collecte TEXT NOT NULL,
                modele_recherche TEXT NOT NULL,
                source TEXT NOT NULL,
                annonces_trouvees INTEGER NOT NULL DEFAULT 0,
                annonces_nouvelles INTEGER NOT NULL DEFAULT 0,
                annonces_disparues INTEGER NOT NULL DEFAULT 0,
                duree_secondes REAL,
                erreur TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_annonces_reelles_modele
                ON annonces_reelles(modele_recherche);
            CREATE INDEX IF NOT EXISTS idx_annonces_reelles_source
                ON annonces_reelles(source);
            CREATE INDEX IF NOT EXISTS idx_annonces_reelles_active
                ON annonces_reelles(active);
            CREATE INDEX IF NOT EXISTS idx_annonces_reelles_dates
                ON annonces_reelles(date_decouverte, date_disparition);
            CREATE INDEX IF NOT EXISTS idx_observations_reelles_annonce
                ON observations_reelles(annonce_id, date_observation);
            CREATE INDEX IF NOT EXISTS idx_collectes_reelles_date
                ON collectes_reelles(date_collecte);
            """
        )


def charger_modeles_surveillance():
    if not TOP50_PATH.exists():
        return []

    with TOP50_PATH.open("r", encoding="utf-8") as fichier:
        donnees = json.load(fichier)

    return [
        modele["modele"]
        for modele in donnees.get("modeles", [])
        if modele.get("modele")
    ]


def scanners_disponibles(inclure_marketplace=True):
    from scanner.autoscout import rechercher_voitures as autoscout
    from scanner.deuxiememain import rechercher_voitures as deuxiememain
    from scanner.gocar import rechercher_voitures as gocar
    from scanner.leparking import rechercher_voitures as leparking

    scanners = {
        "AutoScout24": autoscout,
        "2ememain": deuxiememain,
        "Gocar": gocar,
        "LeParking": leparking,
    }

    if inclure_marketplace:
        try:
            from scanner.marketplace import rechercher_voitures as marketplace

            scanners["Facebook Marketplace"] = marketplace
        except Exception:
            pass

    return scanners


def normaliser_annonce(annonce, modele_recherche, source_defaut):
    return {
        "source": texte(annonce.get("source"), source_defaut),
        "modele_recherche": modele_recherche,
        "modele": texte(annonce.get("modele") or annonce.get("titre"), modele_recherche),
        "titre": texte(annonce.get("titre") or annonce.get("modele"), modele_recherche),
        "prix": nombre(annonce.get("prix")),
        "annee": texte(annonce.get("annee")),
        "kilometrage": nombre(annonce.get("kilometrage")),
        "moteur": texte(
            annonce.get("moteur")
            or annonce.get("carburant")
            or annonce.get("motorisation")
        ),
        "boite": texte(annonce.get("boite") or annonce.get("transmission")),
        "ville": texte(annonce.get("ville") or annonce.get("localisation"), "Belgique"),
        "pays": texte(annonce.get("pays"), "Belgique"),
        "lien": texte(annonce.get("lien"), ""),
    }


def jours_entre(debut, fin):
    debut_dt = datetime.fromisoformat(debut.replace("Z", "+00:00"))
    fin_dt = datetime.fromisoformat(fin.replace("Z", "+00:00"))
    return max(0, (fin_dt - debut_dt).total_seconds() / 86400)


def enregistrer_annonces(connexion, modele_recherche, source, annonces, date_scan):
    nouveaux = 0
    liens_vus = set()

    for annonce_brute in annonces:
        annonce = normaliser_annonce(annonce_brute, modele_recherche, source)
        lien = annonce["lien"]

        if not lien or lien in liens_vus:
            continue

        liens_vus.add(lien)
        existante = connexion.execute(
            "SELECT id, date_decouverte FROM annonces_reelles WHERE lien = ?",
            (lien,),
        ).fetchone()

        if existante:
            connexion.execute(
                """
                UPDATE annonces_reelles
                SET prix = COALESCE(?, prix),
                    annee = COALESCE(NULLIF(?, 'Inconnu'), annee),
                    kilometrage = COALESCE(?, kilometrage),
                    moteur = COALESCE(NULLIF(?, 'Inconnu'), moteur),
                    boite = COALESCE(NULLIF(?, 'Inconnu'), boite),
                    ville = COALESCE(NULLIF(?, 'Inconnu'), ville),
                    pays = COALESCE(NULLIF(?, 'Inconnu'), pays),
                    date_derniere_vue = ?,
                    date_disparition = NULL,
                    duree_en_ligne_jours = NULL,
                    active = 1,
                    observations = observations + 1
                WHERE id = ?
                """,
                (
                    annonce["prix"],
                    annonce["annee"],
                    annonce["kilometrage"],
                    annonce["moteur"],
                    annonce["boite"],
                    annonce["ville"],
                    annonce["pays"],
                    date_scan,
                    existante["id"],
                ),
            )
            annonce_id = existante["id"]
        else:
            curseur = connexion.execute(
                """
                INSERT INTO annonces_reelles (
                    lien, source, modele_recherche, modele, titre, prix, annee,
                    kilometrage, moteur, boite, ville, pays, date_decouverte,
                    date_derniere_vue
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lien,
                    annonce["source"],
                    annonce["modele_recherche"],
                    annonce["modele"],
                    annonce["titre"],
                    annonce["prix"],
                    annonce["annee"],
                    annonce["kilometrage"],
                    annonce["moteur"],
                    annonce["boite"],
                    annonce["ville"],
                    annonce["pays"],
                    date_scan,
                    date_scan,
                ),
            )
            annonce_id = curseur.lastrowid
            nouveaux += 1

        connexion.execute(
            """
            INSERT INTO observations_reelles (
                annonce_id, date_observation, prix, kilometrage, annee, ville
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                annonce_id,
                date_scan,
                annonce["prix"],
                annonce["kilometrage"],
                annonce["annee"],
                annonce["ville"],
            ),
        )

    disparues = marquer_disparitions(
        connexion,
        modele_recherche,
        source,
        liens_vus,
        date_scan,
    )
    return nouveaux, disparues, len(liens_vus)


def marquer_disparitions(connexion, modele_recherche, source, liens_vus, date_scan):
    lignes = connexion.execute(
        """
        SELECT id, lien, date_decouverte
        FROM annonces_reelles
        WHERE modele_recherche = ?
          AND source = ?
          AND active = 1
        """,
        (modele_recherche, source),
    ).fetchall()
    disparues = 0

    for ligne in lignes:
        if ligne["lien"] in liens_vus:
            continue

        duree = jours_entre(ligne["date_decouverte"], date_scan)
        connexion.execute(
            """
            UPDATE annonces_reelles
            SET active = 0,
                date_disparition = ?,
                duree_en_ligne_jours = ?
            WHERE id = ?
            """,
            (date_scan, duree, ligne["id"]),
        )
        disparues += 1

    return disparues


def collecter_modele(modele, scanners=None, db_path=DB_PATH):
    initialiser_base(db_path)
    scanners = scanners or scanners_disponibles()
    date_scan = maintenant()
    resultats = []

    with connecter(db_path) as connexion:
        for source, fonction in scanners.items():
            debut = time.monotonic()
            erreur = None
            annonces = []
            nouveaux = 0
            disparues = 0

            try:
                annonces = fonction(modele) or []
                nouveaux, disparues, total = enregistrer_annonces(
                    connexion,
                    modele,
                    source,
                    annonces,
                    date_scan,
                )
            except Exception as exc:
                erreur = str(exc)
                total = 0

            duree = round(time.monotonic() - debut, 3)
            connexion.execute(
                """
                INSERT INTO collectes_reelles (
                    date_collecte, modele_recherche, source, annonces_trouvees,
                    annonces_nouvelles, annonces_disparues, duree_secondes, erreur
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (date_scan, modele, source, total, nouveaux, disparues, duree, erreur),
            )
            resultats.append({
                "modele": modele,
                "source": source,
                "annonces_trouvees": total,
                "nouvelles": nouveaux,
                "disparues": disparues,
                "erreur": erreur,
                "duree_secondes": duree,
            })

    return resultats


def collecter_tous(modeles=None, limite_modeles=None, db_path=DB_PATH):
    modeles = modeles or charger_modeles_surveillance()

    if limite_modeles:
        modeles = modeles[:limite_modeles]

    resultats = []

    for modele in modeles:
        resultats.extend(collecter_modele(modele, db_path=db_path))

    statistiques = generer_statistiques(db_path=db_path)
    ecrire_statistiques(statistiques)
    return resultats, statistiques


def moyenne(valeurs):
    valeurs = [valeur for valeur in valeurs if valeur is not None]
    return round(sum(valeurs) / len(valeurs), 2) if valeurs else None


def percentile(valeurs, ratio):
    valeurs = sorted(valeur for valeur in valeurs if valeur is not None)

    if not valeurs:
        return None

    index = int((len(valeurs) - 1) * ratio)
    return valeurs[index]


def score_liquidite(delai_moyen, vendues, total):
    if not total:
        return 0

    taux_rotation = vendues / total

    if delai_moyen is None:
        score_delai = 35
    elif delai_moyen <= 15:
        score_delai = 100
    elif delai_moyen <= 30:
        score_delai = 80
    elif delai_moyen <= 60:
        score_delai = 55
    else:
        score_delai = 25

    return round(min(100, score_delai * 0.7 + min(100, taux_rotation * 100) * 0.3), 1)


def score_rentabilite(marge_moyenne, prix_moyen):
    if marge_moyenne is None or not prix_moyen:
        return 0

    roi = marge_moyenne / prix_moyen
    return round(min(100, max(0, roi * 700)), 1)


def generer_statistiques(db_path=DB_PATH):
    initialiser_base(db_path)

    with connecter(db_path) as connexion:
        modeles = connexion.execute(
            """
            SELECT modele_recherche,
                   COUNT(*) AS total,
                   SUM(active) AS actives,
                   SUM(CASE WHEN active = 0 THEN 1 ELSE 0 END) AS disparues
            FROM annonces_reelles
            GROUP BY modele_recherche
            ORDER BY total DESC
            """
        ).fetchall()

        stats_modeles = []

        for modele in modeles:
            nom = modele["modele_recherche"]
            prix = [
                ligne["prix"]
                for ligne in connexion.execute(
                    "SELECT prix FROM annonces_reelles WHERE modele_recherche = ? AND prix IS NOT NULL",
                    (nom,),
                )
            ]
            durees = [
                ligne["duree_en_ligne_jours"]
                for ligne in connexion.execute(
                    """
                    SELECT duree_en_ligne_jours
                    FROM annonces_reelles
                    WHERE modele_recherche = ?
                      AND duree_en_ligne_jours IS NOT NULL
                    """,
                    (nom,),
                )
            ]
            prix_moyen = moyenne(prix)
            prix_bas = percentile(prix, 0.25)
            prix_median = percentile(prix, 0.5)
            marge = prix_median - prix_bas if prix_median is not None and prix_bas is not None else None
            delai = moyenne(durees)
            total = modele["total"]
            vendues = modele["disparues"] or 0

            stats_modeles.append({
                "modele": nom,
                "annonces_total": total,
                "annonces_actives": modele["actives"] or 0,
                "annonces_disparues": vendues,
                "delai_moyen_vente_reel_jours": delai,
                "prix_moyen": prix_moyen,
                "prix_p25": prix_bas,
                "prix_median": prix_median,
                "marge_moyenne_estimee": marge,
                "marge_methode": "prix_median_observe - prix_p25_observe",
                "score_liquidite_reel": score_liquidite(delai, vendues, total),
                "score_rentabilite_reel": score_rentabilite(marge, prix_moyen),
            })

    top_rapides = [
        modele for modele in stats_modeles
        if modele["delai_moyen_vente_reel_jours"] is not None
        and modele["delai_moyen_vente_reel_jours"] < 15
    ][:20]
    top_lents = sorted(
        [
            modele for modele in stats_modeles
            if modele["delai_moyen_vente_reel_jours"] is not None
            and modele["delai_moyen_vente_reel_jours"] > 60
        ],
        key=lambda item: item["delai_moyen_vente_reel_jours"],
        reverse=True,
    )[:20]

    return {
        "date_generation": maintenant(),
        "db": str(db_path),
        "methodologie": {
            "vente_reelle_estimee": (
                "Une annonce est consideree disparue quand elle n'apparait plus "
                "lors d'un scan reussi de la meme plateforme et du meme modele."
            ),
            "marge_moyenne_estimee": "prix median observe - prix premier quartile observe",
        },
        "modeles": stats_modeles,
        "top_20_revente_moins_15_jours": top_rapides,
        "top_20_plus_60_jours": top_lents,
    }


def ecrire_statistiques(statistiques, stats_path=STATS_PATH):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with Path(stats_path).open("w", encoding="utf-8") as fichier:
        json.dump(statistiques, fichier, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Collecte marche reel occasion Belgique")
    parser.add_argument("--init", action="store_true", help="cree la base SQLite")
    parser.add_argument("--stats", action="store_true", help="regenere le JSON de statistiques")
    parser.add_argument("--collect", action="store_true", help="collecte les annonces")
    parser.add_argument("--model", action="append", help="modele a collecter, repetable")
    parser.add_argument("--limit-models", type=int, help="limite le nombre de modeles")
    args = parser.parse_args()

    if args.init:
        initialiser_base()
        ecrire_statistiques(generer_statistiques())
        print(f"Base initialisee: {DB_PATH}")

    if args.collect:
        resultats, _statistiques = collecter_tous(
            modeles=args.model,
            limite_modeles=args.limit_models,
        )
        print(json.dumps(resultats, ensure_ascii=False, indent=2))

    if args.stats:
        statistiques = generer_statistiques()
        ecrire_statistiques(statistiques)
        print(f"Statistiques ecrites: {STATS_PATH}")


if __name__ == "__main__":
    main()
