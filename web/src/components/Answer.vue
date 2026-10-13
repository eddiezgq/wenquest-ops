<script setup>
// An answer with [Type:Key] citations turned into links and unverified sentences marked (ADR-0008 item 4).
import { computed } from 'vue'
import { objectPath } from '../api'

const props = defineProps({ text: String, unverified: { type: Array, default: () => [] } })
const parts = computed(() => {
  const out = []
  for (const line of (props.text || '').split('\n')) {
    const bad = props.unverified.some((u) => u && line.includes(u))
    const pieces = []
    let last = 0
    for (const m of line.matchAll(/\[([A-Za-z]+):([^\]]+)\]/g)) {
      if (m.index > last) pieces.push({ text: line.slice(last, m.index) })
      pieces.push({ link: objectPath(m[1], m[2]), text: m[2] })
      last = m.index + m[0].length
    }
    if (last < line.length) pieces.push({ text: line.slice(last) })
    out.push({ pieces, bad })
  }
  return out
})
</script>

<template>
  <div class="answer">
    <p v-for="(l, i) in parts" :key="i" :class="{ unverified: l.bad }" :title="l.bad ? 'A number here was not found in the data the assistant looked at' : ''">
      <template v-for="(p, j) in l.pieces" :key="j">
        <RouterLink v-if="p.link" :to="p.link">{{ p.text }}</RouterLink><template v-else>{{ p.text }}</template>
      </template>
      <span v-if="l.bad" class="tag warn">unverified</span>
    </p>
  </div>
</template>
