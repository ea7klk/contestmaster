"""Big CTY archive discovery and cty.dat parsing."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from xml.etree import ElementTree

SOURCE_KEY = "big-cty"
DATASET_KEY = "cty"
PARSER_VERSION = "cty-v9-1"
RSS_URL = "https://www.country-files.com/category/big-cty/feed/"
TERMS_URL = "https://www.country-files.com/copyright/"
MAX_FEED_BYTES = 1_000_000
MAX_ARCHIVE_BYTES = 4_000_000
logger = logging.getLogger("contestmaster.master_data.cty")


@dataclass(frozen=True, slots=True)
class PrefixRecord:
    pattern: str
    exact_callsign: bool
    cq_zone: int
    itu_zone: int
    continent: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    utc_offset: float | None = None


@dataclass(frozen=True, slots=True)
class EntityRecord:
    name: str
    cq_zone: int
    itu_zone: int
    continent: str
    latitude: float
    longitude: float
    utc_offset: float
    primary_prefix: str
    prefixes: tuple[PrefixRecord, ...]


@dataclass(frozen=True, slots=True)
class CTYRelease:
    release: str
    archive_url: str
    retrieved_at: datetime
    archive_sha256: str
    license_notice: str
    entities: tuple[EntityRecord, ...]

    @property
    def normalized_checksum(self) -> str:
        payload = json.dumps(
            [asdict(record) for record in self.entities],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def _read_url(url: str, limit: int = MAX_FEED_BYTES) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Contestmaster/0.1 (master-data importer)"},
    )
    started = time.perf_counter()
    logger.info("master_data_source_request_started", extra={"source_url": url})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read(limit + 1)
    except Exception:
        logger.exception(
            "master_data_source_request_failed",
            extra={
                "source_url": url,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        raise
    logger.info(
        "master_data_source_request_finished",
        extra={
            "source_url": url,
            "response_bytes": len(payload),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    if len(payload) > limit:
        raise ValueError(f"Source response exceeded {limit} bytes")
    return payload


def fetch_latest_archive() -> tuple[bytes, str, str, datetime]:
    """Fetch latest release via official RSS, then the dated archive linked by that post."""
    feed_bytes = _read_url(RSS_URL)
    root = ElementTree.fromstring(feed_bytes)
    item = root.find("./channel/item")
    if item is None:
        raise ValueError("Big CTY feed has no release item")
    post_url = (item.findtext("link") or "").strip()
    title = (item.findtext("title") or "").strip()
    release_date = _release_date(title)
    if not post_url.startswith("https://www.country-files.com/"):
        raise ValueError("Big CTY feed contained an unexpected release URL")

    parser = _LinkParser()
    parser.feed(_read_url(post_url).decode("utf-8", "replace"))
    archives = [
        link
        for link in parser.links
        if re.fullmatch(
            r"https://www\.country-files\.com/bigcty/download/\d{4}/bigcty-\d{8}\.zip", link
        )
    ]
    if len(archives) != 1:
        raise ValueError("Big CTY release page must contain one dated archive link")
    archive_url = archives[0]
    archive_bytes = _read_url(archive_url, MAX_ARCHIVE_BYTES)
    return archive_bytes, release_date, archive_url, datetime.now(UTC)


def _release_date(title: str) -> str:
    match = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", title)
    if not match:
        raise ValueError(f"Could not read Big CTY release date from {title!r}")
    return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()


def parse_archive(
    archive_bytes: bytes,
    release: str,
    archive_url: str,
    retrieved_at: datetime,
) -> CTYRelease:
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("Big CTY archive exceeds the configured size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            names = archive.namelist()
            cty_names = [name for name in names if name.rsplit("/", 1)[-1].lower() == "cty.dat"]
            notice_names = [
                name for name in names if name.rsplit("/", 1)[-1].lower() == "copyright.txt"
            ]
            if (
                len(cty_names) != 1
                or len(notice_names) != 1
                or sum(info.file_size for info in archive.infolist()) > MAX_ARCHIVE_BYTES
            ):
                raise ValueError("Big CTY archive must contain cty.dat and copyright.txt")
            info = archive.getinfo(cty_names[0])
            if info.file_size > MAX_ARCHIVE_BYTES:
                raise ValueError("cty.dat exceeds the configured size limit")
            text = archive.read(cty_names[0]).decode("latin-1")
            notice = archive.read(notice_names[0]).decode("utf-8", "replace").strip()
    except zipfile.BadZipFile as exc:
        raise ValueError("Big CTY response is not a valid ZIP archive") from exc

    if not notice or "permission" not in notice.lower():
        raise ValueError("Big CTY archive is missing its reusable copyright notice")
    records = parse_cty_dat(text)
    if len(records) < 100:
        raise ValueError("Big CTY dataset is unexpectedly incomplete")
    return CTYRelease(
        release=release,
        archive_url=archive_url,
        retrieved_at=retrieved_at.astimezone(UTC),
        archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        license_notice=notice,
        entities=records,
    )


_TOKEN = re.compile(
    r"^(?P<exact>=)?(?P<pattern>[A-Za-z0-9*/?]+)"
    r"(?:\((?P<cq>\d{1,2})\))?(?:\[(?P<itu>\d{1,2})\])?"
    r"(?:\{(?P<continent>[^}]*)\})?(?:<(?P<coordinates>[^>]*)>)?"
    r"(?:~(?P<utc_offset>[^~]*)~)?$"
)


def parse_cty_dat(text: str) -> tuple[EntityRecord, ...]:
    """Parse the CTY v9 colon record and comma/semicolon continuation format."""
    records: list[EntityRecord] = []
    header: tuple[str, int, int, str, float, float, float, str] | None = None
    aliases: list[PrefixRecord] = []
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(":")
        if len(fields) >= 8:
            if header is not None:
                raise ValueError(
                    f"CTY record at line {line_number} started before prior record ended"
                )
            try:
                name = fields[0].strip()
                cq_zone = int(fields[1])
                itu_zone = int(fields[2])
                continent = fields[3].strip()
                latitude = float(fields[4])
                longitude = float(fields[5])
                utc_offset = float(fields[6])
                primary = fields[7].strip().lstrip("*")
            except (ValueError, IndexError) as exc:
                raise ValueError(f"Invalid CTY header at line {line_number}") from exc
            if (
                not name
                or not primary
                or not continent
                or not 1 <= cq_zone <= 40
                or not 1 <= itu_zone <= 90
            ):
                raise ValueError(f"Invalid CTY header values at line {line_number}")
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError(f"Invalid CTY coordinates at line {line_number}")
            header = (name, cq_zone, itu_zone, continent, latitude, longitude, utc_offset, primary)
            continue

        if header is None:
            raise ValueError(f"CTY alias encountered before a record header at line {line_number}")
        complete = line.endswith(";")
        data = line[:-1] if complete else line
        tokens = [token.strip() for token in data.split(",") if token.strip()]
        for token in tokens:
            if token.upper() in {"VERSION", "=VERSION"}:
                continue
            match = _TOKEN.fullmatch(token)
            if not match:
                raise ValueError(f"Unsupported CTY prefix token {token!r} at line {line_number}")
            pattern = match.group("pattern").upper()
            cq = int(match.group("cq") or header[1])
            itu = int(match.group("itu") or header[2])
            coordinates = match.group("coordinates")
            latitude = longitude = None
            if coordinates:
                try:
                    latitude, longitude = (float(value) for value in coordinates.split("/", 1))
                except ValueError as exc:
                    raise ValueError(f"Invalid coordinate override in CTY token {token!r}") from exc
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise ValueError(f"Invalid coordinate override in CTY token {token!r}")
            utc_offset = None
            if match.group("utc_offset"):
                try:
                    utc_offset = float(match.group("utc_offset"))
                except ValueError as exc:
                    raise ValueError(f"Invalid UTC offset override in CTY token {token!r}") from exc
            if not 1 <= cq <= 40 or not 1 <= itu <= 90:
                raise ValueError(f"Invalid zone override in CTY token {token!r}")
            aliases.append(
                PrefixRecord(
                    pattern,
                    bool(match.group("exact")),
                    cq,
                    itu,
                    match.group("continent") or None,
                    latitude,
                    longitude,
                    utc_offset,
                )
            )
        if complete:
            if not any(prefix.pattern == header[7] for prefix in aliases):
                aliases.append(PrefixRecord(header[7], False, header[1], header[2]))
            # Keep the first repeated alias, matching CTY lookup order.
            deduplicated: dict[str, PrefixRecord] = {}
            for prefix in aliases:
                deduplicated.setdefault(
                    ("=" if prefix.exact_callsign else "") + prefix.pattern, prefix
                )
            records.append(EntityRecord(*header, tuple(deduplicated.values())))
            header = None
            aliases = []
    if header is not None:
        raise ValueError("CTY file ended before the final record terminator")
    if not records:
        raise ValueError("CTY file contains no records")
    # CTY lookup precedence follows source order when an alias appears more than once.
    # Keep exact-call and prefix entries distinct because an exact call overrides a prefix.
    seen: set[str] = set()
    normalized: list[EntityRecord] = []
    for record in records:
        prefixes: list[PrefixRecord] = []
        for prefix in record.prefixes:
            key = ("=" if prefix.exact_callsign else "") + prefix.pattern
            if key not in seen:
                prefixes.append(prefix)
                seen.add(key)
        normalized.append(
            EntityRecord(
                record.name,
                record.cq_zone,
                record.itu_zone,
                record.continent,
                record.latitude,
                record.longitude,
                record.utc_offset,
                record.primary_prefix,
                tuple(prefixes),
            )
        )
    return tuple(normalized)
