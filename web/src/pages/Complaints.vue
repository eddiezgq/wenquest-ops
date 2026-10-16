<script setup>
// Complaints (ADR-0017, 17e): received, investigated, assessed for reporting by someone other than the owner
// (signed), answered and closed by someone other than the owner (signed).
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'

const router = useRouter()
const v = ref(null)
const error = ref('')
const status = ref('open')
const show = ref(false)
const n = new Date()
const today = `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`   // the local day
const form = ref({ received_on: today, aware_on: today, source: 'customer', customer: '', contact: '', item_code: '', lot_no: '', quantity: '', description: '', injury: 'unknown', malfunction: 'unknown' })
const ST = { new: 'gray', investigation: 'amber', assessed: 'blue', closed: 'green', cancelled: 'gray' }
async function load() {
  error.value = ''
  try { v.value = await api(`/api/complaints?status=${status.value}`) } catch (e) { error.value = e.message }
}
watch(status, load, { immediate: true })
async function create() {
  error.value = ''
  try {
    const body = Object.fromEntries(Object.entries(form.value).filter(([, x]) => x !== ''))
    const r = await api('/api/complaints', { method: 'POST', body })
    router.push(`/quality/complaints/${r.id}`)
  } catch (e) { error.value = e.message }
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality', to: '/quality' }]">
    <template #title>Complaints</template>
    <Button v-if="v?.can_edit" data-help="complaints-new" variant="solid" icon-left="lucide-plus" label="Record a complaint" @click="show = !show" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <form v-if="show" data-help="complaints-form" class="new wq-panel mb-5 grid gap-3 p-5 md:grid-cols-4" @submit.prevent="create">
    <label class="wq-field">Received on<input v-model="form.received_on" type="date" class="wq-input"></label>
    <label class="wq-field">Company first knew on<input v-model="form.aware_on" type="date" class="wq-input"></label>
    <label class="wq-field">Source<select v-model="form.source" class="wq-select"><option>customer</option><option>distributor</option><option>field</option><option>other</option></select></label>
    <label class="wq-field">Customer<input v-model="form.customer" class="wq-input"></label>
    <label class="wq-field">Contact<input v-model="form.contact" class="wq-input"></label>
    <label class="wq-field">Product (item)<input v-model="form.item_code" class="wq-input"></label>
    <label class="wq-field">Lot or serial<input v-model="form.lot_no" class="wq-input"></label>
    <label class="wq-field">Quantity<input v-model="form.quantity" type="number" min="0" step="any" class="wq-input"></label>
    <label class="wq-field md:col-span-4">What happened<textarea v-model="form.description" rows="3" class="wq-input" /></label>
    <label class="wq-field">Anyone hurt?<select v-model="form.injury" class="wq-select"><option>unknown</option><option>yes</option><option>no</option></select></label>
    <label class="wq-field">Did the product fail?<select v-model="form.malfunction" class="wq-select"><option>unknown</option><option>yes</option><option>no</option></select></label>
    <div class="flex items-end"><Button type="submit" variant="solid" label="Record" :disabled="!form.customer.trim() || !form.description.trim()" /></div>
  </form>
  <section v-if="v" data-help="complaints-list" class="wq-panel p-5">
    <div class="mb-3 flex items-center gap-3"><select v-model="status" class="wq-select w-40"><option value="open">Open</option><option value="closed">Closed</option><option value="cancelled">Cancelled</option><option value="all">All</option></select></div>
    <p v-if="!v.complaints.length" class="wq-muted">None.</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>Number</th><th>Received</th><th>Customer</th><th>Product</th><th>Hurt</th><th>Status</th><th>Reporting</th><th>Owner</th></tr></thead>
      <tbody><tr v-for="c in v.complaints" :key="c.id">
        <td><RouterLink :to="`/quality/complaints/${c.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ c.name }}</RouterLink></td>
        <td>{{ c.received_on }}</td><td>{{ c.customer }}</td><td>{{ c.item_code }}</td>
        <td><Badge v-if="c.injury === 'yes'" theme="red" label="yes" /><template v-else>{{ c.injury }}</template></td>
        <td><Badge :theme="ST[c.status]" :label="c.status" /></td>
        <td><template v-if="c.reportable === true">reportable{{ c.reported_on ? `, reported ${c.reported_on}` : `, due ${c.deadline_on || '–'}` }}</template>
          <template v-else-if="c.reportable === false">not reportable</template>
          <Badge v-if="c.report_late" theme="red" label="report late" /> <Badge v-if="c.exception" theme="amber" label="exception" /></td>
        <td>{{ c.owner }}</td></tr></tbody></table>
  </section>
</template>
