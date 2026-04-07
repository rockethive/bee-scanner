# scrapers/justjoin.py
#
# Scraper dla portalu justjoin.it
#
# JAK DZIAŁA:
#   justjoin.it to aplikacja Next.js App Router.
#   Stare API (/api/offers) jest wyłączone od 2023 roku.
#
#   Używamy RSC (React Server Components) payload — serwer zwraca
#   stan TanStack Query z listą ofert wbudowaną w odpowiedź.
#
# PAGINACJA:
#   Parametr ?from=N&itemsCount=100 steruje offsetem.
#   Każda strona zwraca meta.next.cursor — oficjalny offset następnej strony.
#   Gdy meta.next.cursor == null → ostatnia strona.
#
#   Limit: MAX_PAGES = 100 (10 000 ofert maks)

import json
import time
import requests
from scrapers.base import BaseScraper

JUSTJOIN_URL = "https://justjoin.it/job-offers"
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


class JustJoinScraper(BaseScraper):
    """
    Scraper dla justjoin.it używający RSC payload z cursor-based paginacją.
    """

    PLATFORM_NAME = "justjoin"

    def __init__(self, max_pages: int = MAX_PAGES):
        self.max_pages = max_pages

    def fetch_raw(self, progress_callback=None) -> list:
        """
        Pobiera surowe oferty z justjoin.it — wszystkie strony przez cursor.

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
            # Pierwsza strona: bazowy URL. Kolejne: z parametrem ?from=cursor
            if next_cursor is None:
                url = JUSTJOIN_URL
            else:
                url = f"{JUSTJOIN_URL}?from={next_cursor}&itemsCount={PAGE_SIZE}"

            total_display = f"~{total_items}" if total_items else "?"
            print(f"[justjoin] Strona {page_num}: {len(all_offers)} / {total_display} ofert pobranych")

            try:
                response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
            except requests.exceptions.Timeout:
                print(f"[justjoin] BŁĄD: Timeout po {REQUEST_TIMEOUT}s — przerywam.")
                break
            except requests.exceptions.ConnectionError:
                print("[justjoin] BŁĄD: Brak połączenia z justjoin.it — przerywam.")
                break
            except requests.exceptions.HTTPError as e:
                print(f"[justjoin] BŁĄD HTTP: {e} — przerywam.")
                break

            offers, meta = self._extract_offers_and_meta(response.content.decode("utf-8"))

            if not offers:
                print(f"[justjoin] Brak ofert na stronie {page_num} — koniec danych.")
                break

            all_offers.extend(offers)

            if total_items is None:
                total_items = meta.get("totalItems", 0)

            if progress_callback:
                progress_callback(len(all_offers), total_items or 0)

            # Pobierz cursor dla następnej strony z odpowiedzi API
            next_cursor = meta.get("next", {}).get("cursor")

            if next_cursor is None:
                print(f"[justjoin] Pobrano wszystkie {len(all_offers)} ofert.")
                break

            time.sleep(REQUEST_DELAY)

        return all_offers

    def _extract_offers_and_meta(self, rsc_text: str):
        """
        Wyciąga listę ofert i metadata z RSC payload Next.js.

        Używa json.JSONDecoder().raw_decode() do parsowania JSON
        bezpośrednio z pozycji w tekście RSC — działa niezależnie
        od formatu linii RSC (zarówno JSON jak i T-chunk format).

        Parametry:
            rsc_text: pełny tekst odpowiedzi RSC jako string

        Zwraca:
            Tuple (offers: list, meta: dict)
        """
        # Szukamy punktu startowego struktury TanStack Query
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
        Konwertuje surowe oferty z justjoin.it do wspólnego formatu.

        Pola w surowym rekordzie oferty:
          - "title"       → job_title
          - "companyName" → company_name
          - "slug"        → używany do zbudowania URL ogłoszenia

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
                    "job_url":      f"https://justjoin.it/job-offer/{slug}",
                })

            except Exception as e:
                print(f"[justjoin] UWAGA: Pominięto rekord #{i}: {e}")
                continue

        return normalized
