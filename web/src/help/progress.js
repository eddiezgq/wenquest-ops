// Ticks on the help center's "Try it" items (ADR-0019 item 4), kept on the server per person.
import { ref } from 'vue'
import { api } from '../api'

export const done = ref({})
export const error = ref('')
let loaded = null

export function load() {
  loaded ||= api('/api/help/progress').then((r) => { done.value = r.done }).catch((e) => { error.value = e.message; loaded = null })
  return loaded
}

export async function tick(key, value) {
  error.value = ''
  const before = done.value
  done.value = { ...before, [key]: value ? new Date().toISOString() : undefined }
  if (!value) delete done.value[key]
  try { done.value = (await api('/api/help/progress', { method: 'POST', body: { item: key, done: value } })).done } catch (e) { done.value = before; error.value = e.message }
}

export const count = (topic) => topic.try.filter((x) => done.value[x.key]).length
