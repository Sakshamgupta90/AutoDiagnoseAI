/** Standard 17-character VIN — letters I, O and Q are never used. */
const VIN_RE = /^[A-HJ-NPR-Z0-9]{17}$/
/** OBD-II code: system letter, digit 0–3, three hex digits (e.g. P0301, U0100). */
const DTC_RE = /^[PBCU][0-3][0-9A-F]{3}$/

export type VinCheck =
  | { state: 'empty' }
  | { state: 'valid' }
  /** Parallel-imported vehicles may carry shorter chassis numbers — allowed, with a hint. */
  | { state: 'chassis'; message: string }
  | { state: 'invalid'; message: string }

export function normalizeVin(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z0-9]/g, '')
}

export function checkVin(raw: string): VinCheck {
  const vin = normalizeVin(raw)
  if (!vin) return { state: 'empty' }
  if (/[IOQ]/.test(vin)) return { state: 'invalid', message: 'VINs never contain the letters I, O or Q.' }
  if (VIN_RE.test(vin)) return { state: 'valid' }
  if (vin.length > 17) return { state: 'invalid', message: 'A VIN has at most 17 characters.' }
  if (vin.length >= 6)
    return { state: 'chassis', message: 'Not a 17-character VIN — treated as a chassis number. Add make and model below.' }
  return { state: 'invalid', message: 'Too short for a VIN or chassis number.' }
}

export function normalizeDtc(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z0-9]/g, '')
}

export function isValidDtc(code: string): boolean {
  return DTC_RE.test(normalizeDtc(code))
}

/** Split pasted text like "P0301, P0302 p0171" into candidate codes. */
export function splitDtcInput(raw: string): string[] {
  return raw
    .split(/[\s,;]+/)
    .map(normalizeDtc)
    .filter(Boolean)
}
