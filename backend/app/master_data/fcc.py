"""FCC ULS amateur-license source adapter for U.S. callsign districts."""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

DATASET_KEY = "call-districts-us"
SOURCE_KEY = "fcc-uls-amateur"
SOURCE_URL = "https://data.fcc.gov/download/pub/uls/complete/l_amat.zip"
TERMS_URL = "https://opendata.fcc.gov/Wireless/FCC-Universal-Licensing-System-ULS-/x28i-i4z4"
MAX_ARCHIVE_BYTES = 250_000_000
MAX_EXPANDED_BYTES = 1_500_000_000
MIN_LICENSE_RECORDS = 100
MAX_INVALID_CALL_RATIO = 0.05
US_CALLSIGN = re.compile(r"^[A-Z]{1,2}(?P<district>[0-9])[A-Z]{1,4}$")


@dataclass(frozen=True, slots=True)
class FCCCallDistrictData:
    district_codes: tuple[str, ...]
    license_record_count: int
    source_release: str
    source_url: str
    retrieved_at: datetime
    archive_sha256: str

    @property
    def normalized_checksum(self) -> str:
        payload = json.dumps(self.district_codes, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()


def fetch_amateur_archive() -> tuple[bytes, str, str, datetime]:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "Contestmaster/0.1 (FCC ULS master-data sync)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        archive = response.read(MAX_ARCHIVE_BYTES + 1)
        modified = response.headers.get("Last-Modified") or response.headers.get("ETag")
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise ValueError("FCC ULS archive exceeds the configured size limit")
    retrieved_at = datetime.now(UTC)
    release = modified.strip('"') if modified else retrieved_at.date().isoformat()
    return archive, release, SOURCE_URL, retrieved_at


def parse_amateur_archive(
    archive_bytes: bytes,
    source_release: str,
    source_url: str,
    retrieved_at: datetime,
) -> FCCCallDistrictData:
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("FCC ULS archive exceeds the configured size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            files = [
                name for name in archive.namelist() if name.rsplit("/", 1)[-1].lower() == "am.dat"
            ]
            if len(files) != 1:
                raise ValueError("FCC ULS archive must contain one AM.dat amateur-record file")
            info = archive.getinfo(files[0])
            if info.file_size > MAX_EXPANDED_BYTES:
                raise ValueError("FCC ULS AM.dat file exceeds the configured expanded size limit")
            districts, count, invalid = _parse_amateur_rows(archive.open(files[0]))
    except zipfile.BadZipFile as exc:
        raise ValueError("FCC ULS response is not a valid ZIP archive") from exc
    if count < MIN_LICENSE_RECORDS:
        raise ValueError("FCC ULS amateur data is unexpectedly incomplete")
    if not districts:
        raise ValueError("FCC ULS amateur data contains no recognized call districts")
    if invalid / count > MAX_INVALID_CALL_RATIO:
        raise ValueError("FCC ULS amateur data has too many unrecognized callsign formats")
    return FCCCallDistrictData(
        district_codes=tuple(sorted(districts)),
        license_record_count=count,
        source_release=source_release,
        source_url=source_url,
        retrieved_at=retrieved_at.astimezone(UTC),
        archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
    )


def _parse_amateur_rows(stream) -> tuple[set[str], int, int]:
    districts: set[str] = set()
    count = 0
    invalid = 0
    for line_number, raw_line in enumerate(stream, 1):
        row = raw_line.decode("utf-8", "replace").rstrip("\r\n")
        fields = row.split("|")
        if fields and fields[-1] == "":
            fields.pop()
        if not fields or fields[0] != "AM":
            continue
        if len(fields) < 5:
            raise ValueError(f"Malformed FCC AM record at line {line_number}")
        callsign = fields[4].strip().upper()
        if not callsign:
            invalid += 1
            count += 1
            continue
        count += 1
        match = US_CALLSIGN.fullmatch(callsign)
        if match is None:
            invalid += 1
            continue
        # Only the district code is retained. FCC licensee names, addresses, and call signs
        # are discarded after this in-memory aggregation.
        districts.add(match.group("district"))
    return districts, count, invalid
