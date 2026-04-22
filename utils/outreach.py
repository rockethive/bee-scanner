# utils/outreach.py
#
# Pobiera listę firm z Google Sheets (CSV) i cache'uje w pamięci.
# Wymagana zmienna środowiskowa:
#   OUTREACH_SHEET_URL — publiczny link CSV do arkusza Google Sheets

import csv
import io
import os
import time

import requests

_cache: dict = {"names": set(), "fetched_at": 0.0}
CACHE_TTL = 600  # 10 minut


def get_outreach_names() -> set:
    """
    Zwraca zbiór nazw firm (lowercase) z arkusza outreach.
    Cache 10 minut — przy każdym wywołaniu sprawdza czy TTL minął.
    """
    now = time.time()
    if now - _cache["fetched_at"] < CACHE_TTL and _cache["names"]:
        return _cache["names"]

    url = os.environ.get("OUTREACH_SHEET_URL", "").strip()
    if not url:
        return set()

    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        reader = csv.reader(io.StringIO(r.text))
        names = set()
        for row in reader:
            if row and row[0].strip():
                names.add(row[0].strip().lower())
        _cache["names"] = names
        _cache["fetched_at"] = now
        print(f"[outreach] Załadowano {len(names)} firm z listy outreach.")
        return names
    except Exception as e:
        print(f"[outreach] Błąd pobierania listy: {e}")
        return _cache["names"]  # stary cache przy błędzie
