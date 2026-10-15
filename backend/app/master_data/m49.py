"""Official UN Statistics Division M49 country-or-area reference data."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser

SOURCE_KEY = "unsd-m49-country-areas"
DATASET_KEY = "countries-unsd-m49"
SOURCE_URL = "https://unstats.un.org/unsd/methodology/m49/overview"
USE_TERMS_URL = "https://www.un.org/en/about-us/terms-of-use"
PARSER_VERSION = "unsd-m49-country-areas-1"
TABLE_ID = "downloadTableEN"
MINIMUM_COUNTRY_AREAS = 240
MAXIMUM_COUNTRY_AREAS = 1000
MAX_RESPONSE_BYTES = 5_000_000


@dataclass(frozen=True)
class M49CountryArea:
    m49_code: str
    name: str


@dataclass(frozen=True)
class M49CountryAreaData:
    country_areas: tuple[M49CountryArea, ...]
    retrieved_at: datetime
    normalized_checksum: str
    response_sha256: str


class _CountryAreaTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._table_depth = 0
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self._table_depth:
                self._table_depth += 1
            elif dict(attrs).get("id") == TABLE_ID:
                self._table_depth = 1
            return
        if self._table_depth != 1:
            return
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            if self._table_depth:
                self._table_depth -= 1
            return
        if self._table_depth != 1:
            return
        if tag in {"td", "th"} and self._cell_parts is not None:
            assert self._row is not None
            self._row.append("".join(self._cell_parts).strip())
            self._cell_parts = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def parse_country_areas(payload: bytes, retrieved_at: datetime) -> M49CountryAreaData:
    """Extract published country/area names and M49 codes without deriving fields."""
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    if not payload or len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("UN M49 response is empty or exceeds the size limit")
    try:
        html = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("UN M49 response is not UTF-8") from exc

    parser = _CountryAreaTableParser()
    parser.feed(html)
    parser.close()
    header_index = next(
        (
            index
            for index, row in enumerate(parser.rows)
            if any(re.sub(r"\s+", " ", value).casefold() == "country or area" for value in row)
            and any(re.sub(r"\s+", " ", value).casefold() == "m49 code" for value in row)
        ),
        None,
    )
    if header_index is None:
        raise ValueError("UN M49 country-or-area table headers were not found")
    headers = [re.sub(r"\s+", " ", value).casefold() for value in parser.rows[header_index]]
    name_index = headers.index("country or area")
    code_index = headers.index("m49 code")

    country_areas: list[M49CountryArea] = []
    seen_codes: set[str] = set()
    for row in parser.rows[header_index + 1 :]:
        if len(row) <= max(name_index, code_index):
            raise ValueError("UN M49 country-or-area row is missing required columns")
        name = row[name_index]
        code = row[code_index]
        if not name or not re.fullmatch(r"[0-9]{3}", code):
            raise ValueError("UN M49 country-or-area row has an invalid name or code")
        if code in seen_codes:
            raise ValueError("UN M49 country-or-area table contains duplicate M49 codes")
        seen_codes.add(code)
        country_areas.append(M49CountryArea(m49_code=code, name=name))

    if not MINIMUM_COUNTRY_AREAS <= len(country_areas) <= MAXIMUM_COUNTRY_AREAS:
        raise ValueError("UN M49 country-or-area response is incomplete or unexpectedly large")
    country_areas.sort(key=lambda item: item.m49_code)
    canonical = [{"m49_code": item.m49_code, "name": item.name} for item in country_areas]
    normalized = json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode()
    return M49CountryAreaData(
        country_areas=tuple(country_areas),
        retrieved_at=retrieved_at.astimezone(UTC),
        normalized_checksum=hashlib.sha256(normalized).hexdigest(),
        response_sha256=hashlib.sha256(payload).hexdigest(),
    )


def fetch_country_areas() -> M49CountryAreaData:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": "Contestmaster/0.1 (master-data sync)",
            "Accept": "text/html",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(MAX_RESPONSE_BYTES)
        if response.read(1):
            raise ValueError("UN M49 response exceeds the size limit")
    return parse_country_areas(payload, datetime.now(UTC))
