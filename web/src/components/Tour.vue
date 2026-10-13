<script setup>
// Guided tour (ADR-0012): a few steps per role, pointing at the real pages. Starts once on first sign-in
// (remembered in this browser) and can be restarted from Help.
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({ permissions: Array })
const emit = defineEmits(['done'])
const router = useRouter()
const STEPS = [
  { path: '/', target: '.brief, .cards', title: 'Your dashboard', text: 'The daily brief and the key numbers your role can see. Hover a number to see how it is counted; click the orders and items under it.' },
  { path: '/', target: '.anoms', title: 'Needs attention', text: 'Problems the rules found today, most serious first. Open one to see its causes and what it affects.' },
  { path: '/assistant', target: '.search', title: 'Ask the assistant', text: 'Ask in plain English. Answers cite your orders and items; numbers it could not find are marked unverified.' },
  { path: '/drafts', target: 'h1', title: 'Drafts wait for a person', text: 'Purchase orders, messages and reports prepared for you. Nothing is written to ERPNext or sent until someone confirms.' },
  { path: '/quality', target: '.tabs', title: 'Quality', text: 'Nonconformance reports, corrective actions, incoming inspection, supplier quality and control charts. Signing uses your password.', need: 'quality:view' },
  { path: '/objects', target: '.search', title: 'Everything is connected', text: 'Search any order, item, supplier or receipt and follow its links.' },
  { path: '/help', target: '.help-nav', title: 'Help', text: 'Come back here any time, and restart this tour from Help.' },
]
const steps = computed(() => STEPS.filter((s) => !s.need || props.permissions.includes(s.need)))
const i = ref(0)
const box = ref({ top: 120, left: 40 })
async function place() {
  const s = steps.value[i.value]
  if (router.currentRoute.value.path !== s.path) await router.push(s.path)
  await nextTick()
  setTimeout(() => {
    const el = s.target.split(',').map((t) => document.querySelector(t.trim())).find(Boolean)
    document.querySelectorAll('.tour-on').forEach((x) => x.classList.remove('tour-on'))
    if (el) {
      el.classList.add('tour-on')
      el.scrollIntoView({ block: 'center', behavior: 'smooth' })
      const r = el.getBoundingClientRect()
      const h = document.querySelector('.tour')?.offsetHeight || 240   // keep the whole box on screen
      box.value = { top: Math.min(window.innerHeight - h - 12, Math.max(70, r.bottom + 12)), left: Math.max(12, Math.min(r.left, window.innerWidth - 360)) }
    }
  }, 350)
}
function finish() {
  document.querySelectorAll('.tour-on').forEach((x) => x.classList.remove('tour-on'))
  emit('done')
}
watch(i, place, { immediate: true })
</script>

<template>
  <div class="tour" role="dialog" aria-live="polite" :style="{ top: box.top + 'px', left: box.left + 'px' }">
    <p class="muted small">Step {{ i + 1 }} of {{ steps.length }}</p>
    <h3>{{ steps[i].title }}</h3>
    <p>{{ steps[i].text }}</p>
    <div class="row">
      <button v-if="i > 0" @click="i--">Back</button>
      <button v-if="i < steps.length - 1" @click="i++">Next</button>
      <button v-else @click="finish">Done</button>
      <button class="link" @click="finish">Skip the tour</button>
    </div>
  </div>
</template>
