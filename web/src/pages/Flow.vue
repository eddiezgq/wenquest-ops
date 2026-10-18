<script setup>
// Process flow charts (ADR-0022, 22d): each a controlled document - drafted, approved by someone else, then fixed.
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'

const router = useRouter()
const v = ref(null)
const error = ref('')
const status = ref('current')
const show = ref(false)
const f = ref({ title: '', item_code: '', scope: '', owner: '' })
const ST = { draft: 'gray', approved: 'green', superseded: 'gray', withdrawn: 'gray' }

async function load() { try { v.value = await api(`/api/flow?status=${status.value}`) } catch (e) { error.value = e.message } }
watch(status, load, { immediate: true })
async function create() {
  error.value = ''
  try { const r = await api('/api/flow/charts', { method: 'POST', body: f.value }); router.push(`/quality/flow/${r.id}`) } catch (e) { error.value = e.message }
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality', to: '/quality' }]">
    <template #title>Process flow</template>
    <Button v-if="v?.can_edit" variant="solid" icon-left="lucide-plus" label="New flow chart" @click="show = !show" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <form v-if="show" class="wq-panel mb-5 grid gap-3 p-5 md:grid-cols-3" @submit.prevent="create">
    <label class="wq-field md:col-span-2">Process<input v-model="f.title" class="wq-input"></label>
    <label class="wq-field">Item code<input v-model="f.item_code" class="wq-input" placeholder="the item it makes, if one"></label>
    <label class="wq-field md:col-span-2">Scope<input v-model="f.scope" class="wq-input"></label>
    <label class="wq-field">Owner<select v-model="f.owner" class="wq-select"><option value="" /><option v-for="p in v?.people" :key="p">{{ p }}</option></select></label>
    <div><Button type="submit" variant="solid" label="Start" :disabled="!f.title.trim()" /></div>
  </form>
  <section v-if="v" data-help="flow-charts" class="wq-panel p-5">
    <p class="mb-3 max-w-3xl text-base text-ink-gray-6">Each flow chart draws a process step by step and links each step to its work instructions, PFMEA rows,
      inspection plan, production template and measuring equipment. It is the backbone of the PFMEA.</p>
    <div class="mb-3"><select v-model="status" class="wq-select w-40"><option value="current">Current</option><option value="draft">Drafts</option><option value="approved">Approved</option><option value="all">All versions</option></select></div>
    <p v-if="!v.charts.length" class="wq-muted">None.</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>Number</th><th>Version</th><th>Process</th><th>Item</th><th>Status</th><th>Steps</th><th>Approved</th></tr></thead>
      <tbody><tr v-for="r in v.charts" :key="r.id">
        <td><RouterLink :to="`/quality/flow/${r.id}`" class="wq-link font-medium">{{ r.name }}</RouterLink></td>
        <td>{{ r.version }}</td><td>{{ r.title }}</td><td>{{ r.item_code || '' }}</td><td><Badge :theme="ST[r.status]" :label="r.status" /></td>
        <td>{{ r.steps }}</td><td>{{ r.approved_at ? `${r.approved_at.slice(0, 10)} · ${r.approved_by}` : '' }}</td></tr></tbody></table>
  </section>
</template>
