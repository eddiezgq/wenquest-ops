<script setup>
// Production records (ADR-0017, 17i): controlled templates of steps per ERPNext item, and a production record per lot
// started from the active template, recorded step by step and released or rejected by Quality.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { t } from '../i18n'

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
const active = computed(() => (v.value?.templates || []).filter((x) => x.status === 'active'))
async function go(path, body, to) {
  error.value = ''
  try { const r = await api(path, { method: 'POST', body }); router.push(to(r)) } catch (e) { error.value = e.message }
}
const start = () => go('/api/production/records', { ...lot.value, template_id: Number(lot.value.template_id), planned_qty: Number(lot.value.planned_qty) }, (r) => `/quality/production/${r.id}`)
const draft = () => go('/api/production/templates', tpl.value, (r) => `/quality/production/templates/${r.id}`)
</script>

<template>
  <PageTop :crumbs="[{ label: t('Quality'), to: '/quality' }]">
    <template #title>{{ t('Production records') }}</template>
    <Button icon-left="lucide-barcode" :label="t('Device identifiers')" @click="$router.push('/quality/udi')" />
    <div v-if="v?.can_edit" class="flex gap-2">
      <Button variant="solid" icon-left="lucide-plus" :label="t('Start a lot')" @click="show = show === 'lot' ? '' : 'lot'" />
      <Button icon-left="lucide-plus" :label="t('New template')" @click="show = show === 'tpl' ? '' : 'tpl'" />
    </div>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <form v-if="show === 'lot'" class="lot wq-panel mb-5 flex flex-wrap items-end gap-3 p-5" @submit.prevent="start">
    <label class="wq-field">{{ t('Template') }}<select v-model="lot.template_id" class="wq-select"><option value="" />
      <option v-for="tp in active" :key="tp.id" :value="tp.id">{{ tp.code }} v{{ tp.version }} · {{ tp.item_code }}</option></select></label>
    <label class="wq-field">{{ t('Lot or serial number') }}<input v-model="lot.lot_no" class="wq-input"></label>
    <label class="wq-field w-28">{{ t('Quantity planned') }}<input v-model="lot.planned_qty" type="number" min="1" class="wq-input"></label>
    <label class="wq-field">{{ t('ERPNext work order') }}<input v-model="lot.work_order" class="wq-input" :placeholder="t('optional')"></label>
    <Button type="submit" variant="solid" :label="t('Start')" :disabled="!lot.template_id || !lot.lot_no.trim()" />
    <p v-if="!active.length" class="basis-full text-sm text-ink-gray-6">{{ t('No active template yet: draft one and have Quality activate it.') }}</p>
  </form>
  <form v-if="show === 'tpl'" class="tpl wq-panel mb-5 flex flex-wrap items-end gap-3 p-5" @submit.prevent="draft">
    <label class="wq-field w-36">{{ t('Code') }}<input v-model="tpl.code" class="wq-input"></label>
    <label class="wq-field">{{ t('Item (ERPNext)') }}<select v-model="tpl.item_code" class="wq-select"><option value="" /><option v-for="i in v?.items" :key="i.item_code" :value="i.item_code">{{ i.item_code }} · {{ i.name }}</option></select></label>
    <label class="wq-field grow">{{ t('Title') }}<input v-model="tpl.title" class="wq-input"></label>
    <Button type="submit" variant="solid" :label="t('verb::Draft')" :disabled="!tpl.code.trim() || !tpl.item_code" />
  </form>

  <template v-if="v">
    <section data-help="production-records" class="records wq-panel mb-5 p-5">
      <div class="mb-3"><select v-model="status" class="wq-select w-40"><option value="open">{{ t('status::Open') }}</option><option value="released">{{ t('Released') }}</option><option value="rejected">{{ t('Rejected') }}</option><option value="cancelled">{{ t('Cancelled') }}</option><option value="all">{{ t('All') }}</option></select></div>
      <p v-if="!v.records.length" class="wq-muted">{{ t('None.') }}</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Record') }}</th><th>{{ t('Item') }}</th><th>{{ t('Lot') }}</th><th>{{ t('Status') }}</th><th>{{ t('Planned') }}</th><th>{{ t('Good') }}</th><th>{{ t('Work order') }}</th><th>{{ t('Started') }}</th></tr></thead>
        <tbody><tr v-for="r in v.records" :key="r.id">
          <td><RouterLink :to="`/quality/production/${r.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ r.name }}</RouterLink></td>
          <td>{{ r.item_code }}</td><td>{{ r.lot_no }}</td><td><Badge :theme="ST[r.status]" :label="t(r.status.replace('_', ' '))" /></td>
          <td>{{ r.planned_qty }}</td><td>{{ r.good_qty }}</td><td>{{ r.work_order }}</td><td>{{ r.created_at.slice(0, 10) }}</td></tr></tbody></table>
    </section>
    <section data-help="production-templates" class="templates wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Templates') }}</h2>
      <p v-if="!v.templates.length" class="wq-muted">{{ t('None.') }}</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Code') }}</th><th>{{ t('Version') }}</th><th>{{ t('Item') }}</th><th>{{ t('Title') }}</th><th>{{ t('Status') }}</th><th>{{ t('Steps') }}</th></tr></thead>
        <tbody><tr v-for="tp in v.templates" :key="tp.id">
          <td><RouterLink :to="`/quality/production/templates/${tp.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ tp.code }}</RouterLink></td>
          <td>{{ tp.version }}</td><td>{{ tp.item_code }}</td><td>{{ tp.title }}</td><td><Badge :theme="ST[tp.status]" :label="t(tp.status)" /></td><td>{{ tp.steps }}</td></tr></tbody></table>
    </section>
  </template>
</template>
