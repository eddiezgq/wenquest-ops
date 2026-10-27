// Interface language (ADR-0023): English is the source text and the key; Chinese comes from locales/zh.json.
// t('Late orders') or t('{n} days', { n: 3 }); t('status::Open') when one English word needs two Chinese words. A string with no Chinese yet shows in English, and the test
// tests/test_web_i18n.py fails, so every new text is translated in the same change.
import { ref } from 'vue'
import zh from './locales/zh.json'

const KEY = 'wqo-lang'
const TABLES = { zh }
function saved() { try { return localStorage.getItem(KEY) || '' } catch { return '' } }

export const lang = ref(saved() || 'en')
export const locale = () => (lang.value === 'zh' ? 'zh-CN' : 'en-US')

// The company's language (company manifest) unless this person chose one.
export function useCompanyLanguage(l) { if (!saved() && (l === 'zh' || l === 'en')) lang.value = l }

export function setLang(l) {
  lang.value = l === 'zh' ? 'zh' : 'en'
  try { localStorage.setItem(KEY, lang.value) } catch { /* the choice lasts for this visit */ }
  document.documentElement.lang = locale()
}

// 'status::Open': the same English word with another meaning gets its own Chinese; the part before :: is not shown.
export function t(s, p) {
  if (s === null || s === undefined) return ''
  const i = typeof s === 'string' ? s.indexOf('::') : -1
  let out = (TABLES[lang.value] && TABLES[lang.value][s]) || (i > 0 ? s.slice(i + 2) : s)
  if (p) out = out.replace(/\{(\w+)\}/g, (m, k) => (p[k] !== undefined && p[k] !== null ? p[k] : m))
  return out
}
