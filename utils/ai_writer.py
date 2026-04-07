from __future__ import annotations

# utils/ai_writer.py
#
# Generator treści AI (podsumowania kontaktu + emaile) oparty na OpenAI API.
#
# Wymagane zmienne środowiskowe:
#   OPENAI_API_KEY — klucz API z platform.openai.com
#
# Używa modelu gpt-4o-mini (szybki, tani, wystarczający dla krótkich tekstów).

import os

SYSTEM_PROMPT = """Jesteś asystentem handlowym w Bee Talents — polskiej agencji rekrutacyjnej \
specjalizującej się w rekrutacji white collar (IT, finanse, sprzedaż, marketing, prawo, zarządzanie).

Piszesz po polsku. Styl: bezpośredni, konkretny, profesjonalny — bez korporacyjnego żargonu \
i pustych frazesów. Unikaj ogólników — jeśli masz dane o firmie (stanowiska, liczba ofert, \
platformy rekrutacyjne), odwołaj się do nich wprost. Nie używaj nadmiernego entuzjazmu."""


def _get_client():
    """Zwraca klienta OpenAI lub None jeśli biblioteka nie jest zainstalowana."""
    try:
        from openai import OpenAI
        return OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    except ImportError:
        return None


def _chat(client, prompt: str, max_tokens: int = 300) -> str:
    """Wysyła zapytanie do OpenAI i zwraca odpowiedź."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def generate_contact_summary(
    company_data: dict,
    activities: list,
    deal: dict | None,
) -> str:
    """
    Generuje krótkie (2-3 zdania) podsumowanie kontaktu dla handlowca.
    """
    client = _get_client()
    if not client:
        return "Brak biblioteki openai — uruchom: pip install openai"

    parts = [f"Firma: {company_data.get('name', '?')}"]
    if company_data.get("industry"):
        parts.append(f"Branża: {company_data['industry']}")
    if company_data.get("employees"):
        parts.append(f"Liczba pracowników: {company_data['employees']}")
    if company_data.get("days_since_contact") is not None:
        parts.append(f"Ostatni kontakt: {company_data['days_since_contact']} dni temu")
    else:
        parts.append("Brak historii kontaktu w CRM.")

    if activities:
        acts = "\n".join(
            f"  - {a['type'].upper()} ({a.get('timestamp','')[:10]}): {a['label']}"
            for a in activities
        )
        parts.append(f"Ostatnie aktywności:\n{acts}")

    if deal:
        parts.append(
            f"Aktywny deal: {deal.get('dealname','?')} | Etap: {deal.get('dealstage','?')}"
        )

    prompt = (
        "\n".join(parts)
        + "\n\nNapisz krótkie podsumowanie (2-3 zdania) dla handlowca przygotowującego się "
        "do kontaktu z tą firmą. Wskaż najważniejszy kontekst i sugerowany następny krok."
    )

    try:
        return _chat(client, prompt, max_tokens=250)
    except Exception as e:
        return f"Błąd API: {e}"


def generate_email(
    company_name: str,
    email_type: str,
    context: dict,
) -> dict:
    """
    Generuje email do potencjalnego klienta.

    email_type: "cold" | "followup" | "followup_call"
    Zwraca: {"subject": str, "body": str}
    """
    client = _get_client()
    if not client:
        return {"subject": "—", "body": "Brak biblioteki openai — uruchom: pip install openai"}

    type_instructions = {
        "cold": (
            "Napisz cold email — pierwszy kontakt. Maksymalnie 5 zdań. "
            "Powołaj się konkretnie na ich aktualne oferty pracy jako powód kontaktu. "
            "Nie bądź ogólnikowy. Zaproponuj krótką, 15-minutową rozmowę. "
            "Podpisz imieniem i nazwiskiem (możesz wymyślić) oraz 'Bee Talents'."
        ),
        "followup": (
            "Napisz follow-up po braku odpowiedzi na pierwszego maila (wysłanego ok. tydzień temu). "
            "Maksymalnie 3 zdania. Nawiąż krótko do poprzedniej wiadomości, "
            "zapytaj czy to dobry moment i czy możesz pomóc. Nie bądź nachalny."
        ),
        "followup_call": (
            "Napisz follow-up po odbyciu rozmowy telefonicznej/discovery call. "
            "Podziękuj za rozmowę (1 zdanie). Wymień 2-3 konkretne korzyści ze "
            "współpracy z Bee Talents (dostęp do pasywnych kandydatów, skrócenie "
            "czasu rekrutacji, success fee model). Zaproponuj konkretny następny krok. "
            "Łącznie max 6 zdań."
        ),
    }

    instruction = type_instructions.get(email_type, type_instructions["cold"])

    ctx_lines = [f"Firma: {company_name}"]
    if context.get("total_listings"):
        ctx_lines.append(f"Liczba aktualnych ofert pracy: {context['total_listings']}")
    if context.get("job_titles"):
        ctx_lines.append(f"Stanowiska w ofertach: {context['job_titles'][:300]}")
    if context.get("platforms"):
        ctx_lines.append(f"Portale rekrutacyjne: {context['platforms']}")

    prompt = (
        "\n".join(ctx_lines)
        + f"\n\nZadanie: {instruction}"
        + "\n\nOdpowiedz DOKŁADNIE w tym formacie:\n"
        + "TEMAT: [temat wiadomości]\nTREŚĆ:\n[treść emaila]"
    )

    try:
        raw = _chat(client, prompt, max_tokens=600)

        subject, body = "", raw
        if "TEMAT:" in raw and "TREŚĆ:" in raw:
            after_temat  = raw.split("TEMAT:", 1)[1]
            parts        = after_temat.split("TREŚĆ:", 1)
            subject      = parts[0].strip()
            body         = parts[1].strip() if len(parts) > 1 else raw

        return {"subject": subject, "body": body}

    except Exception as e:
        return {"subject": "—", "body": f"Błąd API: {e}"}
