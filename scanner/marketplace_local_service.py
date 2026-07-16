import argparse
import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse


BASE_URL = "https://www.facebook.com"
MAX_ANNONCES = 20
TIMEOUT_MS = 10000
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_PROFILE_DIR = "local_facebook_profile"
ENV_PROFILE_DIR = "MARKETPLACE_PROFILE_DIR"
ENV_BROWSER_EXECUTABLE = "MARKETPLACE_BROWSER_EXECUTABLE"
ENV_HEADLESS = "MARKETPLACE_HEADLESS"

logger = logging.getLogger("marketplace_local_service")


class MarketplaceLocalError(RuntimeError):
    def __init__(self, code, message, etape, diagnostic=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.etape = etape
        self.diagnostic = diagnostic or {}


def _env_token():
    return os.getenv("MARKETPLACE_LOCAL_TOKEN", "").strip()


def _profile_dir():
    return Path(os.getenv(ENV_PROFILE_DIR, DEFAULT_PROFILE_DIR)).expanduser().resolve()


def _browser_executable():
    executable = os.getenv(ENV_BROWSER_EXECUTABLE, "").strip()
    return Path(executable).expanduser().resolve() if executable else None


def _headless():
    return os.getenv(ENV_HEADLESS, "").strip().lower() in ("1", "true", "yes", "on")


def _systeme():
    return "windows" if os.name == "nt" else "linux"


def _est_linux():
    return os.name != "nt"


def _profil_existe():
    profil = _profile_dir()

    if not profil.exists() or not profil.is_dir():
        return False

    try:
        return any(profil.iterdir())
    except OSError:
        return False


def _verifier_navigateur_configure():
    executable = _browser_executable()

    if executable and not executable.exists():
        raise MarketplaceLocalError(
            "BROWSER_MISSING",
            "Navigateur Chromium introuvable. Vérifie MARKETPLACE_BROWSER_EXECUTABLE.",
            "lancement Playwright",
            {
                "browser_configure": str(executable),
                "variable": ENV_BROWSER_EXECUTABLE,
            },
        )

    return executable


def _nombre(texte):
    valeur = re.sub(r"\D", "", texte or "")
    return int(valeur) if valeur else "Inconnu"


def _prix(texte):
    match = re.search(
        r"(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{3,6})\s*(?:€|eur|â‚¬)|"
        r"(?:€|eur|â‚¬)\s*(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{3,6})",
        texte or "",
        re.IGNORECASE
    )

    if not match:
        return "Inconnu"

    return _nombre(match.group(1) or match.group(2))


def _annee(texte):
    match = re.search(r"\b(19|20)\d{2}\b", texte or "")
    return match.group(0) if match else "Inconnu"


def _kilometrage(texte):
    match = re.search(
        r"(?<!\d)(\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6})\s*km",
        texte or "",
        re.IGNORECASE
    )
    return _nombre(match.group(1)) if match else "Inconnu"


def _ville(texte):
    villes = (
        "Bruxelles",
        "Charleroi",
        "Liège",
        "Liege",
        "Namur",
        "Mons",
        "Anvers",
        "Antwerpen",
        "Gand",
        "Gent",
    )

    for ville in villes:
        if ville.lower() in (texte or "").lower():
            return "Liège" if ville == "Liege" else ville

    return "Belgique"


def _titre(texte, modele):
    lignes = [
        ligne.strip()
        for ligne in re.split(r"\n|\r|\s{2,}", texte or "")
        if ligne.strip()
    ]

    for ligne in lignes:
        if "€" not in ligne and "eur" not in ligne.lower() and len(ligne) > 4:
            return ligne[:120]

    return modele


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise MarketplaceLocalError(
            "PLAYWRIGHT_MISSING",
            "Playwright est absent ou impossible à charger sur cet appareil.",
            "lancement Playwright",
            {"type_exception": type(exc).__name__},
        ) from exc

    return sync_playwright


def _options_contexte(headless=None):
    executable = _verifier_navigateur_configure()
    options = {
        "user_data_dir": str(_profile_dir()),
        "headless": _headless() if headless is None else bool(headless),
        "viewport": {"width": 1366, "height": 900},
    }

    if executable:
        options["executable_path"] = str(executable)

    if _est_linux():
        options["args"] = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]

    return options


def _diagnostic_page(page, etape, nombre_cartes=None):
    diagnostic = {
        "etape": etape,
        "url_finale": "Inconnu",
        "titre_page": "Inconnu",
        "login_detecte": False,
        "checkpoint_detecte": False,
        "captcha_detecte": False,
        "checkpoint_mot_html": False,
        "captcha_mot_html": False,
        "checkpoint_blocage_visible": False,
        "captcha_blocage_visible": False,
        "marketplace_detecte": False,
        "nombre_cartes_marketplace": nombre_cartes,
    }

    try:
        diagnostic["url_finale"] = page.url
    except Exception:
        pass

    try:
        diagnostic["titre_page"] = page.title()
    except Exception:
        pass

    try:
        html = page.content().lower()
    except Exception:
        html = ""

    try:
        texte = page.locator("body").inner_text(timeout=2000).lower()
    except Exception:
        texte = ""

    url = str(diagnostic["url_finale"]).lower()
    titre = str(diagnostic["titre_page"]).lower()
    contenu_visible = " ".join([url, titre, texte])

    diagnostic["login_detecte"] = (
        "login" in url
        or "connectez-vous" in contenu_visible
        or "se connecter" in contenu_visible
        or "log in to facebook" in contenu_visible
    )
    diagnostic["checkpoint_mot_html"] = "checkpoint" in html
    diagnostic["captcha_mot_html"] = "captcha" in html
    diagnostic["marketplace_detecte"] = "marketplace" in " ".join([
        url,
        titre,
        html,
        texte,
    ])

    if nombre_cartes is None:
        try:
            diagnostic["nombre_cartes_marketplace"] = page.locator(
                "a[href*='/marketplace/item/']"
            ).count()
        except Exception:
            diagnostic["nombre_cartes_marketplace"] = None

    diagnostic["checkpoint_blocage_visible"] = _checkpoint_visible(
        page,
        url,
        titre,
        texte
    )
    diagnostic["captcha_blocage_visible"] = _captcha_visible(
        page,
        titre,
        texte
    )
    diagnostic["checkpoint_detecte"] = diagnostic["checkpoint_blocage_visible"]
    diagnostic["captcha_detecte"] = diagnostic["captcha_blocage_visible"]

    if (
        diagnostic["marketplace_detecte"]
        and (diagnostic["nombre_cartes_marketplace"] or 0) > 0
    ):
        diagnostic["checkpoint_detecte"] = diagnostic["checkpoint_blocage_visible"]
        diagnostic["captcha_detecte"] = diagnostic["captcha_blocage_visible"]

    logger.info(
        "Marketplace local diagnostic: etape=%s url_finale=%s titre_page=%r "
        "login=%s checkpoint_html=%s checkpoint_visible=%s "
        "captcha_html=%s captcha_visible=%s marketplace=%s cartes=%s",
        diagnostic["etape"],
        diagnostic["url_finale"],
        diagnostic["titre_page"],
        diagnostic["login_detecte"],
        diagnostic["checkpoint_mot_html"],
        diagnostic["checkpoint_blocage_visible"],
        diagnostic["captcha_mot_html"],
        diagnostic["captcha_blocage_visible"],
        diagnostic["marketplace_detecte"],
        diagnostic["nombre_cartes_marketplace"],
    )
    return diagnostic


def _element_visible(page, selecteurs):
    for selecteur in selecteurs:
        try:
            elements = page.locator(selecteur)
            limite = min(elements.count(), 5)

            for index in range(limite):
                try:
                    if elements.nth(index).is_visible(timeout=300):
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    return False


def _checkpoint_visible(page, url, titre, texte):
    if "/checkpoint/" in url:
        return True

    contenu = " ".join([titre, texte])
    expressions = (
        "checkpoint",
        "security check",
        "vérification de sécurité",
        "verification de securite",
        "confirmez votre identité",
        "confirm your identity",
    )

    if any(expression in contenu for expression in expressions):
        return True

    return _element_visible(page, (
        "form[action*='checkpoint']",
        "a[href*='/checkpoint/']",
    ))


def _captcha_visible(page, titre, texte):
    contenu = " ".join([titre, texte])
    expressions = (
        "captcha",
        "recaptcha",
        "je ne suis pas un robot",
        "i'm not a robot",
        "i am not a robot",
        "vérification de sécurité",
        "verification de securite",
    )

    if any(expression in contenu for expression in expressions):
        return True

    return _element_visible(page, (
        "iframe[src*='captcha']",
        "iframe[src*='recaptcha']",
        "form[action*='captcha']",
        "[id*='captcha']",
        "[class*='captcha']",
    ))


def _detecter_blocage(page, etape):
    diagnostic = _diagnostic_page(page, etape)

    if diagnostic["captcha_detecte"]:
        raise MarketplaceLocalError(
            "CAPTCHA_DETECTED",
            "Captcha Facebook détecté : intervention manuelle requise.",
            etape,
            diagnostic,
        )

    if diagnostic["checkpoint_detecte"]:
        raise MarketplaceLocalError(
            "CHECKPOINT_DETECTED",
            "Checkpoint Facebook détecté : intervention manuelle requise.",
            etape,
            diagnostic,
        )

    if diagnostic["login_detecte"]:
        raise MarketplaceLocalError(
            "SESSION_EXPIRED",
            "Session Facebook expirée : reconnecte-toi manuellement sur l'appareil local.",
            etape,
            diagnostic,
        )

    return diagnostic


def _payload_erreur(erreur):
    if isinstance(erreur, MarketplaceLocalError):
        return {
            "ok": False,
            "code": erreur.code,
            "message": erreur.message,
            "etape": erreur.etape,
            "diagnostic": erreur.diagnostic,
            "annonces": [],
        }

    return {
        "ok": False,
        "code": "PLAYWRIGHT_ERROR",
        "message": "Erreur locale Marketplace inattendue.",
        "etape": "inconnue",
        "diagnostic": {"type_exception": type(erreur).__name__},
        "annonces": [],
    }


def _message_erreur_etape(etape):
    messages = {
        "lancement Playwright": "Impossible de lancer le navigateur.",
        "chargement du profil": "Impossible de charger le profil navigateur local.",
        "ouverture Facebook": "Impossible d'ouvrir Facebook Marketplace.",
        "recherche": "Impossible de vérifier la session Facebook.",
        "extraction": "Impossible d'extraire les annonces Marketplace.",
    }
    return messages.get(etape, "Erreur locale Marketplace inattendue.")


def diagnostic_local():
    executable = _browser_executable()
    options = _options_contexte(headless=_headless()) if not executable or executable.exists() else {}
    diagnostic = {
        "ok": True,
        "service": "marketplace_local",
        "systeme": _systeme(),
        "profile_dir": str(_profile_dir()),
        "profile_exists": _profil_existe(),
        "browser_executable": str(executable) if executable else "playwright_default",
        "browser_exists": executable.exists() if executable else None,
        "browser_used": str(executable) if executable else "Playwright default bundled browser",
        "chromium_args": options.get("args", []),
        "headless": _headless(),
        "playwright_available": False,
        "errors": [],
    }

    if executable and not executable.exists():
        diagnostic["ok"] = False
        diagnostic["errors"].append("BROWSER_MISSING")

    if not diagnostic["profile_exists"]:
        diagnostic["ok"] = False
        diagnostic["errors"].append("PROFILE_MISSING")

    try:
        _import_playwright()
        diagnostic["playwright_available"] = True
    except MarketplaceLocalError:
        diagnostic["ok"] = False
        diagnostic["errors"].append("PLAYWRIGHT_MISSING")

    return diagnostic


def ouvrir_connexion_manuelle():
    sync_playwright = _import_playwright()
    _profile_dir().mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        contexte = playwright.chromium.launch_persistent_context(
            **_options_contexte(headless=False)
        )
        page = contexte.new_page()
        page.goto(f"{BASE_URL}/marketplace/", wait_until="domcontentloaded")
        print("Connecte-toi manuellement à Facebook dans la fenêtre ouverte.")
        print("Ne saisis jamais tes identifiants dans le code ou le terminal.")
        input("Appuie sur Entrée ici quand la session est prête...")
        contexte.close()


def rechercher_marketplace(modele, limite=MAX_ANNONCES):
    etape = "lancement Playwright"
    sync_playwright = _import_playwright()
    limite = max(1, min(int(limite or MAX_ANNONCES), MAX_ANNONCES))
    url = f"{BASE_URL}/marketplace/search/?query={quote_plus(modele)}&exact=false"
    contexte = None

    try:
        with sync_playwright() as playwright:
            etape = "chargement du profil"
            profil = _profile_dir()

            if not _profil_existe():
                raise MarketplaceLocalError(
                    "PROFILE_MISSING",
                    "Profil Facebook local absent : lance d'abord le mode --login.",
                    etape,
                    {
                        "profile_dir": str(profil),
                        "variable": ENV_PROFILE_DIR,
                    },
                )

            logger.info(
                "Marketplace local utilise le profil persistant configure."
            )
            etape = "lancement Playwright"
            contexte = playwright.chromium.launch_persistent_context(
                **_options_contexte()
            )
            etape = "ouverture Facebook"
            page = contexte.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)

            etape = "recherche"
            _detecter_blocage(page, etape)

            page.wait_for_timeout(1500)
            etape = "extraction"
            liens = page.locator("a[href*='/marketplace/item/']")
            nombre_cartes = liens.count()
            diagnostic = _diagnostic_page(page, etape, nombre_cartes=nombre_cartes)
            annonces = []
            liens_vus = set()

            for index in range(min(nombre_cartes, limite * 2)):
                element = liens.nth(index)
                href = element.get_attribute("href") or ""

                if not href:
                    continue

                lien = href if href.startswith("http") else f"{BASE_URL}{href}"

                if lien in liens_vus:
                    continue

                texte = element.inner_text(timeout=2000)

                if len(texte.strip()) < 8:
                    continue

                liens_vus.add(lien)
                annonces.append({
                    "titre": _titre(texte, modele),
                    "prix": _prix(texte),
                    "annee": _annee(texte),
                    "kilometrage": _kilometrage(texte),
                    "ville": _ville(texte),
                    "lien": lien,
                })

                if len(annonces) >= limite:
                    break

            logger.info(
                "Marketplace local extraction terminee: cartes=%s annonces=%s",
                nombre_cartes,
                len(annonces),
            )
            return {
                "ok": True,
                "code": "OK",
                "message": None,
                "erreur": None,
                "diagnostic": diagnostic,
                "annonces": annonces,
            }
    except MarketplaceLocalError:
        raise
    except Exception as exc:
        diagnostic = {"type_exception": type(exc).__name__}
        raise MarketplaceLocalError(
            "PLAYWRIGHT_ERROR",
            _message_erreur_etape(etape),
            etape,
            diagnostic,
        ) from exc
    finally:
        if contexte is not None:
            try:
                contexte.close()
            except Exception:
                logger.warning("Impossible de fermer le contexte Playwright proprement.")


class MarketplaceHandler(BaseHTTPRequestHandler):
    server_version = "YBAutoMarketplaceLocal/1.0"

    def log_message(self, format_, *args):
        logger.info("%s - %s", self.address_string(), format_ % args)

    def _json(self, status, donnees):
        payload = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _autorise(self):
        token = _env_token()
        authorization = self.headers.get("Authorization", "")
        attendu = f"Bearer {token}"
        return bool(token) and authorization == attendu

    def do_GET(self):
        chemin = urlparse(self.path)

        if chemin.path == "/health":
            diagnostic = diagnostic_local()
            return self._json(200 if diagnostic["ok"] else 503, diagnostic)

        if not self._autorise():
            return self._json(401, {"ok": False, "erreur": "Token local invalide."})

        if chemin.path != "/marketplace":
            return self._json(404, {"ok": False, "erreur": "Route inconnue."})

        params = parse_qs(chemin.query)
        modele = (params.get("modele") or [""])[0].strip()
        limite = (params.get("limite") or [MAX_ANNONCES])[0]

        if not modele:
            return self._json(400, {"ok": False, "erreur": "Modèle manquant."})

        try:
            resultat = rechercher_marketplace(modele, limite=limite)
        except Exception as exc:
            logger.exception(
                "Marketplace local 503: type=%s message=%s",
                type(exc).__name__,
                exc,
            )
            return self._json(503, _payload_erreur(exc))

        statut = 200 if resultat.get("ok") else 503
        if statut == 503:
            logger.warning(
                "Marketplace local 503: code=%s message=%s etape=%s "
                "diagnostic=%s",
                resultat.get("code"),
                resultat.get("message") or resultat.get("erreur"),
                resultat.get("etape"),
                resultat.get("diagnostic"),
            )
        return self._json(statut, resultat)


def lancer_service(host=DEFAULT_HOST, port=DEFAULT_PORT):
    if not _env_token():
        raise RuntimeError(
            "MARKETPLACE_LOCAL_TOKEN est obligatoire pour lancer le service local."
        )

    serveur = ThreadingHTTPServer((host, port), MarketplaceHandler)
    print(f"Service Marketplace local lancé sur http://{host}:{port}")
    print("Le token n'est jamais affiché dans les logs.")
    serveur.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Service local Facebook Marketplace")
    parser.add_argument("--login", action="store_true", help="ouvre une session Facebook manuelle")
    parser.add_argument("--health", action="store_true", help="affiche un diagnostic local non sensible")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.health:
        print(json.dumps(diagnostic_local(), ensure_ascii=False, indent=2))
        return

    if args.login:
        ouvrir_connexion_manuelle()
        return

    lancer_service(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
