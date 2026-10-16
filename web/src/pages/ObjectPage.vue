<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { SEV } from '../ui/themes'
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
  <PageTop :title="o ? o.title : 'Object'" :crumbs="o ? [{ label: o.label, to: `/objects?type=${o.type}` }] : []">
    <Badge v-if="o?.deleted" theme="red" label="deleted in ERPNext" />
    <template v-if="o && DRAFT[o.type] && !o.deleted">
      <span v-if="drafting" class="wq-muted max-w-xs truncate">{{ drafting }}</span>
      <Button data-help="object-draft" variant="solid" icon-left="lucide-sparkles" :label="DRAFT[o.type][1]" @click="draft" />
    </template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <template v-if="o">
    <p class="wq-muted mb-4">{{ o.source }}</p>
    <ul v-if="o.anomalies.length" class="anoms wq-panel mb-6 divide-y divide-outline-gray-1">
      <li v-for="a in o.anomalies" :key="a.id" class="flex items-center gap-3 px-4 py-2.5">
        <Badge :theme="SEV[a.severity]" :label="a.severity" class="capitalize" />
        <RouterLink :to="`/anomalies/${a.id}`" class="text-base text-ink-gray-8 hover:underline">{{ a.title }}</RouterLink>
      </li>
    </ul>
    <div class="grid gap-6 lg:grid-cols-[3fr_2fr]">
      <section class="min-w-0">
        <h2 class="wq-h2">Details</h2>
        <dl class="wq-panel wq-dl p-4">
          <template v-for="p in o.props" :key="p.name">
            <template v-if="p.type !== 'json'"><dt>{{ p.label }}</dt><dd>{{ show(p) }}</dd></template>
          </template>
        </dl>
        <template v-for="p in o.props" :key="'j' + p.name">
          <template v-if="p.name === 'lines' && p.value.length">
            <h3 class="wq-h2 mt-6">{{ p.label }}</h3>
            <div class="wq-panel overflow-x-auto">
              <table class="wq-table text-sm">
                <thead><tr><th v-for="k in columns(p.value)" :key="k" class="capitalize">{{ k.replaceAll('_', ' ') }}</th></tr></thead>
                <tbody><tr v-for="(l, i) in p.value" :key="i">
                  <td v-for="k in columns(p.value)" :key="k" class="text-sm">
                    <RouterLink v-if="k === 'item_code'" :to="objectPath('Item', l[k])" class="wq-link">{{ l[k] }}</RouterLink>
                    <RouterLink v-else-if="k === 'against_sales_order' && l[k]" :to="objectPath('SalesOrder', l[k])" class="wq-link">{{ l[k] }}</RouterLink>
                    <RouterLink v-else-if="k === 'purchase_order' && l[k]" :to="objectPath('PurchaseOrder', l[k])" class="wq-link">{{ l[k] }}</RouterLink>
                    <template v-else>{{ fmt(l[k]) === 'unknown' ? '' : fmt(l[k]) }}</template>
                  </td></tr></tbody>
              </table>
            </div>
          </template>
          <p v-else-if="p.type === 'json' && p.name !== 'lines'" class="mt-3 text-base text-ink-gray-8">
            <span class="text-ink-gray-5">{{ p.label }}:</span> {{ Array.isArray(p.value) ? p.value.join(', ') : p.value }}</p>
        </template>
      </section>
      <section class="min-w-0">
        <h2 class="wq-h2">Related</h2>
        <p v-if="!o.relations.length" class="wq-muted">No related objects.</p>
        <div v-for="g in o.relations" :key="g.direction + g.link + g.type" class="wq-panel mb-3 p-4">
          <h4 class="mb-2 text-sm font-medium text-ink-gray-6">{{ g.label }} <span class="text-ink-gray-4">({{ g.objects.length }})</span></h4>
          <ul class="space-y-1 text-sm">
            <li v-for="x in g.objects.slice(0, 30)" :key="x.key">
              <RouterLink :to="objectPath(x.type, x.key)" class="text-ink-gray-8 hover:underline">{{ x.title }}</RouterLink>
              <span v-if="!x.known" class="text-ink-gray-4"> (not synced)</span></li>
          </ul>
        </div>
      </section>
    </div>
    <section v-if="explain" class="mt-8"><h2 class="wq-h2">Causes and impact</h2><Chain :explain="explain" /></section>
    <section class="mt-8">
      <h2 class="wq-h2">History</h2>
      <ol class="wq-panel divide-y divide-outline-gray-1">
        <li v-for="(h, i) in o.history" :key="i" class="px-4 py-2 text-sm">
          <span class="font-medium text-ink-gray-8">{{ h.kind }}</span>
          <span class="text-ink-gray-5"> {{ h.at === 'manifest' ? 'from the company manifest' : h.at }}</span>
          <span v-for="(c, k) in (h.kind === 'created' ? {} : h.changes)" :key="k" class="text-ink-gray-6"> · {{ k }}<template v-if="c !== 'changed'">: {{ fmt(c.from) }} → {{ fmt(c.to) }}</template></span>
        </li>
      </ol>
    </section>
  </template>
</template>
