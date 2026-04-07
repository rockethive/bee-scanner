# utils/exporter.py
#
# Ten plik odpowiada za:
#   1. Agregację danych per firma (build_companies_summary)
#   2. Eksport listy ogłoszeń do jobs.csv (export_jobs_csv)
#   3. Eksport podsumowania firm do companies_summary.csv (export_summary_csv)
#
# Używa wyłącznie bibliotek standardowych (csv, os, collections).
# Folder output/ jest tworzony automatycznie jeśli nie istnieje.

import csv
import os
from collections import defaultdict

from utils.scorer import score_company

# Ścieżki do plików wyjściowych
JOBS_CSV_PATH = "output/jobs.csv"
SUMMARY_CSV_PATH = "output/companies_summary.csv"

# Kolumny w pliku jobs.csv
JOB_FIELDS = ["company_name", "job_title", "platform", "job_url"]

# Kolumny w pliku companies_summary.csv
SUMMARY_FIELDS = [
    "company_name", "total_listings", "platforms", "job_titles",
    "score", "level", "level_color", "action", "score_reasons", "matched_criteria",
]


def build_companies_summary(jobs: list) -> list:
    """
    Tworzy zagregowane podsumowanie per firma.

    Dla każdej firmy liczy:
      - ile ma ogłoszeń łącznie (total_listings)
      - na jakich platformach się pojawia (platforms — oddzielone przecinkami)
      - jakie tytuły stanowisk oferuje (job_titles — oddzielone | )

    Wynik jest posortowany malejąco po total_listings
    (firmy z największą liczbą ogłoszeń są na górze).

    Parametry:
        jobs: lista rekordów w wspólnym formacie (wynik merge_all_jobs)

    Zwraca:
        Lista słowników, np.:
        [
            {
                "company_name":   "Allegro",
                "total_listings": 5,
                "platforms":      "justjoin,rocketjobs",
                "job_titles":     "Python Dev | Data Engineer | QA Lead | ...",
            },
            ...
        ]
    """
    # Słownik: company_name → dane agregowane
    # defaultdict automatycznie tworzy pusty wpis dla nowej firmy
    summary = defaultdict(lambda: {
        "total_listings": 0,
        "platforms": set(),    # set() = unikalny zbiór platform (bez duplikatów)
        "job_titles": [],      # lista tytułów stanowisk
    })

    for job in jobs:
        company = job["company_name"]
        summary[company]["total_listings"] += 1
        summary[company]["platforms"].add(job["platform"])
        summary[company]["job_titles"].append(job["job_title"])

    # Konwertuj do listy słowników z czytelnym formatem
    result = []
    for company_name, data in summary.items():
        company = {
            "company_name":   company_name,
            "total_listings": data["total_listings"],
            "platforms":      ",".join(sorted(data["platforms"])),
            "job_titles":     " | ".join(sorted(set(data["job_titles"]))),
        }
        # Dodaj lead score
        scoring = score_company(company)
        company.update(scoring)
        result.append(company)

    # Sortuj: najpierw po poziomie leada (A→D), potem po score malejąco
    level_order = {"A": 0, "B": 1, "C": 2, "D": 3}
    result.sort(key=lambda x: (level_order.get(x["level"], 9), -x["score"]))
    return result


def export_jobs_csv(jobs: list, path: str = JOBS_CSV_PATH) -> None:
    """
    Zapisuje listę wszystkich ogłoszeń do pliku CSV.

    Tworzy folder output/ automatycznie, jeśli nie istnieje.

    Parametry:
        jobs: lista rekordów w wspólnym formacie
        path: ścieżka do pliku wyjściowego (domyślnie output/jobs.csv)

    Przykład wyniku w pliku:
        company_name,job_title,platform,job_url
        Allegro,Senior Python Developer,justjoin,https://justjoin.it/job-offer/...
        CD Projekt,Game Designer,rocketjobs,https://rocketjobs.pl/oferty-pracy/...
    """
    _ensure_output_dir(path)

    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOB_FIELDS)
        writer.writeheader()          # zapisz nagłówek (nazwy kolumn)
        writer.writerows(jobs)        # zapisz wszystkie wiersze

    print(f"[exporter] Zapisano {len(jobs)} ogłoszeń → {path}")


def export_summary_csv(summary: list, path: str = SUMMARY_CSV_PATH) -> None:
    """
    Zapisuje zagregowane podsumowanie per firma do pliku CSV.

    Parametry:
        summary: lista rekordów zwrócona przez build_companies_summary()
        path:    ścieżka do pliku wyjściowego (domyślnie output/companies_summary.csv)

    Przykład wyniku w pliku:
        company_name,total_listings,platforms,job_titles
        Allegro,5,justjoin,Python Dev | Data Eng | QA Lead | ...
        CD Projekt,3,rocketjobs,Game Designer | QA | ...
    """
    _ensure_output_dir(path)

    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary)

    print(f"[exporter] Zapisano {len(summary)} firm → {path}")


def _ensure_output_dir(path: str) -> None:
    """
    Pomocnicza funkcja — tworzy folder nadrzędny pliku jeśli nie istnieje.
    np. dla path="output/jobs.csv" tworzy folder "output/".

    Parametry:
        path: ścieżka do pliku (może zawierać katalog nadrzędny)
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)  # exist_ok=True = nie błądź jeśli już istnieje
