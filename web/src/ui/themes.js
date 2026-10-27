import { t } from '../i18n'
// Badge colors for the states the pages show (ADR-0013). Frappe badge themes: gray, blue, green, amber, red, violet.
export const SEV = { critical: 'red', warn: 'amber', info: 'blue' }
export const STATUS = {
  open: 'red', ack: 'amber', doing: 'blue', closed: 'green', resolved: 'green', cancelled: 'gray',
  contained: 'amber', pending_approval: 'violet', dispositioned: 'blue',
  draft: 'gray', investigation: 'amber', implementation: 'blue', effectiveness: 'violet',
  pending: 'amber', confirmed: 'green', rejected: 'gray', failed: 'red', confirming: 'blue',
  to_classify: 'gray', to_review: 'amber', in_review: 'violet', approved: 'blue', effective: 'green', obsolete: 'gray',
  extracting: 'blue', ready: 'amber', classifying: 'blue', done: 'green',
}
export const CONF = { high: 'green', medium: 'amber', low: 'gray' }
// document states in plain words (ADR-0014)
// (getters, so the words follow the interface language each time they are read)
export const DOC_STATE = {
  get to_classify() { return t('not classified') }, get to_review() { return t('to review') }, get draft() { return t('draft') },
  get in_review() { return t('waiting for approval') }, get approved() { return t('approved, not yet in effect') },
  get effective() { return t('effective') }, get confirmed() { return t('kept') }, get obsolete() { return t('obsolete') },
  get rejected() { return t('not kept') },
}
export const label = (s) => String(s ?? '').replaceAll('_', ' ')
