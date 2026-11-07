import { t } from './i18n'
// Words of the PLM pages (ADR-0026) that come from the hub as codes
export const stl = (s) => ({ draft: t('plm::draft'), released: t('plm::released'), superseded: t('plm::superseded'), obsolete: t('plm::obsolete') })[s] || s
export const fkl = (k) => ({ model: t('plm-file::model'), drawing: t('plm-file::drawing'), image: t('plm-file::image'), other: t('plm-file::other') })[k] || k
export const erpl = (s) => ({ draft: t('erp-bom::draft'), submitted: t('erp-bom::submitted'), cancelled: t('erp-bom::cancelled'), none: t('erp-bom::none'), unknown: t('erp-bom::unknown') })[s] || s
export const diffl = (s) => ({ added: t('bom-diff::added'), removed: t('bom-diff::removed'), changed: t('bom-diff::changed') })[s] || s
