<script setup>
// One recall (ADR-0017, 17i). People classify it and decide what to report; WenQuest Ops takes the consignees from
// ERPNext when it opens, records contact, counts effectiveness, and has it closed with a signature.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'

const route = useRoute()
const r = ref(null)
const error = ref('')
const done = ref('')
const f = ref({})
const x = ref({ password: '', reason: '' })
const cx = ref({})
const ST = { draft: 'gray', open: 'red', closed: 'green', cancelled: 'gray' }
const FIELDS = ['title', 'reason', 'owner', 'classification', 'regulatory_decision', 'strategy', 'effectiveness', 'unconfirmed_note']
const can = (k) => r.value?.can_edit && ({ draft: ['title', 'reason', 'owner', 'classification', 'regulatory_decision', 'strategy'],
  open: ['classification', 'regulatory_decision', 'strategy', 'effectiveness', 'unconfirmed_note', ...(r.value.can_configure ? ['owner'] : [])] }[r.value.status] || []).includes(k)
const pct = (v) => v == null ? '–' : `${Math.round(v * 100)}%`
const eff = computed(() => r.value?.effectiveness_counts)

function set(v) {
  r.value = v
  f.value = Object.fromEntries(FIELDS.map((k) => [k, v[k] ?? '']))
  cx.value = Object.fromEntries(v.consignees.map((c) => [c.id, { notified_on: c.notified_on || '', method: c.method, confirmed_on: c.confirmed_on || '', returned_qty: Math.round(c.returned_qty), corrected_qty: Math.round(c.corrected_qty), note: c.note }]))
}
async function load() { error.value = ''; try { set(await api(`/api/recalls/${route.params.id}`)) } catch (e) { error.value = e.message } }
watch(() => route.params.id, load, { immediate: true })
const changed = () => Object.fromEntries(FIELDS.filter((k) => can(k) && (f.value[k] ?? '') !== (r.value[k] ?? '')).map((k) => [k, f.value[k] === '' && k === 'owner' ? null : f.value[k]]))
async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { set(await api(path, { method, body })); done.value = message; x.value = { password: '', reason: '' } } catch (e) { error.value = e.message }
}
function saveContact(c) {
  const n = cx.value[c.id]
  const body = { notified_on: n.notified_on || null, method: n.method, confirmed_on: n.confirmed_on || null, returned_qty: Number(n.returned_qty) || 0, corrected_qty: Number(n.corrected_qty) || 0, note: n.note }
  call(`/api/recall-consignees/${c.id}`, 'PUT', body, `${c.delivery_note} saved.`)
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Recalls', to: '/quality/recalls' }]">
    <template #title>{{ r ? `${r.name} · ${r.title}` : 'Recall' }}</template>
    <Badge v-if="r" :theme="ST[r.status]" size="lg" :label="r.status" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="r">
    <p v-if="r.after_opening.length" class="wq-error mb-4">Delivered after the recall opened (not on the list): {{ r.after_opening.map((a) => `${a.delivery_note} ${a.customer_name} ${a.qty}`).join('; ') }}.</p>
    <section class="what wq-panel mb-5 grid gap-3 p-5 md:grid-cols-3">
      <label class="wq-field md:col-span-2">Title<input v-model="f.title" class="wq-input" :disabled="!can('title')"></label>
      <label class="wq-field">Owner<select v-model="f.owner" class="wq-select" :disabled="!can('owner')"><option value="" /><option v-for="p in r.people" :key="p">{{ p }}</option></select></label>
      <label class="wq-field md:col-span-3">Reason<textarea v-model="f.reason" rows="2" class="wq-input" :disabled="!can('reason')" /></label>
      <label class="wq-field">Classification (your decision)<select v-model="f.classification" class="wq-select" :disabled="!can('classification')"><option v-for="k in r.classes" :key="k">{{ k }}</option></select></label>
      <label class="wq-field md:col-span-2">Regulatory decision (what will be reported, or why not)<textarea v-model="f.regulatory_decision" rows="2" class="wq-input" :disabled="!can('regulatory_decision')" /></label>
      <label class="wq-field md:col-span-3">Strategy and depth<textarea v-model="f.strategy" rows="2" class="wq-input" :disabled="!can('strategy')" /></label>
      <template v-if="r.status !== 'draft'">
        <label class="wq-field md:col-span-3">Effectiveness conclusion<textarea v-model="f.effectiveness" rows="2" class="wq-input" :disabled="!can('effectiveness')" /></label>
        <label class="wq-field md:col-span-3">Consignees who did not confirm<textarea v-model="f.unconfirmed_note" rows="2" class="wq-input" :disabled="!can('unconfirmed_note')" /></label>
      </template>
      <div v-if="r.can_edit && ['draft', 'open'].includes(r.status)"><Button label="Save" :disabled="!Object.keys(changed()).length" @click="call(`/api/recalls/${r.id}`, 'PUT', changed(), 'Saved.')" /></div>
    </section>

    <section class="scope wq-panel mb-5 p-5 text-sm">
      <h2 class="wq-h2">Lots in scope</h2>
      <ul><li v-for="l in r.lots" :key="l.id"><RouterLink :to="`/quality/trace?record=${l.id}`" class="wq-link">{{ l.name }}</RouterLink> {{ l.item_code }} lot {{ l.lot_no }} · {{ l.status.replace('_', ' ') }}</li></ul>
      <template v-if="r.status === 'draft'">
        <p class="mt-3 text-ink-gray-7">Opening takes these deliveries from ERPNext ({{ r.preview.length }}):</p>
        <ul><li v-for="p in r.preview" :key="`${p.delivery_note}:${p.line}:${p.lot_no}`">{{ p.delivery_note }} {{ p.posting_date }} · {{ p.customer_name || p.customer }} · {{ p.qty }} <Badge :theme="p.batch_match === 'batch' ? 'green' : 'amber'" :label="p.batch_match" /></li></ul>
      </template>
    </section>

    <section v-if="r.status !== 'draft' && r.status !== 'cancelled'" class="consignees wq-panel mb-5 p-5">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 class="wq-h2">Consignees</h2>
        <a :href="`/api/recalls/${r.id}/consignees.csv`" class="wq-link text-sm">Download the list (CSV)</a></div>
      <p class="mb-3 text-sm">Notified {{ pct(eff.notified) }} · confirmed {{ pct(eff.confirmed) }} · recovered {{ pct(eff.recovered) }} ({{ eff.recovered_qty }} of {{ eff.shipped_qty }})</p>
      <table class="wq-table text-sm"><thead><tr><th>Delivery</th><th>Customer</th><th>Lot</th><th>Qty</th><th>Notified</th><th>How</th><th>Confirmed</th><th>Returned</th><th>Corrected</th><th>Note</th><th /></tr></thead>
        <tbody><tr v-for="c in r.consignees" :key="c.id">
          <td>{{ c.delivery_note }}<br><span class="text-xs text-ink-gray-5">{{ c.posting_date }}</span></td><td>{{ c.customer_name || c.customer }}</td>
          <td>{{ c.lot_no }} <Badge v-if="c.batch_match !== 'batch'" theme="amber" :label="c.batch_match" /></td><td>{{ c.qty }}</td>
          <template v-if="r.status === 'open' && r.can_edit">
            <td><input v-model="cx[c.id].notified_on" type="date" class="wq-input w-36"></td><td><input v-model="cx[c.id].method" class="wq-input w-24"></td>
            <td><input v-model="cx[c.id].confirmed_on" type="date" class="wq-input w-36"></td>
            <td><input v-model="cx[c.id].returned_qty" type="number" min="0" class="wq-input w-20"></td><td><input v-model="cx[c.id].corrected_qty" type="number" min="0" class="wq-input w-20"></td>
            <td><input v-model="cx[c.id].note" class="wq-input w-32"></td><td><Button size="sm" label="Save" @click="saveContact(c)" /></td>
          </template>
          <template v-else><td>{{ c.notified_on }}</td><td>{{ c.method }}</td><td>{{ c.confirmed_on }}</td><td>{{ c.returned_qty }}</td><td>{{ c.corrected_qty }}</td><td>{{ c.note }}</td><td /></template>
        </tr></tbody></table>
    </section>

    <section v-if="r.can_edit && ['draft', 'open'].includes(r.status)" class="steps wq-panel mb-5 p-5">
      <template v-if="r.status === 'draft'">
        <p v-if="r.to_open.length" class="mb-2 text-sm text-ink-gray-6">To open: {{ r.to_open.join('; ') }}.</p>
        <Button variant="solid" label="Open the recall" :disabled="!!r.to_open.length || !!Object.keys(changed()).length" @click="call(`/api/recalls/${r.id}/open`, 'POST', {}, 'Open: the consignee list is fixed.')" />
        <p class="mt-2 text-sm text-ink-gray-5">Opened by its owner or Quality.</p>
        <details v-if="r.can_configure" class="mt-3"><summary class="cursor-pointer text-sm text-ink-gray-7">Cancel the draft</summary>
          <div class="mt-2 flex gap-2"><input v-model="x.reason" class="wq-input w-96" placeholder="Why"><Button label="Cancel" :disabled="!x.reason.trim()" @click="call(`/api/recalls/${r.id}/cancel`, 'POST', { reason: x.reason }, 'Cancelled.')" /></div></details>
      </template>
      <template v-else>
        <p v-if="r.to_close.length" class="mb-2 text-sm text-ink-gray-6">To close: {{ r.to_close.join('; ') }}.</p>
        <div v-if="r.can_configure" class="flex flex-wrap items-end gap-2">
          <input v-model="x.password" type="password" class="wq-input w-44" placeholder="Your password" autocomplete="current-password">
          <Button variant="solid" label="Close (sign)" :disabled="!x.password || !!r.to_close.length || !!Object.keys(changed()).length" @click="call(`/api/recalls/${r.id}/close`, 'POST', { password: x.password }, 'Closed.')" />
        </div>
        <p class="mt-2 text-sm text-ink-gray-5">Closed by someone who does not own it and did not raise or open it.</p>
      </template>
    </section>
    <h2 class="wq-h2 mt-6">Signatures</h2>
    <Trail :items="r.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">History</h2>
    <Trail :items="r.history" />
  </template>
</template>
