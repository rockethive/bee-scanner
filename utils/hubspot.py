# utils/hubspot.py
#
# Integracja z HubSpot CRM (Private App Token).
# Używa HubSpot v3 API do wyszukiwania firm, pobierania aktywności i dealów.
#
# Wymagane zmienne środowiskowe:
#   HUBSPOT_ACCESS_TOKEN  — token z HubSpot Private App
#   HUBSPOT_PORTAL_ID     — ID portalu (do budowania linków do CRM)

from __future__ import annotations

import os
import re
import requests
from datetime import datetime, timezone


def _strip_html(text: str) -> str:
    """Usuwa tagi HTML z tekstu (np. z notatek HubSpot)."""
    clean = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", clean).strip()

HUBSPOT_BASE = "https://api.hubapi.com"


def _headers() -> dict:
    token = os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def search_company(company_name: str) -> dict | None:
    """
    Szuka firmy po nazwie w HubSpot CRM.
    Używa operatora CONTAINS_TOKEN — dopasowuje częściowe nazwy.

    Zwraca:
        Pierwszy wynik (dict z HubSpot) lub None jeśli brak.
    """
    url = f"{HUBSPOT_BASE}/crm/v3/objects/companies/search"
    payload = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "name",
                "operator": "CONTAINS_TOKEN",
                "value": company_name,
            }]
        }],
        "properties": [
            "name", "domain", "city", "industry",
            "numberofemployees", "hs_object_id",
            "notes_last_contacted", "hubspot_owner_id",
        ],
        "limit": 1,
    }
    try:
        r = requests.post(url, json=payload, headers=_headers(), timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0] if results else None
    except Exception as e:
        print(f"[hubspot] search_company error: {e}")
        return None


def get_activities(company_id: str, limit: int = 5) -> list:
    """
    Pobiera ostatnie N aktywności (notatki, rozmowy, emaile) dla firmy.

    Dla każdej aktywności zwraca:
        type      — "note" | "call" | "email"
        label     — krótki opis
        timestamp — ISO string
    """
    activities = []

    type_config = {
        "notes":  {
            "props": ["hs_note_body", "hs_timestamp"],
            "label_fn": lambda p: ("Notatka: " + _strip_html(p.get("hs_note_body", ""))[:60]) if p.get("hs_note_body") else "Notatka",
            "body_fn":  lambda p: _strip_html(p.get("hs_note_body", "")),
            "ts_key": "hs_timestamp",
        },
        "calls":  {
            "props": ["hs_call_title", "hs_call_body", "hs_timestamp"],
            "label_fn": lambda p: p.get("hs_call_title") or "Rozmowa telefoniczna",
            "body_fn":  lambda p: _strip_html(p.get("hs_call_body", "")),
            "ts_key": "hs_timestamp",
        },
        "emails": {
            "props": ["hs_email_subject", "hs_email_text", "hs_timestamp", "hs_email_direction"],
            "label_fn": lambda p: p.get("hs_email_subject") or "Email",
            "body_fn":  lambda p: _strip_html(p.get("hs_email_text", "")),
            "ts_key": "hs_timestamp",
        },
    }

    for obj_type, cfg in type_config.items():
        # Pobierz powiązane IDs
        assoc_url = f"{HUBSPOT_BASE}/crm/v3/objects/companies/{company_id}/associations/{obj_type}"
        try:
            r = requests.get(assoc_url, headers=_headers(), timeout=10)
            if r.status_code != 200:
                continue
            ids = [item["id"] for item in r.json().get("results", [])]
            if not ids:
                continue

            # Batch read szczegółów
            batch_url = f"{HUBSPOT_BASE}/crm/v3/objects/{obj_type}/batch/read"
            payload = {
                "inputs": [{"id": i} for i in ids[:10]],
                "properties": cfg["props"],
            }
            r2 = requests.post(batch_url, json=payload, headers=_headers(), timeout=10)
            if r2.status_code != 200:
                continue

            for item in r2.json().get("results", []):
                props = item.get("properties", {})
                ts = props.get(cfg["ts_key"]) or item.get("createdAt", "")
                label = cfg["label_fn"](props)
                body  = cfg["body_fn"](props)
                short_type = obj_type.rstrip("s")  # notes→note, calls→call, emails→email
                activities.append({
                    "type":      short_type,
                    "label":     label,
                    "body":      body,
                    "timestamp": ts,
                })
        except Exception as e:
            print(f"[hubspot] get_activities error ({obj_type}): {e}")

    # Sortuj malejąco po timestamp
    def parse_ts(a: dict) -> datetime:
        ts = a.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    activities.sort(key=parse_ts, reverse=True)
    return activities[:limit]


def get_pipeline_map() -> dict:
    """
    Pobiera mapę pipeline'ów dealów z HubSpot.

    Zwraca:
        {pipeline_id: {"name": str, "stages": {stage_id: label}}}
    """
    url = f"{HUBSPOT_BASE}/crm/v3/pipelines/deals"
    try:
        r = requests.get(url, headers=_headers(), timeout=10)
        r.raise_for_status()
        result = {}
        for p in r.json().get("results", []):
            pid = p.get("id", "")
            result[pid] = {
                "name":   p.get("label", pid),
                "stages": {s.get("id", ""): s.get("label", "") for s in p.get("stages", [])},
            }
        return result
    except Exception as e:
        print(f"[hubspot] get_pipeline_map error: {e}")
        return {}


def get_owner_name(owner_id: str) -> str:
    """Pobiera imię i nazwisko opiekuna (właściciela) firmy z HubSpot."""
    if not owner_id:
        return ""
    url = f"{HUBSPOT_BASE}/crm/v3/owners/{owner_id}"
    try:
        r = requests.get(url, headers=_headers(), timeout=10)
        r.raise_for_status()
        d = r.json()
        return f"{d.get('firstName', '')} {d.get('lastName', '')}".strip()
    except Exception as e:
        print(f"[hubspot] get_owner_name error: {e}")
        return ""


def get_all_deals(company_id: str) -> list:
    """
    Pobiera wszystkie deale powiązane z firmą (posortowane malejąco wg daty).

    Każdy deal zawiera:
        name, pipeline_name, stage_name, date_raw
    """
    assoc_url = f"{HUBSPOT_BASE}/crm/v3/objects/companies/{company_id}/associations/deals"
    try:
        r = requests.get(assoc_url, headers=_headers(), timeout=10)
        if r.status_code != 200:
            return []
        deal_ids = [item["id"] for item in r.json().get("results", [])]
        if not deal_ids:
            return []

        pipeline_map = get_pipeline_map()

        batch_url = f"{HUBSPOT_BASE}/crm/v3/objects/deals/batch/read"
        payload = {
            "inputs":     [{"id": did} for did in deal_ids[:20]],
            "properties": ["dealname", "dealstage", "pipeline", "closedate", "createdate"],
        }
        r2 = requests.post(batch_url, json=payload, headers=_headers(), timeout=10)
        if r2.status_code != 200:
            return []

        deals = []
        for item in r2.json().get("results", []):
            props  = item.get("properties", {})
            pid    = props.get("pipeline", "")
            sid    = props.get("dealstage", "")
            pinfo  = pipeline_map.get(pid, {})
            deals.append({
                "name":          props.get("dealname", ""),
                "pipeline_name": pinfo.get("name", pid),
                "stage_name":    pinfo.get("stages", {}).get(sid, sid),
                "date_raw":      props.get("closedate") or props.get("createdate") or item.get("createdAt", ""),
            })

        def _ts(d: dict) -> datetime:
            try:
                return datetime.fromisoformat(d["date_raw"].replace("Z", "+00:00"))
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        deals.sort(key=_ts, reverse=True)
        return deals
    except Exception as e:
        print(f"[hubspot] get_all_deals error: {e}")
        return []


def lookup_company_full(company_name: str) -> dict:
    """
    Kompleksowe wyszukiwanie: firma + aktywności + deal.

    Zwraca:
        {
            found: bool,
            id, name, domain, city, industry, employees,
            last_contacted, days_since_contact,
            activities: [...],
            deal: {...} | None,
            hubspot_url: str,
        }
    """
    company = search_company(company_name)
    if not company:
        return {"found": False}

    company_id = company["id"]
    props = company.get("properties", {})

    # Oblicz dni od ostatniego kontaktu
    last_contacted = props.get("notes_last_contacted")
    days_since_contact = None
    if last_contacted:
        try:
            lc_dt = datetime.fromisoformat(last_contacted.replace("Z", "+00:00"))
            days_since_contact = (datetime.now(timezone.utc) - lc_dt).days
        except Exception:
            pass

    activities  = get_activities(company_id)
    deals       = get_all_deals(company_id)
    owner_name  = get_owner_name(props.get("hubspot_owner_id", ""))

    portal_id   = os.environ.get("HUBSPOT_PORTAL_ID", "")
    hubspot_url = f"https://app.hubspot.com/contacts/{portal_id}/company/{company_id}" if portal_id else ""

    return {
        "found": True,
        "id": company_id,
        "name": props.get("name", company_name),
        "domain": props.get("domain", ""),
        "city": props.get("city", ""),
        "industry": props.get("industry", ""),
        "employees": props.get("numberofemployees", ""),
        "last_contacted": last_contacted,
        "days_since_contact": days_since_contact,
        "owner_name": owner_name,
        "activities": activities,
        "deals": deals,
        "hubspot_url": hubspot_url,
    }


def create_company(
    company_name: str,
    domain: str = "",
    industry: str = "",
    city: str = "",
) -> dict:
    """
    Tworzy nową firmę w HubSpot.

    Zwraca:
        {success: True, id, hubspot_url} lub {success: False, error: str}
    """
    url = f"{HUBSPOT_BASE}/crm/v3/objects/companies"
    props: dict = {"name": company_name}
    if domain:   props["domain"]   = domain
    if industry: props["industry"] = industry
    if city:     props["city"]     = city

    try:
        r = requests.post(url, json={"properties": props}, headers=_headers(), timeout=10)
        r.raise_for_status()
        result = r.json()
        company_id = result.get("id", "")
        portal_id  = os.environ.get("HUBSPOT_PORTAL_ID", "")
        hubspot_url = f"https://app.hubspot.com/contacts/{portal_id}/company/{company_id}" if portal_id else ""
        return {"success": True, "id": company_id, "hubspot_url": hubspot_url}
    except Exception as e:
        print(f"[hubspot] create_company error: {e}")
        return {"success": False, "error": str(e)}
