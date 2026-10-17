<script setup>
// Production records (ADR-0017, 17i): controlled templates of steps per ERPNext item, and a production record per lot
// started from the active template, recorded step by step and released or rejected by Quality.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'

const router = useRouter()
const v = ref(null)
const error = ref('')
const status = ref('open')
const show = ref('')
const lot = ref({ template_id: '', lot_no: '', planned_qty: 1, work_order: '' })
const tpl = ref({ code: '', item_code: '', title: '' })
const ST = { in_production: 'blue', qa_review: 'amber', released: 'green', rejected: 'red', cancelled: 'gray', draft: 'gray', active: 'green', retired: 'gray', withdrawn: 'gray' }
async function load() { try { v.value = await api(`/api/production?status=${status.value}`) } catch (e) { error.value = e.message } }
watch(status, load, { immediate: true })
const active = computed(() => (v.value?.templates || []).filter((t) => t.status === 'active'))
async function go(path, body, to) {
  error.value = ''
  try { const r = await api(path, { method: 'POST', body }); router.push(to(r)) } catch (e) { error.value = e.message }
}
const start = () => go('/api/production/records', { ...lot.value, template_id: Number(lot.value.template_id), planned_qty: Number(lot.value.planned_qty) }, (r) => `/quality/production/${r.id}`)
const draft = () => go('/api/production/templates', tpl.value, (r) => `/quality/production/templates/${r.id}`)
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality', to: '/quality' }]">
    <template #title>Production records</template>
    <Button icon-left="lucide-barcode" label="Device identifiers" @click="$router.push('/quality/udi')" />
    <div v-if="v?.can_edit" class="flex gap-2">
      <Button variant="solid" icon-left="lucide-plus" label="Start a lot" @click="show = show === 'lot' ? '' : 'lot'" />
      <Button icon-left="lucide-plus" label="New template" @click="show = show === 'tpl' ? '' : 'tpl'" />
    </div>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <form v-if="show === 'lot'" class="lot wq-panel mb-5 flex flex-wrap items-end gap-3 p-5" @submit.prevent="start">
    <label class="wq-field">Template<select v-model="lot.template_id" class="wq-select"><option value="" />
      <option v-for="t in active" :key="t.id" :value="t.id">{{ t.code }} v{{ t.version }} · {{ t.item_code }}</option></select></label>
    <label class="wq-field">Lot or serial number<input v-model="lot.lot_no" class="wq-input"></label>
    <label class="wq-field w-28">Quantity planned<input v-model="lot.planned_qty" type="number" min="1" class="wq-input"></label>
    <label class="wq-field">ERPNext work order<input v-model="lot.work_order" class="wq-input" placeholder="optional"></label>
    <Button type="submit" variant="solid" label="Start" :disabled="!lot.template_id || !lot.lot_no.trim()" />
    <p v-if="!active.length" class="basis-full text-sm text-ink-gray-6">No active template yet: draft one and have Quality activate it.</p>
  </form>
  <form v-if="show === 'tpl'" class="tpl wq-panel mb-5 flex flex-wrap items-end gap-3 p-5" @submit.prevent="draft">
    <label class="wq-field w-36">Code<input v-model="tpl.code" class="wq-input"></label>
    <label class="wq-field">Item (ERPNext)<select v-model="tpl.item_code" class="wq-select"><option value="" /><option v-for="i in v?.items" :key="i.item_code" :value="i.item_code">{{ i.item_code }} · {{ i.name }}</option></select></label>
    <label class="wq-field grow">Title<input v-model="tpl.title" class="wq-input"></label>
    <Button type="submit" variant="solid" label="Draft" :disabled="!tpl.code.trim() || !tpl.item_code" />
  </form>

  <template v-if="v">
    <section data-help="production-records" class="records wq-panel mb-5 p-5">
      <div class="mb-3"><select v-model="status" class="wq-select w-40"><option value="open">Open</option><option value="released">Released</option><option value="rejected">Rejected</option><option value="cancelled">Cancelled</option><option value="all">All</option></select></div>
      <p v-if="!v.records.length" class="wq-muted">None.</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>Record</th><th>Item</th><th>Lot</th><th>Status</th><th>Planned</th><th>Good</th><th>Work order</th><th>Started</th></tr></thead>
        <tbody><tr v-for="r in v.records" :key="r.id">
          <td><RouterLink :to="`/quality/production/${r.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ r.name }}</RouterLink></td>
          <td>{{ r.item_code }}</td><td>{{ r.lot_no }}</td><td><Badge :theme="ST[r.status]" :label="r.status.replace('_', ' ')" /></td>
          <td>{{ r.planned_qty }}</td><td>{{ r.good_qty }}</td><td>{{ r.work_order }}</td><td>{{ r.created_at.slice(0, 10) }}</td></tr></tbody></table>
    </section>
    <section data-help="production-templates" class="templates wq-panel mb-5 p-5">
      <h2 class="wq-h2">Templates</h2>
      <p v-if="!v.templates.length" class="wq-muted">None.</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>Code</th><th>Version</th><th>Item</th><th>Title</th><th>Status</th><th>Steps</th></tr></thead>
        <tbody><tr v-for="t in v.templates" :key="t.id">
          <td><RouterLink :to="`/quality/production/templates/${t.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ t.code }}</RouterLink></td>
          <td>{{ t.version }}</td><td>{{ t.item_code }}</td><td>{{ t.title }}</td><td><Badge :theme="ST[t.status]" :label="t.status" /></td><td>{{ t.steps }}</td></tr></tbody></table>
    </section>
  </template>
</template>
