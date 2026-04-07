# utils/scorer.py
#
# System scoringu leadów dla agencji rekrutacyjnej (white collar).
#
# Na podstawie danych dostępnych ze scraperów (company_name, total_listings,
# platforms, job_titles) przyznaje punkty i nadaje poziom A–D.
#
# Co możemy ocenić automatycznie:
#   ✓ Aktywność rekrutacyjna (liczba ofert)
#   ✓ Profil stanowisk (analiza tytułów: niszowe / menedżerskie / blue collar)
#   ✓ Sygnały zakupowe (obecność na platformie)
#   ✗ Kondycja firmy (brak danych o zatrudnieniu, finansowaniu)
#   ✗ Historia współpracy, outreach (brak danych)

import json


# ---------------------------------------------------------------------------
# Słowa kluczowe do klasyfikacji stanowisk
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ID kryteriów — muszą pasować do data-crit-id w company.html
# ---------------------------------------------------------------------------
CRIT_HAS_RECRUITMENT = "has_recruitment"   # Ma otwartą rekrutację teraz
CRIT_3PLUS_LISTINGS  = "three_plus"        # Ma 3+ otwartych ofert jednocześnie
CRIT_REGULAR         = "regular_recruiting" # Rekrutuje regularnie (proxy: 6+ ofert)
CRIT_NICHE_ROLE      = "niche_role"        # Rola niszowa / rzadka
CRIT_MANAGEMENT      = "management_role"   # Rola menedżerska / C-level
CRIT_OPERATIONAL     = "operational_role"  # Typowa rola operacyjna
CRIT_CAREER_PAGE     = "career_page"       # Aktywna strona kariery / portal
CRIT_BOTH_PLATFORMS  = "both_platforms"    # Wcześniej korzystał z agencji (proxy: 2 portale)
CRIT_BLUE_COLLAR     = "blue_collar"       # Blue collar (dyskwalifikator)
CRIT_COMPETITOR_AGENCY = "competitor_agency" # Ogłoszenie od agencji (dyskwalifikator)

# Stanowiska blue collar — dyskwalifikator (−10 pkt każde)
BLUE_COLLAR_KEYWORDS = [
    "magazynier", "magazyn", "warehouse", "produkcja", "production worker",
    "operator maszyn", "operator linii", "spawacz", "welder",
    "kierowca", "driver", "montażysta", "assembly", "pakowacz",
    "pracownik fizyczn", "pracownik produkcji", "sortowni",
    "forklift", "wózek widłowy", "pracownik magazyn", "logistyk magazyn",
]

# Nazwy agencji rekrutacyjnych — dyskwalifikator (−10 pkt)
RECRUITMENT_AGENCY_KEYWORDS = [
    "hays", "antal", "grafton", "michael page", "adecco", "manpower",
    "randstad", "kelly services", "cpl", "brook street", "page personnel",
    "work service", "trenkwalder", "gi group", "talent place",
    "agencja pracy", "agencja rekrutacyj",
]

# Role menedżerskie / dyrektorskie / C-level (+2 pkt)
MANAGEMENT_KEYWORDS = [
    "manager", "director", "head of", "head ", "lead ", " lead",
    "vp ", "vice president", "chief", "ceo", "cto", "cfo", "coo",
    "dyrektor", "kierownik", "szef", "prezes", "zarząd", "c-level",
    "country manager", "regional manager",
]

# Role niszowe — IT / finanse / prawo / rzadkie (+3 pkt)
NICHE_KEYWORDS = [
    # IT
    "engineer", "developer", "architect", "devops", "data ", "machine learning",
    "python", "java", "javascript", "react", "angular", "vue",
    "backend", "frontend", "fullstack", "full-stack", "full stack",
    "cloud", "security", "cybersecurity", "qa ", "tester", "scrum",
    "product manager", "product owner", "ux", "ui designer",
    # Finanse / prawo / compliance
    "finance", "finanse", "accountant", "księgow", "prawnik", "lawyer",
    "compliance", "auditor", "tax", "controlling", "controller",
    "analityk finansow", "financial analyst",
    # Rzadkie / specjalistyczne
    "consultant", "konsultant", "specialist", "specjalista",
    "scientist", "researcher", "actuar",
]

# Role operacyjne — typowe white collar (+1 pkt)
OPERATIONAL_KEYWORDS = [
    "sprzedaż", "sales", "obsługa klienta", "customer service",
    "administracja", "administration", "hr ", "rekrutacja",
    "marketing", "office", "koordynator", "coordinator",
    "asystent", "assistant", "recepcja", "reception",
]


# ---------------------------------------------------------------------------
# Główna funkcja scoringu
# ---------------------------------------------------------------------------

def score_company(company: dict) -> dict:
    """
    Oblicza lead score firmy na podstawie danych ze scraperów.

    Parametry:
        company: słownik z kluczami:
                 company_name, total_listings, platforms, job_titles

    Zwraca:
        Słownik z:
            score        — łączna liczba punktów (int)
            level        — poziom leada: A / B / C / D
            level_color  — kolor Bootstrap: success / primary / warning / danger
            action       — rekomendowane działanie (str)
            score_reasons — lista przyznanych punktów oddzielona " | " (str)
    """
    score   = 0
    reasons = []
    matched = []   # lista ID kryteriów spełnionych automatycznie

    total         = int(company.get("total_listings", 0))
    platforms_str = company.get("platforms", "")
    platforms     = [p.strip() for p in platforms_str.split(",") if p.strip()]
    titles_lower  = company.get("job_titles", "").lower()
    name_lower    = company.get("company_name", "").lower()

    # -------------------------------------------------------------------
    # 1. DYSKWALIFIKATORY — sprawdź w pierwszej kolejności
    # -------------------------------------------------------------------

    is_blue_collar = False
    for kw in BLUE_COLLAR_KEYWORDS:
        if kw in titles_lower:
            score -= 10
            reasons.append(f"−10: Rola blue collar ('{kw}')")
            matched.append(CRIT_BLUE_COLLAR)
            is_blue_collar = True
            break

    for kw in RECRUITMENT_AGENCY_KEYWORDS:
        if kw in name_lower or kw in titles_lower:
            score -= 10
            reasons.append(f"−10: Agencja rekrutacyjna ('{kw}')")
            matched.append(CRIT_COMPETITOR_AGENCY)
            break

    # -------------------------------------------------------------------
    # 2. AKTYWNOŚĆ REKRUTACYJNA
    # -------------------------------------------------------------------

    score += 1
    reasons.append("+1: Ma otwartą rekrutację teraz")
    matched.append(CRIT_HAS_RECRUITMENT)

    if total >= 3:
        score += 2
        reasons.append(f"+2: {total} otwartych ofert jednocześnie (≥3)")
        matched.append(CRIT_3PLUS_LISTINGS)

    if total >= 6:
        score += 3
        reasons.append(f"+3: Bardzo aktywna rekrutacja ({total} ofert — proxy regularności)")
        matched.append(CRIT_REGULAR)

    # -------------------------------------------------------------------
    # 3. PROFIL STANOWISK
    # -------------------------------------------------------------------

    if not is_blue_collar:
        is_management = any(kw in titles_lower for kw in MANAGEMENT_KEYWORDS)
        is_niche      = any(kw in titles_lower for kw in NICHE_KEYWORDS)

        if is_niche:
            score += 3
            reasons.append("+3: Role niszowe / rzadkie (IT / finanse / prawo)")
            matched.append(CRIT_NICHE_ROLE)

        if is_management:
            score += 2
            reasons.append("+2: Role menedżerskie lub C-level")
            matched.append(CRIT_MANAGEMENT)

        if not is_niche and not is_management:
            score += 1
            reasons.append("+1: Typowe role operacyjne (sprzedaż / obsługa / administracja)")
            matched.append(CRIT_OPERATIONAL)

    # -------------------------------------------------------------------
    # 4. SYGNAŁY ZAKUPOWE
    # -------------------------------------------------------------------

    score += 1
    reasons.append("+1: Aktywna obecność na portalu rekrutacyjnym")
    matched.append(CRIT_CAREER_PAGE)

    if len(platforms) >= 2:
        score += 2
        reasons.append("+2: Obecność na obu portalach (justjoin + rocketjobs)")
        matched.append(CRIT_BOTH_PLATFORMS)

    # -------------------------------------------------------------------
    # 5. POZIOM LEADA
    # -------------------------------------------------------------------

    if score >= 14:
        level, color, action = "A", "success", "Kontakt natychmiastowy — przydziel opiekuna"
    elif score >= 9:
        level, color, action = "B", "primary", "Umów rozmowę odkrywczą w ciągu tygodnia"
    elif score >= 4:
        level, color, action = "C", "warning", "Dodaj do nurturingu, ustaw alert na zmiany"
    else:
        level, color, action = "D", "danger", "Nie angażuj zasobów sprzedażowych"

    return {
        "score":            score,
        "level":            level,
        "level_color":      color,
        "action":           action,
        "score_reasons":    " | ".join(reasons),
        "matched_criteria": json.dumps(matched),
    }
