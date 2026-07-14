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

logger = logging.getLogger("marketplace_local_service")


def _env_token():
    return os.getenv("MARKETPLACE_LOCAL_TOKEN", "").strip()


def _profile_dir():
    return Path(os.getenv("MARKETPLACE_PROFILE_DIR", DEFAULT_PROFILE_DIR))


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
        raise RuntimeError(
            "Playwright n'est pas installé sur ce PC local."
        ) from exc

    return sync_playwright


def _detecter_blocage(page):
    titre = page.title()
    url = page.url.lower()
    html = page.content().lower()
    texte = page.locator("body").inner_text(timeout=2000).lower()
    contenu = " ".join([titre.lower(), url, html, texte])

    if "captcha" in contenu:
        return "Captcha Facebook détecté : intervention manuelle requise."

    if "checkpoint" in contenu:
        return "Checkpoint Facebook détecté : intervention manuelle requise."

    if (
        "login" in url
        or "connectez-vous" in contenu
        or "se connecter" in contenu
        or "log in to facebook" in contenu
    ):
        return "Session Facebook expirée : reconnecte-toi manuellement sur le PC."

    return None


def ouvrir_connexion_manuelle():
    sync_playwright = _import_playwright()

    with sync_playwright() as playwright:
        contexte = playwright.chromium.launch_persistent_context(
            user_data_dir=str(_profile_dir()),
            headless=False,
            viewport={"width": 1366, "height": 900},
        )
        page = contexte.new_page()
        page.goto(f"{BASE_URL}/marketplace/", wait_until="domcontentloaded")
        print("Connecte-toi manuellement à Facebook dans la fenêtre ouverte.")
        print("Ne saisis jamais tes identifiants dans le code ou le terminal.")
        input("Appuie sur Entrée ici quand la session est prête...")
        contexte.close()


def rechercher_marketplace(modele, limite=MAX_ANNONCES):
    sync_playwright = _import_playwright()
    limite = max(1, min(int(limite or MAX_ANNONCES), MAX_ANNONCES))
    url = f"{BASE_URL}/marketplace/search/?query={quote_plus(modele)}&exact=false"

    with sync_playwright() as playwright:
        contexte = playwright.chromium.launch_persistent_context(
            user_data_dir=str(_profile_dir()),
            headless=False,
            viewport={"width": 1366, "height": 900},
        )
        page = contexte.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)

        blocage = _detecter_blocage(page)
        if blocage:
            contexte.close()
            return {
                "ok": False,
                "erreur": blocage,
                "annonces": [],
            }

        page.wait_for_timeout(1500)
        liens = page.locator("a[href*='/marketplace/item/']")
        annonces = []
        liens_vus = set()

        for index in range(min(liens.count(), limite * 2)):
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

        contexte.close()
        return {
            "ok": True,
            "erreur": None,
            "annonces": annonces,
        }


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
            return self._json(200, {"ok": True, "service": "marketplace_local"})

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
            logger.warning("Marketplace local indisponible: %s", exc)
            return self._json(503, {"ok": False, "erreur": str(exc), "annonces": []})

        statut = 200 if resultat.get("ok") else 503
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
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.login:
        ouvrir_connexion_manuelle()
        return

    lancer_service(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
