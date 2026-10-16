<script setup>
// The company at a glance (ADR-0018): the chain from purchase order to payment, a light for each part of the
// business, weekly curves, and what waits for people. Every number is counted by WenQuest Ops from ERPNext and its
// own records; click it to see where it comes from. The page refreshes itself after each ERPNext sync.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Badge, Button, Select, Tooltip } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { SEV } from '../ui/themes'
import { api } from '../api'
import { fmt } from '../format'
import { LIGHT, optionFor } from '../ui/ovcharts'
import Answer from '../components/Answer.vue'
import FlowChain from '../components/FlowChain.vue'
import OvChart from '../components/OvChart.vue'

const weeks = ref(8)
const v = ref(null)
const brief = ref(null)
const active = ref([])
const error = ref('')
const showBrief = ref(false)
const fresh = ref(new Set())          // figures that changed at the last refresh
const PERIODS = [{ label: '8 weeks', value: 8 }, { label: '13 weeks', value: 13 }, { label: '26 weeks', value: 26 }]
const COLOR_WORD = { green: 'on target', amber: 'watch', red: 'act now', unknown: 'not enough data' }
let timer = null

const flat = (o) => Object.fromEntries((o?.panels || []).flatMap((p) => [[`${p.key}:light`, p.light.value],
  ...p.figures.map((f) => [`${p.key}:${f.label}`, f.value])]))

async function load(quiet = false) {
  if (!quiet) error.value = ''
  try {
    const next = await api(`/api/overview?weeks=${weeks.value}`)
    if (quiet && v.value) {
      const a = flat(v.value); const b = flat(next)
      fresh.value = new Set(Object.keys(b).filter((k) => k in a && a[k] !== b[k]))
      setTimeout(() => { fresh.value = new Set() }, 4000)
    }
    v.value = next
    if (!quiet) {
      active.value = await api('/api/anomalies').catch(() => [])
      brief.value = await api('/api/brief').catch(() => null)
    }
  } catch (e) { if (!quiet) error.value = e.message }
}
onMounted(() => { load(); timer = setInterval(() => load(true), 60_000) })
onBeforeUnmount(() => clearInterval(timer))
watch(weeks, () => load())

const panels = computed(() => v.value?.panels || [])
// chart options built once per refresh, so typing elsewhere on the page does not redraw the charts
const charts = computed(() => Object.fromEntries(panels.value.map((p) => [p.key, Object.values(p.series).map((s) => ({ label: s.label, option: optionFor(s) }))])))
const value = (x) => (x.value === null || x.value === undefined ? 'unknown' : fmt(x.value, x.unit === 'items' || x.unit === 'orders' || x.unit === 'lots' || x.unit === 'open' ? '' : x.unit))
const go = (key) => document.getElementById(`panel-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
const isoRows = (p) => p.lists?.iso || []
const targets = ref({})
watch(v, (x) => { if (x && !Object.keys(targets.value).length) targets.value = Object.fromEntries(Object.entries(x.thresholds).map(([k, t]) => [k, { green: t.green, amber: t.amber }])) })
async function saveSetting(key, value) {
  error.value = ''
  try { await api('/api/overview/settings', { method: 'POST', body: { key, value } }); await load(true) } catch (e) { error.value = e.message }
}
const saveTargets = () => saveSetting('thresholds', Object.fromEntries(Object.entries(targets.value).map(([k, t]) => [k, { green: Number(t.green), amber: Number(t.amber) }])))
const pct = (r, k) => { const t = r.met + r.not_met + r.unknown; return t ? (100 * r[k]) / t : 0 }
</script>

<template>
  <PageTop title="Dashboard">
    <span v-if="v" class="hidden text-sm text-ink-gray-5 md:inline">As of {{ v.as_of }}<template v-if="v.synced_at">, ERPNext read {{ new Date(v.synced_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) }}</template></span>
    <Select v-model="weeks" :options="PERIODS" class="w-32" />
    <Button v-if="brief" icon-left="lucide-sun" label="Daily brief" @click="showBrief = !showBrief" />
    <Button icon-left="lucide-monitor" label="Big screen" route="/wall" />
  </PageTop>

  <p v-if="error" class="wq-error mb-4">{{ error }}</p>

  <section v-if="brief && showBrief" class="brief mb-5 rounded-5 border border-outline-gray-2 bg-surface-gray-1 p-4">
    <div class="mb-2 flex items-center gap-2"><h2 class="text-base font-semibold text-ink-gray-9">Daily brief</h2>
      <span class="text-sm text-ink-gray-5">{{ brief.day }}</span></div>
    <Answer :text="brief.text" class="text-p-base text-ink-gray-8" />
  </section>

  <template v-if="v">
    <section v-if="v.chain.length" class="ov-hero mb-5 rounded-5 border border-outline-gray-2 bg-surface-base px-5 pb-4 pt-4">
      <h2 class="mb-3 text-base font-semibold text-ink-gray-9">From purchase order to payment</h2>
      <FlowChain :steps="v.chain" :returns="v.returns" />
    </section>

    <section class="cards mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
      <article v-for="p in panels" :key="p.key" class="light-tile cursor-pointer rounded-5 border border-outline-gray-2 bg-surface-base p-3"
               :class="fresh.has(`${p.key}:light`) ? 'flash' : ''" tabindex="0" @click="go(p.key)" @keydown.enter="go(p.key)">
        <div class="flex items-center gap-2">
          <span class="dot" :style="{ background: LIGHT[p.light.color] }" :aria-label="COLOR_WORD[p.light.color]" />
          <h3 class="text-sm font-medium text-ink-gray-7">{{ p.label }}</h3>
        </div>
        <Tooltip :text="`${p.light.what}. Green ${p.light.better === 'higher' ? 'from' : 'up to'} ${p.light.green}, amber ${p.light.better === 'higher' ? 'from' : 'up to'} ${p.light.amber}${p.light.default ? ' (starting point: set your own target)' : ''}.`">
          <p class="ov-num mt-1 w-fit text-ink-gray-9">{{ value(p.light) }}</p>
        </Tooltip>
        <p class="text-xs text-ink-gray-5">{{ COLOR_WORD[p.light.color] }}</p>
      </article>
    </section>

    <section v-if="v.waiting.length" class="waiting mb-5 rounded-5 border border-outline-gray-2 bg-surface-base p-4">
      <h2 class="mb-2 text-base font-semibold text-ink-gray-9">Waiting for people</h2>
      <ul class="flex flex-wrap gap-2">
        <li v-for="w in v.waiting" :key="w.kind">
          <RouterLink :to="w.link" class="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm"
                      :class="w.urgent ? 'border-outline-red-2 bg-surface-red-1 text-ink-red-7' : 'border-outline-gray-2 text-ink-gray-8 hover:bg-surface-gray-2'">
            <b class="font-semibold">{{ w.count }}</b>{{ w.label }}</RouterLink></li>
      </ul>
    </section>

    <section class="panels grid gap-4 lg:grid-cols-2">
      <article v-for="p in panels" :id="`panel-${p.key}`" :key="p.key" class="panel scroll-mt-4 rounded-5 border border-outline-gray-2 bg-surface-base p-4">
        <header class="mb-2 flex items-baseline justify-between gap-3">
          <h2 class="flex items-center gap-2 text-base font-semibold text-ink-gray-9">
            <span class="dot" :style="{ background: LIGHT[p.light.color] }" />{{ p.label }}</h2>
          <span class="text-sm text-ink-gray-5">{{ p.light.what }}</span>
        </header>
        <div class="mb-3 flex flex-wrap gap-x-6 gap-y-2">
          <div v-for="f in p.figures" :key="f.label" :class="fresh.has(`${p.key}:${f.label}`) ? 'flash' : ''" class="rounded-2 px-1">
            <component :is="f.link ? 'RouterLink' : 'div'" :to="f.link" class="block">
              <p class="ov-fig text-ink-gray-9">{{ value(f) }}</p>
              <p class="text-xs text-ink-gray-5">{{ f.label }}</p>
            </component>
          </div>
        </div>
        <template v-for="(s, i) in charts[p.key]" :key="s.label">
          <p class="text-xs font-medium text-ink-gray-6" :class="i ? 'mt-2' : ''">{{ s.label }}</p>
          <OvChart :option="s.option" :height="i ? '130px' : '150px'" />
        </template>
        <div v-if="isoRows(p).length" class="mt-3 space-y-2">
          <RouterLink v-for="r in isoRows(p)" :key="r.standard" to="/system" class="block">
            <p class="mb-1 flex justify-between text-xs text-ink-gray-6"><span>{{ r.standard.toUpperCase().replace('ISO', 'ISO ') }} control points</span>
              <span>{{ r.met }} met, {{ r.not_met }} not met, {{ r.unknown }} unknown</span></p>
            <div class="flex h-2.5 overflow-hidden rounded-full bg-surface-gray-2">
              <i :style="{ width: `${pct(r, 'met')}%`, background: LIGHT.green }" /><i :style="{ width: `${pct(r, 'not_met')}%`, background: LIGHT.red }" />
              <i :style="{ width: `${pct(r, 'unknown')}%`, background: LIGHT.unknown }" /></div>
          </RouterLink>
        </div>
        <ul v-for="(rows, name) in p.lists" v-show="name !== 'iso' && rows.length" :key="name" class="mt-3 divide-y divide-outline-gray-1 text-sm">
          <li v-for="(r, i) in rows" :key="r.link || i" class="flex justify-between gap-3 py-1.5">
            <RouterLink v-if="r.link" :to="r.link" class="truncate text-ink-gray-8 hover:underline">{{ r.label }}</RouterLink>
            <span v-else class="truncate text-ink-gray-8">{{ r.label }}</span>
            <span class="shrink-0 text-ink-gray-6">{{ r.unit === 'currency' ? fmt(r.value, 'currency') : `${fmt(r.value)} ${r.value === 1 ? r.unit.replace('days', 'day') : r.unit}` }}</span></li>
        </ul>
      </article>
    </section>

    <details v-if="v.can_configure" class="targets mt-6 rounded-5 border border-outline-gray-2 bg-surface-base p-4">
      <summary class="cursor-pointer text-base font-semibold text-ink-gray-9">Targets and big screen</summary>
      <p class="mt-2 max-w-3xl text-sm text-ink-gray-6">Each light turns green or amber at your company's targets. The values here are starting points
        until you change them. In visitor mode the big screen shows no amounts of money and no names.</p>
      <table class="wq-table mt-3 w-auto text-sm"><thead><tr><th>Light</th><th>The number</th><th>Green at</th><th>Amber at</th></tr></thead>
        <tbody><tr v-for="(t, k) in v.thresholds" :key="k"><td class="capitalize">{{ k }}</td><td>{{ t.what }} ({{ t.better }} is better)</td>
          <td><input v-model="targets[k].green" type="number" class="wq-input w-24"></td><td><input v-model="targets[k].amber" type="number" class="wq-input w-24"></td></tr></tbody></table>
      <div class="mt-3 flex flex-wrap items-center gap-4">
        <Button variant="solid" label="Save the targets" @click="saveTargets" />
        <label class="flex items-center gap-2 text-sm"><input type="checkbox" :checked="v.visitor_mode" @change="saveSetting('visitor_mode', $event.target.checked)"> Visitor mode on the big screen</label>
      </div>
    </details>

    <section class="mt-6">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-base font-semibold text-ink-gray-9">Needs attention</h2>
        <RouterLink to="/anomalies" class="text-sm text-ink-gray-5 hover:text-ink-gray-8">All anomalies</RouterLink>
      </div>
      <p v-if="!active.length" class="text-base text-ink-gray-5">No open anomalies.</p>
      <ul v-else class="anoms divide-y divide-outline-gray-1 rounded-5 border border-outline-gray-2">
        <li v-for="a in active.slice(0, 8)" :key="a.id" class="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
          <Badge :theme="SEV[a.severity] || 'gray'" :label="a.severity" class="w-16 justify-center capitalize" />
          <RouterLink :to="`/anomalies/${a.id}`" class="text-base text-ink-gray-8 hover:underline">{{ a.title }}</RouterLink>
          <span class="text-sm text-ink-gray-5">{{ a.rule_name }}</span>
        </li>
      </ul>
    </section>
  </template>
</template>

<style scoped>
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; flex: none; }
.ov-num { font-family: 'Barlow Condensed', 'Inter', sans-serif; font-weight: 600; font-size: 2rem; line-height: 1.1; font-variant-numeric: tabular-nums; }
.ov-fig { font-family: 'Barlow Condensed', 'Inter', sans-serif; font-weight: 600; font-size: 1.4rem; line-height: 1.15; font-variant-numeric: tabular-nums; }
.light-tile:hover, .light-tile:focus-visible { border-color: #1f7a8c; outline: none; }
.flash { animation: flash 2.4s ease-out; }
@keyframes flash { 0% { background: #fff2c6 } 100% { background: transparent } }
@media (prefers-reduced-motion: reduce) { .flash { animation: none; outline: 2px solid #d9902a; } }
i { display: block; height: 100%; }
</style>
