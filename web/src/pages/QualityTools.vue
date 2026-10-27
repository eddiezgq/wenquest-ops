<script setup>
// Quality tools, step 22a (ADR-0022): Pareto, histogram and scatter charts computed from the records the hub keeps,
// and check sheets (a company's own tally forms, signed). Every bar and point leads back to its records. The cause
// analyses of 22b (fishbone, 5 Why) are listed here; each is started from its record.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { t } from '../i18n'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const TABS = { pareto: 'Pareto', histogram: 'Histogram', scatter: 'Scatter', sheets: 'Check sheets', causes: 'Cause analysis' }
const tab = computed({ get: () => (TABS[route.query.tab] ? route.query.tab : 'pareto'), set: (v) => router.replace({ query: { tab: v } }) })
const canEdit = computed(() => ws.value?.user.permissions.includes('quality:edit'))
const error = ref('')
const done = ref('')
const opts = ref(null)
const n = (v) => (Number.isInteger(v) ? v.toLocaleString() : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }))
const pct = (v) => `${Math.round(v * 100)}%`
const f3 = (v) => (v == null ? '–' : Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(3))
const LINK = { ncr: (r) => `/quality/ncr/${r.id}`, iqc: (r) => `/quality/iqc/${r.id}`, complaint: (r) => `/quality/complaints/${r.id}`,
  prod_record: (r) => `/quality/production/${r.id}` }

async function loadOptions() {
  try { opts.value = await api('/api/quality/tools/options') } catch (e) { error.value = e.message }
}
loadOptions()

// ---------- Pareto
const par = ref({ source: 'ncr', by: 'item_code', since: '', until: '', form_id: null })
const pareto = ref(null)
const sel = ref(null)
const byOptions = computed(() => opts.value?.sources[par.value.source]?.by || {})
watch(() => par.value.source, () => {
  const keys = Object.keys(byOptions.value)
  if (!keys.includes(par.value.by)) par.value.by = keys[0]
  if (par.value.source === 'check_sheet' && !par.value.form_id) par.value.form_id = opts.value?.forms[0]?.id || null
})
let asked = 0
async function loadPareto() {
  if (!opts.value || tab.value !== 'pareto') return
  if (par.value.source === 'check_sheet' && !par.value.form_id) { pareto.value = null; return }
  const mine = ++asked
  const q = new URLSearchParams({ source: par.value.source, by: par.value.by })
  for (const k of ['since', 'until']) if (par.value[k]) q.set(k, par.value[k])
  if (par.value.source === 'check_sheet') q.set('form_id', par.value.form_id)
  try {
    const out = await api(`/api/quality/tools/pareto?${q}`)
    if (mine === asked) { pareto.value = out; sel.value = null; error.value = '' }
  } catch (e) { if (mine === asked) { pareto.value = null; error.value = e.message } }
}
watch([par, opts, tab], loadPareto, { deep: true, immediate: true })
const PW = 760, PH = 300, PP = { l: 46, r: 46, t: 16, b: 74 }
const pBars = computed(() => {
  const b = pareto.value?.bars || []
  if (!b.length) return []
  const max = b[0].count, w = (PW - PP.l - PP.r) / b.length
  return b.map((x, i) => ({ ...x, x: PP.l + i * w + w * 0.12, w: w * 0.76, cx: PP.l + i * w + w / 2,
    y: PP.t + (1 - x.count / max) * (PH - PP.t - PP.b), cy: PP.t + (1 - x.cumulative) * (PH - PP.t - PP.b) }))
})
const cumPath = computed(() => pBars.value.map((b, i) => `${i ? 'L' : 'M'}${b.cx},${b.cy}`).join(''))
const y80 = PP.t + 0.2 * (PH - PP.t - PP.b)

// ---------- Histogram and scatter
const params = computed(() => opts.value?.parameters || [])
const hpick = ref(null)
const hist = ref(null)
watch(params, (p) => { if (!hpick.value && p.length) hpick.value = p[0] })
watch([hpick, tab], async () => {
  if (!hpick.value || tab.value !== 'histogram') return
  const p = hpick.value
  try { hist.value = await api(`/api/quality/tools/histogram?source=${p.source}&item_code=${encodeURIComponent(p.item_code)}&parameter=${encodeURIComponent(p.parameter)}`) }
  catch (e) { hist.value = null; error.value = e.message }
}, { immediate: true })
const HW = 760, HH = 280, HP = { l: 40, r: 20, t: 20, b: 40 }
const hView = computed(() => {
  const h = hist.value?.histogram
  if (!h) return null
  const xs = [h.min, h.max, h.LSL, h.USL].filter((v) => v != null)
  const lo = Math.min(...xs), hi = Math.max(...xs), pad = (hi - lo || 1) * 0.05
  const sx = (v) => HP.l + ((v - lo + pad) * (HW - HP.l - HP.r)) / (hi - lo + 2 * pad)
  const top = Math.max(...h.counts)
  const sy = (c) => HP.t + (1 - c / top) * (HH - HP.t - HP.b)
  return { sx, sy, top, bars: h.counts.map((c, i) => ({ c, x: sx(h.edges[i]), w: Math.max(1, sx(h.edges[i + 1]) - sx(h.edges[i]) - 2), y: sy(c), lo: h.edges[i], hi: h.edges[i + 1] })) }
})
const spick = ref({ key: '', x: '', y: '' })
const scatter = ref(null)
const groups = computed(() => {
  const g = {}
  for (const p of params.value) (g[`${p.source}|${p.item_code}`] ||= []).push(p.parameter)
  return g
})
watch(groups, (g) => {
  if (spick.value.key) return
  const k = Object.keys(g).find((x) => g[x].length >= 2)
  if (k) spick.value = { key: k, x: g[k][0], y: g[k][1] }
})
watch([spick, tab], async () => {
  const s = spick.value
  if (!s.key || tab.value !== 'scatter' || !s.x || !s.y || s.x === s.y) { scatter.value = null; return }
  const [source, item] = s.key.split('|')
  try { scatter.value = await api(`/api/quality/tools/scatter?source=${source}&item_code=${encodeURIComponent(item)}&x=${encodeURIComponent(s.x)}&y=${encodeURIComponent(s.y)}`); error.value = '' }
  catch (e) { scatter.value = null; error.value = e.message }
}, { deep: true, immediate: true })
const hoverPt = ref(null)
const sView = computed(() => {
  const pts = scatter.value?.points || []
  if (!pts.length) return null
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y)
  const box = (a) => { const lo = Math.min(...a), hi = Math.max(...a), pad = (hi - lo || Math.abs(lo) || 1) * 0.08; return [lo - pad, hi + pad] }
  const [x0, x1] = box(xs), [y0, y1] = box(ys)
  const sx = (v) => HP.l + 20 + ((v - x0) * (HW - HP.l - 20 - HP.r)) / (x1 - x0)
  const sy = (v) => HP.t + ((y1 - v) * (HH - HP.t - HP.b)) / (y1 - y0)
  const fit = scatter.value.fit
  const line = fit.slope == null ? null : { x1: sx(x0), y1: sy(fit.intercept + fit.slope * x0), x2: sx(x1), y2: sy(fit.intercept + fit.slope * x1) }
  return { sx, sy, line, x0, x1, y0, y1 }
})

// ---------- Check sheets
const cs = ref(null)
const nf = ref({ name: '', categories: '' })
const showForm = ref(false)
const tally = ref({ form_id: null, on_date: '', item_code: '', place: '', counts: {}, note: '', password: '' })
const tallyForm = computed(() => cs.value?.forms.find((f) => f.id === tally.value.form_id))
async function loadSheets() {
  try {
    cs.value = await api('/api/quality/check-sheets')
    if (!tally.value.form_id) tally.value.form_id = cs.value.forms.find((f) => f.active)?.id || null
  } catch (e) { error.value = e.message }
}
watch(tab, (v) => { if (v === 'sheets') loadSheets() }, { immediate: true })
async function makeForm() {
  error.value = ''; done.value = ''
  try {
    const f = await api('/api/quality/check-sheets/forms', { method: 'POST', body: { name: nf.value.name, categories: nf.value.categories.split('\n') } })
    done.value = t('Form {name} made with {n} categories.', { name: f.name, n: f.categories.length })
    nf.value = { name: '', categories: '' }; showForm.value = false; tally.value.form_id = f.id
    await Promise.all([loadSheets(), loadOptions()])
  } catch (e) { error.value = e.message }
}
async function setActive(f, active) {
  error.value = ''
  try { await api(`/api/quality/check-sheets/forms/${f.id}/active`, { method: 'POST', body: { active } }); await Promise.all([loadSheets(), loadOptions()]) }
  catch (e) { error.value = e.message }
}
async function recordTally() {
  error.value = ''; done.value = ''
  const tl = tally.value
  const counts = Object.fromEntries((tallyForm.value?.categories || []).map((c) => [c, String(tl.counts[c] ?? 0)]))
  try {
    const r = await api('/api/quality/check-sheets', { method: 'POST', body: { ...tl, counts } })
    done.value = t('{name} recorded and signed: {total} counted.', { name: r.name, total: r.total })
    tally.value = { ...tl, counts: {}, note: '', password: '' }
    await loadSheets()
  } catch (e) { error.value = e.message; tally.value.password = '' }
}
// ---------- Cause analyses (22b): listed here, started from the record they analyse
const ca = ref(null)
const CA_THEME = { open: 'blue', concluded: 'green', cancelled: 'gray' }
const REF_PAGE = { ncr: 'ncr', capa: 'capa', complaint: 'complaints' }
watch(tab, async (v) => {
  if (v !== 'causes') return
  try { ca.value = await api('/api/quality/causes') } catch (e) { error.value = e.message }
}, { immediate: true })
function showPareto(form) { par.value = { ...par.value, source: 'check_sheet', by: 'category', form_id: form.id }; tab.value = 'pareto' }
</script>

<template>
  <PageTop :crumbs="[{ label: t('Quality'), to: '/quality' }]">
    <template #title>{{ t('Quality tools') }}</template>
  </PageTop>
  <nav data-help="tools-tabs" class="tabs -mt-2 mb-5 flex gap-5 overflow-x-auto border-b border-outline-gray-2">
    <a v-for="(l, k) in TABS" :key="k" href="#" class="-mb-px whitespace-nowrap border-b-2 pb-2 text-base"
       :class="tab === k ? 'border-outline-gray-9 font-medium text-ink-gray-9' : 'border-transparent text-ink-gray-5 hover:text-ink-gray-8'" @click.prevent="tab = k">{{ t(l) }}</a>
  </nav>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <template v-if="tab === 'pareto' && opts">
    <div data-help="pareto-pick" class="mb-4 flex flex-wrap items-end gap-3">
      <label class="wq-field">{{ t('Count') }}<select v-model="par.source" class="wq-input"><option v-for="(s, k) in opts.sources" :key="k" :value="k">{{ s.label }}</option></select></label>
      <label class="wq-field">{{ t('group::By') }}<select v-model="par.by" class="wq-input"><option v-for="(l, k) in byOptions" :key="k" :value="k">{{ l }}</option></select></label>
      <label v-if="par.source === 'check_sheet'" class="wq-field">{{ t('Form') }}<select v-model="par.form_id" class="wq-input"><option v-for="f in opts.forms" :key="f.id" :value="f.id">{{ f.name }}</option></select></label>
      <label class="wq-field">{{ t('From') }}<input v-model="par.since" type="date" class="wq-input"></label>
      <label class="wq-field">{{ t('To') }}<input v-model="par.until" type="date" class="wq-input"></label>
    </div>
    <p v-if="par.source === 'check_sheet' && !opts.forms.length" class="wq-muted">{{ t('No check sheet forms yet: make one on the Check sheets tab.') }}</p>
    <template v-if="pareto">
      <p v-if="!pareto.bars.length" class="wq-muted">{{ pareto.note }}</p>
      <template v-else>
        <figure data-help="pareto-chart" class="chart m-0">
          <svg :viewBox="`0 0 ${PW} ${PH}`" role="img" :aria-label="t('Pareto chart of {measure} by {by}', { measure: pareto.measure, by: pareto.by_label })">
            <line :x1="PP.l" :x2="PW - PP.r" :y1="y80" :y2="y80" class="ref" /><text :x="PW - PP.r + 4" :y="y80 + 4" class="ax">80%</text>
            <g v-for="(b, i) in pBars" :key="b.key" class="bar" @click="sel = i">
              <rect :x="b.x" :y="b.y" :width="b.w" :height="PH - PP.b - b.y" :class="[sel === i ? 'on' : '', i < pareto.vital_few ? 'few' : '', b.key === 'not recorded' ? 'nr' : '']" />
              <text :x="b.cx" :y="b.y - 4" class="val">{{ n(b.count) }}</text>
              <text :x="b.cx" :y="PH - PP.b + 14" class="cat" :transform="`rotate(28 ${b.cx} ${PH - PP.b + 14})`">{{ b.key.length > 18 ? b.key.slice(0, 17) + '…' : b.key }}</text>
            </g>
            <path :d="cumPath" class="cum" />
            <circle v-for="b in pBars" :key="'c' + b.key" :cx="b.cx" :cy="b.cy" r="3" class="cumpt" />
            <text :x="PW - PP.r + 4" :y="PP.t + 4" class="ax">100%</text>
          </svg>
          <figcaption class="mt-2 text-sm text-ink-gray-5">{{ t('{total} {measure} from {records} records, by {by}.', { total: n(pareto.total), measure: pareto.measure, records: pareto.records, by: pareto.by_label.toLowerCase() }) }}
            {{ t('The first {few} of {total} make up 80% or more. Click a bar for its records.', { few: pareto.vital_few, total: pareto.bars.length }) }}</figcaption>
        </figure>
        <p v-if="pareto.note" class="mt-2 text-sm text-ink-amber-8">{{ pareto.note }}</p>
        <section v-if="sel !== null" data-help="pareto-records" class="wq-panel mt-4 p-4">
          <h3 class="mb-2 text-base font-semibold text-ink-gray-9">{{ pareto.bars[sel].key }}: {{ n(pareto.bars[sel].count) }} ({{ pct(pareto.bars[sel].share) }})</h3>
          <ul class="text-sm"><li v-for="r in pareto.bars[sel].records" :key="r.kind + r.id" class="py-1">
            <RouterLink v-if="LINK[r.kind]" :to="LINK[r.kind](r)" class="wq-link">{{ r.name }}</RouterLink><span v-else class="font-medium">{{ r.name }}</span>
            <span class="text-ink-gray-5"> · {{ r.title }}</span></li></ul>
          <p v-if="pareto.bars[sel].records.length >= 50" class="wq-muted mt-1">{{ t('The first 50 are listed; the count includes all.') }}</p>
        </section>
      </template>
    </template>
  </template>

  <template v-if="tab === 'histogram'">
    <p v-if="!params.length" class="wq-muted">{{ t('No measured values yet: they come from signed incoming inspections and production measurements.') }}</p>
    <div v-else data-help="hist-pick" class="mb-4 flex flex-wrap items-end gap-3">
      <label class="wq-field">{{ t('Characteristic') }}<select v-model="hpick" class="wq-input"><option v-for="p in params" :key="p.source + p.item_code + p.parameter" :value="p">{{ p.item_code }} · {{ p.parameter }} ({{ p.source }})</option></select></label>
    </div>
    <template v-if="hist">
      <p v-if="!hist.enough_data" class="wq-muted">{{ hist.note }}</p>
      <div v-else class="grid gap-4 lg:grid-cols-[1fr_16rem]">
        <figure data-help="hist-chart" class="chart m-0">
          <svg :viewBox="`0 0 ${HW} ${HH}`" role="img" :aria-label="t('Histogram of {n} values', { n: hist.values })">
            <g v-for="(b, i) in hView.bars" :key="i"><rect :x="b.x" :y="b.y" :width="b.w" :height="HH - HP.b - b.y" class="hbar"><title>{{ f3(b.lo) }} – {{ f3(b.hi) }}: {{ b.c }}</title></rect>
              <text v-if="b.c" :x="b.x + b.w / 2" :y="b.y - 4" class="val">{{ b.c }}</text></g>
            <g v-for="[k, v, cls] in [['LSL', hist.histogram.LSL, 'spec'], ['USL', hist.histogram.USL, 'spec'], ['mean', hist.histogram.mean, 'mean']]" :key="k">
              <template v-if="v != null"><line :x1="hView.sx(v)" :x2="hView.sx(v)" :y1="HP.t - 6" :y2="HH - HP.b" :class="cls" /><text :x="hView.sx(v)" :y="k === 'mean' ? HH - HP.b + 16 : HP.t - 8" class="ax" text-anchor="middle">{{ k === 'mean' ? t('mean') : k }} {{ f3(v) }}</text></template>
            </g>
            <line :x1="HP.l" :x2="HW - HP.r" :y1="HH - HP.b" :y2="HH - HP.b" class="axis" />
            <text :x="HP.l" :y="HH - HP.b + 16" class="ax">{{ f3(hist.histogram.min) }}</text>
            <text :x="HW - HP.r" :y="HH - HP.b + 16" class="ax" text-anchor="end">{{ f3(hist.histogram.max) }}</text>
          </svg>
          <figcaption class="mt-2 text-sm text-ink-gray-5">{{ t('{n} values in {bins} equal bins. Hover a bar for its range.', { n: hist.values, bins: hist.histogram.counts.length }) }}</figcaption>
        </figure>
        <section data-help="hist-capability" class="wq-panel p-4 text-sm">
          <h3 class="mb-2 text-base font-semibold text-ink-gray-9">{{ t('Spread and capability') }}</h3>
          <div v-for="[k, v] in [['Mean', f3(hist.histogram.mean)], ['Std dev', f3(hist.histogram.s)], ['Below LSL', hist.histogram.below ?? t('unknown')], ['Above USL', hist.histogram.above ?? t('unknown')],
                                  ['Cp', f3(hist.capability?.Cp)], ['Cpk', f3(hist.capability?.Cpk)]]" :key="k" class="flex justify-between border-b border-outline-gray-1 py-1"><span class="text-ink-gray-5">{{ t(k) }}</span><span>{{ v }}</span></div>
          <p v-if="hist.capability_note" class="mt-2 text-ink-amber-8">{{ hist.capability_note }}</p>
          <p v-if="hist.limits_note" class="mt-1 text-ink-amber-8">{{ hist.limits_note }}</p>
        </section>
      </div>
    </template>
  </template>

  <template v-if="tab === 'scatter'">
    <p v-if="!Object.values(groups).some((g) => g.length >= 2)" class="wq-muted">{{ t('A scatter plot needs two measured characteristics of the same item, measured on the same piece.') }}</p>
    <div v-else data-help="scatter-pick" class="mb-4 flex flex-wrap items-end gap-3">
      <label class="wq-field">{{ t('Item') }}<select v-model="spick.key" class="wq-input"><option v-for="(g, k) in groups" :key="k" :value="k" :disabled="g.length < 2">{{ k.split('|')[1] }} ({{ k.split('|')[0] }})</option></select></label>
      <label class="wq-field">{{ t('Across (x)') }}<select v-model="spick.x" class="wq-input"><option v-for="p in groups[spick.key] || []" :key="p">{{ p }}</option></select></label>
      <label class="wq-field">{{ t('Up (y)') }}<select v-model="spick.y" class="wq-input"><option v-for="p in groups[spick.key] || []" :key="p">{{ p }}</option></select></label>
    </div>
    <template v-if="scatter">
      <p v-if="!scatter.points.length" class="wq-muted">{{ t('No piece has both values yet.') }}</p>
      <div v-else class="grid gap-4 lg:grid-cols-[1fr_16rem]">
        <figure data-help="scatter-chart" class="chart relative m-0">
          <svg :viewBox="`0 0 ${HW} ${HH}`" role="img" :aria-label="t('Scatter plot of {y} against {x}', { y: scatter.y, x: scatter.x })">
            <line :x1="HP.l + 20" :x2="HW - HP.r" :y1="HH - HP.b" :y2="HH - HP.b" class="axis" /><line :x1="HP.l + 20" :x2="HP.l + 20" :y1="HP.t" :y2="HH - HP.b" class="axis" />
            <line v-if="sView.line" v-bind="sView.line" class="fit" />
            <circle v-for="(p, i) in scatter.points" :key="i" :cx="sView.sx(p.x)" :cy="sView.sy(p.y)" r="4.5" class="dot" @mouseenter="hoverPt = p" @mouseleave="hoverPt = null" />
            <text :x="HW - HP.r" :y="HH - 8" class="ax" text-anchor="end">{{ scatter.x }} →</text>
            <text :x="HP.l + 24" :y="HP.t + 4" class="ax">↑ {{ scatter.y }}</text>
          </svg>
          <div v-if="hoverPt" class="tip">{{ hoverPt.label }}: {{ f3(hoverPt.x) }}, {{ f3(hoverPt.y) }}</div>
          <figcaption class="mt-2 text-sm text-ink-gray-5">{{ t('{n} pieces with both values. Hover a point for its record.', { n: scatter.points.length }) }}</figcaption>
        </figure>
        <section data-help="scatter-fit" class="wq-panel p-4 text-sm">
          <h3 class="mb-2 text-base font-semibold text-ink-gray-9">{{ t('Correlation') }}</h3>
          <div v-for="[k, v] in [['Pairs', scatter.fit.n], ['r', f3(scatter.fit.r)], ['r²', f3(scatter.fit.r2)], ['Slope', f3(scatter.fit.slope)]]" :key="k" class="flex justify-between border-b border-outline-gray-1 py-1"><span class="text-ink-gray-5">{{ t(k) }}</span><span>{{ v }}</span></div>
          <p class="mt-2 text-ink-gray-7">{{ scatter.fit.note }}</p>
        </section>
      </div>
    </template>
  </template>

  <template v-if="tab === 'causes' && ca">
    <p data-help="causes-list" class="mb-4 max-w-3xl text-base text-ink-gray-6">{{ t("A fishbone or a 5 Why is started from the nonconformance report, corrective action or complaint it analyses. Its signed conclusion is added to that record's root cause.") }}</p>
    <p v-if="!ca.analyses.length" class="wq-muted">{{ t('None yet. Open a nonconformance report, a corrective action or a complaint and start one there.') }}</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Analysis') }}</th><th>{{ t('Method') }}</th><th>{{ t('On') }}</th><th>{{ t('Status') }}</th><th>{{ t('Problem or root cause') }}</th><th>{{ t('Causes') }}</th></tr></thead>
      <tbody><tr v-for="x in ca.analyses" :key="x.id">
        <td><RouterLink :to="`/quality/causes/${x.id}`" class="wq-link font-medium">{{ x.name }}</RouterLink></td>
        <td>{{ ca.methods[x.method] }}</td>
        <td><RouterLink :to="`/quality/${REF_PAGE[x.ref_kind]}/${x.ref_id}`" class="wq-link">{{ x.ref_name }}</RouterLink></td>
        <td><Badge :theme="CA_THEME[x.status]" :label="t(x.status)" /></td>
        <td class="max-w-md">{{ x.conclusion || x.problem }}</td>
        <td>{{ x.accepted }}<span v-if="x.proposed" class="text-ink-amber-7"> {{ t('+ {n} to decide', { n: x.proposed }) }}</span></td></tr></tbody></table>
  </template>

  <template v-if="tab === 'sheets' && cs">
    <div class="mb-4 flex justify-end"><Button v-if="canEdit" icon-left="lucide-plus" :label="t('New check sheet form')" @click="showForm = !showForm" /></div>
    <form v-if="showForm" class="wq-panel mb-5 grid gap-3 p-5 md:grid-cols-2" @submit.prevent="makeForm">
      <label class="wq-field">{{ t('Name') }}<input v-model="nf.name" class="wq-input" :placeholder="t('Packing defects, line 1')"></label>
      <label class="wq-field">{{ t('Categories, one per line') }}<textarea v-model="nf.categories" rows="5" class="wq-input" :placeholder="t('Crushed box\nWrong label\nMissing part')" /></label>
      <p class="wq-muted md:col-span-2">{{ t('A form is kept as made. To change its categories, make a new form and retire this one; earlier tallies keep their form.') }}</p>
      <div><Button type="submit" variant="solid" :label="t('Make the form')" :disabled="!nf.name.trim() || !nf.categories.trim()" /></div>
    </form>
    <div class="grid gap-4 lg:grid-cols-2">
      <section data-help="sheets-record" class="wq-panel p-5">
        <h3 class="mb-3 text-base font-semibold text-ink-gray-9">{{ t('Record a tally') }}</h3>
        <p v-if="!cs.forms.some((f) => f.active)" class="wq-muted">{{ t('No form in use yet.') }}</p>
        <form v-else-if="canEdit" class="grid gap-3" @submit.prevent="recordTally">
          <div class="grid gap-3 md:grid-cols-2">
            <label class="wq-field">{{ t('Form') }}<select v-model="tally.form_id" class="wq-input"><option v-for="f in cs.forms.filter((x) => x.active)" :key="f.id" :value="f.id">{{ f.name }}</option></select></label>
            <label class="wq-field">{{ t('Day counted') }}<input v-model="tally.on_date" type="date" class="wq-input"></label>
            <label class="wq-field">{{ t('Item (optional)') }}<input v-model="tally.item_code" class="wq-input"></label>
            <label class="wq-field">{{ t('Where (line, station, shift)') }}<input v-model="tally.place" class="wq-input"></label>
          </div>
          <div class="grid gap-2 md:grid-cols-2">
            <label v-for="c in tallyForm?.categories || []" :key="c" class="flex items-center justify-between gap-2 rounded-3 border border-outline-gray-2 px-3 py-1.5">
              <span class="text-ink-gray-8">{{ c }}</span>
              <span class="flex items-center gap-1"><Button size="sm" label="−" @click="tally.counts[c] = Math.max(0, (Number(tally.counts[c]) || 0) - 1)" />
                <input v-model="tally.counts[c]" type="number" min="0" class="wq-input w-16 text-center" placeholder="0">
                <Button size="sm" label="+" @click="tally.counts[c] = (Number(tally.counts[c]) || 0) + 1" /></span>
            </label>
          </div>
          <label class="wq-field">{{ t('Note') }}<input v-model="tally.note" class="wq-input"></label>
          <div class="flex items-end gap-2"><label class="wq-field flex-1">{{ t('Your password (signs the tally)') }}<input v-model="tally.password" type="password" class="wq-input" autocomplete="current-password"></label>
            <Button type="submit" variant="solid" :label="t('Record and sign')" :disabled="!tally.password" /></div>
        </form>
        <p v-else class="wq-muted">{{ t('Your role can read check sheets but not record them.') }}</p>
      </section>
      <section data-help="sheets-forms" class="wq-panel p-5">
        <h3 class="mb-3 text-base font-semibold text-ink-gray-9">{{ t('Forms') }}</h3>
        <p v-if="!cs.forms.length" class="wq-muted">{{ t('None yet.') }}</p>
        <ul class="text-sm"><li v-for="f in cs.forms" :key="f.id" class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 py-2">
          <span class="font-medium text-ink-gray-9">{{ f.name }}</span><Badge v-if="!f.active" theme="gray" :label="t('retired')" />
          <span class="text-ink-gray-5">{{ f.categories.join(', ') }}</span>
          <span class="ml-auto flex gap-1"><Button size="sm" :label="t('Pareto')" @click="showPareto(f)" />
            <Button v-if="canEdit" size="sm" :label="f.active ? t('Retire') : t('Use again')" @click="setActive(f, !f.active)" /></span></li></ul>
      </section>
    </div>
    <section data-help="sheets-list" class="wq-panel mt-4 p-5">
      <h3 class="mb-3 text-base font-semibold text-ink-gray-9">{{ t('Recent tallies') }}</h3>
      <p v-if="!cs.sheets.length" class="wq-muted">{{ t('None yet.') }}</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Tally') }}</th><th>{{ t('Form') }}</th><th>{{ t('Day') }}</th><th>{{ t('Where') }}</th><th>{{ t('Item') }}</th><th>{{ t('Counted') }}</th><th>{{ t('Signed by') }}</th></tr></thead>
        <tbody><tr v-for="s in cs.sheets" :key="s.id"><td class="font-medium">{{ s.name }}</td><td>{{ s.form }}</td><td>{{ s.on_date }}</td><td>{{ s.place }}</td><td>{{ s.item_code || '' }}</td>
          <td :title="Object.entries(s.counts).map(([k, v]) => `${k}: ${v}`).join(', ')">{{ s.total }}</td><td>{{ s.signed_by }}</td></tr></tbody></table>
    </section>
  </template>
</template>

<style scoped>
.chart svg { width: 100%; height: auto; max-height: 24rem; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; }
.bar { cursor: pointer; }
.bar rect { fill: var(--accent); opacity: .55; }
.bar rect.few { opacity: .9; }
.bar rect.nr { fill: var(--muted); }
.bar rect.on { stroke: var(--ink); stroke-width: 2; }
.val { fill: var(--ink); font-size: 11px; text-anchor: middle; }
.cat { fill: var(--muted); font-size: 11px; }
.ax { fill: var(--muted); font-size: 10px; }
.cum { fill: none; stroke: var(--warn); stroke-width: 2; }
.cumpt { fill: var(--warn); }
.ref { stroke: var(--muted); stroke-dasharray: 4 4; }
.hbar { fill: var(--accent); opacity: .7; }
.spec { stroke: var(--critical); stroke-width: 1.5; stroke-dasharray: 3 3; }
.mean { stroke: var(--ink); stroke-width: 1.5; }
.axis { stroke: var(--line); }
.fit { stroke: var(--warn); stroke-width: 2; }
.dot { fill: var(--accent); stroke: var(--panel); stroke-width: 1.5; cursor: pointer; }
.tip { position: absolute; top: .4rem; left: 3.6rem; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: .2rem .5rem; font-size: .85rem; }
</style>
