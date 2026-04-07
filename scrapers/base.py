# scrapers/base.py
#
# Klasa bazowa dla wszystkich scraperów.
#
# CEL:
#   Każdy scraper (justjoin, rocketjobs, a w przyszłości np. pracuj.pl)
#   dziedziczy po BaseScraper i implementuje dwie metody:
#     - fetch_raw()  → pobiera surowe dane z portalu
#     - normalize()  → konwertuje surowe dane do wspólnego formatu
#
# DODANIE NOWEGO PORTALU w przyszłości:
#   1. Utwórz plik scrapers/nowaportal.py
#   2. Zdefiniuj klasę NowaPortalScraper(BaseScraper)
#   3. Ustaw PLATFORM_NAME = "nowaportal"
#   4. Zaimplementuj fetch_raw() i normalize()
#   5. Dodaj NowaPortalScraper() do listy scrapers w main.py
#   → Nic innego nie musisz zmieniać!


class BaseScraper:
    """
    Abstrakcyjna klasa bazowa dla wszystkich scraperów portali z ogłoszeniami.

    Każda subklasa MUSI:
      - ustawić atrybut PLATFORM_NAME (np. "justjoin")
      - zaimplementować metodę fetch_raw()
      - zaimplementować metodę normalize()
    """

    # Nazwa platformy używana w polu "platform" każdego rekordu.
    # Subklasa nadpisuje tę wartość, np. PLATFORM_NAME = "justjoin"
    PLATFORM_NAME: str = ""

    def fetch_raw(self) -> list:
        """
        Pobiera surowe dane z portalu (API lub HTML).

        Zwraca:
            list: Lista surowych obiektów (dict) z portalu.
                  W przypadku błędu zwraca pustą listę [].
        """
        raise NotImplementedError(
            f"Scraper '{self.__class__.__name__}' musi implementować fetch_raw()"
        )

    def normalize(self, raw_jobs: list) -> list:
        """
        Konwertuje surowe dane z portalu do wspólnego formatu.

        Wspólny format każdego rekordu:
            {
                "company_name": str,
                "job_title":    str,
                "platform":     str,   # wartość z PLATFORM_NAME
                "job_url":      str,
            }

        Parametry:
            raw_jobs: lista surowych obiektów zwrócona przez fetch_raw()

        Zwraca:
            list: Lista rekordów w wspólnym formacie.
        """
        raise NotImplementedError(
            f"Scraper '{self.__class__.__name__}' musi implementować normalize()"
        )

    def run(self, progress_callback=None) -> list:
        """
        Główna metoda wywoływana przez app.py.
        Kolejno: pobiera dane → normalizuje → zwraca gotową listę.

        Parametry:
            progress_callback: opcjonalna funkcja(fetched: int, total: int)
                               wywoływana po każdej stronie podczas pobierania

        Zwraca:
            list: Lista rekordów w wspólnym formacie (może być pusta).
        """
        print(f"[{self.PLATFORM_NAME}] Rozpoczynam pobieranie danych...")
        raw_jobs = self.fetch_raw(progress_callback=progress_callback)

        if not raw_jobs:
            print(f"[{self.PLATFORM_NAME}] Brak surowych danych — fetch_raw() zwróciło pustą listę.")
            return []

        print(f"[{self.PLATFORM_NAME}] Pobrano {len(raw_jobs)} surowych rekordów. Normalizuję...")
        normalized = self.normalize(raw_jobs)
        print(f"[{self.PLATFORM_NAME}] Po normalizacji: {len(normalized)} rekordów.")
        return normalized
