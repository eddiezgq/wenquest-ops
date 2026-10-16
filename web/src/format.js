// Number and value formatting. Unknown stays "unknown", never 0 (ADR-0007).
let currency = 'USD'
export const setCurrency = (c) => { currency = c || 'USD' }

export function fmt(v, unit) {
  if (v === null || v === undefined) return 'unknown'
  if (unit === 'currency') return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(v)
  if (unit === '%') return `${v}%`
  if (unit === 'days') return `${v} days`
  if (typeof v === 'number') return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(v)
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  return String(v)
}

// Short money for tight places: $4.1K, $12K, $1.2M
export function fmtShort(v) {
  if (v === null || v === undefined) return 'unknown'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, notation: 'compact', maximumFractionDigits: 1 }).format(v)
}

export const docState = (v) => ({ 0: 'Draft', 1: 'Submitted', 2: 'Cancelled' })[v] ?? v
export const ago = (iso) => (iso ? new Date(iso).toLocaleString('en-US') : '')
