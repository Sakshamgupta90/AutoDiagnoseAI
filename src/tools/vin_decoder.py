"""VIN decoding via the free NHTSA vPIC API, with graceful fallback to manual make/model."""

import logging
import re
from typing import Any

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

VPIC_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

FIELDS = {
    "Make": "make",
    "Model": "model",
    "ModelYear": "year",
    "Trim": "trim",
    "DisplacementL": "engine_litres",
    "EngineCylinders": "cylinders",
    "FuelTypePrimary": "fuel",
    "ElectrificationLevel": "electrification",
    "DriveType": "drive",
    "TransmissionStyle": "transmission",
}


async def decode_vin(vin: str) -> dict[str, Any]:
    """Returns decoded fields, or `{"ok": False, "reason": ...}` for chassis numbers / network errors."""
    vin = vin.strip().upper()
    if not VIN_RE.match(vin):
        return {"ok": False, "reason": "Not a 17-character VIN (e.g. a parallel-import chassis number); using manual make/model."}
    if not settings.NHTSA_ENABLED:
        return {"ok": False, "reason": "VIN decoding disabled."}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(VPIC_URL.format(vin=vin))
            res.raise_for_status()
            row = (res.json().get("Results") or [{}])[0]
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("NHTSA vPIC lookup failed: %s", exc)
        return {"ok": False, "reason": "NHTSA vPIC unreachable; using manual make/model."}

    decoded = {out: str(row.get(src)).strip() for src, out in FIELDS.items() if row.get(src) not in (None, "", "Not Applicable")}
    if not decoded.get("make"):
        return {"ok": False, "reason": "VIN not found in NHTSA vPIC (non-US vehicle?); using manual make/model."}
    return {"ok": True, **decoded}


def _litres(value: str) -> str:
    try:
        return f"{float(value):.1f}"
    except ValueError:
        return value


def describe_vehicle(decoded: dict[str, Any]) -> str:
    parts = [decoded.get("year"), decoded.get("make"), decoded.get("model"), decoded.get("trim")]
    engine = " ".join(
        p for p in (
            f"{_litres(decoded['engine_litres'])}L" if decoded.get("engine_litres") else None,
            f"{decoded['cylinders']}-cyl" if decoded.get("cylinders") else None,
            decoded.get("fuel"),
        ) if p
    )
    text = " ".join(p for p in parts if p)
    return f"{text} · {engine}" if engine else text
