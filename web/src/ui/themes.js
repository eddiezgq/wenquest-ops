// Badge colors for the states the pages show (ADR-0013). Frappe badge themes: gray, blue, green, amber, red, violet.
export const SEV = { critical: 'red', warn: 'amber', info: 'blue' }
export const STATUS = {
  open: 'red', ack: 'amber', doing: 'blue', closed: 'green', resolved: 'green', cancelled: 'gray',
  contained: 'amber', pending_approval: 'violet', dispositioned: 'blue',
  draft: 'gray', investigation: 'amber', implementation: 'blue', effectiveness: 'violet',
  pending: 'amber', confirmed: 'green', rejected: 'gray', failed: 'red', confirming: 'blue',
}
export const label = (s) => String(s ?? '').replaceAll('_', ' ')
