# app.py
#
# PUNKT WEJŚCIA dla webowej wersji Bee Scanner.
#
# Jak uruchomić:
#   python3 app.py
#   → otwórz http://localhost:5001 w przeglądarce
#
# Endpointy:
#   GET  /          → strona główna z wynikami ostatniego skanu
#   POST /scan      → uruchamia skanowanie w tle (wątek), od razu zwraca redirect
#   GET  /progress  → JSON z aktualnym postępem skanowania (do paska postępu)

import csv
import json
import os
import threading

# Wczytaj zmienne środowiskowe z .env (jeśli plik istnieje)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from urllib.parse import unquote
from flask import Flask, jsonify, redirect, render_template, request, url_for

from scrapers.justjoin import JustJoinScraper
from scrapers.rocketjobs import RocketJobsScraper
from utils.exporter import build_companies_summary, export_jobs_csv, export_summary_csv
from utils.normalizer import merge_all_jobs

# HubSpot + AI — opcjonalne (wymagają kluczy API w .env)
try:
    from utils.hubspot import lookup_company_full, create_company as hs_create_company
    from utils.ai_writer import generate_email
    INTEGRATIONS_ENABLED = True
except ImportError as _ie:
    print(f"[app] Integracje wyłączone: {_ie}")
    INTEGRATIONS_ENABLED = False

JOBS_CSV    = "output/jobs.csv"
SUMMARY_CSV = "output/companies_summary.csv"

app = Flask(__name__, template_folder="templates")

# Globalny stan skanowania — wątek zapisuje tu postęp, /progress go odczytuje
scan_state = {
    "running": False,
    "mode": None,
    "justjoin_fetched": 0,
    "justjoin_total": 0,
    "rocketjobs_fetched": 0,
    "rocketjobs_total": 0,
    "done": False,
    "error": None,
}


@app.route("/")
def index():
    jobs      = _read_csv(JOBS_CSV)
    companies = _read_csv(SUMMARY_CSV)
    return render_template("index.html", jobs=jobs, companies=companies,
                           scan_running=scan_state["running"])


@app.route("/scan", methods=["POST"])
def scan():
    if scan_state["running"]:
        # Skan już trwa — zignoruj drugi klik
        return redirect(url_for("index"))

    scan_mode = request.form.get("scan_mode", "quick")
    max_pages = 20 if scan_mode == "quick" else 100

    # Zresetuj stan
    scan_state.update({
        "running": True,
        "mode": scan_mode,
        "justjoin_fetched": 0,
        "justjoin_total": 0,
        "rocketjobs_fetched": 0,
        "rocketjobs_total": 0,
        "done": False,
        "error": None,
    })

    # Uruchom skan w tle — przeglądarka dostaje redirect natychmiast
    thread = threading.Thread(target=_run_scan_background, args=(max_pages,), daemon=True)
    thread.start()

    return redirect(url_for("index"))


@app.route("/progress")
def progress():
    return jsonify(scan_state)


def _run_scan_background(max_pages: int):
    """Wykonuje pełne skanowanie w osobnym wątku."""
    print(f"[app] Skan w tle — tryb: {scan_state['mode']} (max {max_pages} stron/portal)")

    def make_callback(platform: str):
        """Zwraca callback aktualizujący stan dla danego portalu."""
        def callback(fetched: int, total: int):
            scan_state[f"{platform}_fetched"] = fetched
            scan_state[f"{platform}_total"]   = total
        return callback

    try:
        scrapers = [
            (JustJoinScraper(max_pages=max_pages),   "justjoin"),
            (RocketJobsScraper(max_pages=max_pages), "rocketjobs"),
        ]

        all_portal_results = []
        for scraper, platform in scrapers:
            jobs = scraper.run(progress_callback=make_callback(platform))

            if not jobs:
                print(f"[app] {platform}: brak danych → ładuję dane testowe")
                jobs = _load_test_data(platform)

            all_portal_results.append(jobs)

        all_jobs = merge_all_jobs(all_portal_results)
        print(f"[app] Łącznie ogłoszeń: {len(all_jobs)}")

        if all_jobs:
            export_jobs_csv(all_jobs, JOBS_CSV)
            summary = build_companies_summary(all_jobs)
            export_summary_csv(summary, SUMMARY_CSV)

    except Exception as e:
        print(f"[app] BŁĄD podczas skanowania: {e}")
        scan_state["error"] = str(e)

    finally:
        scan_state["running"] = False
        scan_state["done"]    = True
        print("[app] Skan zakończony.")


def _read_csv(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except (IOError, csv.Error) as e:
        print(f"[app] BŁĄD przy wczytywaniu {path}: {e}")
        return []


def _load_test_data(platform_name: str) -> list:
    base_dir  = os.path.dirname(os.path.abspath(__file__))
    test_file = os.path.join(base_dir, "data", f"test_{platform_name}.json")
    if not os.path.exists(test_file):
        return []
    try:
        with open(test_file, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


# ---------------------------------------------------------------------------
# Company detail page
# ---------------------------------------------------------------------------

@app.route("/company/<path:company_name>")
def company_detail(company_name):
    company_name  = unquote(company_name)
    all_jobs      = _read_csv(JOBS_CSV)
    all_companies = _read_csv(SUMMARY_CSV)

    company = next((c for c in all_companies if c["company_name"] == company_name), None)
    if not company:
        return redirect(url_for("index"))

    company_jobs = [j for j in all_jobs if j["company_name"] == company_name]
    return render_template("company.html", company=company, jobs=company_jobs)


# ---------------------------------------------------------------------------
# HubSpot & AI endpoints
# ---------------------------------------------------------------------------

@app.route("/api/hubspot/lookup")
def api_hubspot_lookup():
    """GET /api/hubspot/lookup?company=NazwaFirmy → JSON z danymi z CRM."""
    if not INTEGRATIONS_ENABLED:
        return jsonify({"error": "Integracja wyłączona — sprawdź requirements.txt"}), 503
    company_name = request.args.get("company", "").strip()
    if not company_name:
        return jsonify({"error": "Brak parametru 'company'"}), 400
    result = lookup_company_full(company_name)
    return jsonify(result)


@app.route("/api/hubspot/create", methods=["POST"])
def api_hubspot_create():
    """POST /api/hubspot/create → tworzy firmę w HubSpot."""
    if not INTEGRATIONS_ENABLED:
        return jsonify({"error": "Integracja wyłączona — sprawdź requirements.txt"}), 503
    data = request.get_json(silent=True) or {}
    company_name = data.get("company_name", "").strip()
    if not company_name:
        return jsonify({"error": "Brak pola 'company_name'"}), 400
    result = hs_create_company(
        company_name=company_name,
        domain=data.get("domain", ""),
        industry=data.get("industry", ""),
        city=data.get("city", ""),
    )
    return jsonify(result)



@app.route("/api/ai/email", methods=["POST"])
def api_ai_email():
    """POST /api/ai/email → generuje email do klienta (Claude API)."""
    if not INTEGRATIONS_ENABLED:
        return jsonify({"subject": "—", "body": "Integracja AI wyłączona — sprawdź requirements.txt"}), 503
    data         = request.get_json(silent=True) or {}
    company_name = data.get("company_name", "").strip()
    email_type   = data.get("email_type", "cold")
    context      = data.get("context", {})
    if not company_name:
        return jsonify({"error": "Brak pola 'company_name'"}), 400
    result = generate_email(company_name, email_type, context)
    return jsonify(result)


if __name__ == "__main__":
    print("=" * 50)
    print("Bee Scanner — serwer webowy")
    print("Otwórz: http://localhost:5001")
    print("=" * 50)
    # threaded=True  — Flask obsługuje równoległe requesty (skan w tle + /progress)
    # use_reloader=False — wyłącza auto-restart przy zmianach pliku,
    #                      bo reloader zabija wątki tła (background scan)
    app.run(debug=True, port=5001, threaded=True, use_reloader=False)
