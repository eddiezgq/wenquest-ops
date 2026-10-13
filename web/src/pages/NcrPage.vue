<script setup>
// One nonconformance report: details, the next step, 8D, corrective actions, history (ADR-0009 items 1-3).
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, objectPath } from '../api'
import { ago, fmt } from '../format'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const n = ref(null)
const error = ref('')
const input = ref({ containment: '', disposition: 'rework', quantity: '', note: '', reason: '' })
const eight = ref({})
const capa = ref({ kind: 'corrective', title: '', action: '', owner: '', due: '' })
const canEdit = computed(() => ws.value?.user.permissions.includes('quality:edit'))

async function load() {
  try {
    n.value = await api(`/api/quality/ncrs/${route.params.id}`)
    eight.value = { ...(n.value.eightd?.sections || {}) }
  } catch (e) { error.value = e.message }
}
async function step(s, body = {}) {
  error.value = ''
  try { n.value = await api(`/api/quality/ncrs/${n.value.id}/${s}`, { method: 'POST', body }); eight.value = { ...(n.value.eightd?.sections || {}) } }
  catch (e) { error.value = e.message }
}
async function newCapa() {
  error.value = ''
  const c = capa.value
  try {
    const out = await api('/api/quality/capas', { method: 'POST', body: { kind: c.kind, title: c.title, ncr_id: n.value.id,
      actions: c.action ? [{ text: c.action, owner: c.owner || null, due: c.due || null }] : [] } })
    router.push(`/quality/capa/${out.id}`)
  } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
</script>

<template>
  <p v-if="error" class="err">{{ error }}</p>
  <template v-if="n">
    <p class="muted small"><RouterLink to="/quality?tab=ncrs">Nonconformances</RouterLink> · <RouterLink :to="objectPath('Nonconformance', n.name)">object page</RouterLink></p>
    <h1>{{ n.name }} {{ n.title }} <span class="tag">{{ n.status }}</span> <span class="tag">{{ n.severity }}</span></h1>
    <p>{{ n.description }}</p>
    <table class="props">
      <tr v-if="n.item_code"><th>Item</th><td><RouterLink :to="objectPath('Item', n.item_code)">{{ n.item_code }}</RouterLink></td></tr>
      <tr v-if="n.supplier"><th>Supplier</th><td><RouterLink :to="objectPath('Supplier', n.supplier)">{{ n.supplier }}</RouterLink></td></tr>
      <tr v-if="n.receipt"><th>Receipt</th><td><RouterLink :to="objectPath('PurchaseReceipt', n.receipt)">{{ n.receipt }}</RouterLink></td></tr>
      <tr v-if="n.inspection"><th>Inspection</th><td><RouterLink :to="objectPath('QualityInspection', n.inspection)">{{ n.inspection }}</RouterLink></td></tr>
      <tr v-if="n.quantity !== null"><th>Quantity</th><td>{{ fmt(n.quantity) }}</td></tr>
      <tr><th>Owner</th><td>{{ n.owner }}</td></tr>
      <tr v-if="n.containment"><th>Containment</th><td>{{ n.containment }}</td></tr>
      <tr v-if="n.disposition"><th>Disposition</th><td>{{ n.dispositions[n.disposition] }}<span v-if="n.disposition_qty !== null">, {{ fmt(n.disposition_qty) }}</span> (by {{ n.disposition_by }})</td></tr>
      <tr v-if="n.cancel_reason"><th>Cancelled because</th><td>{{ n.cancel_reason }}</td></tr>
    </table>

    <div v-if="canEdit" class="card">
      <template v-if="n.status === 'open'">
        <h3>Contain</h3><p class="small muted">What was done so bad parts go no further?</p>
        <div class="actions"><input v-model="input.containment" placeholder="e.g. lot moved to QC Hold, open orders checked"><button @click="step('contain', { containment: input.containment })">Save containment</button></div>
      </template>
      <template v-if="n.status === 'contained'">
        <h3>Disposition</h3>
        <div class="actions"><select v-model="input.disposition"><option v-for="(l, k) in n.dispositions" :key="k" :value="k">{{ l }}</option></select>
          <input v-model="input.quantity" type="number" min="0" step="any" placeholder="Quantity" style="max-width:8rem">
          <input v-model="input.note" placeholder="Note (approval, RMA number…)">
          <button @click="step('disposition', { disposition: input.disposition, quantity: input.quantity === '' ? null : Number(input.quantity), note: input.note })">Save disposition</button></div>
      </template>
      <template v-if="n.status === 'dispositioned'">
        <h3>Close</h3><p v-if="n.severity === 'major'" class="small muted">A major report closes when a linked corrective action is closed.</p>
        <div class="actions"><input v-model="input.note" placeholder="Closing note"><button @click="step('close', { note: input.note })">Close the report</button></div>
      </template>
      <div v-if="['open', 'contained', 'dispositioned'].includes(n.status)" class="actions">
        <input v-model="input.reason" placeholder="Reason to cancel"><button @click="step('cancel', { reason: input.reason })">Cancel the report</button></div>
    </div>

    <h2>8D <span v-if="n.eightd?.complete" class="tag">complete</span></h2>
    <div class="eightd">
      <label v-for="(label, k) in n.sections" :key="k">{{ label }}
        <textarea v-model="eight[k]" :disabled="!canEdit || n.eightd?.complete" rows="2"></textarea></label>
    </div>
    <div class="actions" v-if="canEdit && !n.eightd?.complete">
      <button @click="step('8d', { sections: eight })">Save 8D</button>
      <button @click="step('8d-complete')">Mark 8D complete</button>
    </div>

    <h2>Corrective and preventive actions</h2>
    <ul class="list"><li v-for="c in n.capas" :key="c.id"><RouterLink :to="`/quality/capa/${c.id}`">{{ c.name }} {{ c.title }}</RouterLink> — {{ c.kind }}, {{ c.status.replace('_', ' ') }}</li></ul>
    <form v-if="canEdit && !['closed', 'cancelled'].includes(n.status)" class="actions" @submit.prevent="newCapa">
      <select v-model="capa.kind"><option value="corrective">Corrective</option><option value="preventive">Preventive</option></select>
      <input v-model="capa.title" placeholder="Title" required>
      <input v-model="capa.action" placeholder="First action (optional)">
      <input v-model="capa.owner" placeholder="Owner email">
      <input v-model="capa.due" type="date">
      <button>Open action</button>
    </form>

    <h2>History</h2>
    <ul class="list small"><li v-for="(h, i) in n.history" :key="i">{{ ago(h.at) }} — <b>{{ h.action }}</b> {{ h.email }} <span class="muted">{{ h.note }}</span></li></ul>
  </template>
</template>
