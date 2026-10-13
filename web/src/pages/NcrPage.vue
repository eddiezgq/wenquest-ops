<script setup>
// One nonconformance report (ADR-0009, ADR-0010): the next step, signed approval and closing, 8D, corrective
// actions, signatures and history.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, objectPath } from '../api'
import { ago, fmt } from '../format'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const n = ref(null)
const error = ref('')
const f = ref({ containment: '', disposition: '', quantity: '', reason: '', note: '', password: '', cancel: '' })
const eight = ref({})
const capa = ref({ kind: 'corrective', title: '', description: '', risk: 'medium' })
const canEdit = computed(() => ws.value?.user.permissions.includes('quality:edit'))
const me = computed(() => ws.value?.user.email)
const activeTypes = computed(() => Object.entries(n.value?.dispositions || {}).filter(([, t]) => t.active))

async function load() {
  try { set(await api(`/api/quality/ncrs/${route.params.id}`)) } catch (e) { error.value = e.message }
}
function set(v) {
  n.value = v
  eight.value = { ...(v.eightd?.sections || {}) }
  f.value.password = ''
}
async function step(s, body = {}) {
  error.value = ''
  try { set(await api(`/api/quality/ncrs/${n.value.id}/${s}`, { method: 'POST', body })) } catch (e) { error.value = e.message }
}
async function newCapa() {
  error.value = ''
  try {
    const out = await api('/api/quality/capas', { method: 'POST', body: { ...capa.value, ncr_id: n.value.id } })
    router.push(`/quality/capa/${out.id}`)
  } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
const label = (s) => s.replace('_', ' ')
</script>

<template>
  <p v-if="error" class="err">{{ error }}</p>
  <template v-if="n">
    <p class="muted small"><RouterLink to="/quality?tab=ncrs">Nonconformances</RouterLink> · <RouterLink :to="objectPath('Nonconformance', n.name)">object page</RouterLink></p>
    <h1>{{ n.name }} {{ n.title }} <span class="tag">{{ label(n.status) }}</span> <span class="tag">{{ n.severity }}</span></h1>
    <p>{{ n.description }}</p>
    <table class="props">
      <tr v-if="n.item_code"><th>Item</th><td><RouterLink :to="objectPath('Item', n.item_code)">{{ n.item_code }}</RouterLink></td></tr>
      <tr v-if="n.supplier"><th>Supplier</th><td><RouterLink :to="objectPath('Supplier', n.supplier)">{{ n.supplier }}</RouterLink></td></tr>
      <tr v-if="n.receipt"><th>Receipt</th><td><RouterLink :to="objectPath('PurchaseReceipt', n.receipt)">{{ n.receipt }}</RouterLink></td></tr>
      <tr v-if="n.inspection"><th>Inspection</th><td><RouterLink :to="objectPath('QualityInspection', n.inspection)">{{ n.inspection }}</RouterLink></td></tr>
      <tr v-if="n.quantity !== null"><th>Quantity</th><td>{{ fmt(n.quantity) }}</td></tr>
      <tr><th>Owner</th><td>{{ n.owner || 'not assigned' }} <span class="muted small">(opened by {{ n.created_by }})</span></td></tr>
      <tr v-if="n.containment"><th>Containment</th><td>{{ n.containment }}</td></tr>
      <tr v-if="n.disposition"><th>Disposition</th><td>{{ n.dispositions[n.disposition]?.name }}, {{ fmt(n.disposition_qty) }} — {{ n.disposition_reason }}
        <span class="muted small">(submitted by {{ n.disposition_by }}<template v-if="n.approved_by">, approved by {{ n.approved_by }}</template>)</span></td></tr>
      <tr v-if="n.cancel_reason"><th>Cancelled because</th><td>{{ n.cancel_reason }}</td></tr>
    </table>

    <div v-if="canEdit && !['closed', 'cancelled'].includes(n.status)" class="card">
      <template v-if="n.status === 'open'">
        <h3>Contain</h3><p class="small muted">What was done so bad parts go no further?</p>
        <div class="actions"><input v-model="f.containment" placeholder="e.g. lot moved to QC Hold, open orders checked"><button @click="step('contain', { containment: f.containment })">Save containment</button></div>
      </template>
      <template v-if="n.status === 'contained'">
        <h3>Disposition</h3>
        <div class="actions"><select v-model="f.disposition"><option value="" disabled>Type</option>
          <option v-for="[k, t] in activeTypes" :key="k" :value="k">{{ t.name }}{{ t.requires_approval ? ' (needs approval)' : '' }}</option></select>
          <input v-model="f.quantity" type="number" min="0" step="any" placeholder="Quantity" style="max-width:8rem">
          <input v-model="f.reason" placeholder="Reason">
          <button @click="step('disposition', { disposition: f.disposition, quantity: f.quantity === '' ? null : Number(f.quantity), reason: f.reason })">Submit disposition</button></div>
      </template>
      <template v-if="n.status === 'pending_approval'">
        <h3>Approve the disposition</h3>
        <p v-if="n.disposition_by === me" class="muted small">You submitted it; someone else must approve it.</p>
        <div v-else class="actions"><input v-model="f.password" type="password" placeholder="Your password to sign" autocomplete="current-password">
          <button @click="step('approve', { password: f.password })">Approve (sign)</button>
          <input v-model="f.reason" placeholder="Reason, if not approving"><button @click="step('reject-disposition', { reason: f.reason })">Not approved</button></div>
      </template>
      <template v-if="n.status === 'dispositioned'">
        <h3>Close</h3><p v-if="n.severity === 'major'" class="small muted">A major report closes when a linked corrective action is closed.</p>
        <div class="actions"><input v-model="f.note" placeholder="Closing note"><input v-model="f.password" type="password" placeholder="Your password to sign" autocomplete="current-password">
          <button @click="step('close', { note: f.note, password: f.password })">Close (sign)</button></div>
      </template>
      <div class="actions"><input v-model="f.cancel" placeholder="Reason to cancel"><button @click="step('cancel', { reason: f.cancel })">Cancel the report</button></div>
    </div>

    <h2>8D <span v-if="n.eightd?.complete" class="tag">complete</span></h2>
    <div class="eightd">
      <label v-for="(lbl, k) in n.sections" :key="k">{{ lbl }}
        <textarea v-model="eight[k]" :disabled="!canEdit || n.eightd?.complete || ['closed', 'cancelled'].includes(n.status)" rows="2"></textarea></label>
    </div>
    <div class="actions" v-if="canEdit && !n.eightd?.complete && !['closed', 'cancelled'].includes(n.status)">
      <button @click="step('8d', { sections: eight })">Save 8D</button>
      <input v-model="f.password" type="password" placeholder="Your password to sign" autocomplete="current-password" style="max-width:14rem">
      <button @click="step('8d-complete', { password: f.password })">Mark 8D complete (sign)</button>
    </div>

    <h2>Corrective and preventive actions</h2>
    <ul class="list"><li v-for="c in n.capas" :key="c.id"><RouterLink :to="`/quality/capa/${c.id}`">{{ c.name }} {{ c.title }}</RouterLink> — {{ c.kind }}, {{ label(c.status) }}</li></ul>
    <form v-if="canEdit && !['closed', 'cancelled'].includes(n.status)" class="actions" @submit.prevent="newCapa">
      <select v-model="capa.kind"><option value="corrective">Corrective</option><option value="preventive">Preventive</option></select>
      <input v-model="capa.title" placeholder="Title" required><input v-model="capa.description" placeholder="Problem">
      <select v-model="capa.risk"><option value="low">Low risk</option><option value="medium">Medium risk</option><option value="high">High risk</option></select>
      <button>Open corrective action</button>
    </form>

    <h2>Signatures</h2>
    <p v-if="!n.signatures.length" class="muted small">None yet.</p>
    <ul class="list small"><li v-for="(s, i) in n.signatures" :key="i">{{ s.meaning }} — {{ s.name }} ({{ s.email }}), {{ ago(s.at) }}</li></ul>
    <h2>History</h2>
    <ul class="list small"><li v-for="(h, i) in n.history" :key="i">{{ ago(h.at) }} — <b>{{ h.action }}</b> {{ h.email }} <span class="muted">{{ h.note }}</span></li></ul>
  </template>
</template>
