import os
import sqlite3
from datetime import datetime


DATABASE_PATH = os.getenv("YB_AUTO_BOT_DB", "voitures.db")

connexion = sqlite3.connect(DATABASE_PATH)
curseur = connexion.cursor()

FILTRES_SURVEILLANCE = (
    "prix_min",
    "prix_max",
    "km_max",
    "annee_min",
    "carburant",
    "boite",
    "score_min",
    "benefice_min",
    "source",
)

FILTRES_NUMERIQUES = {
    "prix_min",
    "prix_max",
    "km_max",
    "annee_min",
    "score_min",
    "benefice_min",
}

curseur.execute("""
CREATE TABLE IF NOT EXISTS annonces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titre TEXT,
    prix INTEGER,
    ville TEXT,
    lien TEXT UNIQUE
)
""")


def _colonnes_annonces():
    curseur.execute("PRAGMA table_info(annonces)")
    return {colonne[1] for colonne in curseur.fetchall()}


def _ajouter_colonne_si_absente(nom, definition):
    if nom not in _colonnes_annonces():
        curseur.execute(f"ALTER TABLE annonces ADD COLUMN {nom} {definition}")


_ajouter_colonne_si_absente("source", "TEXT")
_ajouter_colonne_si_absente("modele", "TEXT")
_ajouter_colonne_si_absente("kilometrage", "INTEGER")
_ajouter_colonne_si_absente("annee", "TEXT")
_ajouter_colonne_si_absente("date_premiere_detection", "TEXT")
_ajouter_colonne_si_absente("score", "INTEGER")
_ajouter_colonne_si_absente("benefice", "INTEGER")

curseur.execute("""
CREATE TABLE IF NOT EXISTS surveillances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recherche TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    prix_min INTEGER,
    prix_max INTEGER,
    km_max INTEGER,
    annee_min INTEGER,
    carburant TEXT,
    boite TEXT,
    score_min INTEGER,
    benefice_min INTEGER,
    source TEXT,
    filtres_signature TEXT NOT NULL,
    date_creation TEXT NOT NULL,
    UNIQUE(recherche, chat_id, filtres_signature)
)
""")

curseur.execute("""
CREATE TABLE IF NOT EXISTS messages_business (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    date_envoi TEXT NOT NULL,
    date_creation TEXT NOT NULL,
    UNIQUE(chat_id, date_envoi)
)
""")

curseur.execute("""
CREATE TABLE IF NOT EXISTS statistiques_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    recherche TEXT NOT NULL,
    annonces_analysees INTEGER NOT NULL,
    nouvelles_annonces INTEGER NOT NULL,
    bonnes_affaires INTEGER NOT NULL,
    meilleur_modele TEXT,
    meilleur_benefice INTEGER,
    date_scan TEXT NOT NULL
)
""")

connexion.commit()


def _colonnes_table(nom_table):
    curseur.execute(f"PRAGMA table_info({nom_table})")
    return {colonne[1] for colonne in curseur.fetchall()}


def _index_unique_surveillances_correct():
    curseur.execute("PRAGMA index_list(surveillances)")
    for index in curseur.fetchall():
        est_unique = index[2]
        nom_index = index[1]

        if not est_unique:
            continue

        curseur.execute(f"PRAGMA index_info({nom_index})")
        colonnes = [colonne[2] for colonne in curseur.fetchall()]

        if colonnes == ["recherche", "chat_id", "filtres_signature"]:
            return True

    return False


def _creer_table_surveillances():
    curseur.execute("""
    CREATE TABLE surveillances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recherche TEXT NOT NULL,
        chat_id INTEGER NOT NULL,
        prix_min INTEGER,
        prix_max INTEGER,
        km_max INTEGER,
        annee_min INTEGER,
        carburant TEXT,
        boite TEXT,
        score_min INTEGER,
        benefice_min INTEGER,
        source TEXT,
        filtres_signature TEXT NOT NULL,
        date_creation TEXT NOT NULL,
        UNIQUE(recherche, chat_id, filtres_signature)
    )
    """)


def normaliser_filtres(filtres=None):
    filtres = filtres or {}
    filtres_normalises = {}

    for cle, valeur in filtres.items():
        if valeur in (None, ""):
            continue

        if cle not in FILTRES_SURVEILLANCE:
            continue

        if cle in FILTRES_NUMERIQUES:
            filtres_normalises[cle] = int(valeur)
        else:
            filtres_normalises[cle] = str(valeur).strip().lower()

    return filtres_normalises


def signature_filtres(filtres=None):
    filtres_normalises = normaliser_filtres(filtres)
    return "|".join(
        f"{cle}={filtres_normalises[cle]}"
        for cle in sorted(filtres_normalises)
    )


def formater_filtres(filtres=None):
    filtres_normalises = normaliser_filtres(filtres)

    if not filtres_normalises:
        return "aucun filtre"

    return ", ".join(
        f"{cle}={filtres_normalises[cle]}"
        for cle in sorted(filtres_normalises)
    )


def _migrer_table_surveillances_si_necessaire():
    colonnes_attendues = {
        "id",
        "recherche",
        "chat_id",
        "prix_min",
        "prix_max",
        "km_max",
        "annee_min",
        "carburant",
        "boite",
        "score_min",
        "benefice_min",
        "source",
        "filtres_signature",
        "date_creation",
    }

    colonnes = _colonnes_table("surveillances")

    if (
        colonnes_attendues.issubset(colonnes)
        and _index_unique_surveillances_correct()
    ):
        return

    ancienne_table = "surveillances_avant_migration"
    curseur.execute(f"DROP TABLE IF EXISTS {ancienne_table}")
    curseur.execute(f"ALTER TABLE surveillances RENAME TO {ancienne_table}")
    _creer_table_surveillances()

    anciennes_colonnes = _colonnes_table(ancienne_table)
    colonnes_communes = [
        colonne
        for colonne in colonnes_attendues
        if colonne in anciennes_colonnes and colonne != "id"
    ]

    curseur.execute(f"SELECT * FROM {ancienne_table}")
    lignes = curseur.fetchall()
    noms_colonnes = [description[0] for description in curseur.description]

    for ligne in lignes:
        donnees = dict(zip(noms_colonnes, ligne))
        filtres = {
            cle: donnees.get(cle)
            for cle in FILTRES_SURVEILLANCE
            if cle in anciennes_colonnes
        }
        signature = donnees.get("filtres_signature") or signature_filtres(filtres)

        valeurs = {
            "recherche": donnees["recherche"],
            "chat_id": donnees["chat_id"],
            "prix_min": donnees.get("prix_min"),
            "prix_max": donnees.get("prix_max"),
            "km_max": donnees.get("km_max"),
            "annee_min": donnees.get("annee_min"),
            "carburant": donnees.get("carburant"),
            "boite": donnees.get("boite"),
            "score_min": donnees.get("score_min"),
            "benefice_min": donnees.get("benefice_min"),
            "source": donnees.get("source"),
            "filtres_signature": signature,
            "date_creation": donnees.get(
                "date_creation",
                datetime.now().isoformat(timespec="seconds")
            ),
        }

        curseur.execute(
            """
            INSERT OR IGNORE INTO surveillances (
                recherche,
                chat_id,
                prix_min,
                prix_max,
                km_max,
                annee_min,
                carburant,
                boite,
                score_min,
                benefice_min,
                source,
                filtres_signature,
                date_creation
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                valeurs["recherche"],
                valeurs["chat_id"],
                valeurs["prix_min"],
                valeurs["prix_max"],
                valeurs["km_max"],
                valeurs["annee_min"],
                valeurs["carburant"],
                valeurs["boite"],
                valeurs["score_min"],
                valeurs["benefice_min"],
                valeurs["source"],
                valeurs["filtres_signature"],
                valeurs["date_creation"],
            )
        )

    curseur.execute(f"DROP TABLE {ancienne_table}")
    connexion.commit()


_migrer_table_surveillances_si_necessaire()


def annonce_existe(lien):
    curseur.execute(
        "SELECT 1 FROM annonces WHERE lien = ?",
        (lien,)
    )
    return curseur.fetchone() is not None


def mettre_a_jour_analyse_annonce(lien, score, benefice):
    curseur.execute(
        """
        UPDATE annonces
        SET score = ?, benefice = ?
        WHERE lien = ?
        """,
        (score, benefice, lien)
    )
    connexion.commit()


def _normaliser_kilometrage(kilometrage):
    if isinstance(kilometrage, int):
        return kilometrage

    return None


def normaliser_recherche(recherche):
    return " ".join(recherche.lower().split())


def ajouter_annonce(*args):
    if len(args) == 4:
        titre, prix, ville, lien = args
        source = "Inconnu"
        modele = titre
        kilometrage = None
        annee = "Inconnu"
    elif len(args) == 6:
        source, modele, prix, kilometrage, annee, lien = args
        titre = modele
        ville = "Inconnu"
    else:
        raise TypeError(
            "ajouter_annonce attend 4 arguments historiques "
            "ou 6 arguments: source, modele, prix, kilometrage, annee, lien"
        )

    if annonce_existe(lien):
        return False

    curseur.execute(
        """
        INSERT INTO annonces (
            titre,
            prix,
            ville,
            lien,
            source,
            modele,
            kilometrage,
            annee,
            date_premiere_detection
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            titre,
            prix,
            ville,
            lien,
            source,
            modele,
            _normaliser_kilometrage(kilometrage),
            str(annee),
            datetime.now().isoformat(timespec="seconds")
        )
    )

    connexion.commit()
    return True


def ajouter_surveillance(recherche, chat_id, filtres=None):
    recherche = normaliser_recherche(recherche)
    filtres_normalises = normaliser_filtres(filtres)
    filtres_signature = signature_filtres(filtres_normalises)

    if not recherche:
        return False

    try:
        curseur.execute(
            """
            INSERT INTO surveillances (
                recherche,
                chat_id,
                prix_min,
                prix_max,
                km_max,
                annee_min,
                carburant,
                boite,
                score_min,
                benefice_min,
                source,
                filtres_signature,
                date_creation
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recherche,
                chat_id,
                filtres_normalises.get("prix_min"),
                filtres_normalises.get("prix_max"),
                filtres_normalises.get("km_max"),
                filtres_normalises.get("annee_min"),
                filtres_normalises.get("carburant"),
                filtres_normalises.get("boite"),
                filtres_normalises.get("score_min"),
                filtres_normalises.get("benefice_min"),
                filtres_normalises.get("source"),
                filtres_signature,
                datetime.now().isoformat(timespec="seconds")
            )
        )
        connexion.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def supprimer_surveillance(recherche, chat_id, filtres=None):
    recherche = normaliser_recherche(recherche)
    filtres_signature = signature_filtres(filtres)
    curseur.execute(
        """
        DELETE FROM surveillances
        WHERE recherche = ? AND chat_id = ? AND filtres_signature = ?
        """,
        (recherche, chat_id, filtres_signature)
    )
    connexion.commit()
    return curseur.rowcount > 0


def lister_surveillances(chat_id=None):
    colonnes_filtres = ", ".join(FILTRES_SURVEILLANCE)

    if chat_id is None:
        curseur.execute(
            f"""
            SELECT recherche, chat_id, {colonnes_filtres}
            FROM surveillances
            ORDER BY recherche, filtres_signature
            """
        )
        return [
            (
                ligne[0],
                ligne[1],
                normaliser_filtres(dict(zip(FILTRES_SURVEILLANCE, ligne[2:])))
            )
            for ligne in curseur.fetchall()
        ]

    curseur.execute(
        f"""
        SELECT recherche, {colonnes_filtres}
        FROM surveillances
        WHERE chat_id = ?
        ORDER BY recherche, filtres_signature
        """,
        (chat_id,)
    )
    return [
        (
            ligne[0],
            normaliser_filtres(dict(zip(FILTRES_SURVEILLANCE, ligne[1:])))
        )
        for ligne in curseur.fetchall()
    ]


def lister_chat_ids_surveillance():
    curseur.execute(
        """
        SELECT DISTINCT chat_id
        FROM surveillances
        ORDER BY chat_id
        """
    )
    return [ligne[0] for ligne in curseur.fetchall()]


def enregistrer_statistiques_scan(
    chat_id,
    recherche,
    annonces_analysees,
    nouvelles_annonces,
    bonnes_affaires,
    meilleur_modele=None,
    meilleur_benefice=None,
    date_scan=None
):
    curseur.execute(
        """
        INSERT INTO statistiques_scans (
            chat_id,
            recherche,
            annonces_analysees,
            nouvelles_annonces,
            bonnes_affaires,
            meilleur_modele,
            meilleur_benefice,
            date_scan
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chat_id,
            recherche,
            annonces_analysees,
            nouvelles_annonces,
            bonnes_affaires,
            meilleur_modele,
            meilleur_benefice,
            date_scan or datetime.now().isoformat(timespec="seconds")
        )
    )
    connexion.commit()


def bilan_business(date_bilan, chat_id):
    debut = f"{date_bilan}T00:00:00"
    fin = f"{date_bilan}T23:59:59"

    curseur.execute(
        """
        SELECT
            COALESCE(SUM(annonces_analysees), 0),
            COALESCE(SUM(nouvelles_annonces), 0),
            COALESCE(SUM(bonnes_affaires), 0)
        FROM statistiques_scans
        WHERE chat_id = ?
        AND date_scan BETWEEN ? AND ?
        """,
        (chat_id, debut, fin)
    )
    annonces_analysees, nouvelles_annonces, bonnes_affaires = curseur.fetchone()

    curseur.execute(
        """
        SELECT meilleur_modele, meilleur_benefice
        FROM statistiques_scans
        WHERE chat_id = ?
        AND date_scan BETWEEN ? AND ?
        AND meilleur_modele IS NOT NULL
        AND meilleur_benefice IS NOT NULL
        ORDER BY meilleur_benefice DESC
        LIMIT 1
        """,
        (chat_id, debut, fin)
    )
    meilleure = curseur.fetchone()

    return {
        "annonces_analysees": annonces_analysees,
        "nouvelles_annonces": nouvelles_annonces,
        "bonnes_affaires": bonnes_affaires,
        "meilleur_modele": meilleure[0] if meilleure else None,
        "meilleur_benefice": meilleure[1] if meilleure else None,
    }


def message_business_deja_envoye(chat_id, date_envoi):
    curseur.execute(
        """
        SELECT 1
        FROM messages_business
        WHERE chat_id = ? AND date_envoi = ?
        """,
        (chat_id, str(date_envoi))
    )
    return curseur.fetchone() is not None


def enregistrer_message_business(chat_id, date_envoi):
    try:
        curseur.execute(
            """
            INSERT INTO messages_business (chat_id, date_envoi, date_creation)
            VALUES (?, ?, ?)
            """,
            (
                chat_id,
                str(date_envoi),
                datetime.now().isoformat(timespec="seconds")
            )
        )
        connexion.commit()
        return True
    except sqlite3.IntegrityError:
        return False
