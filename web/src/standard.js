// The standard the quality system pages show (ADR-0017): ISO 9001, ISO 13485 or another pack. Remembered in this
// browser only as a convenience; every page works without it.
import { ref } from 'vue'

const KEY = 'wq-standard'
let saved = ''
try { saved = localStorage.getItem(KEY) || '' } catch { saved = '' }

export const standard = ref(saved || 'iso9001')

export function setStandard(s) {
  standard.value = s
  try { localStorage.setItem(KEY, s) } catch { /* private window: keep it for this visit only */ }
}
