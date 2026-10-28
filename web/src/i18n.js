// Interface language (ADR-0023): English is the source text and the key; Chinese comes from locales/zh.json.
// t('Late orders') or t('{n} days', { n: 3 }); t('status::Open') when one English word needs two Chinese words. A string with no Chinese yet shows in English, and the test
// tests/test_web_i18n.py fails, so every new text is translated in the same change.
import { ref, shallowRef, watch } from 'vue'
import zh from './locales/zh.json'

const KEY = 'wqo-lang'
const TABLES = { zh }
function saved() { try { return localStorage.getItem(KEY) || '' } catch { return '' } }

export const lang = ref(saved() || 'en')
export const locale = () => (lang.value === 'zh' ? 'zh-CN' : 'en-US')

// The company's language (company manifest) unless this person chose one.
export function useCompanyLanguage(l) { if (!saved() && (l === 'zh' || l === 'en')) lang.value = l }

// The hub writes its messages and records in the same language (cookie wqo-lang, wqops/i18n.py), so the page reloads.
export function setLang(l) {
  lang.value = l === 'zh' ? 'zh' : 'en'
  try { localStorage.setItem(KEY, lang.value) } catch { /* the choice lasts for this visit */ }
  document.cookie = `${KEY}=${lang.value}; path=/; max-age=31536000; SameSite=Lax`
  document.documentElement.lang = locale()
  location.reload()
}
// a choice made before the hub read the cookie (or with the cookie cleared) is sent again
if (saved()) document.cookie = `${KEY}=${saved()}; path=/; max-age=31536000; SameSite=Lax`

// Fixed texts the hub writes into records (history entries, signature meanings) keep the language they were written in;
// the hub's own table (wqops/locales, /api/i18n/zh) lets t() show an English one in Chinese too. Loaded once, in Chinese only.
const hub = shallowRef({})
let hubLoading = null
function loadHub(l) {
  if (l !== 'zh' || hubLoading) return
  hubLoading = fetch('/api/i18n/zh', { credentials: 'same-origin' }).then((r) => (r.ok ? r.json() : {}))
    .then((d) => { hub.value = d || {} }).catch(() => { hubLoading = null })
}
watch(lang, loadHub, { immediate: true })

// 'status::Open': the same English word with another meaning gets its own Chinese; the part before :: is not shown.
export function t(s, p) {
  if (s === null || s === undefined) return ''
  const i = typeof s === 'string' ? s.indexOf('::') : -1
  const own = TABLES[lang.value] && TABLES[lang.value][s]
  let out = own || (lang.value === 'zh' && hub.value[s]) || (i > 0 ? s.slice(i + 2) : s)
  if (p) out = out.replace(/\{(\w+)\}/g, (m, k) => (p[k] !== undefined && p[k] !== null ? p[k] : m))
  return out
}
