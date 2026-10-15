<script setup>
// Incoming inspection (ADR-0017, 17b): lots waiting and inspections, the inspection plans, the company's sampling
// table, and inspection levels with the switching rules. The judgement is code; people sign.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, objectPath } from '../api'
import { ago } from '../format'

const route = useRoute()
const router = useRouter()
const h = ref(null)
const error = ref('')
const done = ref('')
const busy = ref('')
const status = ref('open')
const tab = computed({ get: () => route.query.tab || 'inspections', set: (t) => router.replace({ query: { tab: t } }) })
const TABS = { inspections: 'Inspections', plans: 'Plans', table: 'Sampling table', levels: 'Inspection levels' }
const LEVEL = { normal: 'gray', tightened: 'red', reduced: 'green' }
const ST = { in_progress: { theme: 'gray', label: 'in progress' }, judged: { theme: 'amber', label: 'signed, to decide' },
  released: { theme: 'green', label: 'released' }, rejected: { theme: 'red', label: 'rejected' }, void: { theme: 'gray', label: 'void' } }
const manual = ref({ item_code: '', lot_qty: '', supplier: '', lot_no: '' })
const lotNo = ref({})
const row = ref({ aql: '', level: 'normal', lot_min: '', lot_max: '', n: '', ac: '' })
const source = ref({})
const plan = ref({ item_code: '', aql: '' })
const sw = ref({})
const rule = ref({ from_level: 'normal', to_level: 'tightened', condition: 'window_rejected', n: 5, k: 2 })

async function load() {
  error.value = ''
  try { h.value = await api(`/api/iqc?status=${status.value}`) } catch (e) { error.value = e.message }
}
watch(status, load, { immediate: true })
async function run(key, fn, message) {
  error.value = ''; done.value = ''; busy.value = key
  try { await fn(); done.value = message; await load() } catch (e) { error.value = e.message } finally { busy.value = '' }
}
const start = (body) => run('start', async () => {
  const r = await api('/api/iqc/inspections', { method: 'POST', body })
  router.push(`/quality/iqc/${r.id}`)
}, '')
const startLine = (x) => start({ item_code: x.item_code, receipt: x.receipt, lot_no: lotNo.value[x.receipt + x.item_code] || '' })
const startManual = () => start({ ...manual.value, lot_qty: Number(manual.value.lot_qty) })
const addRow = () => run('row', () => api('/api/iqc/rows', { method: 'POST',
  body: { ...row.value, aql: Number(row.value.aql), lot_min: Number(row.value.lot_min), lot_max: Number(row.value.lot_max), n: Number(row.value.n), ac: Number(row.value.ac) } }), 'Row added.')
const rowAction = (r, action) => run(`r${r.id}`, () => api(`/api/iqc/rows/${r.id}/${action}`, { method: 'POST', body: { source: source.value[r.id] || '' } }),
  action === 'check' ? 'Marked as checked.' : action === 'archive' ? 'Archived.' : 'In use again.')
const newPlan = () => run('plan', async () => {
  const p = await api('/api/iqc/plans', { method: 'POST', body: { item_code: plan.value.item_code, aql: Number(plan.value.aql),
    characteristics: [] } })
  router.push(`/quality/iqc/plans/${p.id}`)
}, '')
const key = (x) => `${x.supplier}|${x.item_code}`
const doSwitch = (x) => run(key(x), () => api('/api/iqc/levels', { method: 'POST',
  body: { supplier: x.supplier, item_code: x.item_code, to_level: sw.value[key(x)]?.to, reason: sw.value[key(x)]?.reason || '' } }), 'Level switched.')
const saveRule = (r) => run(`rule${r.id || 'new'}`, () => api('/api/iqc/rules', { method: 'POST',
  body: { ...r, n: r.n === '' || r.n === null ? null : Number(r.n), k: r.k === '' || r.k === null ? null : Number(r.k) } }), 'Rule saved.')
const setting = (k, v) => run(k, () => api('/api/iqc/settings', { method: 'POST', body: { key: k, value: v } }), 'Setting saved.')
const ruleText = (r) => h.value.conditions[r.condition].replace('K', r.k).replace('N', r.n)
function pickSwitch(x) { sw.value[key(x)] = { to: x.suggestion?.to || '', reason: '', open: !sw.value[key(x)]?.open } }
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality', to: '/quality' }]">
    <template #title>Incoming inspection</template>
  </PageTop>
  <nav class="tabs -mt-2 mb-5 flex gap-5 overflow-x-auto border-b border-outline-gray-2">
    <a v-for="(l, k) in TABS" :key="k" href="#" class="-mb-px whitespace-nowrap border-b-2 pb-2 text-base"
       :class="tab === k ? 'border-outline-gray-9 font-medium text-ink-gray-9' : 'border-transparent text-ink-gray-5 hover:text-ink-gray-8'" @click.prevent="tab = k">{{ l }}</a>
  </nav>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <template v-if="h && tab === 'inspections'">
    <section class="waiting wq-panel mb-5 p-5">
      <h2 class="wq-h2">Lots waiting</h2>
      <p class="wq-muted mb-3">Receipt lines of items to inspect on receipt. Items with a plan in use are sampled here: the sampling table gives n, Ac and Re
        for the lot size and the supplier's inspection level, and the result goes to ERPNext as a draft to confirm.</p>
      <p v-if="!h.waiting.length" class="wq-muted">Nothing waiting.</p>
      <div v-else class="overflow-x-auto"><table class="wq-table text-sm">
        <thead><tr><th>Receipt</th><th>Item</th><th>Qty</th><th>Supplier</th><th>Received</th><th v-if="h.can_edit" /></tr></thead>
        <tbody><tr v-for="x in h.waiting" :key="x.receipt + x.item_code">
          <td><RouterLink :to="objectPath('PurchaseReceipt', x.receipt)" class="wq-link">{{ x.receipt }}</RouterLink></td>
          <td>{{ x.item_code }}</td><td>{{ x.qty }}</td><td>{{ x.supplier }}</td><td class="whitespace-nowrap">{{ x.received }}</td>
          <td v-if="h.can_edit"><div v-if="x.plan" class="flex items-center gap-2">
            <input v-model="lotNo[x.receipt + x.item_code]" class="wq-input w-32" placeholder="Lot number">
            <Button size="sm" variant="solid" label="Start inspection" :loading="busy === 'start'" @click="startLine(x)" /></div>
            <span v-else class="text-ink-gray-5">no plan: <a href="#" class="wq-link" @click.prevent="plan.item_code = x.item_code; tab = 'plans'">make one</a></span></td>
        </tr></tbody></table></div>
      <details v-if="h.can_edit" class="mt-4">
        <summary class="cursor-pointer text-sm text-ink-gray-7">Inspect a lot that is not on a receipt</summary>
        <form class="mt-3 flex flex-wrap items-end gap-2" @submit.prevent="startManual">
          <label class="wq-field">Item<select v-model="manual.item_code" class="wq-select"><option value="" />
            <option v-for="p in h.plans.filter((p) => p.status === 'enabled')" :key="p.id" :value="p.item_code">{{ p.item_code }}</option></select></label>
          <label class="wq-field">Lot size<input v-model="manual.lot_qty" type="number" min="1" class="wq-input w-28"></label>
          <label class="wq-field">Supplier<input v-model="manual.supplier" class="wq-input w-44"></label>
          <label class="wq-field">Lot number<input v-model="manual.lot_no" class="wq-input w-32"></label>
          <Button type="submit" label="Start inspection" :disabled="!manual.item_code || !(Number(manual.lot_qty) > 0)" />
        </form>
      </details>
    </section>
    <section class="wq-panel p-5">
      <div class="mb-3 flex flex-wrap items-center gap-3"><h2 class="wq-h2 m-0">Inspections</h2>
        <select v-model="status" class="wq-select w-44"><option value="open">Open</option><option value="done">Released or rejected</option>
          <option value="void">Void</option><option value="all">All</option></select></div>
      <p v-if="!h.inspections.length" class="wq-muted">None.</p>
      <div v-else class="overflow-x-auto"><table class="wq-table text-sm">
        <thead><tr><th>Number</th><th>Item</th><th>Supplier</th><th>Lot</th><th>Level</th><th>n / Ac / Re</th><th>Status</th><th>Started</th></tr></thead>
        <tbody><tr v-for="i in h.inspections" :key="i.id">
          <td><RouterLink :to="`/quality/iqc/${i.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ i.name }}</RouterLink></td>
          <td>{{ i.item_code }}</td><td>{{ i.supplier }}</td><td>{{ i.lot_no }} <span class="text-ink-gray-5">({{ i.lot_qty }})</span></td>
          <td><Badge :theme="LEVEL[i.level]" :label="i.level" /></td><td>{{ i.n }} / {{ i.ac }} / {{ i.re }}</td>
          <td><Badge v-bind="ST[i.status]" /> <Badge v-if="i.unverified" theme="amber" label="table not checked" /></td>
          <td class="whitespace-nowrap">{{ ago(i.created_at) }}</td></tr></tbody></table></div>
    </section>
  </template>

  <template v-if="h && tab === 'plans'">
    <section v-if="h.can_edit" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">New plan</h2>
      <p class="wq-muted mb-3">A plan says what to check on an item and at which AQL. It is enabled with a password and then frozen; a change is a new version.</p>
      <form class="flex flex-wrap items-end gap-2" @submit.prevent="newPlan">
        <label class="wq-field">Item<select v-model="plan.item_code" class="wq-select w-56"><option value="" />
          <option v-for="it in h.items" :key="it.item_code" :value="it.item_code">{{ it.item_code }}{{ it.inspect ? ' (inspect on receipt)' : '' }}</option></select></label>
        <label class="wq-field">AQL<input v-model="plan.aql" class="wq-input w-24" inputmode="decimal"></label>
        <Button type="submit" variant="solid" label="Draft the plan" :disabled="!plan.item_code || !(Number(plan.aql) > 0)" :loading="busy === 'plan'" />
      </form>
    </section>
    <section class="wq-panel p-5">
      <p v-if="!h.plans.length" class="wq-muted">No plans yet.</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>Item</th><th>Version</th><th>AQL</th><th>Characteristics</th><th>Status</th><th>Enabled</th></tr></thead>
        <tbody><tr v-for="p in h.plans" :key="p.id">
          <td><RouterLink :to="`/quality/iqc/plans/${p.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ p.item_code }}</RouterLink></td>
          <td>{{ p.version }}</td><td>{{ p.aql }}</td><td>{{ p.characteristics.map((c) => c.name).join(', ') }}</td>
          <td><Badge :theme="p.status === 'enabled' ? 'green' : p.status === 'draft' ? 'amber' : 'gray'" :label="p.status" /></td>
          <td class="whitespace-nowrap">{{ p.enabled_by ? `${p.enabled_by} ${ago(p.enabled_at)}` : '' }}</td></tr></tbody></table>
    </section>
  </template>

  <template v-if="h && tab === 'table'">
    <section class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">The company's sampling table</h2>
      <p class="wq-muted mb-3">Enter the rows from your own controlled copy of the sampling standard you use. WenQuest Ops does not supply the numbers.
        A row is marked as checked once someone has compared it with the source; lots sampled with an unchecked row are flagged and need a reason to release.
        A row an inspection used cannot change: archive it and add a new one.</p>
      <form v-if="h.can_configure" class="mb-4 flex flex-wrap items-end gap-2" @submit.prevent="addRow">
        <label class="wq-field">AQL<input v-model="row.aql" class="wq-input w-20" inputmode="decimal"></label>
        <label class="wq-field">Level<select v-model="row.level" class="wq-select"><option>normal</option><option>tightened</option><option>reduced</option></select></label>
        <label class="wq-field">Lot from<input v-model="row.lot_min" type="number" min="1" class="wq-input w-24"></label>
        <label class="wq-field">to<input v-model="row.lot_max" type="number" min="1" class="wq-input w-24"></label>
        <label class="wq-field">n<input v-model="row.n" type="number" min="1" class="wq-input w-20"></label>
        <label class="wq-field">Ac<input v-model="row.ac" type="number" min="0" class="wq-input w-20"></label>
        <span class="pb-2 text-sm text-ink-gray-5">Re = Ac + 1</span>
        <Button type="submit" label="Add the row" :loading="busy === 'row'" />
      </form>
      <p v-if="!h.rows.length" class="wq-muted">No rows yet.</p>
      <div v-else class="overflow-x-auto"><table class="wq-table text-sm">
        <thead><tr><th>AQL</th><th>Level</th><th>Lot size</th><th>n</th><th>Ac</th><th>Re</th><th>Checked against</th><th /></tr></thead>
        <tbody><tr v-for="r in h.rows" :key="r.id" :class="r.active ? '' : 'text-ink-gray-4'">
          <td>{{ r.aql }}</td><td><Badge :theme="LEVEL[r.level]" :label="r.level" /></td><td>{{ r.lot_min }}–{{ r.lot_max }}</td>
          <td>{{ r.n }}</td><td>{{ r.ac }}</td><td>{{ r.re }}</td>
          <td><template v-if="r.verified_by">{{ r.source }} <span class="text-ink-gray-5">({{ r.verified_by }} {{ ago(r.verified_at) }})</span></template>
            <template v-else-if="h.can_configure && r.active"><div class="flex items-center gap-1">
              <input v-model="source[r.id]" class="wq-input w-56" placeholder="Standard, edition, table">
              <Button size="sm" label="Mark checked" :disabled="!(source[r.id] || '').trim()" @click="rowAction(r, 'check')" /></div></template>
            <Badge v-else theme="amber" label="not checked" /></td>
          <td class="whitespace-nowrap"><span v-if="r.used" class="me-2 text-ink-gray-5">used</span><span v-if="!r.active" class="me-2">archived</span>
            <Button v-if="h.can_configure" size="sm" variant="ghost" :label="r.active ? 'Archive' : 'Use again'" @click="rowAction(r, r.active ? 'archive' : 'restore')" /></td>
        </tr></tbody></table></div>
    </section>
  </template>

  <template v-if="h && tab === 'levels'">
    <section class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">Inspection level by supplier and item</h2>
      <p class="wq-muted mb-3">The rules below suggest a switch from the lots decided at the current level. A person switches, with a reason; the suggestion and the lots are kept with it.</p>
      <p v-if="!h.levels.length" class="wq-muted">No lots decided yet.</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>Supplier</th><th>Item</th><th>Level</th><th>Lots at this level</th><th>Suggestion</th><th /></tr></thead>
        <tbody><template v-for="x in h.levels" :key="key(x)"><tr>
          <td>{{ x.supplier }}</td><td>{{ x.item_code }}</td><td><Badge :theme="LEVEL[x.level]" :label="x.level" /></td>
          <td class="font-mono">{{ x.lots.map((r) => (r === 'accept' ? 'A' : 'R')).join(' ') || '–' }}</td>
          <td>{{ x.suggestion ? x.suggestion.reason : '' }}</td>
          <td><Button v-if="h.can_configure" size="sm" :variant="x.suggestion ? 'solid' : 'ghost'" label="Switch" @click="pickSwitch(x)" /></td></tr>
          <tr v-if="sw[key(x)]?.open"><td colspan="6"><div class="flex flex-wrap items-end gap-2">
            <label class="wq-field">To<select v-model="sw[key(x)].to" class="wq-select"><option value="" />
              <option v-for="l in ['normal', 'tightened', 'reduced'].filter((l) => l !== x.level)" :key="l">{{ l }}</option></select></label>
            <label class="wq-field">Reason<input v-model="sw[key(x)].reason" class="wq-input w-96"></label>
            <Button variant="solid" label="Switch" :disabled="!sw[key(x)].to || !sw[key(x)].reason.trim()" :loading="busy === key(x)" @click="doSwitch(x)" /></div></td></tr>
        </template></tbody></table>
    </section>
    <section class="rules wq-panel mb-5 p-5">
      <h2 class="wq-h2">Switching rules</h2>
      <p class="wq-muted mb-3">The starting rules are defaults: set them to what your procedure says. Rules are switched off, never deleted.</p>
      <table class="wq-table text-sm"><thead><tr><th>From</th><th>To</th><th>When</th><th>In use</th></tr></thead>
        <tbody><tr v-for="r in h.rules" :key="r.id" :class="r.active ? '' : 'text-ink-gray-4'">
          <td>{{ r.from_level }}</td><td>{{ r.to_level }}</td><td>{{ ruleText(r) }}</td>
          <td><input type="checkbox" class="form-checkbox" :checked="r.active" :disabled="!h.can_configure" @change="saveRule({ ...r, active: $event.target.checked })"></td></tr></tbody></table>
      <form v-if="h.can_configure" class="mt-3 flex flex-wrap items-end gap-2" @submit.prevent="saveRule(rule)">
        <label class="wq-field">From<select v-model="rule.from_level" class="wq-select"><option>normal</option><option>tightened</option><option>reduced</option></select></label>
        <label class="wq-field">To<select v-model="rule.to_level" class="wq-select"><option>normal</option><option>tightened</option><option>reduced</option></select></label>
        <label class="wq-field">When<select v-model="rule.condition" class="wq-select"><option v-for="(t, k) in h.conditions" :key="k" :value="k">{{ t }}</option></select></label>
        <label v-if="rule.condition !== 'any_rejected'" class="wq-field">N<input v-model="rule.n" type="number" min="1" class="wq-input w-20"></label>
        <label v-if="rule.condition === 'window_rejected'" class="wq-field">K<input v-model="rule.k" type="number" min="1" class="wq-input w-20"></label>
        <Button type="submit" label="Add the rule" />
      </form>
    </section>
    <section class="wq-panel p-5">
      <h2 class="wq-h2">Who may do what</h2>
      <label v-for="(label, k) in h.setting_labels" :key="k" class="mb-2 flex items-center gap-2 text-sm">
        <input type="checkbox" class="form-checkbox" :checked="h.settings[k]" :disabled="!h.can_configure || busy === k" @change="setting(k, $event.target.checked)">{{ label }}</label>
    </section>
  </template>
</template>
