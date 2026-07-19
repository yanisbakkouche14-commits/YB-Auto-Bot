import argparse
import json
import logging
import os
import re
from datetime import datetime
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
ENV_LOCATION_ID = "MARKETPLACE_LOCATION_ID"

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


def _marketplace_location_id():
    return os.getenv(ENV_LOCATION_ID, "").strip().strip("/")


def _marketplace_base_url():
    location_id = _marketplace_location_id()

    if location_id:
        return f"{BASE_URL}/marketplace/{location_id}"

    return f"{BASE_URL}/marketplace"


def _url_recherche(modele):
    return f"{_marketplace_base_url()}/search/?query={quote_plus(modele)}&exact=false"


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


MARQUES_AUTO = (
    "Volkswagen",
    "VW",
    "BMW",
    "Audi",
    "Mercedes",
    "Mercedes-Benz",
    "Opel",
    "Peugeot",
    "Renault",
    "Ford",
    "Toyota",
    "Seat",
    "Skoda",
    "Citroen",
    "Citroën",
    "Hyundai",
    "Kia",
    "Volvo",
    "Fiat",
    "Nissan",
    "Mazda",
    "Honda",
    "Suzuki",
    "Mini",
    "Dacia",
    "Jeep",
    "Alfa Romeo",
    "Porsche",
    "Mitsubishi",
    "Chevrolet",
)

REGIONS_BELGES = {"WAL", "VLG", "BRU"}


def _normaliser_texte(texte):
    texte = str(texte or "")
    texte = texte.replace("\u00a0", " ")
    texte = re.sub(r"[ \t]+", " ", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    return texte.strip()


def _lignes(texte):
    lignes = []

    for ligne in re.split(r"\n|\r|\s{2,}", _normaliser_texte(texte)):
        ligne = ligne.strip(" -•|")

        if ligne:
            lignes.append(ligne)

    return lignes


def _nombre_francais(valeur):
    chiffres = re.sub(r"[^\d]", "", str(valeur or ""))
    return int(chiffres) if chiffres else None


def _est_ville_ligne(ligne):
    ligne = _normaliser_texte(ligne)

    if not ligne:
        return False

    if ligne.lower() in {"belgique", "belgium"}:
        return True

    match = re.match(r"^[A-Za-zÀ-ÿ' .-]{2,40},\s*([A-Z]{3})$", ligne)
    return bool(match and match.group(1) in REGIONS_BELGES)


def _ville_depuis_ligne(ligne):
    ligne = _normaliser_texte(ligne)

    if ligne.lower() in {"belgique", "belgium"}:
        return "Belgique"

    match = re.match(r"^([A-Za-zÀ-ÿ' .-]{2,40}),\s*([A-Z]{3})$", ligne)

    if match and match.group(2) in REGIONS_BELGES:
        return match.group(1).strip()

    return None


def _contient_marque(ligne):
    ligne_min = ligne.lower()
    return any(re.search(rf"\b{re.escape(marque.lower())}\b", ligne_min) for marque in MARQUES_AUTO)


def _ligne_prix(ligne):
    ligne_min = ligne.lower()
    return "\u20ac" in ligne or "eur" in ligne_min or "gratuit" in ligne_min


def _ligne_km(ligne):
    return bool(re.search(r"\bkm\b|kilom", ligne, re.IGNORECASE))


def _prix_detail(texte):
    texte = _normaliser_texte(texte)

    if re.search(r"\bgratuit\b", texte, re.IGNORECASE):
        return 0, "mot gratuit detecte"

    candidats = []
    motif = re.compile(
        r"(?P<avant>(?:€|\u20ac|eur)\s*)?"
        r"(?P<nombre>\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{3,6})"
        r"(?P<apres>\s*(?:€|\u20ac|eur))?",
        re.IGNORECASE,
    )

    for index_ligne, ligne in enumerate(_lignes(texte)):
        if _ligne_km(ligne):
            continue

        for match in motif.finditer(ligne):
            if not (match.group("avant") or match.group("apres")):
                continue

            valeur = _nombre_francais(match.group("nombre"))

            if valeur is None or not 100 <= valeur <= 250000:
                continue

            candidats.append({
                "valeur": valeur,
                "ligne": ligne,
                "index_ligne": index_ligne,
                "position": match.start(),
                "score": 100 - min(index_ligne, 20),
            })

    if not candidats:
        return "Inconnu", "aucun prix plausible avec devise"

    choisi = sorted(
        candidats,
        key=lambda item: (item["score"], -item["position"]),
        reverse=True,
    )[0]

    return choisi["valeur"], f"prix avec devise dans ligne: {choisi['ligne'][:80]}"


def _prix(texte):
    prix, _raison = _prix_detail(texte)
    return prix


def _annee_detail(texte):
    annee_max = datetime.now().year + 1
    candidats = []

    for index_ligne, ligne in enumerate(_lignes(texte)):
        if _ligne_prix(ligne) or _ligne_km(ligne):
            continue

        for match in re.finditer(r"\b(19[8-9]\d|20\d{2})\b", ligne):
            valeur = int(match.group(1))

            if 1980 <= valeur <= annee_max:
                candidats.append({
                    "valeur": valeur,
                    "ligne": ligne,
                    "score": 80 + (10 if _contient_marque(ligne) else 0),
                })

    if not candidats:
        return "Inconnu", "aucune annee plausible"

    choisi = sorted(candidats, key=lambda item: item["score"], reverse=True)[0]
    return choisi["valeur"], f"annee plausible dans ligne: {choisi['ligne'][:80]}"


def _annee(texte):
    annee, _raison = _annee_detail(texte)
    return annee


def _kilometrage_detail(texte):
    candidats = []
    motif = re.compile(
        r"(?<!\d)(?P<nombre>\d{1,3}(?:[\s\.\u00a0]\d{3})+|\d{4,6}|\d{1,3}\s*k)"
        r"\s*(?P<unite>km|kilom[eè]tres?)?",
        re.IGNORECASE,
    )

    for index_ligne, ligne in enumerate(_lignes(texte)):
        if _ligne_prix(ligne):
            continue

        for match in motif.finditer(ligne):
            brut = match.group("nombre")
            unite = match.group("unite")
            contient_k = bool(re.search(r"k\s*$", brut, re.IGNORECASE))

            if not unite and not contient_k:
                continue

            if contient_k:
                valeur = int(re.sub(r"\D", "", brut)) * 1000
            else:
                valeur = _nombre_francais(brut)

            if valeur is None or not 0 <= valeur <= 1000000:
                continue

            candidats.append({
                "valeur": valeur,
                "ligne": ligne,
                "score": 100 - min(index_ligne, 20),
            })

    if not candidats:
        return "Inconnu", "aucun kilometrage plausible"

    choisi = sorted(candidats, key=lambda item: item["score"], reverse=True)[0]
    return choisi["valeur"], f"kilometrage dans ligne: {choisi['ligne'][:80]}"


def _kilometrage(texte):
    kilometrage, _raison = _kilometrage_detail(texte)
    return kilometrage


def _ville(texte):
    for ligne in _lignes(texte):
        ville = _ville_depuis_ligne(ligne)

        if ville:
            return ville

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
    titre, _incomplet, _raison = _titre_detail(texte, modele)
    return titre


def _titre_detail(texte, modele):
    lignes = _lignes(texte)
    candidats = []

    for index, ligne in enumerate(lignes):
        if len(ligne) < 4:
            continue

        if _ligne_prix(ligne) or _ligne_km(ligne) or _est_ville_ligne(ligne):
            continue

        score = 10

        if _contient_marque(ligne):
            score += 80

        for mot in re.findall(r"[A-Za-z0-9]+", modele or ""):
            if len(mot) > 2 and mot.lower() in ligne.lower():
                score += 10

        if re.search(r"\b(gti|gtd|tdi|tsi|hdi|dci|hybrid|automatique|manual|pack|amg|m sport)\b", ligne, re.IGNORECASE):
            score += 15

        score -= index
        candidats.append({"ligne": ligne, "score": score})

    if candidats:
        choisi = sorted(candidats, key=lambda item: item["score"], reverse=True)[0]
        return choisi["ligne"][:120], False, f"ligne titre score={choisi['score']}"

    for ligne in lignes:
        if not _ligne_prix(ligne) and not _ligne_km(ligne):
            return ligne[:120], True, "fallback meilleure ligne sans prix/km"

    return modele, True, "fallback modele recherche"


def _score_texte_carte(texte, modele):
    score = 0

    if _prix(texte) != "Inconnu":
        score += 40

    if _kilometrage(texte) != "Inconnu":
        score += 25

    if _annee(texte) != "Inconnu":
        score += 20

    titre, incomplet, _raison = _titre_detail(texte, modele)

    if titre and not incomplet:
        score += 35

    if _ville(texte) != "Belgique":
        score += 10

    longueur = len(_normaliser_texte(texte))

    if 20 <= longueur <= 1200:
        score += 10

    return score


def _texte_locator(locator, timeout=1000):
    try:
        return locator.inner_text(timeout=timeout)
    except Exception:
        return ""


def _attribut_locator(locator, nom):
    try:
        return locator.get_attribute(nom) or ""
    except Exception:
        return ""


def _donnees_carte(element, modele):
    candidats = []

    try:
        donnees = element.evaluate(
            """(node) => {
                const pick = (el) => {
                    if (!el) return null;
                    const texts = [];
                    el.querySelectorAll('*').forEach((child) => {
                        const style = window.getComputedStyle(child);
                        const visible = style && style.display !== 'none' &&
                            style.visibility !== 'hidden' &&
                            child.offsetParent !== null;
                        const text = (child.innerText || child.textContent || '').trim();
                        if (visible && text) texts.push(text);
                    });
                    return {
                        inner_text: (el.innerText || el.textContent || '').trim(),
                        aria_label: el.getAttribute('aria-label') || '',
                        title: el.getAttribute('title') || '',
                        textes_enfants: texts.slice(0, 80),
                    };
                };
                const out = [];
                let current = node;
                for (let depth = 0; current && depth <= 6; depth++) {
                    out.push({depth, data: pick(current)});
                    current = current.parentElement;
                }
                return out;
            }"""
        )
    except Exception:
        donnees = []

    lien_texte = _texte_locator(element)
    lien_aria = _attribut_locator(element, "aria-label")
    lien_title = _attribut_locator(element, "title")
    textes_lien = [lien_texte, lien_aria, lien_title]

    for entree in donnees:
        data = entree.get("data") or {}
        morceaux = [
            data.get("inner_text", ""),
            data.get("aria_label", ""),
            data.get("title", ""),
            "\n".join(data.get("textes_enfants") or []),
            "\n".join(textes_lien),
        ]
        texte = _normaliser_texte("\n".join(morceau for morceau in morceaux if morceau))

        if not texte:
            continue

        candidats.append({
            "depth": entree.get("depth", 0),
            "texte": texte,
            "score": _score_texte_carte(texte, modele),
        })

    if not candidats:
        texte = _normaliser_texte("\n".join(textes_lien))
        candidats.append({"depth": 0, "texte": texte, "score": _score_texte_carte(texte, modele)})

    choisi = sorted(
        candidats,
        key=lambda item: (item["score"], -item["depth"]),
        reverse=True,
    )[0]

    return {
        "texte": choisi["texte"],
        "depth": choisi["depth"],
        "score_conteneur": choisi["score"],
        "candidats": candidats,
        "aria_label": lien_aria,
        "title": lien_title,
        "texte_lien": lien_texte,
    }


def _annonce_depuis_texte(texte, modele, lien):
    prix, raison_prix = _prix_detail(texte)
    annee, raison_annee = _annee_detail(texte)
    kilometrage, raison_km = _kilometrage_detail(texte)
    titre, titre_incomplet, raison_titre = _titre_detail(texte, modele)
    ville = _ville(texte)

    return {
        "titre": titre,
        "prix": prix,
        "annee": annee,
        "kilometrage": kilometrage,
        "ville": ville,
        "lien": lien,
        "titre_incomplet": titre_incomplet,
        "_debug": {
            "raison_prix": raison_prix,
            "raison_annee": raison_annee,
            "raison_kilometrage": raison_km,
            "raison_titre": raison_titre,
            "texte_normalise": _normaliser_texte(texte)[:1000],
        },
    }


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
        "location_id_utilise": _marketplace_location_id() or None,
        "url_construite": None,
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
        "marketplace_location_id": _marketplace_location_id() or None,
        "marketplace_base_url": _marketplace_base_url(),
        "marketplace_search_base_url": f"{_marketplace_base_url()}/search/",
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


def _extraire_cartes_page(page, modele, limite=MAX_ANNONCES, debug=False):
    liens = page.locator("a[href*='/marketplace/item/']")
    nombre_cartes = liens.count()
    annonces = []
    debug_cartes = []
    liens_vus = set()
    limite = max(1, min(int(limite or MAX_ANNONCES), MAX_ANNONCES))

    for index in range(min(nombre_cartes, limite * 3)):
        element = liens.nth(index)
        href = element.get_attribute("href") or ""

        if not href:
            continue

        lien = href if href.startswith("http") else f"{BASE_URL}{href}"

        if lien in liens_vus:
            continue

        donnees_carte = _donnees_carte(element, modele)
        texte = donnees_carte["texte"]

        if len(texte.strip()) < 8:
            continue

        liens_vus.add(lien)
        annonce = _annonce_depuis_texte(texte, modele, lien)
        annonce["score_conteneur"] = donnees_carte["score_conteneur"]

        if debug and len(debug_cartes) < 3:
            debug_cartes.append({
                "index": index,
                "href": lien,
                "texte_brut_normalise": annonce["_debug"]["texte_normalise"],
                "titre_choisi": annonce["titre"],
                "prix_choisi": annonce["prix"],
                "annee_choisie": annonce["annee"],
                "kilometrage_choisi": annonce["kilometrage"],
                "ville_choisie": annonce["ville"],
                "titre_incomplet": annonce["titre_incomplet"],
                "score_conteneur": annonce["score_conteneur"],
                "raisons": {
                    "titre": annonce["_debug"]["raison_titre"],
                    "prix": annonce["_debug"]["raison_prix"],
                    "annee": annonce["_debug"]["raison_annee"],
                    "kilometrage": annonce["_debug"]["raison_kilometrage"],
                },
            })

        annonces.append({
            cle: valeur
            for cle, valeur in annonce.items()
            if cle != "_debug"
        })

        if len(annonces) >= limite:
            break

    return nombre_cartes, annonces, debug_cartes


def rechercher_marketplace(modele, limite=MAX_ANNONCES):
    etape = "lancement Playwright"
    sync_playwright = _import_playwright()
    limite = max(1, min(int(limite or MAX_ANNONCES), MAX_ANNONCES))
    url = _url_recherche(modele)
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
            nombre_cartes, annonces, _debug_cartes = _extraire_cartes_page(
                page,
                modele,
                limite=limite,
                debug=False,
            )
            diagnostic = _diagnostic_page(page, etape, nombre_cartes=nombre_cartes)
            diagnostic["location_id_utilise"] = _marketplace_location_id() or None
            diagnostic["url_construite"] = url

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


def debug_recherche_marketplace(modele):
    sync_playwright = _import_playwright()
    url = _url_recherche(modele)
    contexte = None

    try:
        with sync_playwright() as playwright:
            if not _profil_existe():
                raise MarketplaceLocalError(
                    "PROFILE_MISSING",
                    "Profil Facebook local absent : lance d'abord le mode --login.",
                    "chargement du profil",
                    {
                        "profile_dir": str(_profile_dir()),
                        "variable": ENV_PROFILE_DIR,
                    },
                )

            contexte = playwright.chromium.launch_persistent_context(
                **_options_contexte()
            )
            page = contexte.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            _detecter_blocage(page, "debug recherche")
            page.wait_for_timeout(1500)
            nombre_cartes, annonces, debug_cartes = _extraire_cartes_page(
                page,
                modele,
                limite=3,
                debug=True,
            )
            diagnostic = _diagnostic_page(page, "debug extraction", nombre_cartes)
            diagnostic["location_id_utilise"] = _marketplace_location_id() or None
            diagnostic["url_construite"] = url

            return {
                "ok": True,
                "modele": modele,
                "diagnostic": diagnostic,
                "nombre_annonces_normalisees": len(annonces),
                "cartes_debug": debug_cartes,
            }
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
    parser.add_argument(
        "--debug-search",
        metavar="MODELE",
        help="inspecte 3 cartes Marketplace sans afficher de donnees sensibles",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.health:
        print(json.dumps(diagnostic_local(), ensure_ascii=False, indent=2))
        return

    if args.debug_search:
        print(json.dumps(
            debug_recherche_marketplace(args.debug_search),
            ensure_ascii=False,
            indent=2,
        ))
        return

    if args.login:
        ouvrir_connexion_manuelle()
        return

    lancer_service(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
