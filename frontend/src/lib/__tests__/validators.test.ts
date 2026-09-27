import { describe, expect, it } from 'vitest'
import { checkVin, isValidDtc, normalizeVin, splitDtcInput } from '../validators'

describe('checkVin', () => {
  it('accepts a standard 17-character VIN', () => {
    expect(checkVin('JTDBR32E530012345').state).toBe('valid')
    expect(checkVin(' jtdbr32e5-30012345 ').state).toBe('valid')
  })
  it('rejects the letters I, O and Q', () => {
    expect(checkVin('JTDBR32E53001234O').state).toBe('invalid')
  })
  it('treats shorter numbers as chassis numbers (parallel imports)', () => {
    expect(checkVin('NZE1213012345').state).toBe('chassis')
  })
  it('rejects values that are too short or too long', () => {
    expect(checkVin('AB12').state).toBe('invalid')
    expect(checkVin('JTDBR32E5300123456').state).toBe('invalid')
  })
  it('is empty for blank input', () => {
    expect(checkVin('   ').state).toBe('empty')
    expect(normalizeVin('ab-12 c')).toBe('AB12C')
  })
})

describe('DTC codes', () => {
  it('validates OBD-II codes', () => {
    for (const c of ['P0301', 'p0171', 'C0035', 'B1000', 'U0100', 'P2A00']) expect(isValidDtc(c)).toBe(true)
    for (const c of ['P9301', 'X0301', 'P030', 'P03011', '']) expect(isValidDtc(c)).toBe(false)
  })
  it('splits pasted lists', () => {
    expect(splitDtcInput('P0301, p0302 ;P0171')).toEqual(['P0301', 'P0302', 'P0171'])
  })
})
