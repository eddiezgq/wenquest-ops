<script setup>
// Quality (ADR-0009): nonconformance reports, corrective actions, incoming inspection, supplier scores, SPC.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { STATUS, label } from '../ui/themes'
import { api, objectPath } from '../api'
import { ago, fmt } from '../format'
import ControlChart from '../components/ControlChart.vue'
import Workflow from '../components/Workflow.vue'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const tab = computed({ get: () => route.query.tab || 'ncrs', set: (t) => router.replace({ query: { tab: t } }) })
const canEdit = computed(() => ws.value?.user.permissions.includes('quality:edit'))
const error = ref('')
const rows = ref([])
const filter = ref('active')
const scores = ref(null)
const flows = ref(null)
const params = ref([])
const pick = ref(null)
const spc = ref(null)
const sample = ref({})
const form = ref({ title: '', description: '', severity: 'minor', item_code: '', supplier: '', quantity: '' })
const showNew = ref(false)

async function load() {
  error.value = ''
  try {
    if (tab.value === 'ncrs') rows.value = await api(`/api/quality/ncrs?status=${filter.value}`)
    if (tab.value === 'capas') rows.value = await api(`/api/quality/capas?status=${filter.value}`)
    if (tab.value === 'incoming') rows.value = await api('/api/quality/incoming')
    if (tab.value === 'suppliers') scores.value = await api('/api/quality/suppliers')
    if (tab.value === 'workflows') flows.value = await api('/api/quality/workflows')
    if (tab.value === 'spc') {
      // the hub's own readings (signed incoming inspections, production measurements) and ERPNext quality inspections
      const [hub, erp] = await Promise.all([api('/api/quality/measurements/parameters'), api('/api/quality/spc/parameters')])
      params.value = [...hub, ...erp.map((p) => ({ ...p, source: 'erpnext' }))]
      if (!pick.value && params.value[0]) pick.value = params.value[0]
    }
  } catch (e) { error.value = e.message }
}
watch([tab, filter], load, { immediate: true })
let asked = 0
watch(pick, async (p) => {
  const mine = ++asked                          // a slower earlier answer does not replace a newer one
  const q = p && `item_code=${encodeURIComponent(p.item_code)}&parameter=${encodeURIComponent(p.parameter)}`
  try {
    const out = !p ? null : p.source === 'erpnext' ? await api(`/api/quality/spc?${q}`)
      : await api(`/api/quality/measurements/spc?source=${p.source}&${q}`)
    if (mine === asked) spc.value = out
  } catch (e) { if (mine === asked) { spc.value = null; error.value = e.message } }
})
const SOURCES = { incoming: 'incoming inspections', production: 'production lots', erpnext: 'ERPNext inspections' }
async function spcNcr() {                       // a broken rule is a reason to look: someone opens the report
  error.value = ''
  const p = pick.value
  const body = { title: `${p.parameter} of ${p.item_code} out of statistical control`, item_code: p.item_code, severity: 'minor',
    description: `Control chart of ${p.parameter} (${SOURCES[p.source]}): ` + spc.value.signals.map((s) => `rule ${s.rule}, ${s.text}`).join('; ') }
  try { const n = await api('/api/quality/ncrs', { method: 'POST', body }); router.push(`/quality/ncr/${n.id}`) } catch (e) { error.value = e.message }
}
async function newNcr() {
  error.value = ''
  const body = Object.fromEntries(Object.entries(form.value).filter(([, v]) => v !== ''))
  if (body.quantity) body.quantity = Number(body.quantity)
  try { const n = await api('/api/quality/ncrs', { method: 'POST', body }); router.push(`/quality/ncr/${n.id}`) }
  catch (e) { error.value = e.message }
}
async function draftInspection(x) {
  error.value = ''
  try {
    await api('/api/quality/incoming/draft', { method: 'POST', body: { receipt: x.receipt, item_code: x.item_code, sample_size: Number(sample.value[x.receipt + x.item_code]) } })
    router.push('/drafts')
  } catch (e) { error.value = e.message }
}
const TABS = { ncrs: 'Nonconformances', capas: 'Corrective actions', incoming: 'Incoming inspection', suppliers: 'Supplier quality', spc: 'SPC', workflows: 'Workflows' }
const r3 = (v) => (v === null || v === undefined ? 'unknown' : v.toFixed(2))
</script>

<template>
  <PageTop title="Quality">
    <Button v-if="tab === 'ncrs' && canEdit" data-help="ncr-new" variant="solid" icon-left="lucide-plus" label="New nonconformance" @click="showNew = !showNew" />
  </PageTop>
  <nav data-help="quality-tabs" class="tabs -mt-2 mb-5 flex gap-5 overflow-x-auto border-b border-outline-gray-2">
    <a v-for="(l, k) in TABS" :key="k" href="#" @click.prevent="tab = k"
       class="-mb-px whitespace-nowrap border-b-2 py-2.5 text-base transition-colors"
       :class="tab === k ? 'border-outline-gray-9 font-medium text-ink-gray-9' : 'border-transparent text-ink-gray-5 hover:text-ink-gray-8'">{{ l }}</a>
  </nav>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>

  <template v-if="tab === 'ncrs' || tab === 'capas'">
    <form v-if="showNew && tab === 'ncrs'" data-help="ncr-form" class="form wq-panel mb-5 grid gap-3 p-5" @submit.prevent="newNcr">
      <h2 class="text-base font-semibold text-ink-gray-9">New nonconformance</h2>
      <input v-model="form.title" class="wq-input" placeholder="Title" required>
      <textarea v-model="form.description" class="wq-textarea" rows="3" placeholder="What is wrong, how many, where found" required></textarea>
      <div class="grid gap-3 sm:grid-cols-4">
        <select v-model="form.severity" class="wq-select"><option value="minor">Minor</option><option value="major">Major (needs a corrective action)</option></select>
        <input v-model="form.item_code" class="wq-input" placeholder="Item code (optional)">
        <input v-model="form.supplier" class="wq-input" placeholder="Supplier (optional)">
        <input v-model="form.quantity" class="wq-input" type="number" min="0" step="any" placeholder="Quantity">
      </div>
      <div><Button type="submit" variant="solid" label="Open the report" /></div>
    </form>
    <div class="mb-3 flex items-center gap-2">
      <span class="wq-muted">Show</span>
      <select v-model="filter" class="wq-select" aria-label="Show"><option value="active">Open</option><option value="closed">Closed</option>
        <option v-if="tab === 'ncrs'" value="cancelled">Cancelled</option><option value="all">All</option></select>
    </div>
    <p v-if="!rows.length" class="wq-muted">None.</p>
    <div v-else data-help="quality-list" class="wq-panel overflow-x-auto">
      <table class="wq-table">
        <thead><tr><th>Number</th><th>Title</th><th>{{ tab === 'ncrs' ? 'Severity' : 'Kind' }}</th><th>Status</th><th>Owner</th><th>Opened</th></tr></thead>
        <tbody><tr v-for="r in rows" :key="r.id">
          <td class="whitespace-nowrap"><RouterLink :to="`/quality/${tab === 'ncrs' ? 'ncr' : 'capa'}/${r.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ r.name }}</RouterLink></td>
          <td>{{ r.title }}</td>
          <td class="capitalize">{{ tab === 'ncrs' ? (r.severity || 'unknown') : r.kind }}</td>
          <td><Badge :theme="STATUS[r.status] || 'gray'" :label="label(r.status)" /></td>
          <td class="text-sm text-ink-gray-6">{{ r.owner }}</td><td class="whitespace-nowrap text-sm text-ink-gray-5">{{ ago(r.created_at) }}</td></tr></tbody>
      </table>
    </div>
  </template>

  <template v-if="tab === 'incoming'">
    <p class="wq-muted mb-3">Receipts of items marked "inspect on receipt" in ERPNext that have no inspection yet. A draft inspection goes to Drafts for Quality to confirm; it is then created in ERPNext.
      To sample a lot by plan, with readings, a signed result and switching between normal, tightened and reduced inspection, use
      <RouterLink to="/quality/iqc" class="wq-link">Incoming inspection</RouterLink>.</p>
    <p v-if="!rows.length" class="wq-muted">Nothing waiting.</p>
    <div v-else data-help="incoming-receipts" class="wq-panel overflow-x-auto">
      <table class="wq-table">
        <thead><tr><th>Receipt</th><th>Item</th><th>Qty</th><th>Supplier</th><th>Received</th><th v-if="canEdit">Inspect</th></tr></thead>
        <tbody><tr v-for="x in rows" :key="x.receipt + x.item_code">
          <td><RouterLink :to="objectPath('PurchaseReceipt', x.receipt)" class="wq-link">{{ x.receipt }}</RouterLink>
            <Badge v-if="x.draft" theme="amber" label="draft, waiting for inspection" class="ms-2" /></td>
          <td><RouterLink :to="objectPath('Item', x.item_code)" class="wq-link">{{ x.item_code }}</RouterLink></td><td>{{ fmt(x.qty) }}</td>
          <td>{{ x.supplier }}</td><td class="whitespace-nowrap">{{ x.received }}</td>
          <td v-if="canEdit"><div class="flex items-center gap-2">
            <input v-model="sample[x.receipt + x.item_code]" class="wq-input w-28" type="number" min="1" placeholder="Sample size">
            <Button :disabled="!(Number(sample[x.receipt + x.item_code]) > 0)" title="Enter the sample size first" label="Draft inspection" @click="draftInspection(x)" />
          </div></td></tr></tbody>
      </table>
    </div>
    <p v-if="rows.length && canEdit" class="wq-muted mt-2">Enter how many pieces you will inspect, then draft the inspection.</p>
  </template>

  <template v-if="tab === 'suppliers' && scores">
    <p class="wq-muted mb-3">{{ scores.period[0] }} to {{ scores.period[1] }}. Facts only: incoming lots inspected and rejected, on-time receipt lines,
      nonconformance reports, concessions (closed reports whose disposition needed approval) and open corrective actions.</p>
    <div data-help="supplier-scores" class="wq-panel overflow-x-auto">
      <table class="wq-table">
        <thead><tr><th>Supplier</th><th>Lots</th><th>Rejected</th><th>Rejection rate</th><th>On time</th><th>NCRs</th><th>Concessions</th><th>Open CAPAs</th></tr></thead>
        <tbody><tr v-for="s in scores.suppliers" :key="s.supplier">
          <td><RouterLink :to="objectPath('Supplier', s.supplier)" class="font-medium text-ink-gray-9 hover:underline">{{ s.name }}</RouterLink></td>
          <td>{{ s.lots }}</td><td>{{ s.rejected }}</td><td>{{ fmt(s.rejection_rate, '%') }}</td>
          <td>{{ fmt(s.on_time, '%') }} <span class="text-sm text-ink-gray-5">({{ s.on_time_lines }} lines)</span></td>
          <td>{{ s.ncrs }}</td><td>{{ s.concessions }}</td><td>{{ s.open_capas }}</td></tr></tbody>
      </table>
    </div>
  </template>

  <template v-if="tab === 'spc'">
    <p v-if="!params.length" class="wq-muted">No measured values yet. Signed incoming inspections, production measurements and ERPNext quality inspections show here.</p>
    <div v-else data-help="spc-pick" class="mb-4 flex flex-wrap items-center gap-2">
      <span class="wq-muted">Item and parameter</span>
      <select v-model="pick" class="wq-select" aria-label="Item and parameter"><option v-for="p in params" :key="p.source + '|' + p.item_code + '|' + p.parameter" :value="p">{{ p.item_code }} — {{ p.parameter }} ({{ p.inspections }} {{ SOURCES[p.source] }})</option></select>
    </div>
    <template v-if="spc">
      <p v-if="!spc.enough_data" class="wq-muted">{{ spc.note }}</p>
      <template v-else>
        <ControlChart data-help="spc-chart" :data="spc" />
        <div class="mt-4 grid gap-4 md:grid-cols-2">
          <section data-help="spc-signals" class="wq-panel p-4"><h3 class="mb-2 text-base font-semibold text-ink-gray-9">Signals</h3>
            <p v-if="!spc.signals.length" class="wq-muted">No rule broken.</p>
            <ul class="divide-y divide-outline-gray-1 text-sm">
              <li v-for="s in spc.signals" :key="s.index + '-' + s.rule" class="py-1.5 text-ink-gray-8">
                <Badge theme="red" :label="`Rule ${s.rule}`" class="me-2" />{{ s.text }}</li></ul>
            <Button v-if="spc.signals.length && canEdit" class="mt-3" size="sm" icon-left="lucide-triangle-alert" label="Open a nonconformance report" @click="spcNcr" /></section>
          <section data-help="spc-capability" class="wq-panel p-4"><h3 class="mb-2 text-base font-semibold text-ink-gray-9">Capability</h3>
            <p v-if="!spc.capability" class="wq-muted">{{ spc.capability_note || 'Unknown: needs both spec limits on the readings.' }}</p>
            <dl v-else class="grid grid-cols-3 gap-3">
              <div v-for="[k, v] in [['Cp', r3(spc.capability.Cp)], ['Cpk', r3(spc.capability.Cpk)], ['Pp', r3(spc.capability.Pp)],
                                       ['Ppk', r3(spc.capability.Ppk)], ['Values', spc.capability.n], ['Out of spec', spc.out_of_spec]]" :key="k"
                   class="rounded-4 bg-surface-gray-1 p-3">
                <dt class="text-sm text-ink-gray-5">{{ k }}</dt><dd class="m-0 text-xl font-semibold text-ink-gray-9">{{ v }}</dd></div>
            </dl>
            <p v-if="spc.capability && (spc.capability_note || spc.limits_note)" class="mt-2 text-sm text-ink-amber-8">{{ spc.capability_note || spc.limits_note }}</p></section>
        </div>
      </template>
    </template>
  </template>
  <template v-if="tab === 'workflows' && flows">
    <p class="wq-muted mb-4 max-w-3xl">How nonconformance reports and corrective actions move, step by step. The workflow is configuration: these
      are the rules WenQuest Ops checks before every step. Signing, approval by someone else and the record history cannot be switched off.</p>
    <Workflow v-for="(d, k) in flows" :key="k" :data="d" :kind="k" />
  </template>
</template>
