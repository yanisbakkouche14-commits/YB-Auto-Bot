import os
import sqlite3
from datetime import datetime, timedelta


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
_ajouter_colonne_si_absente("prix_initial", "INTEGER")
_ajouter_colonne_si_absente("date_derniere_detection", "TEXT")

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


def _ajouter_colonne_table_si_absente(nom_table, nom_colonne, definition):
    curseur.execute(f"PRAGMA table_info({nom_table})")
    colonnes = {colonne[1] for colonne in curseur.fetchall()}

    if nom_colonne not in colonnes:
        curseur.execute(
            f"ALTER TABLE {nom_table} ADD COLUMN {nom_colonne} {definition}"
        )


_ajouter_colonne_table_si_absente(
    "statistiques_scans",
    "type_scan",
    "TEXT DEFAULT 'surveillance'"
)
_ajouter_colonne_table_si_absente("statistiques_scans", "lot", "TEXT")
_ajouter_colonne_table_si_absente("statistiques_scans", "source", "TEXT")
_ajouter_colonne_table_si_absente(
    "statistiques_scans",
    "alertes_envoyees",
    "INTEGER NOT NULL DEFAULT 0"
)
_ajouter_colonne_table_si_absente(
    "statistiques_scans",
    "duree_secondes",
    "REAL"
)
_ajouter_colonne_table_si_absente(
    "statistiques_scans",
    "meilleur_score_business",
    "INTEGER"
)

curseur.execute("""
CREATE TABLE IF NOT EXISTS historique_prix (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lien TEXT NOT NULL,
    ancien_prix INTEGER NOT NULL,
    nouveau_prix INTEGER NOT NULL,
    variation INTEGER NOT NULL,
    date_changement TEXT NOT NULL
)
""")

curseur.execute("""
CREATE TABLE IF NOT EXISTS scanner_global (
    chat_id INTEGER PRIMARY KEY,
    actif INTEGER NOT NULL,
    prix_max INTEGER,
    prochain_lot_index INTEGER NOT NULL,
    date_activation TEXT NOT NULL,
    date_modification TEXT NOT NULL
)
""")

curseur.execute("""
CREATE TABLE IF NOT EXISTS opportunites_globales_envoyees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    lien TEXT NOT NULL,
    prix INTEGER,
    score_business INTEGER,
    baisse_totale INTEGER,
    date_envoi TEXT NOT NULL,
    signature TEXT NOT NULL,
    UNIQUE(chat_id, lien, signature)
)
""")

curseur.execute("""
CREATE TABLE IF NOT EXISTS favoris (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    lien TEXT NOT NULL,
    modele TEXT,
    prix INTEGER,
    prix_initial INTEGER,
    score_business INTEGER,
    score_negociation INTEGER,
    date_ajout TEXT NOT NULL,
    date_derniere_verification TEXT,
    actif INTEGER NOT NULL DEFAULT 1,
    UNIQUE(chat_id, lien)
)
""")

curseur.execute("""
CREATE TABLE IF NOT EXISTS alertes_baisse_favoris (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    lien TEXT NOT NULL,
    ancien_prix INTEGER,
    nouveau_prix INTEGER NOT NULL,
    variation INTEGER NOT NULL,
    signature TEXT NOT NULL,
    date_alerte TEXT NOT NULL,
    UNIQUE(signature)
)
""")

curseur.execute("""
CREATE TABLE IF NOT EXISTS opportunites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    lien TEXT NOT NULL,
    modele TEXT,
    source TEXT,
    prix INTEGER,
    benefice INTEGER,
    score_business INTEGER,
    score_negociation INTEGER,
    score_vendeur_presse INTEGER,
    baisse_prix INTEGER,
    date_detection TEXT NOT NULL,
    UNIQUE(chat_id, lien, date_detection)
)
""")

curseur.execute(
    "CREATE INDEX IF NOT EXISTS idx_statistiques_scans_date "
    "ON statistiques_scans(date_scan)"
)
curseur.execute(
    "CREATE INDEX IF NOT EXISTS idx_statistiques_scans_chat "
    "ON statistiques_scans(chat_id)"
)
curseur.execute(
    "CREATE INDEX IF NOT EXISTS idx_statistiques_scans_source "
    "ON statistiques_scans(source)"
)
curseur.execute(
    "CREATE INDEX IF NOT EXISTS idx_opportunites_chat_date "
    "ON opportunites(chat_id, date_detection)"
)
curseur.execute(
    "CREATE INDEX IF NOT EXISTS idx_opportunites_modele "
    "ON opportunites(modele)"
)
curseur.execute(
    "CREATE INDEX IF NOT EXISTS idx_opportunites_source "
    "ON opportunites(source)"
)
curseur.execute(
    "CREATE INDEX IF NOT EXISTS idx_opportunites_score_business "
    "ON opportunites(score_business)"
)
curseur.execute(
    "CREATE INDEX IF NOT EXISTS idx_opportunites_benefice "
    "ON opportunites(benefice)"
)
curseur.execute(
    "CREATE INDEX IF NOT EXISTS idx_favoris_chat_actif "
    "ON favoris(chat_id, actif)"
)
curseur.execute(
    "CREATE INDEX IF NOT EXISTS idx_historique_prix_lien "
    "ON historique_prix(lien)"
)

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

curseur.execute(
    """
    UPDATE annonces
    SET prix_initial = prix
    WHERE prix_initial IS NULL AND prix IS NOT NULL
    """
)
curseur.execute(
    """
    UPDATE annonces
    SET date_derniere_detection = date_premiere_detection
    WHERE date_derniere_detection IS NULL
    AND date_premiere_detection IS NOT NULL
    """
)
connexion.commit()


def annonce_existe(lien):
    curseur.execute(
        "SELECT 1 FROM annonces WHERE lien = ?",
        (lien,)
    )
    return curseur.fetchone() is not None


def recuperer_annonce(identifiant):
    if str(identifiant).isdigit():
        curseur.execute(
            """
            SELECT *
            FROM annonces
            WHERE id = ?
            """,
            (int(identifiant),)
        )
    else:
        curseur.execute(
            """
            SELECT *
            FROM annonces
            WHERE lien = ?
            """,
            (identifiant,)
        )

    ligne = curseur.fetchone()

    if ligne is None:
        return None

    colonnes = [description[0] for description in curseur.description]
    return dict(zip(colonnes, ligne))


def _prix_numerique(prix):
    if isinstance(prix, int):
        return prix

    if prix is None:
        return None

    chiffres = "".join(caractere for caractere in str(prix) if caractere.isdigit())

    if not chiffres:
        return None

    return int(chiffres)


def _date_iso_maintenant():
    return datetime.now().isoformat(timespec="seconds")


def _jours_depuis(date_iso):
    if not date_iso:
        return 0

    try:
        date_detection = datetime.fromisoformat(str(date_iso))
    except ValueError:
        return 0

    jours = (datetime.now() - date_detection).days
    return max(jours, 0)


def _texte_annonce(annonce):
    return " ".join(
        str(annonce.get(cle) or "")
        for cle in ("titre", "modele")
    ).lower()


def _score_mots_cles(annonce):
    texte = _texte_annonce(annonce)
    mots_cles = (
        "urgent",
        "à débattre",
        "a debattre",
        "départ",
        "depart",
        "besoin d’argent",
        "besoin d'argent",
        "prix à discuter",
        "prix a discuter",
        "premier arrivé",
        "premier arrive",
    )

    return 15 if any(mot in texte for mot in mots_cles) else 0


def _verdict_vendeur_presse(score):
    if score >= 70:
        return "vendeur probablement pressé"

    if score >= 40:
        return "probablement négociable"

    return "peu pressé"


def _conseil_negociation(score, baisse_totale, nombre_baisses):
    if score >= 70:
        return (
            "Prépare une offre ferme sous le prix affiché en rappelant "
            "les baisses déjà observées."
        )

    if score >= 40 or nombre_baisses > 0:
        return (
            "Tente une négociation mesurée, surtout si l'annonce reste active."
        )

    return "Reste prudent : peu de signes de pression vendeur pour l'instant."


def historique_prix(lien):
    curseur.execute(
        """
        SELECT ancien_prix, nouveau_prix, variation, date_changement
        FROM historique_prix
        WHERE lien = ?
        ORDER BY date_changement ASC, id ASC
        """,
        (lien,)
    )
    return [
        {
            "ancien_prix": ligne[0],
            "nouveau_prix": ligne[1],
            "variation": ligne[2],
            "date_changement": ligne[3],
        }
        for ligne in curseur.fetchall()
    ]


def analyser_pression_vendeur(identifiant):
    annonce = recuperer_annonce(identifiant)

    if annonce is None:
        return None

    historique = historique_prix(annonce["lien"])
    baisses = [ligne for ligne in historique if ligne["variation"] < 0]
    prix_initial = annonce.get("prix_initial") or annonce.get("prix")
    prix_actuel = annonce.get("prix")
    baisse_totale = sum(abs(ligne["variation"]) for ligne in baisses)
    nombre_baisses = len(baisses)
    jours = _jours_depuis(annonce.get("date_premiere_detection"))

    if prix_initial:
        baisse_pourcentage = round((baisse_totale / prix_initial) * 100, 2)
    else:
        baisse_pourcentage = 0

    score_baisses = min(nombre_baisses * 15, 30)
    score_importance = min(baisse_pourcentage * 1.2, 30)
    score_frequence = 0

    if nombre_baisses:
        score_frequence = min((nombre_baisses / max(jours, 1)) * 100, 20)

    if jours > 20:
        score_anciennete = 15
    elif jours >= 8:
        score_anciennete = 10
    elif jours >= 3:
        score_anciennete = 5
    else:
        score_anciennete = 0

    score = int(round(min(
        score_baisses
        + score_importance
        + score_frequence
        + score_anciennete
        + _score_mots_cles(annonce),
        100
    )))

    return {
        "annonce": annonce,
        "historique": historique,
        "baisses": baisses,
        "prix_initial": prix_initial,
        "prix_actuel": prix_actuel,
        "nombre_baisses": nombre_baisses,
        "baisse_totale": baisse_totale,
        "baisse_pourcentage": baisse_pourcentage,
        "jours_depuis_detection": jours,
        "score": score,
        "verdict": _verdict_vendeur_presse(score),
        "conseil": _conseil_negociation(score, baisse_totale, nombre_baisses),
        "alerte_speciale": (
            baisse_totale >= 1000
            or nombre_baisses >= 2
            or score >= 70
        ),
    }


def _enregistrer_changement_prix(lien, ancien_prix, nouveau_prix):
    variation = nouveau_prix - ancien_prix

    if variation == 0:
        return False

    curseur.execute(
        """
        INSERT INTO historique_prix (
            lien,
            ancien_prix,
            nouveau_prix,
            variation,
            date_changement
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            lien,
            ancien_prix,
            nouveau_prix,
            variation,
            _date_iso_maintenant()
        )
    )
    return True


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

    prix = _prix_numerique(prix)
    maintenant = _date_iso_maintenant()

    annonce_connue = recuperer_annonce(lien)

    if annonce_connue is not None:
        ancien_prix = _prix_numerique(annonce_connue.get("prix"))

        if ancien_prix is not None and prix is not None:
            _enregistrer_changement_prix(lien, ancien_prix, prix)

        curseur.execute(
            """
            UPDATE annonces
            SET prix = ?,
                date_derniere_detection = ?
            WHERE lien = ?
            """,
            (prix, maintenant, lien)
        )
        connexion.commit()
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
            date_premiere_detection,
            prix_initial,
            date_derniere_detection
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            maintenant,
            prix,
            maintenant
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
    date_scan=None,
    type_scan="surveillance",
    lot=None,
    source=None,
    alertes_envoyees=0,
    duree_secondes=None,
    meilleur_score_business=None,
):
    curseur.execute(
        """
        INSERT INTO statistiques_scans (
            chat_id,
            type_scan,
            recherche,
            lot,
            source,
            annonces_analysees,
            nouvelles_annonces,
            bonnes_affaires,
            alertes_envoyees,
            duree_secondes,
            meilleur_modele,
            meilleur_benefice,
            meilleur_score_business,
            date_scan
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chat_id,
            type_scan,
            recherche,
            lot,
            source,
            annonces_analysees,
            nouvelles_annonces,
            bonnes_affaires,
            alertes_envoyees,
            duree_secondes,
            meilleur_modele,
            meilleur_benefice,
            meilleur_score_business,
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


def activer_scanner_global(chat_id, prix_max=None):
    maintenant = _date_iso_maintenant()

    try:
        curseur.execute(
            """
            INSERT INTO scanner_global (
                chat_id,
                actif,
                prix_max,
                prochain_lot_index,
                date_activation,
                date_modification
            )
            VALUES (?, 1, ?, 0, ?, ?)
            """,
            (chat_id, prix_max, maintenant, maintenant)
        )
        connexion.commit()
        return True
    except sqlite3.IntegrityError:
        curseur.execute(
            """
            SELECT actif
            FROM scanner_global
            WHERE chat_id = ?
            """,
            (chat_id,)
        )
        ligne = curseur.fetchone()

        if ligne and ligne[0] == 1:
            return False

        curseur.execute(
            """
            UPDATE scanner_global
            SET actif = 1,
                prix_max = ?,
                date_activation = ?,
                date_modification = ?
            WHERE chat_id = ?
            """,
            (prix_max, maintenant, maintenant, chat_id)
        )
        connexion.commit()
        return True


def desactiver_scanner_global(chat_id):
    curseur.execute(
        """
        UPDATE scanner_global
        SET actif = 0,
            date_modification = ?
        WHERE chat_id = ? AND actif = 1
        """,
        (_date_iso_maintenant(), chat_id)
    )
    connexion.commit()
    return curseur.rowcount > 0


def statut_scanner_global(chat_id):
    curseur.execute(
        """
        SELECT chat_id, actif, prix_max, prochain_lot_index,
               date_activation, date_modification
        FROM scanner_global
        WHERE chat_id = ?
        """,
        (chat_id,)
    )
    ligne = curseur.fetchone()

    if ligne is None:
        return None

    return {
        "chat_id": ligne[0],
        "actif": bool(ligne[1]),
        "prix_max": ligne[2],
        "prochain_lot_index": ligne[3],
        "date_activation": ligne[4],
        "date_modification": ligne[5],
    }


def lister_scanners_globaux_actifs():
    curseur.execute(
        """
        SELECT chat_id, prix_max, prochain_lot_index
        FROM scanner_global
        WHERE actif = 1
        ORDER BY chat_id
        """
    )
    return [
        {
            "chat_id": ligne[0],
            "prix_max": ligne[1],
            "prochain_lot_index": ligne[2],
        }
        for ligne in curseur.fetchall()
    ]


def avancer_lot_scanner_global(chat_id, nombre_lots):
    statut = statut_scanner_global(chat_id)

    if statut is None:
        return 0

    prochain_index = (statut["prochain_lot_index"] + 1) % nombre_lots
    curseur.execute(
        """
        UPDATE scanner_global
        SET prochain_lot_index = ?,
            date_modification = ?
        WHERE chat_id = ?
        """,
        (prochain_index, _date_iso_maintenant(), chat_id)
    )
    connexion.commit()
    return prochain_index


def signature_opportunite_globale(lien, prix, score_business, baisse_totale):
    return f"{lien}|{prix}|{score_business}|{baisse_totale}"


def opportunite_globale_deja_envoyee(chat_id, lien, signature):
    curseur.execute(
        """
        SELECT 1
        FROM opportunites_globales_envoyees
        WHERE chat_id = ? AND lien = ? AND signature = ?
        """,
        (chat_id, lien, signature)
    )
    return curseur.fetchone() is not None


def enregistrer_opportunite_globale_envoyee(
    chat_id,
    lien,
    prix,
    score_business,
    baisse_totale,
    signature
):
    try:
        curseur.execute(
            """
            INSERT INTO opportunites_globales_envoyees (
                chat_id,
                lien,
                prix,
                score_business,
                baisse_totale,
                date_envoi,
                signature
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                lien,
                prix,
                score_business,
                baisse_totale,
                _date_iso_maintenant(),
                signature
            )
        )
        connexion.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def ajouter_favori(
    chat_id,
    lien,
    modele=None,
    prix=None,
    prix_initial=None,
    score_business=None,
    score_negociation=None,
):
    maintenant = _date_iso_maintenant()
    prix = _prix_numerique(prix)
    prix_initial = _prix_numerique(prix_initial) or prix

    try:
        curseur.execute(
            """
            INSERT INTO favoris (
                chat_id,
                lien,
                modele,
                prix,
                prix_initial,
                score_business,
                score_negociation,
                date_ajout,
                date_derniere_verification,
                actif
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                chat_id,
                lien,
                modele,
                prix,
                prix_initial,
                score_business,
                score_negociation,
                maintenant,
                maintenant,
            )
        )
        connexion.commit()
        return True
    except sqlite3.IntegrityError:
        curseur.execute(
            """
            UPDATE favoris
            SET actif = 1,
                modele = COALESCE(?, modele),
                prix = COALESCE(?, prix),
                prix_initial = COALESCE(prix_initial, ?),
                score_business = COALESCE(?, score_business),
                score_negociation = COALESCE(?, score_negociation),
                date_derniere_verification = ?
            WHERE chat_id = ? AND lien = ? AND actif = 0
            """,
            (
                modele,
                prix,
                prix_initial,
                score_business,
                score_negociation,
                maintenant,
                chat_id,
                lien,
            )
        )
        connexion.commit()
        return curseur.rowcount > 0


def supprimer_favori(chat_id, lien):
    curseur.execute(
        """
        UPDATE favoris
        SET actif = 0
        WHERE chat_id = ? AND lien = ? AND actif = 1
        """,
        (chat_id, lien)
    )
    connexion.commit()
    return curseur.rowcount > 0


def supprimer_favori_par_id(chat_id, favori_id):
    curseur.execute(
        """
        UPDATE favoris
        SET actif = 0
        WHERE chat_id = ? AND id = ? AND actif = 1
        """,
        (chat_id, favori_id)
    )
    connexion.commit()
    return curseur.rowcount > 0


def _favori_depuis_ligne(ligne):
    colonnes = [description[0] for description in curseur.description]
    return dict(zip(colonnes, ligne))


def lister_favoris(chat_id, actifs_seulement=True):
    requete = """
        SELECT *
        FROM favoris
        WHERE chat_id = ?
    """
    parametres = [chat_id]

    if actifs_seulement:
        requete += " AND actif = 1"

    requete += " ORDER BY date_ajout DESC, id DESC"
    curseur.execute(requete, parametres)
    return [_favori_depuis_ligne(ligne) for ligne in curseur.fetchall()]


def lister_favoris_actifs():
    curseur.execute(
        """
        SELECT *
        FROM favoris
        WHERE actif = 1
        ORDER BY chat_id, date_ajout DESC
        """
    )
    return [_favori_depuis_ligne(ligne) for ligne in curseur.fetchall()]


def obtenir_favori(chat_id, lien):
    curseur.execute(
        """
        SELECT *
        FROM favoris
        WHERE chat_id = ? AND lien = ?
        """,
        (chat_id, lien)
    )
    ligne = curseur.fetchone()
    return _favori_depuis_ligne(ligne) if ligne else None


def obtenir_favori_par_id(chat_id, favori_id):
    curseur.execute(
        """
        SELECT *
        FROM favoris
        WHERE chat_id = ? AND id = ?
        """,
        (chat_id, favori_id)
    )
    ligne = curseur.fetchone()
    return _favori_depuis_ligne(ligne) if ligne else None


def mettre_a_jour_favori(
    chat_id,
    lien,
    prix=None,
    score_business=None,
    score_negociation=None,
    modele=None,
):
    curseur.execute(
        """
        UPDATE favoris
        SET prix = COALESCE(?, prix),
            modele = COALESCE(?, modele),
            score_business = COALESCE(?, score_business),
            score_negociation = COALESCE(?, score_negociation),
            date_derniere_verification = ?
        WHERE chat_id = ? AND lien = ?
        """,
        (
            _prix_numerique(prix),
            modele,
            score_business,
            score_negociation,
            _date_iso_maintenant(),
            chat_id,
            lien,
        )
    )
    connexion.commit()
    return curseur.rowcount > 0


def signature_alerte_baisse_favori(chat_id, lien, nouveau_prix):
    return f"{chat_id}|{lien}|{nouveau_prix}"


def alerte_baisse_favori_deja_envoyee(signature):
    curseur.execute(
        """
        SELECT 1
        FROM alertes_baisse_favoris
        WHERE signature = ?
        """,
        (signature,)
    )
    return curseur.fetchone() is not None


def enregistrer_alerte_baisse_favori(
    chat_id,
    lien,
    ancien_prix,
    nouveau_prix,
    variation,
    signature,
):
    try:
        curseur.execute(
            """
            INSERT INTO alertes_baisse_favoris (
                chat_id,
                lien,
                ancien_prix,
                nouveau_prix,
                variation,
                signature,
                date_alerte
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                lien,
                ancien_prix,
                nouveau_prix,
                variation,
                signature,
                _date_iso_maintenant(),
            )
        )
        connexion.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def nombre_alertes_baisse_favori(chat_id, lien):
    curseur.execute(
        """
        SELECT COUNT(*)
        FROM alertes_baisse_favoris
        WHERE chat_id = ? AND lien = ?
        """,
        (chat_id, lien)
    )
    return curseur.fetchone()[0]


def _periode_sql(jours=None):
    if jours is None:
        return None

    return datetime.now().timestamp() - jours * 86400


def _debut_jour_iso():
    return datetime.now().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    ).isoformat(timespec="seconds")


def _debut_periode_iso(jours=None):
    if jours is None:
        return None

    return (
        datetime.now()
        .replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(days=jours - 1)
    ).isoformat(timespec="seconds")


def enregistrer_opportunite(
    chat_id,
    lien,
    modele=None,
    source=None,
    prix=None,
    benefice=None,
    score_business=None,
    score_negociation=None,
    score_vendeur_presse=None,
    baisse_prix=None,
    date_detection=None,
):
    try:
        curseur.execute(
            """
            INSERT OR IGNORE INTO opportunites (
                chat_id,
                lien,
                modele,
                source,
                prix,
                benefice,
                score_business,
                score_negociation,
                score_vendeur_presse,
                baisse_prix,
                date_detection
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                lien,
                modele,
                source,
                _prix_numerique(prix),
                _prix_numerique(benefice),
                score_business,
                score_negociation,
                score_vendeur_presse,
                _prix_numerique(baisse_prix) or 0,
                date_detection or _date_iso_maintenant(),
            )
        )
        connexion.commit()
        return curseur.rowcount > 0
    except sqlite3.IntegrityError:
        return False


def compter_favoris_actifs(chat_id):
    curseur.execute(
        """
        SELECT COUNT(*)
        FROM favoris
        WHERE chat_id = ? AND actif = 1
        """,
        (chat_id,)
    )
    return curseur.fetchone()[0]


def compter_surveillances_actives(chat_id):
    curseur.execute(
        """
        SELECT COUNT(*)
        FROM surveillances
        WHERE chat_id = ?
        """,
        (chat_id,)
    )
    return curseur.fetchone()[0]


def compter_alertes_favoris_depuis(chat_id, date_debut):
    curseur.execute(
        """
        SELECT COUNT(*)
        FROM alertes_baisse_favoris
        WHERE chat_id = ?
        AND date_alerte >= ?
        """,
        (chat_id, date_debut)
    )
    return curseur.fetchone()[0]


def dashboard_resume(chat_id):
    debut_jour = _debut_jour_iso()

    curseur.execute(
        """
        SELECT
            COALESCE(SUM(annonces_analysees), 0),
            COALESCE(SUM(nouvelles_annonces), 0),
            COALESCE(SUM(bonnes_affaires), 0),
            COALESCE(SUM(alertes_envoyees), 0),
            MAX(date_scan)
        FROM statistiques_scans
        WHERE chat_id = ?
        """,
        (chat_id,)
    )
    total, _nouvelles_total, _bonnes_total, _alertes_total, dernier_scan = (
        curseur.fetchone()
    )

    curseur.execute(
        """
        SELECT
            COALESCE(SUM(nouvelles_annonces), 0),
            COALESCE(SUM(bonnes_affaires), 0),
            COALESCE(SUM(alertes_envoyees), 0)
        FROM statistiques_scans
        WHERE chat_id = ?
        AND date_scan >= ?
        """,
        (chat_id, debut_jour)
    )
    nouvelles_jour, bonnes_jour, alertes_jour = curseur.fetchone()
    alertes_jour += compter_alertes_favoris_depuis(chat_id, debut_jour)

    curseur.execute(
        """
        SELECT
            COALESCE(SUM(benefice), 0),
            AVG(score_business)
        FROM opportunites
        WHERE chat_id = ?
        AND date_detection >= ?
        """,
        (chat_id, debut_jour)
    )
    marge_jour, score_moyen = curseur.fetchone()

    curseur.execute(
        """
        SELECT modele, benefice, score_business, lien
        FROM opportunites
        WHERE chat_id = ?
        ORDER BY score_business DESC, benefice DESC
        LIMIT 1
        """,
        (chat_id,)
    )
    meilleure = curseur.fetchone()
    statut = statut_scanner_global(chat_id)

    return {
        "annonces_total": total,
        "nouvelles_aujourdhui": nouvelles_jour,
        "bonnes_affaires_aujourdhui": bonnes_jour,
        "alertes_aujourdhui": alertes_jour,
        "favoris_actifs": compter_favoris_actifs(chat_id),
        "surveillances_actives": compter_surveillances_actives(chat_id),
        "scanner_global_actif": bool(statut and statut["actif"]),
        "dernier_scan": dernier_scan,
        "marge_potentielle_jour": marge_jour,
        "business_score_moyen_jour": round(score_moyen, 1) if score_moyen else 0,
        "meilleure_opportunite": {
            "modele": meilleure[0],
            "benefice": meilleure[1],
            "score_business": meilleure[2],
            "lien": meilleure[3],
        } if meilleure else None,
    }


def top_opportunites(chat_id, jours=None, limite=10, tri="score_business"):
    date_debut = _debut_periode_iso(jours)
    clauses = ["chat_id = ?"]
    params = [chat_id]

    if date_debut:
        clauses.append("date_detection >= ?")
        params.append(date_debut)

    tris = {
        "benefice": "benefice DESC, score_business DESC",
        "score_business": "score_business DESC, benefice DESC",
        "vendeur": "score_vendeur_presse DESC, score_business DESC",
        "baisse": "baisse_prix DESC, score_business DESC",
        "roi": (
            "CASE WHEN prix > 0 THEN CAST(benefice AS REAL) / prix "
            "ELSE 0 END DESC, score_business DESC"
        ),
    }
    ordre = tris.get(tri, tris["score_business"])
    params.append(limite)
    curseur.execute(
        f"""
        SELECT *
        FROM opportunites
        WHERE {' AND '.join(clauses)}
        ORDER BY {ordre}
        LIMIT ?
        """,
        params
    )
    colonnes = [description[0] for description in curseur.description]
    return [dict(zip(colonnes, ligne)) for ligne in curseur.fetchall()]


def stats_modele(chat_id, modele, jours=None):
    date_debut = _debut_periode_iso(jours)
    clauses = ["chat_id = ?", "LOWER(modele) LIKE ?"]
    params = [chat_id, f"%{modele.lower()}%"]

    if date_debut:
        clauses.append("date_detection >= ?")
        params.append(date_debut)

    curseur.execute(
        f"""
        SELECT prix, benefice, score_business, baisse_prix,
               modele, lien, date_detection
        FROM opportunites
        WHERE {' AND '.join(clauses)}
        ORDER BY date_detection ASC
        """,
        params
    )
    lignes = curseur.fetchall()

    if not lignes:
        return {
            "modele": modele,
            "nombre": 0,
            "prix_moyen": 0,
            "prix_median": 0,
            "prix_min": 0,
            "prix_max": 0,
            "benefice_moyen": 0,
            "score_business_moyen": 0,
            "bonnes_affaires": 0,
            "nombre_baisses": 0,
            "meilleure_annonce": None,
            "periode_debut": None,
            "periode_fin": None,
        }

    prix = sorted(ligne[0] for ligne in lignes if ligne[0] is not None)
    benefices = [ligne[1] for ligne in lignes if ligne[1] is not None]
    scores = [ligne[2] for ligne in lignes if ligne[2] is not None]
    baisses = [ligne[3] for ligne in lignes if ligne[3] and ligne[3] > 0]
    milieu = len(prix) // 2
    mediane = (
        prix[milieu]
        if len(prix) % 2
        else round((prix[milieu - 1] + prix[milieu]) / 2)
    ) if prix else 0
    meilleure = max(
        lignes,
        key=lambda ligne: ((ligne[2] or 0), (ligne[1] or 0))
    )

    return {
        "modele": modele,
        "nombre": len(lignes),
        "prix_moyen": round(sum(prix) / len(prix)) if prix else 0,
        "prix_median": mediane,
        "prix_min": min(prix) if prix else 0,
        "prix_max": max(prix) if prix else 0,
        "benefice_moyen": round(sum(benefices) / len(benefices)) if benefices else 0,
        "score_business_moyen": round(sum(scores) / len(scores), 1) if scores else 0,
        "bonnes_affaires": len([s for s in scores if s >= 80]),
        "nombre_baisses": len(baisses),
        "meilleure_annonce": {
            "modele": meilleure[4],
            "lien": meilleure[5],
            "score_business": meilleure[2],
            "benefice": meilleure[1],
        },
        "periode_debut": lignes[0][6],
        "periode_fin": lignes[-1][6],
    }


def stats_sources():
    curseur.execute(
        """
        SELECT
            source,
            COALESCE(SUM(annonces_analysees), 0),
            COALESCE(SUM(nouvelles_annonces), 0),
            COALESCE(SUM(bonnes_affaires), 0),
            AVG(duree_secondes),
            MAX(CASE WHEN annonces_analysees > 0 THEN date_scan END),
            MAX(CASE WHEN annonces_analysees = 0 THEN date_scan END),
            SUM(CASE WHEN annonces_analysees = 0 THEN 1 ELSE 0 END)
        FROM statistiques_scans
        WHERE source IS NOT NULL
        GROUP BY source
        ORDER BY source
        """
    )
    return [
        {
            "source": ligne[0],
            "annonces_recuperees": ligne[1],
            "annonces_pertinentes": ligne[2],
            "bonnes_affaires": ligne[3],
            "erreurs": ligne[7],
            "temps_moyen": round(ligne[4], 2) if ligne[4] is not None else None,
            "derniere_reussite": ligne[5],
            "dernier_echec": ligne[6],
        }
        for ligne in curseur.fetchall()
    ]


def series_dashboard(chat_id, jours=30):
    date_debut = _debut_periode_iso(jours)
    curseur.execute(
        """
        SELECT substr(date_detection, 1, 10), COUNT(*),
               COALESCE(SUM(benefice), 0), AVG(score_business)
        FROM opportunites
        WHERE chat_id = ?
        AND date_detection >= ?
        GROUP BY substr(date_detection, 1, 10)
        ORDER BY substr(date_detection, 1, 10)
        """,
        (chat_id, date_debut)
    )
    return [
        {
            "date": ligne[0],
            "opportunites": ligne[1],
            "marge": ligne[2],
            "score_business_moyen": round(ligne[3], 1) if ligne[3] else 0,
        }
        for ligne in curseur.fetchall()
    ]
