<script setup>
// The dashboard in Frappe's design (ADR-0013, 13a). Same numbers and lists as before; only the look changed.
import { onMounted, ref, watch } from 'vue'
import { Badge, PageHeader, PageHeaderTitle, Select, Tooltip } from 'frappe-ui'
import { api, objectPath } from '../api'
import { fmt } from '../format'
import Trend from '../components/Trend.vue'
import Answer from '../components/Answer.vue'

const days = ref(30)
const brief = ref(null)
const data = ref(null)
const active = ref([])
const error = ref('')
const PERIODS = [{ label: 'Last 7 days', value: 7 }, { label: 'Last 30 days', value: 30 }, { label: 'Last 90 days', value: 90 }]

async function load() {
  error.value = ''
  try {
    data.value = await api(`/api/dashboard?days=${days.value}`)
    active.value = await api('/api/anomalies')
    brief.value = await api('/api/brief').catch(() => null)
  } catch (e) {
    error.value = e.message
  }
}
onMounted(load)
watch(days, load)

const unitOf = { on_time_delivery: '%', supplier_on_time: '%', open_nonconformances: '' }
const SEV = { critical: 'red', warn: 'amber', info: 'blue' }
const valueUnit = (m) => (['items', 'inspections', 'open'].includes(m.unit) ? '' : m.unit)
</script>

<template>
  <PageHeader>
    <PageHeaderTitle><h1 class="text-lg font-semibold text-ink-gray-9">Dashboard</h1></PageHeaderTitle>
    <div class="flex items-center gap-3">
      <span v-if="data" class="hidden text-sm text-ink-gray-5 sm:inline">As of {{ data.as_of }}</span>
      <Select v-model="days" :options="PERIODS" class="w-36" />
    </div>
  </PageHeader>

  <p v-if="error" class="mb-4 text-base text-ink-red-7">{{ error }}</p>

  <section v-if="brief" class="brief mb-5 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4">
    <div class="mb-2 flex items-center gap-2">
      <span class="lucide-sun size-4 text-ink-amber-6" />
      <h2 class="text-base font-semibold text-ink-gray-9">Daily brief</h2>
      <span class="text-sm text-ink-gray-5">{{ brief.day }}</span>
    </div>
    <Answer :text="brief.text" class="text-p-base text-ink-gray-8" />
  </section>

  <template v-if="data">
    <p class="mb-3 text-sm text-ink-gray-5">Hover a number to see how it is counted.</p>
    <section class="cards grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <article v-for="m in data.metrics" :key="m.name"
               class="flex flex-col rounded-lg border border-outline-gray-2 bg-surface-base p-4">
        <h3 class="text-sm font-medium text-ink-gray-5">{{ m.label }}</h3>
        <Tooltip :text="m.definition" side="bottom">
          <p class="mt-1 w-fit cursor-help text-3xl font-semibold tracking-tight text-ink-gray-9">
            {{ fmt(m.value, valueUnit(m)) }}</p>
        </Tooltip>
        <p class="mt-1 text-sm text-ink-gray-6">
          <template v-if="m.name === 'on_time_delivery' || m.name === 'supplier_on_time'">
            {{ m.on_time }} of {{ m.total }} on time<span v-if="m.unknown.length">; {{ m.unknown.length }} unknown</span>
          </template>
          <template v-else-if="m.name === 'days_of_inventory'">Shipped {{ fmt(m.shipped_value, 'currency') }} in 90 days</template>
          <template v-else-if="m.name === 'inventory_value'">{{ Object.keys(m.by_warehouse).length }} warehouses</template>
        </p>
        <ul class="mt-3 divide-y divide-outline-gray-1 text-sm">
          <li v-for="o in (m.late || []).slice(0, 5)" :key="o.key" class="flex justify-between gap-3 py-1.5">
            <RouterLink :to="objectPath('SalesOrder', o.key)" class="truncate text-ink-gray-8 hover:underline">{{ o.title }}</RouterLink>
            <span class="shrink-0 text-ink-amber-7">{{ o.days_late }} day{{ o.days_late === 1 ? '' : 's' }} late</span></li>
          <li v-for="i in (m.items || []).slice(0, 5)" :key="i.item" class="flex justify-between gap-3 py-1.5">
            <RouterLink :to="objectPath('Item', i.item)" class="truncate text-ink-gray-8 hover:underline">{{ i.title }}</RouterLink>
            <span class="shrink-0 text-ink-red-7">short {{ fmt(i.short) }}</span></li>
          <li v-for="s in (m.suppliers || []).slice(0, 5)" :key="s.supplier" class="flex justify-between gap-3 py-1.5">
            <span class="truncate text-ink-gray-8">{{ s.supplier }}</span>
            <span class="shrink-0 text-ink-gray-6">{{ fmt(s.value, '%') }} ({{ s.on_time }}/{{ s.total }})</span></li>
          <li v-for="n in (m.ncrs || []).slice(0, 5)" :key="n.key" class="flex justify-between gap-3 py-1.5">
            <RouterLink :to="objectPath('Nonconformance', n.key)" class="truncate text-ink-gray-8 hover:underline">{{ n.title }}</RouterLink>
            <Badge :label="n.status.replace('_', ' ')" class="shrink-0" /></li>
          <li v-for="q in (m.inspections || []).slice(0, 5)" :key="q.key" class="py-1.5">
            <RouterLink :to="objectPath('QualityInspection', q.key)" class="text-ink-gray-8 hover:underline">{{ q.title }}</RouterLink></li>
          <li v-for="(v, w) in (m.by_warehouse || {})" :key="w" class="flex justify-between gap-3 py-1.5">
            <span class="truncate text-ink-gray-8">{{ w }}</span><span class="shrink-0 text-ink-gray-6">{{ fmt(v, 'currency') }}</span></li>
        </ul>
      </article>
    </section>

    <section v-if="Object.keys(data.trends).length" class="mt-6">
      <h2 class="mb-3 text-base font-semibold text-ink-gray-9">Trends</h2>
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Trend v-for="(pts, name) in data.trends" :key="name" :points="pts" :unit="unitOf[name]"
               :label="data.metrics.find((m) => m.name === name)?.label" />
      </div>
    </section>

    <section class="mt-6">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-base font-semibold text-ink-gray-9">Needs attention</h2>
        <RouterLink to="/anomalies" class="text-sm text-ink-gray-5 hover:text-ink-gray-8">All anomalies →</RouterLink>
      </div>
      <p v-if="!active.length" class="text-base text-ink-gray-5">No open anomalies.</p>
      <ul v-else class="anoms divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
        <li v-for="a in active.slice(0, 8)" :key="a.id" class="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
          <Badge :theme="SEV[a.severity] || 'gray'" :label="a.severity" class="w-16 justify-center capitalize" />
          <RouterLink :to="`/anomalies/${a.id}`" class="text-base text-ink-gray-8 hover:underline">{{ a.title }}</RouterLink>
          <span class="text-sm text-ink-gray-5">{{ a.rule_name }}</span>
        </li>
      </ul>
    </section>
  </template>
</template>
