<script setup>
// Complaints (ADR-0017, 17e): received, investigated, assessed for reporting by someone other than the owner
// (signed), answered and closed by someone other than the owner (signed).
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { t } from '../i18n'

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
  <PageTop :crumbs="[{ label: t('Quality'), to: '/quality' }]">
    <template #title>{{ t('Complaints') }}</template>
    <Button v-if="v?.can_edit" data-help="complaints-new" variant="solid" icon-left="lucide-plus" :label="t('Record a complaint')" @click="show = !show" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <form v-if="show" data-help="complaints-form" class="new wq-panel mb-5 grid gap-3 p-5 md:grid-cols-4" @submit.prevent="create">
    <label class="wq-field">{{ t('Received on') }}<input v-model="form.received_on" type="date" class="wq-input"></label>
    <label class="wq-field">{{ t('Company first knew on') }}<input v-model="form.aware_on" type="date" class="wq-input"></label>
    <label class="wq-field">{{ t('Source') }}<select v-model="form.source" class="wq-select"><option value="customer">{{ t('customer') }}</option><option value="distributor">{{ t('distributor') }}</option><option value="field">{{ t('field') }}</option><option value="other">{{ t('other') }}</option></select></label>
    <label class="wq-field">{{ t('Customer') }}<input v-model="form.customer" class="wq-input"></label>
    <label class="wq-field">{{ t('Contact') }}<input v-model="form.contact" class="wq-input"></label>
    <label class="wq-field">{{ t('Product (item)') }}<input v-model="form.item_code" class="wq-input"></label>
    <label class="wq-field">{{ t('Lot or serial') }}<input v-model="form.lot_no" class="wq-input"></label>
    <label class="wq-field">{{ t('Quantity') }}<input v-model="form.quantity" type="number" min="0" step="any" class="wq-input"></label>
    <label class="wq-field md:col-span-4">{{ t('What happened') }}<textarea v-model="form.description" rows="3" class="wq-input" /></label>
    <label class="wq-field">{{ t('Anyone hurt?') }}<select v-model="form.injury" class="wq-select"><option value="unknown">{{ t('unknown') }}</option><option value="yes">{{ t('yes') }}</option><option value="no">{{ t('no') }}</option></select></label>
    <label class="wq-field">{{ t('Did the product fail?') }}<select v-model="form.malfunction" class="wq-select"><option value="unknown">{{ t('unknown') }}</option><option value="yes">{{ t('yes') }}</option><option value="no">{{ t('no') }}</option></select></label>
    <div class="flex items-end"><Button type="submit" variant="solid" :label="t('Record')" :disabled="!form.customer.trim() || !form.description.trim()" /></div>
  </form>
  <section v-if="v" data-help="complaints-list" class="wq-panel p-5">
    <div class="mb-3 flex items-center gap-3"><select v-model="status" class="wq-select w-40"><option value="open">{{ t('status::Open') }}</option><option value="closed">{{ t('Closed') }}</option><option value="cancelled">{{ t('Cancelled') }}</option><option value="all">{{ t('All') }}</option></select></div>
    <p v-if="!v.complaints.length" class="wq-muted">{{ t('None.') }}</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Number') }}</th><th>{{ t('Received') }}</th><th>{{ t('Customer') }}</th><th>{{ t('Product') }}</th><th>{{ t('Hurt') }}</th><th>{{ t('Status') }}</th><th>{{ t('Reporting') }}</th><th>{{ t('Owner') }}</th></tr></thead>
      <tbody><tr v-for="c in v.complaints" :key="c.id">
        <td><RouterLink :to="`/quality/complaints/${c.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ c.name }}</RouterLink></td>
        <td>{{ c.received_on }}</td><td>{{ c.customer }}</td><td>{{ c.item_code }}</td>
        <td><Badge v-if="c.injury === 'yes'" theme="red" :label="t('yes')" /><template v-else>{{ t(c.injury) }}</template></td>
        <td><Badge :theme="ST[c.status]" :label="t(c.status)" /></td>
        <td><template v-if="c.reportable === true">{{ c.reported_on ? t('reportable, reported {date}', { date: c.reported_on }) : t('reportable, due {date}', { date: c.deadline_on || '–' }) }}</template>
          <template v-else-if="c.reportable === false">{{ t('not reportable') }}</template>
          <Badge v-if="c.report_late" theme="red" :label="t('report late')" /> <Badge v-if="c.exception" theme="amber" :label="t('exception')" /></td>
        <td>{{ c.owner }}</td></tr></tbody></table>
  </section>
</template>
