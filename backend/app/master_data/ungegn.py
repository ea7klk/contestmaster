"""UNGEGN World Geographical Names country reference data."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime

SOURCE_KEY = "ungegn-wgn-countries"
DATASET_KEY = "countries-ungegn-wgn"
SOURCE_URL = "https://ungegn-api.azurewebsites.net/API/GetCountriesWithSearch/250/1/"
API_DOCS_URL = "https://ungegn-api.azurewebsites.net/swagger/v1/swagger.json"
USE_TERMS_URL = (
    "https://unstats.un.org/unsd/ungegn/meetings/Bureau_Divisions/documents/"
    "UNGEGN_Bureau_WGN_November_2023_updated.pdf"
)
PARSER_VERSION = "ungegn-wgn-countries-1"


@dataclass(frozen=True)
class WgnCountry:
    m49_code: str
    name: str
    iso3_code: str
    iso2_code: str | None


@dataclass(frozen=True)
class WgnCountryData:
    countries: tuple[WgnCountry, ...]
    retrieved_at: datetime
    normalized_checksum: str
    response_sha256: str


def parse_country_response(payload: bytes, retrieved_at: datetime) -> WgnCountryData:
    """Parse the compact country fields and reject incomplete or ambiguous feeds."""
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    try:
        records = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid UNGEGN WGN JSON response") from exc
    if not isinstance(records, list) or not 190 <= len(records) <= 250:
        raise ValueError("UNGEGN WGN country response is incomplete")

    countries: list[WgnCountry] = []
    seen_m49: set[str] = set()
    seen_iso3: set[str] = set()
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("UNGEGN WGN country record must be an object")
        try:
            m49 = str(row["crM49"]).zfill(3)
            name = row["countryName"].strip()
            iso3 = row["crIso3"].strip().upper()
            raw_iso2 = row.get("crIso2")
            iso2 = (
                raw_iso2.strip().upper()
                if isinstance(raw_iso2, str) and raw_iso2.strip()
                else None
            )
        except (KeyError, AttributeError, TypeError) as exc:
            raise ValueError("UNGEGN WGN country record is missing required fields") from exc
        if len(m49) != 3 or not m49.isdigit() or not name or len(iso3) != 3 or not iso3.isalpha():
            raise ValueError("UNGEGN WGN country record has invalid identifiers or name")
        if iso2 is not None and (len(iso2) != 2 or not iso2.isalpha()):
            raise ValueError("UNGEGN WGN country record has invalid ISO alpha-2 code")
        if m49 in seen_m49 or iso3 in seen_iso3:
            raise ValueError("UNGEGN WGN country response contains duplicate identifiers")
        seen_m49.add(m49)
        seen_iso3.add(iso3)
        countries.append(WgnCountry(m49, name, iso3, iso2))

    countries.sort(key=lambda item: item.m49_code)
    canonical = [
        {
            "m49_code": item.m49_code,
            "name": item.name,
        }
        for item in countries
    ]
    normalized = json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode()
    return WgnCountryData(
        tuple(countries),
        retrieved_at.astimezone(UTC),
        hashlib.sha256(normalized).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


def fetch_countries() -> WgnCountryData:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": "Contestmaster/0.1 (master-data sync)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(4_000_000)
        if response.read(1):
            raise ValueError("UNGEGN WGN response exceeds the 4 MB limit")
    return parse_country_response(payload, datetime.now(UTC))
