<script setup>
import { onMounted, ref, watch } from 'vue'
import { api, objectPath } from '../api'
import { fmt } from '../format'
import Trend from '../components/Trend.vue'
import Answer from '../components/Answer.vue'

const days = ref(30)
const brief = ref(null)
const data = ref(null)
const active = ref([])
const error = ref('')

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
</script>

<template>
  <div class="head">
    <h1>Dashboard</h1>
    <label class="muted">Period
      <select v-model.number="days"><option :value="7">7 days</option><option :value="30">30 days</option>
        <option :value="90">90 days</option></select>
    </label>
  </div>
  <p v-if="error" class="err">{{ error }}</p>
  <article v-if="brief" class="card brief">
    <h3>Daily brief <span class="muted small">{{ brief.day }}</span></h3>
    <Answer :text="brief.text" />
  </article>
  <template v-if="data">
    <p class="muted">As of {{ data.as_of }}. Hover a number to see how it is counted.</p>
    <section class="cards">
      <article v-for="m in data.metrics" :key="m.name" class="card">
        <h3>{{ m.label }}</h3>
        <p class="big" :title="m.definition">{{ fmt(m.value, ['items', 'inspections', 'open'].includes(m.unit) ? '' : m.unit) }}</p>
        <p class="muted small">
          <template v-if="m.name === 'on_time_delivery' || m.name === 'supplier_on_time'">
            {{ m.on_time }} of {{ m.total }} on time<span v-if="m.unknown.length">; {{ m.unknown.length }} unknown</span>
          </template>
          <template v-else-if="m.name === 'days_of_inventory'">shipped {{ fmt(m.shipped_value, 'currency') }} in 90 days</template>
          <template v-else-if="m.name === 'inventory_value'">{{ Object.keys(m.by_warehouse).length }} warehouses</template>
        </p>
        <ul class="list small">
          <li v-for="o in (m.late || []).slice(0, 5)" :key="o.key">
            <RouterLink :to="objectPath('SalesOrder', o.key)">{{ o.title }}</RouterLink> {{ o.days_late }} days late</li>
          <li v-for="i in (m.items || []).slice(0, 5)" :key="i.item">
            <RouterLink :to="objectPath('Item', i.item)">{{ i.title }}</RouterLink> short {{ fmt(i.short) }}</li>
          <li v-for="s in (m.suppliers || []).slice(0, 5)" :key="s.supplier">{{ s.supplier }}: {{ fmt(s.value, '%') }}
            ({{ s.on_time }}/{{ s.total }})</li>
          <li v-for="n in (m.ncrs || []).slice(0, 5)" :key="n.key">
            <RouterLink :to="objectPath('Nonconformance', n.key)">{{ n.title }}</RouterLink> {{ n.status }}</li>
          <li v-for="q in (m.inspections || []).slice(0, 5)" :key="q.key">
            <RouterLink :to="objectPath('QualityInspection', q.key)">{{ q.title }}</RouterLink></li>
          <li v-for="(v, w) in (m.by_warehouse || {})" :key="w">{{ w }}: {{ fmt(v, 'currency') }}</li>
        </ul>
      </article>
    </section>
    <section class="trends" v-if="Object.keys(data.trends).length">
      <Trend v-for="(pts, name) in data.trends" :key="name" :points="pts" :unit="unitOf[name]"
             :label="data.metrics.find((m) => m.name === name)?.label" />
    </section>
    <section>
      <h2>Needs attention <RouterLink to="/anomalies" class="small">all anomalies</RouterLink></h2>
      <p v-if="!active.length" class="muted">No open anomalies.</p>
      <ul class="anoms">
        <li v-for="a in active.slice(0, 8)" :key="a.id" :class="a.severity">
          <span class="sev">{{ a.severity }}</span>
          <RouterLink :to="`/anomalies/${a.id}`">{{ a.title }}</RouterLink>
          <span class="muted small">{{ a.rule_name }}</span>
        </li>
      </ul>
    </section>
  </template>
</template>
