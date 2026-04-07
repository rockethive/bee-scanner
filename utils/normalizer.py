# utils/normalizer.py
#
# Ten plik odpowiada za:
#   1. Walidację i czyszczenie pojedynczego rekordu (clean_job)
#   2. Łączenie wyników ze wszystkich scraperów w jedną listę (merge_all_jobs)
#
# CEL:
#   Każdy scraper zwraca listę rekordów. Ten moduł gwarantuje,
#   że trafiają do CSV tylko rekordy kompletne i deduplikowane.

import re

# Zbiór polskich miast (i lokalizacji) używanych do normalizacji tytułów.
# Dzięki temu "Backend developer | Poznan" i "Backend developer - Warszawa"
# są traktowane jako to samo stanowisko.
POLISH_CITIES = {
    "warszawa", "krakow", "kraków", "lodz", "łódź", "wroclaw", "wrocław",
    "poznan", "poznań", "gdansk", "gdańsk", "szczecin", "bydgoszcz",
    "lublin", "katowice", "bialystok", "białystok", "gdynia", "czestochowa",
    "częstochowa", "radom", "sosnowiec", "torun", "toruń", "kielce",
    "rzeszow", "rzeszów", "gliwice", "zabrze", "olsztyn", "bielsko-biala",
    "bielsko-biała", "bytom", "zielona gora", "zielona góra", "rybnik",
    "ruda slaska", "ruda śląska", "opole", "tychy", "gorzow", "gorzów",
    "elblag", "elbląg", "plock", "płock", "walbrzych", "wałbrzych",
    "dabrowa gornicza", "dąbrowa górnicza", "tarnow", "tarnów",
    "chorzow", "chorzów", "koszalin", "legnica", "kalisz",
    "trojmiasto", "trójmiasto", "tri-city",
    "remote", "zdalnie", "hybrydowo", "cała polska",
}


def normalize_title(title: str) -> str:
    """
    Usuwa nazwę miasta/lokalizacji z końca tytułu stanowiska.

    Obsługuje separatory: |  -  ,  oraz brak separatora (samo miasto na końcu).

    Przykłady:
        "Backend developer | Poznan"  →  "Backend developer"
        "Backend developer - Warszawa" →  "Backend developer"
        "Backend developer Gdańsk"    →  "Backend developer"
        "Python Developer"            →  "Python Developer"  (bez zmian)
        "Full-Stack Developer"        →  "Full-Stack Developer"  (bez zmian)
    """
    # Przypadek z separatorem: "Tytuł | Miasto", "Tytuł - Miasto", "Tytuł, Miasto"
    pattern = r'\s*[|\-,]\s*([^|\-,]+)$'
    match = re.search(pattern, title)
    if match:
        candidate = match.group(1).strip().lower()
        if candidate in POLISH_CITIES:
            return title[:match.start()].strip()

    # Przypadek bez separatora: "Python Developer Warszawa"
    parts = title.rsplit(None, 1)
    if len(parts) == 2 and parts[1].strip().lower() in POLISH_CITIES:
        return parts[0].strip()

    return title


def clean_job(raw_job: dict):
    """
    Waliduje i czyści pojedynczy rekord ogłoszenia.

    Sprawdza, czy wymagane pola są niepuste.
    Usuwa zbędne spacje z wartości tekstowych (strip).
    Normalizuje tytuł stanowiska — usuwa suffix z miastem (np. "| Poznań").

    Parametry:
        raw_job: słownik z kluczami company_name, job_title, platform, job_url

    Zwraca:
        Oczyszczony słownik LUB None, jeśli któreś wymagane pole jest puste.

    Przykład wejścia:
        {"company_name": " Allegro ", "job_title": "Python Dev | Warszawa", ...}

    Przykład wyjścia:
        {"company_name": "Allegro", "job_title": "Python Dev", ...}
    """
    required_fields = ["company_name", "job_title", "platform", "job_url"]

    cleaned = {}
    for field in required_fields:
        value = raw_job.get(field, "")

        # Jeśli wartość nie jest stringiem, spróbuj ją skonwertować
        if not isinstance(value, str):
            value = str(value) if value is not None else ""

        value = value.strip()

        # Normalizacja tytułu — usuwa suffix z miastem
        if field == "job_title":
            value = normalize_title(value)

        # Jeśli pole jest puste po oczyszczeniu — odrzuć cały rekord
        if not value:
            return None

        cleaned[field] = value

    return cleaned


def merge_all_jobs(jobs_per_portal: list) -> list:
    """
    Łączy wyniki ze wszystkich scraperów w jedną listę.
    Usuwa duplikaty na podstawie klucza (company_name, job_title, platform).

    Dzięki temu to samo stanowisko wystawione w wielu miastach
    (różne URL, ten sam tytuł i firma) traktowane jest jako jeden rekord.
    Cross-portal duplikaty są zachowane (justjoin i rocketjobs to osobne wpisy).

    Parametry:
        jobs_per_portal: lista list — każda wewnętrzna lista to wyniki jednego scrapera
                         np. [[{...}, {...}], [{...}]]

    Zwraca:
        Jedna płaska lista unikalnych rekordów.
    """
    seen_jobs = set()
    merged = []

    for portal_jobs in jobs_per_portal:
        for raw_job in portal_jobs:
            job = clean_job(raw_job)

            if job is None:
                continue

            key = (
                job["company_name"].lower().strip(),
                job["job_title"].lower().strip(),
                job["platform"],
            )

            if key in seen_jobs:
                continue

            seen_jobs.add(key)
            merged.append(job)

    return merged
