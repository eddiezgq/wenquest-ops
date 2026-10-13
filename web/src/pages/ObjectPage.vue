<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, apiObject, objectPath } from '../api'
import { ago, docState, fmt } from '../format'
import Chain from '../components/Chain.vue'

const route = useRoute()
const router = useRouter()
const DRAFT = { Item: ['purchase_order', 'Draft a replenishment purchase order'],
  SalesOrder: ['delay_message', 'Draft a delay message to the customer'],
  QualityInspection: ['nonconformance', 'Draft a nonconformance report'] }
const drafting = ref('')
async function draft() {
  drafting.value = 'Preparing…'
  try {
    const [kind] = DRAFT[route.params.type]
    await api('/api/ai/draft', { method: 'POST', body: { kind, key: route.params.key } })
    router.push('/drafts')
  } catch (e) {
    drafting.value = e.message
  }
}
const o = ref(null)
const explain = ref(null)
const error = ref('')
const EXPLAINED = ['SalesOrder', 'Item', 'PurchaseOrder', 'QualityInspection', 'Supplier']

async function load() {
  error.value = ''
  o.value = explain.value = null
  try {
    o.value = await api(apiObject(route.params.type, route.params.key))
    if (EXPLAINED.includes(route.params.type)) {
      explain.value = await api(`/api/explain/${encodeURIComponent(route.params.type)}/${encodeURIComponent(route.params.key)}`)
    }
  } catch (e) {
    error.value = e.message
  }
}
watch(() => route.fullPath, load, { immediate: true })
const show = (p) => (p.name === 'docstatus' ? docState(p.value) : fmt(p.value, p.unit))
const ORDER = ['item_code', 'qty', 'delivered_qty', 'received_qty', 'rejected_qty', 'rate', 'amount', 'warehouse',
  'delivery_date', 'schedule_date', 'against_sales_order', 'purchase_order']
const HIDE = ['name', 'purchase_order_item']
function columns(lines) {
  const keys = new Set(lines.flatMap((l) => Object.keys(l)))
  return [...ORDER.filter((k) => keys.has(k)), ...[...keys].filter((k) => !ORDER.includes(k) && !HIDE.includes(k))]
}
</script>

<template>
  <p v-if="error" class="err">{{ error }}</p>
  <template v-if="o">
    <p class="muted small"><RouterLink :to="`/objects?type=${o.type}`">{{ o.label }}</RouterLink> · {{ o.source }}</p>
    <h1>{{ o.title }} <span v-if="o.deleted" class="tag">deleted in ERPNext</span></h1>
    <div class="actions" v-if="DRAFT[o.type] && !o.deleted">
      <button @click="draft">{{ DRAFT[o.type][1] }}</button><span class="muted small">{{ drafting }}</span>
    </div>
    <ul v-if="o.anomalies.length" class="anoms">
      <li v-for="a in o.anomalies" :key="a.id" :class="a.severity">
        <span class="sev">{{ a.severity }}</span> <RouterLink :to="`/anomalies/${a.id}`">{{ a.title }}</RouterLink>
      </li>
    </ul>
    <div class="cols">
      <section>
        <h2>Details</h2>
        <table class="props">
          <template v-for="p in o.props" :key="p.name">
            <tr v-if="p.type !== 'json'"><th>{{ p.label }}</th><td>{{ show(p) }}</td></tr>
          </template>
        </table>
        <template v-for="p in o.props" :key="'j' + p.name">
          <template v-if="p.name === 'lines' && p.value.length">
            <h3>{{ p.label }}</h3>
            <table class="grid small">
              <thead><tr><th v-for="k in columns(p.value)" :key="k">{{ k.replaceAll('_', ' ') }}</th></tr></thead>
              <tbody><tr v-for="(l, i) in p.value" :key="i">
                <td v-for="k in columns(p.value)" :key="k">
                  <RouterLink v-if="k === 'item_code'" :to="objectPath('Item', l[k])">{{ l[k] }}</RouterLink>
                  <RouterLink v-else-if="k === 'against_sales_order' && l[k]" :to="objectPath('SalesOrder', l[k])">{{ l[k] }}</RouterLink>
                  <RouterLink v-else-if="k === 'purchase_order' && l[k]" :to="objectPath('PurchaseOrder', l[k])">{{ l[k] }}</RouterLink>
                  <template v-else>{{ fmt(l[k]) === 'unknown' ? '' : fmt(l[k]) }}</template>
                </td></tr></tbody>
            </table>
          </template>
          <p v-else-if="p.type === 'json' && p.name !== 'lines'"><b>{{ p.label }}:</b> {{ Array.isArray(p.value) ? p.value.join(', ') : p.value }}</p>
        </template>
      </section>
      <section>
        <h2>Related</h2>
        <p v-if="!o.relations.length" class="muted">No related objects.</p>
        <div v-for="g in o.relations" :key="g.direction + g.link + g.type" class="rel-group">
          <h4>{{ g.label }} <span class="muted small">({{ g.objects.length }})</span></h4>
          <ul class="list small">
            <li v-for="x in g.objects.slice(0, 30)" :key="x.key">
              <RouterLink :to="objectPath(x.type, x.key)">{{ x.title }}</RouterLink>
              <span v-if="!x.known" class="muted"> (not synced)</span></li>
          </ul>
        </div>
      </section>
    </div>
    <section v-if="explain"><h2>Causes and impact</h2><Chain :explain="explain" /></section>
    <section>
      <h2>History</h2>
      <ul class="list small">
        <li v-for="(h, i) in o.history" :key="i"><b>{{ h.kind }}</b> {{ h.at === 'manifest' ? 'from the company manifest' : h.at }}
          <span v-for="(c, k) in (h.kind === 'created' ? {} : h.changes)" :key="k" class="muted"> · {{ k }}<template v-if="c !== 'changed'">: {{ fmt(c.from) }} → {{ fmt(c.to) }}</template></span>
        </li>
      </ul>
    </section>
  </template>
</template>
