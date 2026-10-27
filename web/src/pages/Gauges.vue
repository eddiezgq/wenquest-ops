<script setup>
// Measuring equipment (ADR-0017, 17f): the list, with calibration status; registering new equipment.
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { t } from '../i18n'

const router = useRouter()
const v = ref(null)
const error = ref('')
const show = ref(false)
const f = ref({ code: '', name: '', kind: '', range_text: '', location: '', interval_months: 12, acceptance: '', traceability: '' })
const ST = { in_service: 'green', out_of_service: 'amber', retired: 'gray' }
async function load() { try { v.value = await api('/api/gauges') } catch (e) { error.value = e.message } }
load()
async function add() {
  error.value = ''
  try { const r = await api('/api/gauges', { method: 'POST', body: { ...f.value, interval_months: Number(f.value.interval_months) } }); router.push(`/quality/gauges/${r.id}`) }
  catch (e) { error.value = e.message }
}
</script>

<template>
  <PageTop :crumbs="[{ label: t('Quality'), to: '/quality' }]">
    <template #title>{{ t('Measuring equipment') }}</template>
    <Button v-if="v?.can_edit" variant="solid" icon-left="lucide-plus" :label="t('Register equipment')" @click="show = !show" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <form v-if="show" class="new wq-panel mb-5 grid gap-3 p-5 md:grid-cols-4" @submit.prevent="add">
    <label class="wq-field">{{ t('Equipment ID') }}<input v-model="f.code" class="wq-input"></label>
    <label class="wq-field">{{ t('Name') }}<input v-model="f.name" class="wq-input"></label>
    <label class="wq-field">{{ t('Type') }}<input v-model="f.kind" class="wq-input" :placeholder="t('caliper, gauge, scale…')"></label>
    <label class="wq-field">{{ t('Months between calibrations') }}<input v-model="f.interval_months" type="number" min="1" max="120" class="wq-input"></label>
    <label class="wq-field">{{ t('Range and resolution') }}<input v-model="f.range_text" class="wq-input"></label>
    <label class="wq-field">{{ t('Location') }}<input v-model="f.location" class="wq-input"></label>
    <label class="wq-field">{{ t('Acceptance criteria') }}<input v-model="f.acceptance" class="wq-input"></label>
    <label class="wq-field">{{ t('Traceable to') }}<input v-model="f.traceability" class="wq-input"></label>
    <p class="wq-muted md:col-span-3">{{ t('New equipment is out of service until its first good calibration is approved.') }}</p>
    <div><Button type="submit" variant="solid" :label="t('Register')" :disabled="!f.code.trim() || !f.name.trim()" /></div>
  </form>
  <section v-if="v" data-help="gauges-list" class="wq-panel p-5">
    <p class="wq-muted mb-3">{{ t('Once equipment is registered, incoming inspection names the equipment for each measured characteristic, and only equipment in calibration can be used when the inspector signs.') }}</p>
    <p v-if="!v.gauges.length" class="wq-muted">{{ t('No equipment registered yet.') }}</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('ID') }}</th><th>{{ t('Name') }}</th><th>{{ t('Status') }}</th><th>{{ t('Last good calibration') }}</th><th>{{ t('Next due') }}</th><th>{{ t('Location') }}</th></tr></thead>
      <tbody><tr v-for="g in v.gauges" :key="g.id" :class="g.status === 'retired' ? 'text-ink-gray-4' : ''">
        <td><RouterLink :to="`/quality/gauges/${g.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ g.code }}</RouterLink></td>
        <td>{{ g.name }}</td><td><Badge :theme="ST[g.status]" :label="t(g.status.replaceAll('_', ' '))" /> <Badge v-if="g.open_impacts" theme="red" :label="t('to assess')" /></td>
        <td>{{ g.last_pass || '–' }}</td><td :class="g.overdue ? 'font-medium text-ink-red-7' : ''">{{ g.next_due || '–' }}{{ g.overdue ? ' ' + t('(overdue)') : '' }}</td><td>{{ g.location }}</td></tr></tbody></table>
  </section>
</template>
