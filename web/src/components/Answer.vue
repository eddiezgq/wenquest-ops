<script setup>
// An answer with [Type:Key] citations turned into links and unverified sentences marked (ADR-0008 item 4).
import { computed } from 'vue'
import { objectPath } from '../api'

// a quality or document record the assistant read (ADR-0021): [Record:kind/id/name]
const PATHS = { ncr: '/quality/ncr/', capa: '/quality/capa/', complaint: '/quality/complaints/', change: '/quality/changes/',
  risk_file: '/quality/risk/', production: '/quality/production/', recall: '/quality/recalls/', review: '/quality/reviews/',
  iqc: '/quality/iqc/', gauge: '/quality/gauges/', asl: '/quality/suppliers#a', document: '/documents/' }
function record(key) {
  const [kind, id, ...name] = key.split('/')
  return PATHS[kind] ? { link: PATHS[kind] + id, text: name.join('/') || `${kind} ${id}` } : { text: key }
}
const props = defineProps({ text: String, unverified: { type: Array, default: () => [] } })
const parts = computed(() => {
  const out = []
  for (const line of (props.text || '').split('\n')) {
    const bad = props.unverified.some((u) => u && line.includes(u))
    const pieces = []
    let last = 0
    for (const m of line.matchAll(/\[([A-Za-z]+):([^\]]+)\]/g)) {
      if (m.index > last) pieces.push({ text: line.slice(last, m.index) })
      pieces.push(m[1] === 'Record' ? record(m[2]) : { link: objectPath(m[1], m[2]), text: m[2] })
      last = m.index + m[0].length
    }
    if (last < line.length) pieces.push({ text: line.slice(last) })
    out.push({ pieces, bad })
  }
  return out
})
</script>

<template>
  <div class="answer space-y-1 text-p-base text-ink-gray-8">
    <p v-for="(l, i) in parts" :key="i" :class="{ 'rounded bg-surface-amber-2': l.bad }"
       :title="l.bad ? 'A number here was not found in the data the assistant looked at' : ''">
      <template v-for="(p, j) in l.pieces" :key="j">
        <RouterLink v-if="p.link" :to="p.link" class="wq-link">{{ p.text }}</RouterLink><template v-else>{{ p.text }}</template>
      </template>
      <span v-if="l.bad" class="ms-2 rounded-3 border border-outline-amber-3 px-1.5 text-xs text-ink-amber-7">unverified</span>
    </p>
  </div>
</template>
