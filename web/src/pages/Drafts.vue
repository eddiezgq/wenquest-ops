<script setup>
// Drafts waiting for a person (ADR-0006, ADR-0008). Nothing is written to ERPNext or sent before "Confirm".
import { inject, ref, watch } from 'vue'
import { api, objectPath } from '../api'
import { fmt } from '../format'

const ws = inject('workspace')
const status = ref('pending')
const rows = ref([])
const error = ref('')
const notes = ref({})
const copied = ref(null)

async function load() {
  error.value = ''
  try { rows.value = await api(`/api/erp/drafts${status.value === 'all' ? '' : '?status=' + status.value}`) }
  catch (e) { error.value = e.message }
}
async function act(d, what) {
  error.value = ''
  try {
    await api(`/api/erp/drafts/${d.id}/${what}`, { method: 'POST', body: what === 'reject' ? { reason: notes.value[d.id] || '' } : undefined })
    await load()
  } catch (e) { error.value = e.message }
}
async function copy(d) {
  await navigator.clipboard.writeText(`Subject: ${d.payload.subject}\n\n${d.payload.body}`)
  copied.value = d.id
}
watch(status, load, { immediate: true })
const WHAT = { 'Purchase Order': 'Creates a draft purchase order in ERPNext; submit it there.',
  'Material Request': 'Creates a draft material request in ERPNext.', 'Quality Inspection': 'Creates a draft inspection in ERPNext.',
  'Customer Message': 'Marks the message ready; you send it yourself.', 'Nonconformance Report': 'Opens a nonconformance report (NCR).' }
</script>

<template>
  <div class="head">
    <h1>Drafts</h1>
    <label class="muted">Show <select v-model="status">
      <option value="pending">Waiting for you</option><option value="confirmed">Confirmed</option>
      <option value="rejected">Rejected</option><option value="failed">Failed</option><option value="all">All</option></select></label>
  </div>
  <p class="muted small">Drafts are prepared by the assistant or by people. Nothing is written to ERPNext or sent until someone with the right role confirms.</p>
  <p v-if="error" class="err">{{ error }}</p>
  <p v-if="!rows.length" class="muted">None.</p>
  <article v-for="d in rows" :key="d.id" class="card draft">
    <div class="head">
      <h3>{{ d.doctype }} <span class="tag">{{ d.status }}</span> <span class="tag" v-if="d.source === 'ai'">AI draft</span></h3>
      <span class="muted small">#{{ d.id }} by {{ d.proposed_by }}</span>
    </div>
    <p>{{ d.summary }}</p>
    <template v-if="d.doctype === 'Purchase Order'">
      <p class="small">Supplier <RouterLink :to="objectPath('Supplier', d.payload.supplier)">{{ d.payload.supplier }}</RouterLink>,
        required by {{ d.payload.schedule_date }}</p>
      <table class="grid small"><thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Warehouse</th></tr></thead>
        <tbody><tr v-for="(l, i) in d.payload.items" :key="i">
          <td><RouterLink :to="objectPath('Item', l.item_code)">{{ l.item_code }}</RouterLink></td><td>{{ fmt(l.qty) }}</td>
          <td>{{ l.rate === undefined ? 'from ERPNext' : fmt(l.rate, 'currency') }}</td><td>{{ l.warehouse }}</td></tr></tbody></table>
    </template>
    <template v-else-if="d.doctype === 'Customer Message'">
      <p class="small"><b>To:</b> {{ d.payload.customer }} · <b>Subject:</b> {{ d.payload.subject }}</p>
      <pre class="msg">{{ d.payload.body }}</pre>
      <button v-if="d.status === 'confirmed'" @click="copy(d)">{{ copied === d.id ? 'Copied' : 'Copy to send' }}</button>
    </template>
    <template v-else-if="d.doctype === 'Nonconformance Report'">
      <p class="small"><b>{{ d.payload.title }}</b></p><p class="small">{{ d.payload.description }}</p>
    </template>
    <pre v-else class="msg small">{{ JSON.stringify(d.payload, null, 2) }}</pre>
    <p v-if="d.erp_url" class="small">In ERPNext: <a :href="d.erp_url" target="_blank" rel="noopener">{{ d.erp_name }} ↗</a> (submit it there)</p>
    <p v-if="d.record" class="small">Recorded as {{ d.record }}</p>
    <p v-if="d.error" class="err small">{{ d.error }}</p>
    <div class="actions" v-if="d.status === 'pending' || d.status === 'failed'">
      <input v-model="notes[d.id]" placeholder="Reason, if rejecting">
      <button @click="act(d, 'confirm')">Confirm</button>
      <button @click="act(d, 'reject')">Reject</button>
      <span class="muted small">{{ WHAT[d.doctype] }}</span>
    </div>
  </article>
</template>
