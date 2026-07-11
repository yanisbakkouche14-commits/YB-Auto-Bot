import os
import sqlite3
from datetime import datetime


DATABASE_PATH = os.getenv("YB_AUTO_BOT_DB", "voitures.db")

connexion = sqlite3.connect(DATABASE_PATH)
curseur = connexion.cursor()

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

curseur.execute("""
CREATE TABLE IF NOT EXISTS surveillances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recherche TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    date_creation TEXT NOT NULL,
    UNIQUE(recherche, chat_id)
)
""")

connexion.commit()


def annonce_existe(lien):
    curseur.execute(
        "SELECT 1 FROM annonces WHERE lien = ?",
        (lien,)
    )
    return curseur.fetchone() is not None


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


def ajouter_surveillance(recherche, chat_id):
    recherche = normaliser_recherche(recherche)

    if not recherche:
        return False

    try:
        curseur.execute(
            """
            INSERT INTO surveillances (recherche, chat_id, date_creation)
            VALUES (?, ?, ?)
            """,
            (
                recherche,
                chat_id,
                datetime.now().isoformat(timespec="seconds")
            )
        )
        connexion.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def supprimer_surveillance(recherche, chat_id):
    recherche = normaliser_recherche(recherche)
    curseur.execute(
        """
        DELETE FROM surveillances
        WHERE recherche = ? AND chat_id = ?
        """,
        (recherche, chat_id)
    )
    connexion.commit()
    return curseur.rowcount > 0


def lister_surveillances(chat_id=None):
    if chat_id is None:
        curseur.execute(
            """
            SELECT recherche, chat_id
            FROM surveillances
            ORDER BY recherche
            """
        )
        return curseur.fetchall()

    curseur.execute(
        """
        SELECT recherche
        FROM surveillances
        WHERE chat_id = ?
        ORDER BY recherche
        """,
        (chat_id,)
    )
    return [ligne[0] for ligne in curseur.fetchall()]
