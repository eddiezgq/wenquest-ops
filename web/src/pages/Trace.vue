<script setup>
// Traceability (ADR-0017, 17i): from a production lot, an incoming lot or a complaint, to the material lots,
// suppliers, equipment, nonconformances, deliveries (ERPNext) and complaints. Read only; a recall can start here.
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const pick = ref(null)
const t = ref(null)
const error = ref('')
const KINDS = { record: 'Production lot', incoming: 'Incoming lot', complaint: 'Complaint' }
const kind = ref(Object.keys(KINDS).find((k) => route.query[k]) || 'record')
const id = ref(route.query[kind.value] || '')

async function load() {
  error.value = ''
  try {
    pick.value = pick.value || await api('/api/trace')
    t.value = id.value ? await api(`/api/trace?${kind.value}=${id.value}`) : null
  } catch (e) { error.value = e.message }
}
watch(() => route.query, () => { kind.value = Object.keys(KINDS).find((k) => route.query[k]) || kind.value; id.value = route.query[kind.value] || ''; load() }, { immediate: true })
const go = () => router.push({ query: { [kind.value]: id.value } })
const options = () => ({ record: pick.value?.records, incoming: pick.value?.incoming, complaint: pick.value?.complaints }[kind.value] || [])
async function startRecall() {
  error.value = ''
  try {
    const r = await api('/api/recalls', { method: 'POST', body: { title: `Recall of ${t.value.lots.map((l) => `${l.item_code} lot ${l.lot_no}`).join(', ')}`.slice(0, 200), scope: t.value.lots.map((l) => l.id) } })
    router.push(`/quality/recalls/${r.id}`)
  } catch (e) { error.value = e.message }
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality', to: '/quality' }]"><template #title>Trace</template></PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <form class="pick wq-panel mb-5 flex flex-wrap items-end gap-3 p-5" @submit.prevent="go">
    <label class="wq-field">Start from<select v-model="kind" class="wq-select" @change="id = ''"><option v-for="(l, k) in KINDS" :key="k" :value="k">{{ l }}</option></select></label>
    <label class="wq-field grow">Which<select v-model="id" class="wq-select"><option value="" />
      <option v-for="o in options()" :key="o.id" :value="String(o.id)">{{ o.name }} · {{ o.item_code || '' }} {{ o.lot_no ? `lot ${o.lot_no}` : '' }} {{ o.supplier || o.customer || '' }}</option></select></label>
    <Button type="submit" variant="solid" label="Trace" :disabled="!id" />
  </form>

  <template v-if="t">
    <p v-if="t.note" class="mb-4 rounded-3 border border-outline-amber-3 bg-surface-amber-1 px-3 py-2 text-sm">{{ t.note }}</p>
    <section class="lots wq-panel mb-5 p-5">
      <div class="flex items-center justify-between"><h2 class="wq-h2">Production lots</h2>
        <Button v-if="t.lots.length && pick" icon-left="lucide-siren" label="Start a recall of these lots" @click="startRecall" /></div>
      <p v-if="!t.lots.length" class="wq-muted">None.</p>
      <ul v-else class="text-sm"><li v-for="l in t.lots" :key="l.id"><RouterLink :to="`/quality/production/${l.id}`" class="wq-link">{{ l.name }}</RouterLink> {{ l.item_code }} lot {{ l.lot_no }} · {{ l.status.replace('_', ' ') }} · {{ l.good_qty }} good</li></ul>
      <p v-if="t.recalls?.length" class="mt-2 text-sm text-ink-red-7">On recall: <RouterLink v-for="r in t.recalls" :key="r.id" :to="`/quality/recalls/${r.id}`" class="wq-link me-2">{{ r.name }} ({{ r.status }})</RouterLink></p>
    </section>
    <section v-if="t.materials" class="back wq-panel mb-5 grid gap-4 p-5 md:grid-cols-2 text-sm">
      <div><h2 class="wq-h2">Material lots</h2><p v-if="!t.materials.length" class="wq-muted">None recorded.</p>
        <ul><li v-for="m in t.materials" :key="m.inspection_id + m.item_code"><RouterLink :to="`/quality/iqc/${m.inspection_id}`" class="wq-link">{{ m.inspection }}</RouterLink> {{ m.item_code }} lot {{ m.lot_no || '–' }} · {{ m.supplier }} · {{ m.qty }}<span v-if="m.ncr"> · {{ m.ncr }}</span></li></ul></div>
      <div><h2 class="wq-h2">Equipment</h2><p v-if="!t.gauges.length" class="wq-muted">None named.</p>
        <ul><li v-for="g in t.gauges" :key="g.gauge_id"><RouterLink :to="`/quality/gauges/${g.gauge_id}`" class="wq-link">{{ g.gauge_code }}</RouterLink> (due {{ g.gauge_due }})</li></ul></div>
      <div><h2 class="wq-h2">Nonconformances</h2><p v-if="!t.ncrs.length" class="wq-muted">None.</p>
        <ul><li v-for="n in t.ncrs" :key="n.id"><RouterLink :to="`/quality/ncr/${n.id}`" class="wq-link">{{ n.name }}</RouterLink> step {{ n.seq }} · {{ n.status }}</li></ul></div>
      <div><h2 class="wq-h2">Other lots using the same material lots</h2><p v-if="!t.siblings.length" class="wq-muted">None.</p>
        <ul><li v-for="s in t.siblings" :key="s.id"><RouterLink :to="`/quality/trace?record=${s.id}`" class="wq-link">{{ s.name }}</RouterLink> {{ s.item_code }} lot {{ s.lot_no }} · {{ s.status.replace('_', ' ') }}</li></ul></div>
    </section>
    <section class="ship wq-panel mb-5 p-5">
      <h2 class="wq-h2">Delivered (ERPNext delivery notes)</h2>
      <p v-if="t.item_only" class="mb-2 text-sm text-ink-amber-7">{{ t.item_only }} delivery lines of the item carry no batch number we can read (none, or kept in an ERPNext bundle): they may hold these lots.</p>
      <p v-if="!t.shipments.length" class="wq-muted">No delivery found.</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>Delivery note</th><th>Date</th><th>Customer</th><th>Lot</th><th>Quantity</th><th>Matched by</th></tr></thead>
        <tbody><tr v-for="s in t.shipments" :key="`${s.delivery_note}:${s.line}:${s.record}`"><td><RouterLink :to="`/o/DeliveryNote/${s.delivery_note}`" class="wq-link">{{ s.delivery_note }}</RouterLink></td>
          <td>{{ s.posting_date }}</td><td>{{ s.customer_name || s.customer }}</td><td>{{ s.lot_no }}</td><td>{{ s.qty }}</td>
          <td><Badge :theme="s.batch_match === 'batch' ? 'green' : 'amber'" :label="s.batch_match === 'bundle' ? 'batch in an ERPNext bundle' : s.batch_match" /></td></tr></tbody></table>
      <p v-if="t.customers.length" class="mt-2 text-sm">Customers: {{ t.customers.join(', ') }}</p>
    </section>
    <section class="complaints wq-panel mb-5 p-5">
      <h2 class="wq-h2">Complaints about these lots</h2>
      <p v-if="!t.complaints.length" class="wq-muted">None.</p>
      <ul v-else class="text-sm"><li v-for="c in t.complaints" :key="c.id"><RouterLink :to="`/quality/complaints/${c.id}`" class="wq-link">{{ c.name }}</RouterLink> {{ c.received_on }} · {{ c.customer }} · {{ c.status }}</li></ul>
    </section>
  </template>
</template>
