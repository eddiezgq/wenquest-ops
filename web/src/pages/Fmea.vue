<script setup>
// Process FMEA (ADR-0022, 22c): the PFMEAs, and the company's own criteria: severity, occurrence and detection scales
// in its own words, and its rule for when a row needs action. RPN is computed, never typed.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'

const router = useRouter()
const v = ref(null)
const error = ref('')
const done = ref('')
const status = ref('current')
const show = ref(false)
const f = ref({ process: '', item_code: '', scope: '', owner: '' })
const sc = ref({ kind: 'severity', rank: '', name: '', description: '' })
const rule = ref(null)
const KINDS = { severity: 'Severity (S)', occurrence: 'Occurrence (O)', detection: 'Detection (D)' }
const ST = { draft: 'gray', approved: 'green', superseded: 'gray', withdrawn: 'gray' }

async function load() {
  try { v.value = await api(`/api/fmea?status=${status.value}`); if (!rule.value) resetRule() } catch (e) { error.value = e.message }
}
watch(status, load, { immediate: true })
function resetRule() {
  const r = v.value?.rule
  rule.value = r ? JSON.parse(JSON.stringify({ ...r, severity_action: r.severity_action ?? '' }))
    : { method: 'rpn', rpn_action: '', severity_action: '', rules: [], needs_action: ['high'] }
}
const byKind = computed(() => Object.fromEntries(Object.keys(KINDS).map((k) => [k, (v.value?.scales || []).filter((s) => s.kind === k).sort((a, b) => a.rank - b.rank)])))

async function call(path, method, body, msg) {
  error.value = ''; done.value = ''
  try { const r = await api(path, { method, body }); done.value = msg || ''; await load(); return r } catch (e) { error.value = e.message }
}
async function create() {
  error.value = ''
  try { const r = await api('/api/fmea/files', { method: 'POST', body: f.value }); router.push(`/quality/fmea/${r.id}`) } catch (e) { error.value = e.message }
}
async function addScale() {
  if (await call('/api/fmea/scales', 'POST', { ...sc.value, rank: Number(sc.value.rank) }, 'Rank added.')) sc.value = { kind: sc.value.kind, rank: '', name: '', description: '' }
}
const changeScale = (s, body) => call(`/api/fmea/scales/${s.id}`, 'PUT', body)
function saveRule() {
  const r = rule.value
  const body = r.method === 'rpn'
    ? { method: 'rpn', rpn_action: Number(r.rpn_action) || null, severity_action: r.severity_action === '' ? null : Number(r.severity_action) }
    : { method: 'lookup', needs_action: r.needs_action, rules: r.rules.map((x) => ({ priority: x.priority, s: x.s.map(Number), o: x.o.map(Number), d: x.d.map(Number) })) }
  return call('/api/fmea/rule', 'PUT', body, 'The rule is saved. PFMEAs approved before keep the rule they were approved with.').then((ok) => { if (ok) { rule.value = null; resetRule() } })
}
const addRange = () => rule.value.rules.push({ s: [1, 10], o: [1, 10], d: [1, 10], priority: 'low' })
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality', to: '/quality' }]">
    <template #title>Process FMEA</template>
    <Button v-if="v?.can_edit" variant="solid" icon-left="lucide-plus" label="New PFMEA" @click="show = !show" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <form v-if="show" class="wq-panel mb-5 grid gap-3 p-5 md:grid-cols-3" @submit.prevent="create">
    <label class="wq-field md:col-span-2">Process (and the product it makes)<input v-model="f.process" class="wq-input"></label>
    <label class="wq-field">Item code<input v-model="f.item_code" class="wq-input" placeholder="the item it makes, if one"></label>
    <label class="wq-field md:col-span-2">Scope<input v-model="f.scope" class="wq-input"></label>
    <label class="wq-field">Owner<select v-model="f.owner" class="wq-select"><option value="" /><option v-for="p in v?.people" :key="p">{{ p }}</option></select></label>
    <div><Button type="submit" variant="solid" label="Start" :disabled="!f.process.trim()" /></div>
  </form>

  <template v-if="v">
    <section data-help="fmea-files" class="wq-panel mb-5 p-5">
      <div class="mb-3"><select v-model="status" class="wq-select w-40"><option value="current">Current</option><option value="draft">Drafts</option><option value="approved">Approved</option><option value="all">All versions</option></select></div>
      <p v-if="!v.files.length" class="wq-muted">None.</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>Number</th><th>Version</th><th>Process</th><th>Item</th><th>Status</th><th>Rows</th><th>Approved</th><th>Reports since</th></tr></thead>
        <tbody><tr v-for="r in v.files" :key="r.id">
          <td><RouterLink :to="`/quality/fmea/${r.id}`" class="wq-link font-medium">{{ r.name }}</RouterLink></td>
          <td>{{ r.version }}</td><td>{{ r.process }}</td><td>{{ r.item_code || '' }}</td><td><Badge :theme="ST[r.status]" :label="r.status" /></td>
          <td>{{ r.rows }}</td><td>{{ r.approved_at ? `${r.approved_at.slice(0, 10)} · ${r.approved_by}` : '' }}</td>
          <td><span v-if="r.ncrs_since" class="text-ink-amber-7">{{ r.ncrs_since }}</span></td></tr></tbody></table>
    </section>

    <section data-help="fmea-criteria" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">The company's FMEA criteria</h2>
      <p class="wq-muted mb-4 max-w-3xl">Your own words for each rank, 1 to 10, and your own rule for when a row needs action. Set them to what your
        procedure says; nothing here is taken from a standard. An approved PFMEA keeps the criteria it was approved with.</p>
      <div class="scales mb-5 grid gap-4 lg:grid-cols-3">
        <div v-for="(label, k) in KINDS" :key="k">
          <h3 class="mb-2 font-semibold text-ink-gray-9">{{ label }}</h3>
          <p v-if="!byKind[k].length" class="text-sm text-ink-amber-7">No ranks yet.</p>
          <ol class="flex flex-col gap-1 text-sm">
            <li v-for="s in byKind[k]" :key="s.id" class="flex items-center gap-2" :class="{ 'opacity-50': !s.active }">
              <span class="w-6 text-right font-semibold tabular-nums text-ink-gray-8">{{ s.rank }}</span>
              <input v-if="v.can_configure" class="wq-input flex-1" :value="s.name" @change="changeScale(s, { name: $event.target.value })"><span v-else class="flex-1">{{ s.name }}</span>
              <input type="checkbox" :checked="s.active" :disabled="!v.can_configure" :title="s.active ? 'In use' : 'Not in use'" @change="changeScale(s, { active: $event.target.checked })">
            </li>
          </ol>
        </div>
      </div>
      <form v-if="v.can_configure" class="mb-6 flex flex-wrap items-end gap-2" @submit.prevent="addScale">
        <label class="wq-field">Scale<select v-model="sc.kind" class="wq-select"><option v-for="(l, k) in KINDS" :key="k" :value="k">{{ l }}</option></select></label>
        <label class="wq-field w-20">Rank<input v-model="sc.rank" type="number" min="1" max="10" class="wq-input"></label>
        <label class="wq-field grow">What it means in your company<input v-model="sc.name" class="wq-input"></label>
        <Button type="submit" label="Add rank" :disabled="!sc.rank || !sc.name.trim()" />
      </form>

      <h3 data-help="fmea-rule" class="mb-2 font-semibold text-ink-gray-9">When a row needs action</h3>
      <p v-if="!v.rule" class="mb-2 text-sm text-ink-amber-7">No rule yet: no PFMEA can be approved until there is one.</p>
      <template v-if="rule">
        <div class="mb-3 flex flex-wrap gap-4 text-sm">
          <label class="flex items-center gap-1.5"><input v-model="rule.method" type="radio" value="rpn" :disabled="!v.can_configure"> RPN threshold</label>
          <label class="flex items-center gap-1.5"><input v-model="rule.method" type="radio" value="lookup" :disabled="!v.can_configure"> Lookup table of S / O / D ranges</label>
        </div>
        <div v-if="rule.method === 'rpn'" class="mb-3 flex flex-wrap items-end gap-3 text-sm">
          <label class="wq-field w-48">Action when RPN is at least<input v-model="rule.rpn_action" type="number" min="1" max="1000" class="wq-input" :disabled="!v.can_configure"></label>
          <label class="wq-field w-56">…or severity is at least (optional)<input v-model="rule.severity_action" type="number" min="1" max="10" class="wq-input" :disabled="!v.can_configure"></label>
        </div>
        <div v-else class="mb-3 overflow-x-auto">
          <table class="wq-table w-auto text-sm"><thead><tr><th>S from–to</th><th>O from–to</th><th>D from–to</th><th>Priority</th><th /></tr></thead>
            <tbody><tr v-for="(x, i) in rule.rules" :key="i">
              <td v-for="key in ['s', 'o', 'd']" :key="key" class="whitespace-nowrap"><input v-model="x[key][0]" type="number" min="1" max="10" class="wq-input w-16" :disabled="!v.can_configure"> – <input v-model="x[key][1]" type="number" min="1" max="10" class="wq-input w-16" :disabled="!v.can_configure"></td>
              <td><select v-model="x.priority" class="wq-select" :disabled="!v.can_configure"><option v-for="p in v.priorities" :key="p">{{ p }}</option></select></td>
              <td><Button v-if="v.can_configure" size="sm" variant="ghost" label="Remove" @click="rule.rules.splice(i, 1)" /></td></tr></tbody></table>
          <div class="mt-2 flex flex-wrap items-center gap-4 text-sm">
            <Button v-if="v.can_configure" size="sm" label="Add a range" @click="addRange" />
            <span>Needs action:</span>
            <label v-for="p in v.priorities" :key="p" class="flex items-center gap-1"><input v-model="rule.needs_action" type="checkbox" :value="p" :disabled="!v.can_configure"> {{ p }}</label>
          </div>
          <p class="mt-2 text-sm text-ink-gray-6">The first range that matches decides. A combination no range matches is not determined, and a PFMEA with such a row cannot be approved.</p>
          <p v-if="v.rule?.method === 'lookup' && v.lookup_gaps" class="mt-1 text-sm text-ink-amber-7">The saved table leaves {{ v.lookup_gaps }} of 1,000 combinations undecided.</p>
        </div>
        <Button v-if="v.can_configure" label="Save the rule" @click="saveRule" />
      </template>
      <details class="mt-4"><summary class="cursor-pointer text-sm text-ink-gray-7">Changes to the criteria</summary><Trail :items="v.criteria_history" /></details>
    </section>
  </template>
</template>
