# main.py
#
# PUNKT WEJŚCIA — uruchom ten plik żeby wykonać skanowanie.
#
# Jak uruchomić:
#   python main.py
#
# Co robi:
#   1. Uruchamia scraper dla justjoin.it
#   2. Uruchamia scraper dla rocketjobs.pl
#   3. Łączy wyniki w jedną listę (deduplikuje po URL)
#   4. Zapisuje jobs.csv (wszystkie ogłoszenia)
#   5. Zapisuje companies_summary.csv (agregacja per firma)
#
# Jeśli portal jest niedostępny → program ładuje dane testowe z data/
# i dalej działa normalnie (eksportuje CSV z przykładowymi danymi).

import json
import os

from scrapers.justjoin import JustJoinScraper
from scrapers.rocketjobs import RocketJobsScraper
from utils.normalizer import merge_all_jobs
from utils.exporter import build_companies_summary, export_jobs_csv, export_summary_csv


def load_test_data(platform_name: str) -> list:
    """
    Ładuje dane testowe z pliku data/test_{platform_name}.json.

    Używane jako fallback gdy scraper nie może pobrać danych z portalu
    (np. brak internetu, portal zablokował scraping, zmienił strukturę).

    Parametry:
        platform_name: nazwa platformy, np. "justjoin" lub "rocketjobs"

    Zwraca:
        Lista rekordów z pliku testowego, lub [] jeśli plik nie istnieje.
    """
    # Buduj ścieżkę do pliku testowego
    # os.path.dirname(__file__) = katalog w którym jest main.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_file = os.path.join(base_dir, "data", f"test_{platform_name}.json")

    if not os.path.exists(test_file):
        print(f"[main] UWAGA: Brak pliku testowego: {test_file}")
        return []

    try:
        with open(test_file, encoding="utf-8") as f:
            data = json.load(f)
        print(f"[main] Załadowano {len(data)} rekordów testowych z {test_file}")
        return data

    except (json.JSONDecodeError, IOError) as e:
        print(f"[main] BŁĄD przy ładowaniu danych testowych: {e}")
        return []


def print_summary(all_jobs: list, companies: list) -> None:
    """
    Wyświetla czytelne podsumowanie wyników w terminalu.

    Pokazuje:
      - łączną liczbę ogłoszeń
      - liczbę unikalnych firm
      - TOP 10 firm z największą liczbą ogłoszeń
      - przykład zagregowanego widoku per firma

    Parametry:
        all_jobs:  lista wszystkich ogłoszeń
        companies: lista podsumowań per firma (wynik build_companies_summary)
    """
    print("\n" + "=" * 60)
    print("WYNIKI SKANOWANIA")
    print("=" * 60)
    print(f"Łącznie ogłoszeń:    {len(all_jobs)}")
    print(f"Unikalnych firm:     {len(companies)}")

    # Policz ile ogłoszeń pochodzi z każdej platformy
    platform_counts = {}
    for job in all_jobs:
        p = job["platform"]
        platform_counts[p] = platform_counts.get(p, 0) + 1
    for platform, count in sorted(platform_counts.items()):
        print(f"  - {platform}: {count} ogłoszeń")

    # Pokaż TOP 10 firm
    print("\nTOP 10 firm według liczby ogłoszeń:")
    print("-" * 60)
    for i, company in enumerate(companies[:10], start=1):
        print(f"  {i:2}. {company['company_name']}")
        print(f"       Ogłoszeń: {company['total_listings']}  |  Platformy: {company['platforms']}")
        # Pokaż max 3 tytuły stanowisk żeby nie zaśmiecać terminala
        titles = company["job_titles"].split(" | ")
        preview = titles[:3]
        more = len(titles) - 3
        print(f"       Stanowiska: {', '.join(preview)}", end="")
        if more > 0:
            print(f" (+{more} więcej)")
        else:
            print()

    print("=" * 60)


def main():
    """
    Główna funkcja programu.

    Uruchamia wszystkie scrapery, łączy dane, zapisuje CSV.
    """
    print("=" * 60)
    print("BEE SCANNER — start skanowania")
    print("=" * 60)

    # Lista scraperów do uruchomienia.
    # Żeby dodać nowy portal: dodaj tutaj nową klasę scrapera.
    scrapers = [
        JustJoinScraper(),
        RocketJobsScraper(),
        # W przyszłości: PracujScraper(), NoBFlufferScraper(), ...
    ]

    # Zbierz wyniki ze wszystkich scraperów
    all_portal_results = []

    for scraper in scrapers:
        print(f"\n--- {scraper.PLATFORM_NAME.upper()} ---")

        # Uruchom scraper
        jobs = scraper.run()

        # Jeśli scraper nie zwrócił danych — użyj danych testowych jako fallback
        if not jobs:
            print(f"[main] {scraper.PLATFORM_NAME}: brak danych z portalu → ładuję dane testowe.")
            jobs = load_test_data(scraper.PLATFORM_NAME)

        all_portal_results.append(jobs)

    # Połącz wyniki ze wszystkich portali w jedną listę
    # merge_all_jobs() też usuwa duplikaty (po job_url)
    print("\n--- ŁĄCZENIE WYNIKÓW ---")
    all_jobs = merge_all_jobs(all_portal_results)
    print(f"[main] Łącznie unikalnych ogłoszeń: {len(all_jobs)}")

    if not all_jobs:
        print("[main] UWAGA: Brak jakichkolwiek danych. Sprawdź połączenie lub pliki testowe.")
        return

    # Zbuduj agregację per firma
    companies = build_companies_summary(all_jobs)

    # Wyeksportuj do CSV
    print("\n--- EKSPORT DO CSV ---")
    export_jobs_csv(all_jobs)
    export_summary_csv(companies)

    # Wyświetl podsumowanie w terminalu
    print_summary(all_jobs, companies)

    print("\nGotowe! Pliki zapisane w katalogu output/")
    print("  - output/jobs.csv             (wszystkie ogłoszenia)")
    print("  - output/companies_summary.csv (agregacja per firma)")


if __name__ == "__main__":
    # Ten blok uruchamia main() tylko gdy plik jest uruchomiony bezpośrednio:
    #   python main.py       → uruchamia main()
    #   import main          → NIE uruchamia main() (tylko importuje)
    main()
