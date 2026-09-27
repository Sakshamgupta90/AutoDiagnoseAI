"""Turn OBD-II fault codes into plain words so they can be embedded and searched.

The Zenodo dataset contains no fault codes, so a raw "P0301" would match nothing
semantically. Common codes come from a lookup table; everything else is decoded
from the standard SAE J2012 structure.
"""

import re

DTC_RE = re.compile(r"^[PBCU][0-3][0-9A-F]{3}$")

COMMON_CODES: dict[str, str] = {
    "P0100": "Mass air flow (MAF) sensor circuit malfunction",
    "P0101": "Mass air flow (MAF) sensor range/performance problem",
    "P0113": "Intake air temperature sensor circuit high input",
    "P0115": "Engine coolant temperature sensor circuit malfunction",
    "P0117": "Engine coolant temperature sensor circuit low input",
    "P0118": "Engine coolant temperature sensor circuit high input",
    "P0125": "Insufficient coolant temperature for closed-loop fuel control",
    "P0128": "Coolant thermostat below regulating temperature (thermostat stuck open)",
    "P0130": "O2 sensor circuit malfunction (bank 1 sensor 1)",
    "P0133": "O2 sensor slow response (bank 1 sensor 1)",
    "P0171": "System too lean (bank 1) — vacuum leak, MAF or fuel delivery",
    "P0172": "System too rich (bank 1)",
    "P0174": "System too lean (bank 2)",
    "P0217": "Engine overheating condition (engine coolant over-temperature)",
    "P0230": "Fuel pump primary circuit malfunction",
    "P0299": "Turbocharger/supercharger underboost",
    "P0300": "Random or multiple cylinder misfire detected",
    "P0325": "Knock sensor 1 circuit malfunction",
    "P0335": "Crankshaft position sensor A circuit malfunction",
    "P0340": "Camshaft position sensor circuit malfunction",
    "P0401": "Exhaust gas recirculation (EGR) flow insufficient",
    "P0420": "Catalyst system efficiency below threshold (bank 1)",
    "P0430": "Catalyst system efficiency below threshold (bank 2)",
    "P0440": "Evaporative emission (EVAP) system malfunction",
    "P0442": "EVAP system small leak detected",
    "P0455": "EVAP system large leak detected (often loose fuel cap)",
    "P0500": "Vehicle speed sensor malfunction",
    "P0505": "Idle air control system malfunction",
    "P0506": "Idle speed lower than expected",
    "P0507": "Idle speed higher than expected",
    "P0562": "System voltage low (charging system / battery)",
    "P0563": "System voltage high (charging system)",
    "P0600": "Serial communication link malfunction",
    "P0700": "Transmission control system malfunction",
    "P0715": "Transmission input/turbine speed sensor circuit malfunction",
    "P0740": "Torque converter clutch circuit malfunction",
    "P0741": "Torque converter clutch stuck off (slipping)",
    "P0750": "Shift solenoid A malfunction",
    "C0035": "Left front wheel speed sensor circuit (ABS)",
    "C0040": "Right front wheel speed sensor circuit (ABS)",
    "C0045": "Left rear wheel speed sensor circuit (ABS)",
    "C0050": "Right rear wheel speed sensor circuit (ABS)",
    "C0265": "ABS/EBCM motor relay circuit",
    "B0001": "Driver frontal airbag deployment loop (SRS)",
    "B0100": "Electronic frontal sensor (SRS airbag)",
    "U0100": "Lost communication with engine control module (ECM/PCM)",
    "U0121": "Lost communication with ABS control module",
}

_SYSTEM = {"P": "Powertrain", "B": "Body", "C": "Chassis", "U": "Network/communication"}
_P_SUBSYSTEM = {
    "0": "fuel and air metering / auxiliary emission controls",
    "1": "fuel and air metering",
    "2": "fuel and air metering (injector circuit)",
    "3": "ignition system or misfire",
    "4": "auxiliary emission controls",
    "5": "vehicle speed, idle control and auxiliary inputs",
    "6": "computer and output circuits",
    "7": "transmission",
    "8": "transmission",
    "9": "transmission",
    "A": "hybrid propulsion",
    "B": "hybrid propulsion",
    "C": "hybrid propulsion",
}


def describe_dtc(code: str) -> str:
    code = code.strip().upper()
    if not DTC_RE.match(code):
        return f"{code}: unrecognised code format"
    if code in COMMON_CODES:
        return f"{code}: {COMMON_CODES[code]}"
    if code.startswith("P030") and code[4].isdigit():
        return f"{code}: Cylinder {code[4]} misfire detected"
    system = _SYSTEM[code[0]]
    scope = "manufacturer-specific" if code[1] in "13" else "generic"
    if code[0] == "P":
        return f"{code}: {scope} {system.lower()} code — {_P_SUBSYSTEM.get(code[2], 'powertrain')} fault"
    return f"{code}: {scope} {system.lower()} fault code"


def describe_all(codes: list[str]) -> list[str]:
    return [describe_dtc(c) for c in codes]
