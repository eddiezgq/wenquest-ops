<script setup>
// Guided tour (ADR-0012): a few steps per role, pointing at the real pages. Starts once on first sign-in
// (remembered in this browser) and can be restarted from Help. A help topic's "Show me" (ADR-0019) passes its own
// steps: each points at an element (usually [data-help=...]) on the page the step names, or on the page you are on.
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Button } from 'frappe-ui'

const props = defineProps({ permissions: Array, steps: { type: Array, default: null }, name: { type: String, default: '' } })
const emit = defineEmits(['done'])
const router = useRouter()
const STEPS = [
  { path: '/', target: '.brief, .cards', title: 'Your dashboard', text: 'The whole business at a glance: the chain from purchase order to payment, a light for each part of it, and weekly curves. Hover a light to see how it is judged; click anything to open it.' },
  { path: '/', target: '.anoms', title: 'Needs attention', text: 'Problems the rules found today, most serious first. Open one to see its causes and what it affects.' },
  { path: '/assistant', target: '.search', title: 'Ask the assistant', text: 'Ask in plain English. Answers cite your orders and items; numbers it could not find are marked unverified.' },
  { path: '/drafts', target: 'h1', title: 'Drafts wait for a person', text: 'Purchase orders, messages and reports prepared for you. Nothing is written to ERPNext or sent until someone confirms.' },
  { path: '/quality', target: '.tabs', title: 'Quality', text: 'Nonconformance reports, corrective actions, incoming inspection, supplier quality and control charts. Signing uses your password.', need: 'quality:view' },
  { path: '/documents', target: '.tabs', title: 'Documents', text: 'Drop in your procedures, forms and records. AI sorts them and quotes the file for every field; a person confirms, and approvals are signed.', need: 'documents:view' },
  { path: '/objects', target: '.search', title: 'Everything is connected', text: 'Search any order, item, supplier or receipt and follow its links.' },
  { path: '/help', target: '.help-nav', title: 'Help', text: 'Come back here any time, and restart this tour from Help.' },
]
const steps = computed(() => (props.steps || STEPS).filter((s) => !s.need || props.permissions.includes(s.need)))
const missing = ref(false)
const i = ref(0)
const box = ref({ top: 120, left: 40 })
async function place() {
  const s = steps.value[i.value]
  if (s.path && router.currentRoute.value.path !== s.path) await router.push(s.path)
  await nextTick()
  document.querySelectorAll('.tour-on').forEach((x) => x.classList.remove('tour-on'))
  if (s.click) document.querySelector(s.click)?.click()   // e.g. open the form the step is about
  let el = null
  for (let k = 0; k < 15 && !el; k++) {             // the page may still be loading its data
    await new Promise((r) => setTimeout(r, k ? 200 : 350))
    if (steps.value[i.value] !== s) return
    el = s.target.split(',').map((t) => document.querySelector(t.trim())).find(Boolean)
  }
  missing.value = !el
  if (el) {
    el.classList.add('tour-on')
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    const r = el.getBoundingClientRect()
    const h = document.querySelector('.tour')?.offsetHeight || 240   // keep the whole box on screen
    box.value = { top: Math.min(window.innerHeight - h - 12, Math.max(70, r.bottom + 12)), left: Math.max(12, Math.min(r.left, window.innerWidth - 360)) }
  } else {
    box.value = { top: 90, left: Math.max(12, window.innerWidth - 372) }
  }
}
function finish() {
  document.querySelectorAll('.tour-on').forEach((x) => x.classList.remove('tour-on'))
  emit('done')
}
watch(i, place, { immediate: true })
</script>

<template>
  <div class="tour rounded-5 border border-outline-gray-2 bg-surface-base p-4 shadow-xl" role="dialog" aria-live="polite"
       :style="{ top: box.top + 'px', left: box.left + 'px' }">
    <p class="text-xs text-ink-gray-5">{{ name ? `${name}: ` : '' }}step {{ i + 1 }} of {{ steps.length }}</p>
    <h3 v-if="steps[i].title" class="mt-1 text-base font-semibold text-ink-gray-9">{{ steps[i].title }}</h3>
    <p class="mt-1 text-p-sm text-ink-gray-7">{{ steps[i].text }}</p>
    <p v-if="missing" class="mt-2 text-p-sm text-ink-amber-7">{{ steps[i].elsewhere || 'This part is not on the page you are on: open it first, then choose Show me again.' }}</p>
    <div class="mt-3 flex items-center gap-2">
      <Button v-if="i > 0" label="Back" @click="i--" />
      <Button v-if="i < steps.length - 1" variant="solid" label="Next" @click="i++" />
      <Button v-else variant="solid" label="Done" @click="finish" />
      <Button variant="ghost" :label="name ? 'Close' : 'Skip the tour'" class="ms-auto" @click="finish" />
    </div>
  </div>
</template>
