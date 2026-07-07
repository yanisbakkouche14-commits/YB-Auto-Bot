import sqlite3

connexion = sqlite3.connect("voitures.db")
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

connexion.commit()


def annonce_existe(lien):
    curseur.execute(
        "SELECT * FROM annonces WHERE lien = ?",
        (lien,)
    )
    return curseur.fetchone() is not None


def ajouter_annonce(titre, prix, ville, lien):
    if not annonce_existe(lien):
        curseur.execute(
            "INSERT INTO annonces (titre, prix, ville, lien) VALUES (?, ?, ?, ?)",
            (titre, prix, ville, lien)
        )
        connexion.commit()