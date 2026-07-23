"""AML Monitor — Sanctions data provider.

Downloads and parses the OFAC SDN (Specially Designated Nationals) list
from the US Treasury website and populates the local ``sanctions_lists`` table.

Supports incremental updates by checking the SDN XML file's modification date.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date, datetime, timezone
from typing import Any
from zipfile import ZipFile

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# OFAC SDN list — CSV format (zipped)
OFAC_SDN_URL = (
    "https://www.treasury.gov/ofac/downloads/sdn.csv"
)

# Alternative: advanced XML-based download (more structured)
OFAC_XML_URL = "https://www.treasury.gov/ofac/downloads/sdn.xml"

# Column indices in the OFAC SDN CSV (0-based)
# Format: ent_num, SDN_Name, SDN_Type, Program, Title, Call_Sign,
#         Vess_type, Tonnage, GRT, Vess_flag, Vess_owner, Remarks,
#         Address, City, State/Province, Postal_Code, Country, Other
_COL_SDN_NAME = 1
_COL_SDN_TYPE = 2       # "Individual" or "Entity"
_COL_PROGRAM = 3
_COL_COUNTRY = 16
_COL_REMARKS = 11

# Mapping from OFAC SDN_Type to our entity_type
_ENTITY_TYPE_MAP: dict[str, str] = {
    "individual": "individual",
    "entity": "entity",
    "aircraft": "entity",
    "vessel": "entity",
}

# ---------------------------------------------------------------------------
# OFAC SDN CSV parser
# ---------------------------------------------------------------------------


def _parse_sdn_csv_row(row: list[str]) -> dict[str, Any] | None:
    """Parse a single row from the OFAC SDN CSV.

    Returns a dict suitable for creating a SanctionsList record,
    or ``None`` if the row should be skipped.
    """
    if len(row) < 4:
        return None

    raw_name = row[_COL_SDN_NAME].strip()
    if not raw_name:
        return None

    sdn_type_raw = row[_COL_SDN_TYPE].strip().lower()
    entity_type = _ENTITY_TYPE_MAP.get(sdn_type_raw, "individual")

    program = row[_COL_PROGRAM].strip() if len(row) > _COL_PROGRAM else ""
    country = row[_COL_COUNTRY].strip() if len(row) > _COL_COUNTRY else ""

    # Extract aliases from remarks field (parenthetical names)
    remarks = row[_COL_REMARKS].strip() if len(row) > _COL_REMARKS else ""
    aliases = _extract_aliases(remarks)

    return {
        "list_source": "ofac",
        "full_name": raw_name,
        "name_variations": aliases if aliases else None,
        "entity_type": entity_type,
        "country": country or None,
        "program": program or None,
        "is_active": True,
        "last_updated": date.today(),
    }


def _extract_aliases(remarks: str) -> list[str]:
    """Extract alias names from the OFAC remarks field.

    Aliases often appear as ``(a.k.a. JOHN DOE)`` or ``(f.k.a. JOHN DOE)``
    in the remarks column.
    """
    aliases: list[str] = []
    # Match patterns like (a.k.a. NAME) or (f.k.a. NAME) or (aka NAME)
    for match in re.finditer(
        r"(?:a\.k\.a\.|aka|f\.k\.a\.|n\.k\.a\.)\s+(.*?)(?:[;)]|$)",
        remarks,
        re.IGNORECASE,
    ):
        alias = match.group(1).strip().rstrip(";")
        if alias:
            aliases.append(alias)
    return aliases


# ---------------------------------------------------------------------------
# Download & import
# ---------------------------------------------------------------------------


async def download_ofac_sdn_csv() -> str:
    """Download the OFAC SDN CSV file and return its raw text content.

    Raises:
        httpx.HTTPError: If the download fails.
    """
    logger.info("Downloading OFAC SDN list from %s", OFAC_SDN_URL)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(OFAC_SDN_URL)
        resp.raise_for_status()
        content = resp.text
    logger.info("Downloaded %d bytes", len(content))
    return content


async def download_ofac_sdn_zip() -> str:
    """Download the OFAC SDN zip and extract the CSV inside.

    The OFAC server sometimes returns a zip file even for the .csv URL.
    This method handles both cases.
    """
    logger.info("Downloading OFAC SDN list (zip mode) from %s", OFAC_SDN_URL)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(OFAC_SDN_URL)
        resp.raise_for_status()
        data = resp.content

    # Check if it's a zip file
    if data[:4] == b"PK\x03\x04":
        with ZipFile(io.BytesIO(data)) as zf:
            csv_files = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_files:
                raise ValueError("No CSV found inside OFAC zip archive")
            text = zf.read(csv_files[0]).decode("utf-8-sig")
    else:
        text = data.decode("utf-8-sig")

    logger.info("Extracted %d bytes from OFAC data", len(text))
    return text


def parse_sdn_csv(content: str) -> list[dict[str, Any]]:
    """Parse the full OFAC SDN CSV content into a list of record dicts.

    Handles the CSV format which may have quoted fields with embedded commas.
    """
    reader = csv.reader(io.StringIO(content))
    records: list[dict[str, Any]] = []

    for row in reader:
        if not row or not row[0].strip():
            continue
        # Skip header row
        if row[0].strip() == "ent_num":
            continue

        parsed = _parse_sdn_csv_row(row)
        if parsed is not None:
            records.append(parsed)

    logger.info("Parsed %d SDN records from CSV", len(records))
    return records


# ---------------------------------------------------------------------------
# High-level import function
# ---------------------------------------------------------------------------


async def import_ofac_sdn(db_session_factory: Any) -> int:
    """Download, parse, and import the OFAC SDN list into the database.

    Args:
        db_session_factory: An async callable that returns a database session.

    Returns:
        Number of records imported.
    """
    from app.models.sanctions_list import SanctionsList
    from sqlalchemy import select

    content = await download_ofac_sdn_zip()
    records = parse_sdn_csv(content)

    async with db_session_factory() as db:
        # Get existing full_names to avoid duplicates
        result = await db.execute(select(SanctionsList.full_name))
        existing_names: set[str] = {row[0] for row in result.fetchall()}

        imported = 0
        for rec in records:
            if rec["full_name"] in existing_names:
                continue
            entry = SanctionsList(**rec)
            db.add(entry)
            imported += 1

        if imported:
            await db.flush()
            logger.info("Imported %d new sanctions records", imported)
        else:
            logger.info("No new sanctions records to import")

    return imported