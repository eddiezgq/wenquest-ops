<script setup>
// One control chart: the plotted points (subgroup means or individuals), the center line and control limits,
// spec limits if given, and points that break a rule marked and labelled (ADR-0009 item 6).
import { computed, ref } from 'vue'
import { t } from '../i18n'

const props = defineProps({ data: Object })
const W = 720, H = 260, PAD = { l: 52, r: 70, t: 14, b: 30 }
const hover = ref(null)
const ch = computed(() => props.data.chart)
const flagged = computed(() => new Map(props.data.signals.map((s) => [s.index, s])))
const lines = computed(() => {
  const out = [{ y: ch.value.UCL, label: 'UCL', cls: 'lim' }, { y: ch.value.center, label: 'CL', cls: 'center' },
    { y: ch.value.LCL, label: 'LCL', cls: 'lim' }]
  const cap = props.data.capability
  if (cap) out.push({ y: cap.USL, label: 'USL', cls: 'spec' }, { y: cap.LSL, label: 'LSL', cls: 'spec' })
  return out
})
const scale = computed(() => {
  const ys = [...ch.value.points, ...lines.value.map((l) => l.y)]
  const lo = Math.min(...ys), hi = Math.max(...ys), pad = (hi - lo || 1) * 0.08
  const n = ch.value.points.length
  return {
    x: (i) => PAD.l + (n === 1 ? 0 : (i * (W - PAD.l - PAD.r)) / (n - 1)),
    y: (v) => PAD.t + ((hi + pad - v) * (H - PAD.t - PAD.b)) / (hi - lo + 2 * pad),
  }
})
const path = computed(() => ch.value.points.map((p, i) => `${i ? 'L' : 'M'}${scale.value.x(i)},${scale.value.y(p)}`).join(''))
const f = (v) => (Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(3))
</script>

<template>
  <figure class="cc">
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="t('Control chart, {n} points', { n: ch.points.length })">
      <g v-for="l in lines" :key="l.label">
        <line :x1="PAD.l" :x2="W - PAD.r" :y1="scale.y(l.y)" :y2="scale.y(l.y)" :class="l.cls" />
        <text :x="W - PAD.r + 6" :y="scale.y(l.y) + 4" class="ax">{{ l.label }} {{ f(l.y) }}</text>
      </g>
      <path :d="path" class="series" />
      <g v-for="(p, i) in ch.points" :key="i" @mouseenter="hover = i" @mouseleave="hover = null">
        <circle :cx="scale.x(i)" :cy="scale.y(p)" r="12" class="hit" />
        <circle :cx="scale.x(i)" :cy="scale.y(p)" :r="flagged.has(i) ? 6 : 4" :class="flagged.has(i) ? 'bad' : 'pt'" />
        <text v-if="flagged.has(i)" :x="scale.x(i)" :y="scale.y(p) - 10" class="flag">{{ t('rule {n}', { n: flagged.get(i).rule }) }}</text>
      </g>
      <text :x="PAD.l" :y="H - 8" class="ax">{{ data.labels[0] }}</text>
      <text :x="W - PAD.r" :y="H - 8" class="ax" text-anchor="end">{{ data.labels.at(-1) }}</text>
    </svg>
    <div v-if="hover !== null" class="tip">{{ data.labels[hover] }}: {{ f(ch.points[hover]) }}
      <span v-if="flagged.has(hover)"> — {{ flagged.get(hover).text }}</span></div>
    <figcaption class="mt-2 text-sm text-ink-gray-5">{{ ch.kind === 'xbar_r' ? t('X-bar chart, subgroups of {n}.', { n: ch.n }) : t('Individuals chart (inspection means).') }}
      {{ t('Hover a point for its inspection.') }}</figcaption>
  </figure>
</template>

<style scoped>
.cc { margin: 0; position: relative; }
svg { width: 100%; height: auto; max-height: 22rem; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; }
.series { fill: none; stroke: var(--accent); stroke-width: 2; }
.pt { fill: var(--accent); stroke: var(--panel); stroke-width: 2; }
.bad { fill: var(--critical); stroke: var(--panel); stroke-width: 2; }
.hit { fill: transparent; }
.center { stroke: var(--muted); stroke-width: 1; }
.lim { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 5 4; }
.spec { stroke: var(--warn); stroke-width: 1; stroke-dasharray: 2 3; }
.ax { fill: var(--muted); font-size: 10px; }
.flag { fill: var(--ink); font-size: 10px; text-anchor: middle; }
.tip { position: absolute; top: .4rem; left: 3.6rem; background: var(--panel); border: 1px solid var(--line);
       border-radius: 6px; padding: .2rem .5rem; font-size: .85rem; }
</style>
