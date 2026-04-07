# scrapers/rocketjobs.py
#
# Scraper dla portalu rocketjobs.pl
#
# JAK DZIAŁA:
#   rocketjobs.pl i justjoin.it są prowadzone przez tę samą firmę
#   (Just Join IT sp. z o.o.) i używają identycznej infrastruktury.
#
#   Podejście RSC + cursor-based paginacja przez ?from=N&itemsCount=100.
#   Identyczna logika jak justjoin.py — różni się tylko URL i bazą linku.
#
# WAŻNE:
#   ?from=0 nie działa dla rocketjobs — pierwsza strona musi używać
#   bazowego URL bez parametrów. Kolejne strony: ?from=cursor.

import json
import time
import requests
from scrapers.base import BaseScraper

ROCKETJOBS_URL = "https://rocketjobs.pl/oferty-pracy/wszystkie-lokalizacje"
PAGE_SIZE    = 100
MAX_PAGES    = 20   # 20 stron × 100 ofert = 2000 ofert maks (~40s skanu)
REQUEST_DELAY   = 0.3
REQUEST_TIMEOUT = 20

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/x-component",
    "RSC": "1",
}


class RocketJobsScraper(BaseScraper):
    """
    Scraper dla rocketjobs.pl używający RSC payload z cursor-based paginacją.

    Identyczna logika jak JustJoinScraper — różni się URL i formatem linku.
    """

    PLATFORM_NAME = "rocketjobs"

    def __init__(self, max_pages: int = MAX_PAGES):
        self.max_pages = max_pages

    def fetch_raw(self, progress_callback=None) -> list:
        """
        Pobiera surowe oferty z rocketjobs.pl — wszystkie strony przez cursor.

        Parametry:
            progress_callback: opcjonalna funkcja(fetched, total) wywoływana
                               po każdej stronie — używana do paska postępu w UI

        Zwraca:
            list: Lista surowych słowników ofert ze wszystkich stron.
        """
        all_offers = []
        next_cursor = None  # None = pierwsza strona (bazowy URL)
        total_items = None

        for page_num in range(1, self.max_pages + 1):
            if next_cursor is None:
                url = ROCKETJOBS_URL
            else:
                url = f"{ROCKETJOBS_URL}?from={next_cursor}&itemsCount={PAGE_SIZE}"

            total_display = f"~{total_items}" if total_items else "?"
            print(f"[rocketjobs] Strona {page_num}: {len(all_offers)} / {total_display} ofert pobranych")

            try:
                response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
            except requests.exceptions.Timeout:
                print(f"[rocketjobs] BŁĄD: Timeout po {REQUEST_TIMEOUT}s — przerywam.")
                break
            except requests.exceptions.ConnectionError:
                print("[rocketjobs] BŁĄD: Brak połączenia z rocketjobs.pl — przerywam.")
                break
            except requests.exceptions.HTTPError as e:
                print(f"[rocketjobs] BŁĄD HTTP: {e} — przerywam.")
                break

            offers, meta = self._extract_offers_and_meta(response.content.decode("utf-8"))

            if not offers:
                print(f"[rocketjobs] Brak ofert na stronie {page_num} — koniec danych.")
                break

            all_offers.extend(offers)

            if total_items is None:
                total_items = meta.get("totalItems", 0)

            if progress_callback:
                progress_callback(len(all_offers), total_items or 0)

            next_cursor = meta.get("next", {}).get("cursor")

            if next_cursor is None:
                print(f"[rocketjobs] Pobrano wszystkie {len(all_offers)} ofert.")
                break

            time.sleep(REQUEST_DELAY)

        return all_offers

    def _extract_offers_and_meta(self, rsc_text: str):
        """
        Wyciąga listę ofert i metadata z RSC payload Next.js.

        Identyczna metoda jak w JustJoinScraper — używa raw_decode
        zamiast parsowania linii po linii. Działa dla obu portali.

        Parametry:
            rsc_text: pełny tekst odpowiedzi RSC jako string

        Zwraca:
            Tuple (offers: list, meta: dict)
        """
        needle = '{"data":{"pages":['
        idx = rsc_text.find(needle)
        if idx < 0:
            return [], {}

        try:
            obj, _ = json.JSONDecoder().raw_decode(rsc_text, idx)
        except (json.JSONDecodeError, ValueError):
            return [], {}

        pages = obj.get("data", {}).get("pages", [])
        if not pages:
            return [], {}

        return pages[0].get("data", []), pages[0].get("meta", {})

    def normalize(self, raw_jobs: list) -> list:
        """
        Konwertuje surowe oferty z rocketjobs.pl do wspólnego formatu.

        Pola identyczne jak w justjoin.it:
          - "title"       → job_title
          - "companyName" → company_name
          - "slug"        → do zbudowania URL

        URL ogłoszenia: https://rocketjobs.pl/oferty-pracy/{slug}

        Parametry:
            raw_jobs: lista surowych słowników z fetch_raw()

        Zwraca:
            Lista rekordów w wspólnym formacie.
        """
        normalized = []

        for i, offer in enumerate(raw_jobs):
            try:
                company_name = offer.get("companyName", "").strip()
                job_title    = offer.get("title", "").strip()
                slug         = offer.get("slug", "").strip()

                if not company_name or not job_title or not slug:
                    continue

                normalized.append({
                    "company_name": company_name,
                    "job_title":    job_title,
                    "platform":     self.PLATFORM_NAME,
                    "job_url":      f"https://rocketjobs.pl/oferty-pracy/{slug}",
                })

            except Exception as e:
                print(f"[rocketjobs] UWAGA: Pominięto rekord #{i}: {e}")
                continue

        return normalized
