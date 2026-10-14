// Badge colors for the states the pages show (ADR-0013). Frappe badge themes: gray, blue, green, amber, red, violet.
export const SEV = { critical: 'red', warn: 'amber', info: 'blue' }
export const STATUS = {
  open: 'red', ack: 'amber', doing: 'blue', closed: 'green', resolved: 'green', cancelled: 'gray',
  contained: 'amber', pending_approval: 'violet', dispositioned: 'blue',
  draft: 'gray', investigation: 'amber', implementation: 'blue', effectiveness: 'violet',
  pending: 'amber', confirmed: 'green', rejected: 'gray', failed: 'red', confirming: 'blue',
  to_classify: 'gray', to_review: 'amber', in_review: 'violet', effective: 'green', obsolete: 'gray',
  extracting: 'blue', ready: 'amber', classifying: 'blue', done: 'green',
}
export const CONF = { high: 'green', medium: 'amber', low: 'gray' }
// document states in plain words (ADR-0014)
export const DOC_STATE = {
  to_classify: 'not classified', to_review: 'to review', draft: 'draft', in_review: 'waiting for approval',
  effective: 'effective', confirmed: 'kept', obsolete: 'obsolete', rejected: 'not kept',
}
export const label = (s) => String(s ?? '').replaceAll('_', ' ')
