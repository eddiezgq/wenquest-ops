<script setup>
// Recalls (ADR-0017, 17i): drafted from a trace or here, opened with the consignee list from ERPNext, closed with a
// signature.
import { ref, watch } from 'vue'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'

const v = ref(null)
const error = ref('')
const status = ref('open')
const ST = { draft: 'gray', open: 'red', closed: 'green', cancelled: 'gray' }
async function load() { try { v.value = await api(`/api/recalls?status=${status.value}`) } catch (e) { error.value = e.message } }
watch(status, load, { immediate: true })
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality', to: '/quality' }]">
    <template #title>Recalls</template>
    <RouterLink to="/quality/trace"><Button icon-left="lucide-route" label="Trace a lot" /></RouterLink>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <section v-if="v" class="wq-panel p-5">
    <p class="wq-muted mb-3 max-w-3xl">A recall starts from a trace: trace the lot, then <i>Start a recall of these lots</i>.</p>
    <div class="mb-3"><select v-model="status" class="wq-select w-40"><option value="open">Draft and open</option><option value="closed">Closed</option><option value="cancelled">Cancelled</option><option value="all">All</option></select></div>
    <p v-if="!v.recalls.length" class="wq-muted">None.</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>Number</th><th>Title</th><th>Class</th><th>Status</th><th>Owner</th><th>Opened</th></tr></thead>
      <tbody><tr v-for="r in v.recalls" :key="r.id">
        <td><RouterLink :to="`/quality/recalls/${r.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ r.name }}</RouterLink></td>
        <td>{{ r.title }}</td><td>{{ r.classification }}</td><td><Badge :theme="ST[r.status]" :label="r.status" /></td><td>{{ r.owner }}</td><td>{{ r.opened_at?.slice(0, 10) }}</td></tr></tbody></table>
  </section>
</template>
