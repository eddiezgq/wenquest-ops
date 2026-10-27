// Number and value formatting. Unknown stays "unknown", never 0 (ADR-0007). Locale follows the interface (ADR-0023).
import { locale, t } from './i18n'

let currency = 'USD'
export const setCurrency = (c) => { currency = c || 'USD' }

export function fmt(v, unit) {
  if (v === null || v === undefined) return t('unknown')
  if (unit === 'currency') return new Intl.NumberFormat(locale(), { style: 'currency', currency }).format(v)
  if (unit === '%') return `${v}%`
  if (unit === 'days') return t('{n} days', { n: v })
  if (typeof v === 'number') return new Intl.NumberFormat(locale(), { maximumFractionDigits: 2 }).format(v)
  if (typeof v === 'boolean') return v ? t('Yes') : t('No')
  return String(v)
}

// Short money for tight places: $4.1K, $12K, $1.2M
export function fmtShort(v) {
  if (v === null || v === undefined) return t('unknown')
  return new Intl.NumberFormat(locale(), { style: 'currency', currency, notation: 'compact', maximumFractionDigits: 1 }).format(v)
}

export const docState = (v) => t(({ 0: 'Draft', 1: 'Submitted', 2: 'Cancelled' })[v] ?? v)
export const ago = (iso) => (iso ? new Date(iso).toLocaleString(locale()) : '')
