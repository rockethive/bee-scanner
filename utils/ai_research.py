# utils/ai_research.py
#
# Research AI — analizuje firmę przez Claude z web searchem.
# Wymagana zmienna środowiskowa: ANTHROPIC_API_KEY

import os
import anthropic

PROMPT_TEMPLATE = """Jesteś asystentem sprzedażowym agencji rekrutacyjnej Bee Talents. \
Twoim zadaniem jest zebranie aktualnych informacji o firmie "{company_name}", \
które pomogą handlowcowi przygotować się do rozmowy sprzedażowej.

Użyj narzędzia web_search aby znaleźć aktualne informacje o tej firmie.
{hs_context}
Odpowiedz w języku polskim używając poniższej struktury:

**1. Czym się zajmuje firma**
Krótki opis działalności (2-3 zdania). Branża, główne produkty/usługi, rynki.

**2. Skala i struktura**
Liczba pracowników, lokalizacje w Polsce, polska firma czy oddział zagranicznego podmiotu.

**3. Sytuacja rekrutacyjna**
Jak aktywnie rekrutują? Jakie role najczęściej szukają? Czy mają własny dział HR/TA? \
Czy posiadają dedykowaną stronę kariery (careers page)?

**4. Potencjalne potrzeby rekrutacyjne**
Jakich kandydatów prawdopodobnie szukają? Jakie wyzwania rekrutacyjne mogą mieć?

**5. Kontekst dla sprzedawcy**
Z czym warto zacząć rozmowę? Niedawne wydarzenia jako punkt wejścia? \
Podaj 1-2 konkretne opening linie.

Dla każdego podpunktu — jeśli nie możesz znaleźć danej informacji, \
napisz wprost "Brak informacji" zamiast zgadywać lub pomijać punkt."""


def research_company_stream(company_name: str, hs_data: dict = None):
    """Generator streamujący odpowiedź Claude z web searchem."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    hs_context = ""
    if hs_data:
        parts = []
        if hs_data.get("industry"):
            parts.append(f"branża: {hs_data['industry']}")
        if hs_data.get("employees"):
            parts.append(f"pracownicy: {hs_data['employees']}")
        if hs_data.get("city"):
            parts.append(f"miasto: {hs_data['city']}")
        if parts:
            hs_context = f"Dane z naszego CRM: {', '.join(parts)}.\n"

    prompt = PROMPT_TEMPLATE.format(
        company_name=company_name,
        hs_context=hs_context,
    )

    with client.messages.stream(
        model="claude-opus-4-5",
        max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
