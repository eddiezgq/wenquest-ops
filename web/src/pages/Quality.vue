<script setup>
// Quality (ADR-0009): nonconformance reports, corrective actions, incoming inspection, supplier scores, SPC.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, objectPath } from '../api'
import { ago, fmt } from '../format'
import ControlChart from '../components/ControlChart.vue'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const tab = computed({ get: () => route.query.tab || 'ncrs', set: (t) => router.replace({ query: { tab: t } }) })
const canEdit = computed(() => ws.value?.user.permissions.includes('quality:edit'))
const error = ref('')
const rows = ref([])
const filter = ref('active')
const scores = ref(null)
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
    if (tab.value === 'spc') { params.value = await api('/api/quality/spc/parameters'); if (!pick.value && params.value[0]) pick.value = params.value[0] }
  } catch (e) { error.value = e.message }
}
watch([tab, filter], load, { immediate: true })
watch(pick, async (p) => {
  spc.value = p ? await api(`/api/quality/spc?item_code=${encodeURIComponent(p.item_code)}&parameter=${encodeURIComponent(p.parameter)}`) : null
})
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
const TABS = { ncrs: 'Nonconformances', capas: 'Corrective actions', incoming: 'Incoming inspection', suppliers: 'Supplier scores', spc: 'SPC' }
const r3 = (v) => (v === null || v === undefined ? 'unknown' : v.toFixed(2))
</script>

<template>
  <h1>Quality</h1>
  <nav class="tabs"><a v-for="(l, k) in TABS" :key="k" href="#" :class="{ on: tab === k }" @click.prevent="tab = k">{{ l }}</a></nav>
  <p v-if="error" class="err">{{ error }}</p>

  <template v-if="tab === 'ncrs' || tab === 'capas'">
    <div class="head">
      <label class="muted">Show <select v-model="filter"><option value="active">Open</option><option value="closed">Closed</option>
        <option v-if="tab === 'ncrs'" value="cancelled">Cancelled</option><option value="all">All</option></select></label>
      <button v-if="tab === 'ncrs' && canEdit" @click="showNew = !showNew">New nonconformance</button>
    </div>
    <form v-if="showNew && tab === 'ncrs'" class="card form" @submit.prevent="newNcr">
      <input v-model="form.title" placeholder="Title" required>
      <textarea v-model="form.description" placeholder="What is wrong, how many, where found" required></textarea>
      <div class="row"><select v-model="form.severity"><option value="minor">Minor</option><option value="major">Major (needs a corrective action)</option></select>
        <input v-model="form.item_code" placeholder="Item code (optional)"><input v-model="form.supplier" placeholder="Supplier (optional)">
        <input v-model="form.quantity" type="number" min="0" step="any" placeholder="Quantity"></div>
      <button>Open the report</button>
    </form>
    <p v-if="!rows.length" class="muted">None.</p>
    <table v-else class="grid">
      <thead><tr><th>Number</th><th>Title</th><th>{{ tab === 'ncrs' ? 'Severity' : 'Kind' }}</th><th>Status</th><th>Owner</th><th>Opened</th></tr></thead>
      <tbody><tr v-for="r in rows" :key="r.id">
        <td><RouterLink :to="`/quality/${tab === 'ncrs' ? 'ncr' : 'capa'}/${r.id}`">{{ r.name }}</RouterLink></td>
        <td>{{ r.title }}</td><td>{{ tab === 'ncrs' ? r.severity : r.kind }}</td><td>{{ r.status.replace('_', ' ') }}</td>
        <td class="small">{{ r.owner }}</td><td class="small">{{ ago(r.created_at) }}</td></tr></tbody>
    </table>
  </template>

  <template v-if="tab === 'incoming'">
    <p class="muted small">Receipts of items marked "inspect on receipt" in ERPNext that have no inspection yet. A draft inspection goes to Drafts for Quality to confirm; it is then created in ERPNext.</p>
    <p v-if="!rows.length" class="muted">Nothing waiting.</p>
    <table v-else class="grid">
      <thead><tr><th>Receipt</th><th>Item</th><th>Qty</th><th>Supplier</th><th>Received</th><th></th></tr></thead>
      <tbody><tr v-for="x in rows" :key="x.receipt + x.item_code">
        <td><RouterLink :to="objectPath('PurchaseReceipt', x.receipt)">{{ x.receipt }}</RouterLink></td>
        <td><RouterLink :to="objectPath('Item', x.item_code)">{{ x.item_code }}</RouterLink></td><td>{{ fmt(x.qty) }}</td>
        <td>{{ x.supplier }}</td><td>{{ x.received }}</td>
        <td v-if="canEdit" class="row"><input v-model="sample[x.receipt + x.item_code]" type="number" min="1" placeholder="Sample size" style="width:7rem">
          <button @click="draftInspection(x)">Draft inspection</button></td></tr></tbody>
    </table>
  </template>

  <template v-if="tab === 'suppliers' && scores">
    <p class="muted small">{{ scores.period[0] }} to {{ scores.period[1] }}. Score = {{ scores.weights.lot_acceptance * 100 }}% lot acceptance
      + {{ scores.weights.on_time * 100 }}% on-time delivery; A ≥ {{ scores.grades.A }}, B ≥ {{ scores.grades.B }}, C ≥ {{ scores.grades.C }}, else D.
      Unknown when either part has no data.</p>
    <table class="grid">
      <thead><tr><th>Supplier</th><th>Grade</th><th>Score</th><th>Lot acceptance</th><th>On time</th><th>NCRs</th></tr></thead>
      <tbody><tr v-for="s in scores.suppliers" :key="s.supplier">
        <td><RouterLink :to="objectPath('Supplier', s.supplier)">{{ s.name }}</RouterLink></td>
        <td><b>{{ s.grade || '—' }}</b></td><td>{{ fmt(s.score) }}</td>
        <td>{{ fmt(s.lot_acceptance, '%') }} <span class="muted small">({{ s.accepted }}/{{ s.lots }} lots)</span></td>
        <td>{{ fmt(s.on_time, '%') }} <span class="muted small">({{ s.on_time_lines }} lines)</span></td><td>{{ s.ncrs }}</td></tr></tbody>
    </table>
  </template>

  <template v-if="tab === 'spc'">
    <p v-if="!params.length" class="muted">No numeric readings yet. Enter measured values on ERPNext quality inspections to see control charts here.</p>
    <label v-else class="muted">Item and parameter
      <select v-model="pick"><option v-for="p in params" :key="p.item_code + p.parameter" :value="p">{{ p.item_code }} — {{ p.parameter }} ({{ p.inspections }} inspections)</option></select></label>
    <template v-if="spc">
      <p v-if="!spc.enough_data" class="muted">{{ spc.note }}</p>
      <template v-else>
        <ControlChart :data="spc" />
        <div class="cards">
          <div class="card"><h3>Signals</h3><p v-if="!spc.signals.length" class="muted">No rule broken.</p>
            <ul class="list small"><li v-for="s in spc.signals" :key="s.index + '-' + s.rule">Rule {{ s.rule }}: {{ s.text }}</li></ul></div>
          <div class="card"><h3>Capability</h3>
            <p v-if="!spc.capability" class="muted small">Needs both spec limits on the readings.</p>
            <table v-else class="props small"><tr><th>Cp</th><td>{{ r3(spc.capability.Cp) }}</td><th>Cpk</th><td>{{ r3(spc.capability.Cpk) }}</td></tr>
              <tr><th>Pp</th><td>{{ r3(spc.capability.Pp) }}</td><th>Ppk</th><td>{{ r3(spc.capability.Ppk) }}</td></tr>
              <tr><th>Values</th><td>{{ spc.capability.n }}</td><th>Out of spec</th><td>{{ spc.out_of_spec }}</td></tr></table></div>
        </div>
      </template>
    </template>
  </template>
</template>
