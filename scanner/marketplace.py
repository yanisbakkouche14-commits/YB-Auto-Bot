import argparse
import json
import logging
import os
import re
import sys
import traceback
from datetime import datetime
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.facebook.com"
SEARCH_URL = f"{BASE_URL}/marketplace/search/"
MAX_ANNONCES = 20
TIMEOUT = 10
SEUIL_ECHECS = 3
TEST_SANTE_RECHERCHE = "golf"
LOCAL_SERVICE_URL = os.getenv("MARKETPLACE_LOCAL_URL", "").strip().rstrip("/")
LOCAL_SERVICE_TOKEN = os.getenv("MARKETPLACE_LOCAL_TOKEN", "").strip()
LOCAL_SERVICE_TIMEOUT = 12

logger = logging.getLogger(__name__)

_DERNIER_DIAGNOSTIC_LOCAL = None

_ETAT = {
    "actif": True,
    "desactive_temporairement": False,
    "derniere_reussite": None,
    "derniere_erreur": None,
    "echecs_consecutifs": 0,
    "notification_panne_envoyee": False,
    "notification_retour_envoyee": False,
    "retablissement_a_notifier": False,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/137.0 Safari/537.36"
    ),
    "Accept-Language": "fr-BE,fr;q=0.9,en;q=0.8",
}


class MarketplaceIndisponible(RuntimeError):
    pass


class MarketplaceAuthentificationRequise(MarketplaceIndisponible):
    pass


def _diagnostic_vide():
    return {
        "local_url_definie": bool(LOCAL_SERVICE_URL),
        "local_token_defini": bool(LOCAL_SERVICE_TOKEN),
        "authorization_header_present": False,
        "authorization_header_format": None,
        "authorization_header_final_present": None,
        "authorization_header_final_format": None,
        "url_appelee": None,
        "url_finale": None,
        "historique_redirections": [],
        "code_http": None,
        "ok_recu": None,
        "annonces_brut_nombre": None,
        "annonces_type": None,
        "annonces_normalisees": 0,
        "annonces_rejetees": 0,
        "raisons_rejet": [],
        "nombre_final_retourne": 0,
        "erreur": None,
        "traceback": None,
    }


def _historique_redirections(reponse):
    return [
        {
            "code_http": etape.status_code,
            "url": etape.url,
        }
        for etape in getattr(reponse, "history", [])
    ]


def _apercu_reponse(reponse):
    texte = getattr(reponse, "text", "") or ""
    return texte[:300].replace("\n", " ").replace("\r", " ")


def _logger_diagnostic_local(diagnostic):
    global _DERNIER_DIAGNOSTIC_LOCAL

    _DERNIER_DIAGNOSTIC_LOCAL = dict(diagnostic)
    logger.info(
        "Facebook Marketplace diagnostic local: local_url_definie=%s "
        "token_present=%s authorization_header_present=%s "
        "authorization_header_format=%s authorization_header_final_present=%s "
        "authorization_header_final_format=%s url_appelee=%s code_http=%s "
        "url_finale=%s redirections=%s ok_recu=%s annonces_brut=%s "
        "annonces_type=%s rejetees=%s finales=%s",
        diagnostic["local_url_definie"],
        diagnostic["local_token_defini"],
        diagnostic["authorization_header_present"],
        diagnostic["authorization_header_format"],
        diagnostic["authorization_header_final_present"],
        diagnostic["authorization_header_final_format"],
        diagnostic["url_appelee"],
        diagnostic["code_http"],
        diagnostic["url_finale"],
        diagnostic["historique_redirections"],
        diagnostic["ok_recu"],
        diagnostic["annonces_brut_nombre"],
        diagnostic["annonces_type"],
        diagnostic["annonces_rejetees"],
        diagnostic["nombre_final_retourne"],
    )


def _erreur_diagnostic(diagnostic, code, erreur, reponse=None):
    global _DERNIER_DIAGNOSTIC_LOCAL

    diagnostic["erreur"] = {
        "code": code,
        "type": type(erreur).__name__,
        "message": str(erreur),
    }
    exception_active = sys.exc_info()[0] is not None
    diagnostic["traceback"] = (
        traceback.format_exc()
        if exception_active
        else "".join(traceback.format_stack(limit=8))
    )

    if reponse is not None:
        diagnostic["code_http"] = getattr(reponse, "status_code", None)
        diagnostic["url_finale"] = getattr(reponse, "url", None)
        diagnostic["historique_redirections"] = _historique_redirections(reponse)
        diagnostic["apercu_reponse"] = _apercu_reponse(reponse)

    message_log = (
        "Facebook Marketplace service local erreur: code=%s type=%s message=%s "
        "url_appelee=%s code_http=%s url_finale=%s apercu_reponse=%s"
    )
    arguments_log = (
        code,
        type(erreur).__name__,
        erreur,
        diagnostic["url_appelee"],
        diagnostic["code_http"],
        diagnostic["url_finale"],
        diagnostic.get("apercu_reponse"),
    )

    if exception_active:
        logger.exception(message_log, *arguments_log)
    else:
        logger.error(message_log, *arguments_log)
    _DERNIER_DIAGNOSTIC_LOCAL = dict(diagnostic)


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


def etat_marketplace():
    return dict(_ETAT)


def reinitialiser_etat_marketplace():
    _ETAT.update({
        "actif": True,
        "desactive_temporairement": False,
        "derniere_reussite": None,
        "derniere_erreur": None,
        "echecs_consecutifs": 0,
        "notification_panne_envoyee": False,
        "notification_retour_envoyee": False,
        "retablissement_a_notifier": False,
    })


def _enregistrer_reussite(etait_desactive=None):
    if etait_desactive is None:
        etait_desactive = _ETAT["desactive_temporairement"]

    _ETAT.update({
        "actif": True,
        "desactive_temporairement": False,
        "derniere_reussite": _maintenant(),
        "derniere_erreur": None,
        "echecs_consecutifs": 0,
    })

    if etait_desactive:
        _ETAT["notification_retour_envoyee"] = False
        _ETAT["notification_panne_envoyee"] = False
        _ETAT["retablissement_a_notifier"] = True


def _enregistrer_echec(erreur):
    _ETAT["derniere_erreur"] = str(erreur)
    _ETAT["echecs_consecutifs"] += 1
    logger.warning("Facebook Marketplace erreur: %s", erreur)

    if _ETAT["echecs_consecutifs"] >= SEUIL_ECHECS:
        _ETAT["actif"] = False
        _ETAT["desactive_temporairement"] = True


def panne_a_notifier():
    return (
        _ETAT["desactive_temporairement"]
        and not _ETAT["notification_panne_envoyee"]
    )


def retour_a_notifier():
    return (
        _ETAT["retablissement_a_notifier"]
        and not _ETAT["notification_retour_envoyee"]
    )


def marquer_notification_panne_envoyee():
    _ETAT["notification_panne_envoyee"] = True


def marquer_notification_retour_envoyee():
    _ETAT["notification_retour_envoyee"] = True
    _ETAT["retablissement_a_notifier"] = False


def _session():
    session = requests.Session()
    session.headers.update(HEADERS)
    cookie = os.getenv("FACEBOOK_COOKIE")

    if cookie:
        session.headers.update({"Cookie": cookie})

    return session


def _construire_url(modele):
    return f"{SEARCH_URL}?query={quote_plus(modele)}&exact=false"


def _valeur_renseignee(valeur):
    if valeur is None:
        return False

    texte = str(valeur).strip()

    return bool(texte) and texte.lower() not in {
        "inconnu",
        "inconnue",
        "non renseigne",
        "non renseigné",
        "n/a",
        "none",
    }


def _normaliser_champ(valeur, remplacement):
    return valeur if _valeur_renseignee(valeur) else remplacement


def _lien_valide(lien):
    if not lien:
        return False

    try:
        resultat = urlparse(str(lien).strip())
    except ValueError:
        return False

    return resultat.scheme in {"http", "https"} and bool(resultat.netloc)


def _titre_ressemble_ville(titre, ville):
    titre_normalise = re.sub(r"\s+", " ", str(titre or "").strip()).lower()
    ville_normalisee = re.sub(r"\s+", " ", str(ville or "").strip()).lower()

    villes_connues = {
        "anderlecht",
        "anvers",
        "antwerpen",
        "bruges",
        "bruxelles",
        "brussels",
        "charleroi",
        "gand",
        "gent",
        "liege",
        "liège",
        "louvain",
        "mons",
        "namur",
        "tournai",
        "wavre",
    }

    if not titre_normalise:
        return False

    return (
        titre_normalise == ville_normalisee
        or titre_normalise in villes_connues
    )


def _annonce_service_local(annonce, modele):
    ville = _normaliser_champ(annonce.get("ville"), "Non renseigné")
    titre = str(annonce.get("titre") or "").strip()

    return {
        "source": "Facebook Marketplace",
        "pays": "Belgique",
        "modele": titre,
        "titre": titre,
        "prix": _normaliser_champ(annonce.get("prix"), "Non renseigné"),
        "kilometrage": _normaliser_champ(
            annonce.get("kilometrage"),
            "Non renseigné"
        ),
        "annee": _normaliser_champ(annonce.get("annee"), "Non renseignée"),
        "ville": ville,
        "localisation": ville,
        "lien": str(annonce.get("lien") or "").strip(),
        "titre_incomplet": _titre_ressemble_ville(titre, ville),
    }


def _rechercher_service_local_avec_diagnostic(modele):
    diagnostic = _diagnostic_vide()

    if not LOCAL_SERVICE_URL:
        _logger_diagnostic_local(diagnostic)
        return None, diagnostic

    headers = {}

    if LOCAL_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {LOCAL_SERVICE_TOKEN}"
        diagnostic["authorization_header_present"] = True
        diagnostic["authorization_header_format"] = "Bearer <token>"

    url = f"{LOCAL_SERVICE_URL}/marketplace"
    diagnostic["url_appelee"] = url
    reponse = None

    try:
        reponse = requests.get(
            url,
            params={"modele": modele, "limite": MAX_ANNONCES},
            headers=headers,
            timeout=LOCAL_SERVICE_TIMEOUT
        )
        diagnostic["code_http"] = reponse.status_code
        diagnostic["url_finale"] = reponse.url
        diagnostic["historique_redirections"] = _historique_redirections(reponse)
        authorization_final = getattr(
            getattr(reponse, "request", None),
            "headers",
            {},
        ).get("Authorization")
        diagnostic["authorization_header_final_present"] = bool(authorization_final)
        diagnostic["authorization_header_final_format"] = (
            "Bearer <token>"
            if str(authorization_final or "").startswith("Bearer ")
            else None
        )
        logger.info(
            "Facebook Marketplace service local: url=%s code_http=%s "
            "taille_reponse=%s",
            reponse.url,
            reponse.status_code,
            len(reponse.text or "")
        )
        if reponse.status_code in {401, 403, 404, 502}:
            erreur_http = MarketplaceIndisponible(
                f"service local Marketplace HTTP {reponse.status_code}"
            )
            _erreur_diagnostic(
                diagnostic,
                f"HTTP_{reponse.status_code}",
                erreur_http,
                reponse=reponse,
            )
            raise erreur_http

        donnees = reponse.json()
    except requests.exceptions.Timeout as erreur:
        _erreur_diagnostic(diagnostic, "TIMEOUT", erreur)
        raise MarketplaceIndisponible(
            f"service local Marketplace timeout: {erreur}"
        ) from erreur
    except requests.exceptions.RequestException as erreur:
        _erreur_diagnostic(diagnostic, "REQUEST_ERROR", erreur)
        raise MarketplaceIndisponible(
            f"service local Marketplace indisponible: {erreur}"
        ) from erreur
    except ValueError as erreur:
        _erreur_diagnostic(diagnostic, "JSON_INVALIDE", erreur, reponse=reponse)
        raise MarketplaceIndisponible(
            "service local Marketplace réponse JSON invalide"
        ) from erreur

    diagnostic["ok_recu"] = donnees.get("ok")

    if not donnees.get("ok"):
        erreur = (
            donnees.get("message")
            or donnees.get("erreur")
            or "service local Marketplace indisponible"
        )

        if "session facebook expirée" in erreur.lower():
            exception = MarketplaceAuthentificationRequise(erreur)
            _erreur_diagnostic(diagnostic, "AUTH_REQUISE", exception)
            raise exception

        exception = MarketplaceIndisponible(erreur)
        _erreur_diagnostic(diagnostic, "OK_FALSE", exception, reponse=reponse)
        raise exception

    annonces_brutes = donnees.get("annonces", [])
    diagnostic["annonces_type"] = type(annonces_brutes).__name__

    if annonces_brutes is None:
        annonces_brutes = []

    if not isinstance(annonces_brutes, list):
        exception = MarketplaceIndisponible(
            f"structure inattendue: annonces est {type(annonces_brutes).__name__}"
        )
        _erreur_diagnostic(diagnostic, "STRUCTURE_INATTENDUE", exception)
        raise exception

    diagnostic["annonces_brut_nombre"] = len(annonces_brutes)
    annonces_recues = annonces_brutes[:MAX_ANNONCES]
    annonces = []
    rejets = []

    for index, annonce in enumerate(annonces_recues, start=1):
        if not isinstance(annonce, dict):
            rejets.append((index, f"annonce non objet: {type(annonce).__name__}"))
            continue

        normalisee = _annonce_service_local(annonce, modele)

        if not _lien_valide(normalisee["lien"]):
            rejets.append((index, "lien absent ou invalide"))
            continue

        if not normalisee["titre"]:
            rejets.append((index, "titre vide"))
            continue

        annonces.append(normalisee)

    for index, raison in rejets:
        diagnostic["raisons_rejet"].append({"index": index, "raison": raison})
        logger.info(
            "Facebook Marketplace service local: annonce_rejetee=%s raison=%s",
            index,
            raison
        )

    diagnostic["annonces_normalisees"] = len(annonces_recues)
    diagnostic["annonces_rejetees"] = len(rejets)
    diagnostic["nombre_final_retourne"] = len(annonces)
    logger.info(
        "Facebook Marketplace service local: recues=%s rejetees=%s finales=%s",
        len(annonces_recues),
        len(rejets),
        len(annonces)
    )
    _logger_diagnostic_local(diagnostic)
    return annonces, diagnostic


def _rechercher_service_local(modele):
    annonces, _diagnostic = _rechercher_service_local_avec_diagnostic(modele)
    return annonces


def _titre_page(soup):
    titre = soup.select_one("title")
    return titre.get_text(" ", strip=True) if titre else "Inconnu"


def _diagnostic_html(soup, html, status_code=None):
    html_min = (html or "").lower()
    texte = soup.get_text(" ", strip=True).lower()
    titre = _titre_page(soup)
    diagnostic = {
        "code_http": status_code,
        "taille_html": len(html or ""),
        "titre_page": titre,
        "login": any(
            mot in texte or mot in html_min
            for mot in (
                "login",
                "connectez-vous",
                "se connecter",
                "log in to facebook",
            )
        ),
        "checkpoint": "checkpoint" in texte or "checkpoint" in html_min,
        "captcha": "captcha" in texte or "captcha" in html_min,
        "marketplace": "marketplace" in texte or "marketplace" in html_min,
    }
    logger.info(
        "Facebook Marketplace diagnostic: code_http=%s taille_html=%s "
        "titre_page=%r login=%s checkpoint=%s captcha=%s marketplace=%s",
        diagnostic["code_http"],
        diagnostic["taille_html"],
        diagnostic["titre_page"],
        diagnostic["login"],
        diagnostic["checkpoint"],
        diagnostic["captcha"],
        diagnostic["marketplace"],
    )
    return diagnostic


def _nombre(texte):
    valeur = re.sub(r"\D", "", texte or "")
    return int(valeur) if valeur else "Inconnu"


def _prix(texte):
    match = re.search(
        r"(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{3,6})\s*(?:€|eur|â‚¬|Ã¢â€šÂ¬)|"
        r"(?:€|eur|â‚¬|Ã¢â€šÂ¬)\s*(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{3,6})",
        texte or "",
        re.IGNORECASE
    )

    if not match:
        candidats = re.findall(
            r"(?<!\d)(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{3,6})(?!\d)",
            re.sub(r"\b(19|20)\d{2}\b", "", texte or "")
        )

        for candidat in candidats:
            prix = _nombre(candidat)

            if isinstance(prix, int) and prix >= 500:
                return prix

        return "Inconnu"

    return _nombre(match.group(1) or match.group(2))


def _annee(texte):
    match = re.search(r"\b(19|20)\d{2}\b", texte or "")
    return match.group(0) if match else "Inconnu"


def _kilometrage(texte):
    matchs = re.findall(
        r"(?<!\d)(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6})\s*km",
        texte or "",
        re.IGNORECASE
    )
    return _nombre(matchs[-1]) if matchs else "Inconnu"


def _ville(texte):
    villes = (
        "Bruxelles",
        "Charleroi",
        "Liège",
        "LiÃ¨ge",
        "Liege",
        "Li?ge",
        "Namur",
        "Mons",
        "Anvers",
        "Antwerpen",
        "Gand",
        "Gent",
    )

    for ville in villes:
        if ville.lower() in (texte or "").lower():
            return "Liège" if ville in ("Liege", "LiÃ¨ge") else ville

    return "Belgique"


def _detecter_blocage(soup, html, diagnostic=None):
    diagnostic = diagnostic or _diagnostic_html(soup, html)
    texte = soup.get_text(" ", strip=True).lower()

    if diagnostic["checkpoint"]:
        raise MarketplaceIndisponible("checkpoint Facebook detecte")

    if diagnostic["captcha"]:
        raise MarketplaceIndisponible("captcha Facebook detecte")

    if diagnostic["login"]:
        raise MarketplaceAuthentificationRequise(
            "Facebook nécessite une authentification pour afficher Marketplace"
        )

    if not texte.strip():
        raise MarketplaceIndisponible("page vide")


def _annonce(titre, texte, lien, modele):
    titre = titre or modele
    ville = _ville(texte)

    return {
        "source": "Facebook Marketplace",
        "pays": "Belgique",
        "modele": titre,
        "titre": titre,
        "prix": _prix(texte),
        "kilometrage": _kilometrage(texte),
        "annee": _annee(texte),
        "ville": ville,
        "localisation": ville,
        "lien": lien,
    }


def _extraire_donnees_structurees(soup, modele):
    annonces = []

    for script in soup.select("script[type='application/ld+json']"):
        try:
            donnees = json.loads(script.get_text(" ", strip=True))
        except json.JSONDecodeError:
            continue

        items = donnees if isinstance(donnees, list) else [donnees]

        for item in items:
            if not isinstance(item, dict):
                continue

            lien = item.get("url")
            titre = item.get("name")
            texte = " ".join(
                str(valeur)
                for valeur in (
                    titre,
                    item.get("description"),
                    item.get("price"),
                    item.get("offers", {}).get("price")
                    if isinstance(item.get("offers"), dict) else None,
                )
                if valeur
            )

            if lien and titre:
                annonces.append(_annonce(titre, texte, urljoin(BASE_URL, lien), modele))

    return annonces


def _extraire_selecteurs(soup, modele, selecteurs):
    annonces = []
    liens_vus = set()

    for selecteur in selecteurs:
        for carte in soup.select(selecteur):
            lien_element = (
                carte
                if getattr(carte, "name", None) == "a"
                else carte.select_one("a[href*='/marketplace/item/']")
            )
            lien = urljoin(BASE_URL, lien_element.get("href")) if lien_element else ""
            texte = carte.get_text(" ", strip=True)

            if not lien or len(texte) < 8 or lien in liens_vus:
                continue

            liens_vus.add(lien)
            titre = _titre(carte, texte, modele)
            annonces.append(_annonce(titre, texte, lien, modele))

            if len(annonces) >= MAX_ANNONCES:
                return annonces

    return annonces


def _extraire_navigateur_automatise(_modele):
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return []

    logger.info(
        "Playwright disponible, mais le navigateur automatise Marketplace "
        "n'est pas active dans cette version pour eviter login/captcha."
    )
    return []


def _titre(carte, texte, modele):
    for selecteur in ("span[dir='auto']", "h2", "h3"):
        element = carte.select_one(selecteur)

        if element:
            titre = element.get_text(" ", strip=True)

            if titre and "€" not in titre and "â‚¬" not in titre:
                return titre[:120]

    lignes = [ligne.strip() for ligne in re.split(r"\s{2,}|\n|\r", texte) if ligne.strip()]

    for ligne in lignes:
        if "€" not in ligne and "â‚¬" not in ligne and len(ligne) > 4:
            return ligne[:120]

    return modele


def _extraire_annonces(html, modele, status_code=None):
    soup = BeautifulSoup(html, "html.parser")
    diagnostic = _diagnostic_html(soup, html, status_code=status_code)
    _detecter_blocage(soup, html, diagnostic=diagnostic)

    strategies = [
        ("donnees_structurees", _extraire_donnees_structurees(soup, modele)),
        (
            "selecteurs_principaux",
            _extraire_selecteurs(
                soup,
                modele,
                ("a[href*='/marketplace/item/']",),
            ),
        ),
        (
            "selecteurs_secours",
            _extraire_selecteurs(
                soup,
                modele,
                ("[role='article']", "div[data-testid*='marketplace']"),
            ),
        ),
        ("navigateur_automatise", _extraire_navigateur_automatise(modele)),
    ]

    for nom, annonces in strategies:
        logger.info(
            "Facebook Marketplace strategie=%s annonces=%s",
            nom,
            len(annonces)
        )
        if annonces:
            return annonces[:MAX_ANNONCES]

    raise MarketplaceIndisponible("structure HTML Marketplace inconnue")


def rechercher_voitures(modele, ignorer_desactivation=False):
    if _ETAT["desactive_temporairement"] and not ignorer_desactivation:
        logger.warning("Facebook Marketplace desactive temporairement.")
        return []

    if LOCAL_SERVICE_URL:
        try:
            annonces = _rechercher_service_local(modele)
            _enregistrer_reussite()
            return annonces
        except MarketplaceAuthentificationRequise as erreur:
            logger.warning("%s", erreur)
            _enregistrer_echec(erreur)
            return []
        except MarketplaceIndisponible as erreur:
            logger.warning(
                "Facebook Marketplace service local indisponible: %s",
                erreur
            )
            _enregistrer_echec(erreur)
            return []

    url = _construire_url(modele)

    try:
        reponse = _session().get(url, timeout=TIMEOUT)
        logger.info(
            "Facebook Marketplace requete: url=%s code_http=%s taille_html=%s",
            url,
            reponse.status_code,
            len(reponse.text or "")
        )
        reponse.raise_for_status()
        annonces = _extraire_annonces(
            reponse.text,
            modele,
            status_code=reponse.status_code
        )
        _enregistrer_reussite()
        return annonces
    except requests.exceptions.Timeout as erreur:
        _enregistrer_echec(f"timeout: {erreur}")
        return []
    except requests.exceptions.RequestException as erreur:
        _enregistrer_echec(f"inaccessible: {erreur}")
        return []
    except MarketplaceAuthentificationRequise as erreur:
        logger.warning("%s", erreur)
        _enregistrer_echec(erreur)
        return []
    except MarketplaceIndisponible as erreur:
        logger.warning("Facebook Marketplace indisponible: %s", erreur)
        _enregistrer_echec(erreur)
        return []


def tester_sante():
    etait_desactive = _ETAT["desactive_temporairement"]

    annonces = rechercher_voitures(
        TEST_SANTE_RECHERCHE,
        ignorer_desactivation=True
    )
    succes = bool(annonces)

    if succes:
        _enregistrer_reussite(etait_desactive=etait_desactive)
        return True

    if etait_desactive:
        _ETAT["desactive_temporairement"] = True
        _ETAT["actif"] = False

    return False


def diagnostic_service_local(modele):
    try:
        annonces, diagnostic = _rechercher_service_local_avec_diagnostic(modele)
        diagnostic["nombre_final_retourne"] = len(annonces or [])
        return diagnostic
    except MarketplaceIndisponible as erreur:
        diagnostic = dict(_DERNIER_DIAGNOSTIC_LOCAL or _diagnostic_vide())
        diagnostic["local_url_definie"] = bool(LOCAL_SERVICE_URL)
        diagnostic["local_token_defini"] = bool(LOCAL_SERVICE_TOKEN)
        if not diagnostic.get("erreur"):
            diagnostic["erreur"] = {
                "code": "MARKETPLACE_INDISPONIBLE",
                "type": type(erreur).__name__,
                "message": str(erreur),
            }
            diagnostic["traceback"] = traceback.format_exc()
        logger.exception(
            "Facebook Marketplace diagnostic CLI erreur: type=%s message=%s",
            type(erreur).__name__,
            erreur,
        )
        return diagnostic


def _main_cli():
    parser = argparse.ArgumentParser(
        description="Diagnostic du scanner Facebook Marketplace."
    )
    parser.add_argument(
        "--diagnostic",
        metavar="MODELE",
        help="Appelle le service Marketplace local avec le meme code que Railway.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")

    if args.diagnostic:
        diagnostic = diagnostic_service_local(args.diagnostic)
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    _main_cli()
