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

export const docState = (v) => ({ 0: 'Draft', 1: 'Submitted', 2: 'Cancelled' })[v] ?? v
export const ago = (iso) => (iso ? new Date(iso).toLocaleString('en-US') : '')
