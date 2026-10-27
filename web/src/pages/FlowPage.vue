<script setup>
// One process flow chart (ADR-0022, 22d): the steps drawn in order with their branches (rework loops, lots leaving
// the flow), each step linked to what it rests on. Links are checked against what is in effect; approval is signed by
// someone who does not own and did not edit it, and the chart is then fixed.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'
import { t } from '../i18n'

const route = useRoute()
const router = useRouter()
const r = ref(null)
const opts = ref(null)
const error = ref('')
const done = ref('')
const busy = ref(false)
const sel = ref(null)
const f = ref({})
const x = ref({ password: '', reason: '' })
const FIELDS = ['title', 'item_code', 'scope', 'owner']
const ST = { draft: 'gray', approved: 'green', superseded: 'gray', withdrawn: 'gray' }
const blank = () => ({ code: '', kind: 'operation', name: '', description: '', branches: [], links: { documents: [], fmea: [], plan: '', template: '', gauges: [] } })
const step = ref(blank())
const pick = ref({ documents: '', fmea: '', gauges: '' })
const draft = computed(() => r.value?.status === 'draft' && r.value?.can_edit)
const current = computed(() => r.value?.steps.find((s) => s.id === sel.value))

function set(v) { r.value = v; f.value = Object.fromEntries(FIELDS.map((k) => [k, v[k] ?? ''])) }
async function load() { error.value = ''; try { set(await api(`/api/flow/charts/${route.params.id}`)) } catch (e) { error.value = e.message } }
watch(() => route.params.id, () => { sel.value = null; step.value = blank(); load() }, { immediate: true })
watch(draft, async (d) => { if (d && !opts.value) { try { opts.value = await api('/api/flow/options') } catch (e) { error.value = e.message } } }, { immediate: true })
const changed = () => Object.fromEntries(FIELDS.filter((k) => (f.value[k] ?? '') !== (r.value[k] ?? '')).map((k) => [k, f.value[k]]))
async function call(path, method, body, message) {
  error.value = ''; done.value = ''; busy.value = true
  try { const v = await api(path, { method, body }); if (v.steps) set(v); done.value = message; return v } catch (e) { error.value = e.message } finally { busy.value = false }
}

// ---------- the drawing
const ROW = 84, TOP = 34, SX = 250, W = 900
const H = computed(() => TOP * 2 + Math.max(1, r.value?.steps.length || 1) * ROW - ROW / 2)
const ys = computed(() => Object.fromEntries((r.value?.steps || []).map((s, i) => [s.seq, TOP + i * ROW])))
const lanes = computed(() => {
  const out = []
  let k = 0
  for (const s of r.value?.steps || []) {
    for (const b of s.branches) {
      const y0 = ys.value[s.seq]
      if (b.to == null) { out.push({ out: true, y0, label: b.label || t('leaves the flow'), kind: b.kind }); continue }
      const y1 = ys.value[b.to]
      if (y1 == null) continue
      const lane = 44 + 26 * k++
      out.push({ d: `M${SX - 19},${y0} H${SX - lane} V${y1} H${SX - 24}`, lx: SX - lane - 6, ly: (y0 + y1) / 2, label: b.label || b.kind, kind: b.kind })
    }
  }
  return out
})
const linkKeys = (s) => {
  const l = s.links || {}
  return [...(l.documents || []).map((d) => `documents:${d}`), ...(l.fmea || []).map((m) => `fmea:${m.name}#${m.seq}`),
    ...['plan', 'template'].filter((k) => l[k]).map((k) => `${k}:${l[k]}`), ...(l.gauges || []).map((g) => `gauges:${g}`)]
}
const short = (k) => { const [kind, key] = k.split(/:(.*)/s); return kind === 'fmea' ? key.replace('#', ` ${t('row')} `) : key }
const linkState = (k) => r.value?.links_now[k] || { ok: false, why: t('not checked') }
const rowText = (v) => v.replace('#', ` ${t('row')} `)
const cut = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s)

// ---------- editing a step
function choose(s) {
  sel.value = s.id
  const l = s.links || {}
  step.value = { code: s.code, kind: s.kind, name: s.name, description: s.description, branches: s.branches.map((b) => ({ ...b, to: b.to ?? '' })),
    links: { documents: [...(l.documents || [])], fmea: (l.fmea || []).map((m) => `${m.name}#${m.seq}`), plan: l.plan || '', template: l.template || '', gauges: [...(l.gauges || [])] } }
}
function fresh() { sel.value = null; step.value = blank() }
function payload() {
  const s = step.value
  return { code: s.code, kind: s.kind, name: s.name, description: s.description,
    branches: s.branches.map((b) => ({ to: b.to === '' ? null : Number(b.to), kind: b.kind, label: b.label })),
    links: { documents: s.links.documents, gauges: s.links.gauges, plan: s.links.plan || null, template: s.links.template || null,
      fmea: s.links.fmea.map((k) => { const [name, seq] = k.split('#'); return { name, seq: Number(seq) } }) } }
}
async function save() {
  const ok = sel.value
    ? await call(`/api/flow/charts/${r.value.id}/steps/${sel.value}`, 'PUT', payload(), t('Step saved.'))
    : await call(`/api/flow/charts/${r.value.id}/steps`, 'POST', payload(), t('Step added.'))
  if (ok && !sel.value) fresh()
}
const add = (k) => { const v = pick.value[k]; if (v && !step.value.links[k].includes(v)) step.value.links[k].push(v); pick.value[k] = '' }
const drop = (k, v) => { step.value.links[k] = step.value.links[k].filter((x_) => x_ !== v) }
const move = (dir) => call(`/api/flow/charts/${r.value.id}/steps/${sel.value}/move`, 'POST', { direction: dir }, '')
async function remove() { if (await call(`/api/flow/charts/${r.value.id}/steps/${sel.value}`, 'DELETE', null, t('Step removed.'))) fresh() }
async function revise() {
  const v = await call(`/api/flow/charts/${r.value.id}/revise`, 'POST', {}, t('A new version is started.'))
  if (v) router.push(`/quality/flow/${v.id}`)
}
</script>

<template>
  <PageTop :crumbs="[{ label: t('Process flow'), to: '/quality/flow' }]">
    <template #title>{{ r ? `${r.name} v${r.version} · ${r.title}` : t('Flow chart') }}</template>
    <Badge v-if="r" :theme="ST[r.status]" size="lg" :label="t(r.status)" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="r">
    <p v-if="r.intact === false" class="wq-error mb-4">{{ t('This flow chart no longer matches what was approved.') }}</p>
    <section v-if="r.changed_since.length" data-help="flow-changed" class="mb-5 rounded-3 border border-outline-amber-2 bg-surface-amber-1 p-4 text-sm">
      <p class="mb-1 font-medium text-ink-amber-8">{{ t('Since this chart was approved, what some of its links point to has changed. If the process changed too, start a new version.') }}</p>
      <ul class="list-disc ps-5"><li v-for="c in r.changed_since" :key="c.link">{{ t('{link}: was {was}; now {now}', { link: short(c.link), was: c.was, now: c.now }) }}</li></ul>
    </section>

    <section class="wq-panel mb-5 grid gap-3 p-5 md:grid-cols-4">
      <label class="wq-field md:col-span-2">{{ t('Process') }}<input v-model="f.title" class="wq-input" :disabled="!draft"></label>
      <label class="wq-field">{{ t('Item code') }}<input v-model="f.item_code" class="wq-input" :disabled="!draft"></label>
      <label class="wq-field">{{ t('Owner') }}<select v-model="f.owner" class="wq-select" :disabled="!draft"><option value="" /><option v-for="p in r.people" :key="p">{{ p }}</option></select></label>
      <label class="wq-field md:col-span-4">{{ t('Scope') }}<input v-model="f.scope" class="wq-input" :disabled="!draft"></label>
      <div v-if="draft" class="md:col-span-4"><Button :label="t('Save')" :disabled="!Object.keys(changed()).length" @click="call(`/api/flow/charts/${r.id}`, 'PUT', changed(), t('Saved.'))" /></div>
    </section>

    <div class="mb-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]">
      <section data-help="flow-diagram" class="wq-panel overflow-x-auto p-3">
        <p v-if="!r.steps.length" class="wq-muted p-3">{{ t('No steps yet.') }}</p>
        <svg v-else :viewBox="`0 0 ${W} ${H}`" class="flow" role="img" :aria-label="t('Process flow {name}', { name: r.name })">
          <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ahead" /></marker></defs>
          <line v-for="(s, i) in r.steps.slice(0, -1)" :key="'m' + s.id" :x1="SX" :x2="SX" :y1="ys[s.seq] + 20" :y2="ys[r.steps[i + 1].seq] - 21" class="main" marker-end="url(#ah)" />
          <g v-for="(b, i) in lanes" :key="'b' + i" :class="['br', b.kind]">
            <template v-if="b.out"><line :x1="SX - 19" :x2="SX - 70" :y1="b.y0" :y2="b.y0" marker-end="url(#ah)" /><text :x="SX - 76" :y="b.y0 + 4" text-anchor="end" class="blabel">{{ cut(b.label, 32) }}<title>{{ b.label }}</title></text></template>
            <template v-else><path :d="b.d" marker-end="url(#ah)" /><text :x="b.lx" :y="b.ly" text-anchor="end" class="blabel">{{ cut(b.label, 24) }}<title>{{ b.label }}</title></text></template>
          </g>
          <g v-for="s in r.steps" :key="s.id" class="step" :class="{ on: sel === s.id }" :transform="`translate(${SX},${ys[s.seq]})`" @click="choose(s)">
            <rect x="-26" y="-26" width="600" height="52" rx="8" class="hit" />
            <circle v-if="s.kind === 'operation'" r="18" class="shape" />
            <rect v-else-if="s.kind === 'inspection'" x="-17" y="-17" width="34" height="34" class="shape" />
            <path v-else-if="s.kind === 'move'" d="M-20,-9 H4 V-17 L20,0 L4,17 V9 H-20 Z" class="shape" />
            <path v-else-if="s.kind === 'store'" d="M-19,-16 H19 L0,17 Z" class="shape" />
            <path v-else d="M-16,-16 H2 A16,16 0 0 1 2,16 H-16 Z" class="shape" />
            <text x="34" y="-2" class="sname"><tspan class="scode">{{ s.code }}</tspan> {{ s.name }}</text>
            <text x="34" y="17" class="slinks">{{ t(r.kinds[s.kind]) }}<tspan v-for="k in linkKeys(s)" :key="k" :class="linkState(k).ok ? (linkState(k).warn ? 'warn' : '') : 'bad'"> · {{ short(k) }}{{ linkState(k).ok ? (linkState(k).warn ? ` (${linkState(k).warn})` : '') : ' (!)' }}</tspan></text>
          </g>
        </svg>
        <p class="px-3 pb-1 text-xs text-ink-gray-5">{{ draft ? t('○ operation · □ inspection · ➜ move · ▽ storage · D wait. Click a step to see it and change it.') : t('○ operation · □ inspection · ➜ move · ▽ storage · D wait. Click a step to see it.') }}</p>
      </section>

      <section data-help="flow-step" class="editor wq-panel h-fit min-w-0 p-5">
        <template v-if="draft">
          <div class="mb-3 flex items-center gap-2"><h3 class="font-semibold text-ink-gray-9">{{ sel ? t('Step {n}', { n: current?.code || current?.seq }) : t('Add a step') }}</h3>
            <template v-if="sel"><Button size="sm" variant="ghost" icon="lucide-arrow-up" @click="move('up')" /><Button size="sm" variant="ghost" icon="lucide-arrow-down" @click="move('down')" />
              <Button size="sm" variant="ghost" :label="t('New step')" class="ml-auto" @click="fresh" /></template></div>
          <form class="grid gap-3" @submit.prevent="save">
            <div class="grid grid-cols-[5rem_1fr] gap-2"><label class="wq-field">{{ t('No.') }}<input v-model="step.code" class="wq-input" placeholder="10"></label>
              <label class="wq-field">{{ t('Kind') }}<select v-model="step.kind" class="wq-select"><option v-for="(l, k) in r.kinds" :key="k" :value="k">{{ t(l) }}</option></select></label></div>
            <label class="wq-field">{{ t('Name') }}<input v-model="step.name" class="wq-input"></label>
            <label class="wq-field">{{ t('Description') }}<textarea v-model="step.description" rows="2" class="wq-input" /></label>
            <fieldset class="grid gap-2"><legend class="mb-1 text-sm text-ink-gray-7">{{ t('Branches') }}</legend>
              <div v-for="(b, i) in step.branches" :key="i" class="grid grid-cols-[1fr_6rem_auto] gap-1">
                <select v-model="b.to" class="wq-select"><option value="">{{ t('leaves the flow') }}</option><option v-for="s in r.steps.filter((y) => y.id !== sel)" :key="s.seq" :value="s.seq">{{ t('to {step}', { step: `${s.code || s.seq} ${s.name}` }) }}</option></select>
                <select v-model="b.kind" class="wq-select"><option value="rework">{{ t('rework') }}</option><option value="scrap">{{ t('scrap') }}</option><option value="other">{{ t('other') }}</option></select>
                <Button size="sm" variant="ghost" icon="lucide-x" @click="step.branches.splice(i, 1)" />
                <input v-model="b.label" class="wq-input col-span-3" :placeholder="t('when, e.g. Light kit: count again')"></div>
              <div><Button size="sm" :label="t('Add a branch')" @click="step.branches.push({ to: '', kind: 'rework', label: '' })" /></div></fieldset>
            <fieldset v-if="opts" class="grid gap-2"><legend class="mb-1 text-sm text-ink-gray-7">{{ t('Links') }}</legend>
              <div v-for="[k, label, list, val, text] in [['documents', 'Documents in effect', opts.documents, (d) => d.number, (d) => `${d.number} ${d.title || ''}`],
                                                       ['fmea', 'PFMEA rows', opts.fmea, (m) => `${m.name}#${m.seq}`, (m) => t('{name} row {seq}: {mode}', { name: m.name, seq: m.seq, mode: m.failure_mode })],
                                                       ['gauges', 'Measuring equipment', opts.gauges, (g) => g.code, (g) => `${g.code} ${g.name}`]]" :key="k">
                <label class="wq-field">{{ t(label) }}<select v-model="pick[k]" class="wq-select" @change="add(k)"><option value="">{{ t('Add…') }}</option><option v-for="o in list" :key="val(o)" :value="val(o)">{{ text(o) }}</option></select></label>
                <p class="mt-1 flex flex-wrap gap-1"><button v-for="v in step.links[k]" :key="v" type="button" class="chip" @click="drop(k, v)">{{ rowText(v) }} ×</button></p>
              </div>
              <label class="wq-field">{{ t('Incoming inspection plan') }}<select v-model="step.links.plan" class="wq-select"><option value="" /><option v-for="p in opts.plans" :key="p">{{ p }}</option></select></label>
              <label class="wq-field">{{ t('Production template') }}<select v-model="step.links.template" class="wq-select"><option value="" /><option v-for="tp in opts.templates" :key="tp.code" :value="tp.code">{{ tp.code }} {{ tp.title }}</option></select></label>
            </fieldset>
            <div class="flex gap-2"><Button type="submit" variant="solid" :label="sel ? t('Save the step') : t('Add the step')" :disabled="busy || !step.name.trim()" />
              <Button v-if="sel" variant="ghost" theme="red" :label="t('Remove')" @click="remove" /></div>
          </form>
        </template>
        <template v-else-if="current">
          <h3 class="mb-1 font-semibold text-ink-gray-9">{{ current.code }} {{ current.name }}</h3>
          <p class="mb-2 text-sm text-ink-gray-5">{{ r.kinds[current.kind] }}</p>
          <p v-if="current.description" class="mb-3 text-sm">{{ current.description }}</p>
          <ul class="flex flex-col gap-1.5 text-sm">
            <li v-for="k in linkKeys(current)" :key="k"><RouterLink v-if="linkState(k).url" :to="linkState(k).url" class="wq-link">{{ linkState(k).label }}</RouterLink><span v-else>{{ short(k) }}</span>
              <span v-if="!linkState(k).ok" class="text-ink-red-7"> {{ linkState(k).why }}</span><span v-else-if="linkState(k).warn" class="text-ink-amber-7"> {{ linkState(k).warn }}</span></li>
            <li v-if="!linkKeys(current).length" class="wq-muted">{{ t('No links.') }}</li>
          </ul>
          <ul v-if="current.branches.length" class="mt-3 text-sm"><li v-for="(b, i) in current.branches" :key="i">{{ t(b.kind) }}: {{ b.label }} → {{ b.to == null ? t('leaves the flow') : r.steps.find((y) => y.seq === b.to)?.name }}</li></ul>
        </template>
        <p v-else class="wq-muted">{{ t('Click a step in the drawing.') }}</p>
      </section>
    </div>

    <section v-if="r.not_analysed.length" class="mb-5 text-sm text-ink-gray-6"><b class="text-ink-gray-8">{{ t('No PFMEA row linked yet:') }}</b> {{ r.not_analysed.join(', ') }}.</section>

    <section v-if="r.status === 'draft' || (r.status === 'approved' && r.can_edit)" data-help="flow-approve" class="wq-panel mb-5 max-w-3xl p-5">
      <template v-if="r.status === 'draft'">
        <h3 class="mb-2 text-base font-semibold text-ink-gray-9">{{ t('Approve') }}</h3>
        <ul v-if="r.to_approve.length" class="mb-3 list-disc ps-5 text-sm text-ink-gray-6"><li v-for="a in r.to_approve" :key="a">{{ a }}</li></ul>
        <div v-if="r.can_configure" class="flex flex-wrap items-end gap-2">
          <input v-model="x.password" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
          <Button variant="solid" :label="t('Approve (sign)')" :disabled="!x.password || !!r.to_approve.length || !!Object.keys(changed()).length" @click="call(`/api/flow/charts/${r.id}/approve`, 'POST', { password: x.password }, t('Approved: the flow chart is fixed now.')).then(() => { x.password = '' })" />
        </div>
        <p class="mt-2 text-sm text-ink-gray-5">{{ t('Approved by someone who does not own and did not edit it. What each link points to is checked again and kept.') }}</p>
        <details v-if="r.can_edit" class="mt-3"><summary class="cursor-pointer text-sm text-ink-gray-7">{{ t('Withdraw the draft') }}</summary>
          <div class="mt-2 flex gap-2"><input v-model="x.reason" class="wq-input w-80" :placeholder="t('Why')"><Button :label="t('Withdraw')" :disabled="!x.reason.trim()" @click="call(`/api/flow/charts/${r.id}/withdraw`, 'POST', { reason: x.reason }, t('Withdrawn.'))" /></div></details>
      </template>
      <template v-else><h3 class="mb-2 text-base font-semibold text-ink-gray-9">{{ t('Change it') }}</h3><p class="mb-3 text-sm text-ink-gray-6">{{ t('An approved flow chart is fixed. A new version starts as a copy; approving it supersedes this one.') }}</p><Button :label="t('Start a new version')" @click="revise" /></template>
    </section>

    <p v-if="r.fingerprint" class="mb-4 text-xs text-ink-gray-5">{{ t('Fingerprint {fp}', { fp: r.fingerprint }) }}</p>
    <h2 class="wq-h2 mt-6">{{ t('Versions') }}</h2>
    <ul class="mb-4 text-sm"><li v-for="ver in r.versions" :key="ver.id"><RouterLink :to="`/quality/flow/${ver.id}`" class="hover:underline">v{{ ver.version }}</RouterLink> · {{ t(ver.status) }}<span v-if="ver.approved_by"> · {{ ver.approved_by }} {{ ver.approved_at?.slice(0, 10) }}</span></li></ul>
    <h2 class="wq-h2 mt-6">{{ t('Signatures') }}</h2>
    <Trail :items="r.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
    <Trail :items="r.history" />
  </template>
</template>

<style scoped>
.flow { width: 100%; min-width: 640px; height: auto; }
.main { stroke: var(--ink-gray-6); stroke-width: 1.6; }
.ahead { fill: var(--ink-gray-6); }
.br path, .br line { fill: none; stroke-width: 1.6; stroke-dasharray: 5 4; }
.br.rework path, .br.rework line { stroke: var(--warn); }
.br.scrap path, .br.scrap line { stroke: var(--critical); }
.br.other path, .br.other line { stroke: var(--ink-gray-5); }
.blabel { font-size: 13px; fill: var(--ink-gray-6); }
.step { cursor: pointer; }
.hit { fill: transparent; }
.step:hover .hit, .step.on .hit { fill: var(--surface-gray-1); }
.shape { fill: var(--panel); stroke: var(--ink-gray-8); stroke-width: 2; }
.step:hover .shape { fill: var(--surface-gray-2); }
.step.on .shape { fill: var(--surface-gray-3); stroke-width: 3; }
.sname { font-size: 18px; fill: var(--ink-gray-9); font-weight: 500; }
.scode { fill: var(--ink-gray-5); font-variant-numeric: tabular-nums; }
.slinks { font-size: 13px; fill: var(--ink-gray-5); }
.slinks .bad { fill: var(--critical); }
.slinks .warn { fill: var(--warn); }
.editor :is(input, select, textarea) { width: 100%; min-width: 0; box-sizing: border-box; }
.editor label, .editor fieldset, .editor form > * { min-width: 0; }
.chip { font-size: .78rem; border: 1px solid var(--line); border-radius: 999px; padding: 0 .5rem; color: var(--ink-gray-8); }
.chip:hover { border-color: var(--critical); color: var(--critical); }
</style>
