<script setup>
// One piece of measuring equipment (ADR-0017, 17f): its details, calibrations (approved by someone else, signed),
// and what it measured when it was found out of tolerance (assessed, signed).
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { ago } from '../format'
import { t } from '../i18n'

const route = useRoute()
const g = ref(null)
const error = ref('')
const done = ref('')
const n = new Date()
const today = `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`
const cal = ref({ done_on: today, done_by: '', certificate: '', result: 'pass', as_found: '', as_left: '' })
const pw = ref({})
const imp = ref({})
const reason = ref('')
const ST = { in_service: 'green', out_of_service: 'amber', retired: 'gray' }
async function load() { try { g.value = await api(`/api/gauges/${route.params.id}`) } catch (e) { error.value = e.message } }
watch(() => route.params.id, load, { immediate: true })
async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { g.value = await api(path, { method, body }); done.value = message; pw.value = {} } catch (e) { error.value = e.message }
}
const record = () => call(`/api/gauges/${g.value.id}/calibrations`, 'POST', cal.value, t('Calibration recorded: someone else approves it.'))
const approve = (c) => call(`/api/gauge-calibrations/${c.id}/approve`, 'POST', { password: pw.value[`c${c.id}`] }, t('Approved.'))
const assess = (i) => call(`/api/gauge-impacts/${i.id}/assess`, 'POST', { password: pw.value[`i${i.id}`], conclusion: imp.value[i.id]?.text || '', open_ncr: !!imp.value[i.id]?.ncr }, t('Assessed.'))
</script>

<template>
  <PageTop :crumbs="[{ label: t('Measuring equipment'), to: '/quality/gauges' }]">
    <template #title>{{ g ? `${g.code} · ${g.name}` : t('Equipment') }}</template>
    <Badge v-if="g" :theme="ST[g.status]" size="lg" :label="t(g.status.replaceAll('_', ' '))" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="g">
    <section class="wq-panel mb-5 p-5 text-sm">
      <p data-help="gauge-usable" class="mb-2 text-base" :class="g.usable ? 'text-ink-green-7' : 'text-ink-amber-7'">{{ g.usable ? t('Can be used: ') : t('Cannot be used: ') }}{{ g.why }}</p>
      <p class="text-ink-gray-7">{{ [g.kind, g.range_text, g.location, t('calibrated every {n} months', { n: g.interval_months })].filter(Boolean).join(' · ') }}
        <template v-if="g.acceptance"> · {{ t('acceptance: {x}', { x: g.acceptance }) }}</template><template v-if="g.traceability"> · {{ t('traceable to {x}', { x: g.traceability }) }}</template></p>
      <p v-if="g.retired_reason" class="text-ink-gray-7">{{ t('Retired: {reason}', { reason: g.retired_reason }) }}</p>
    </section>

    <section v-for="i in g.impacts.filter((x) => x.status === 'open')" :key="i.id" data-help="gauge-impact" class="impact mb-5 rounded-5 border border-outline-red-2 bg-surface-red-1 p-5 text-sm">
      <h2 class="wq-h2">{{ t('Found out of tolerance: what it measured') }}</h2>
      <p class="mb-2 text-ink-gray-8">{{ t('{n} incoming inspections since {since}:', { n: i.inspections.length, since: i.since || t('it was registered') }) }}
        <RouterLink v-for="x in i.inspections" :key="x.id" :to="`/quality/iqc/${x.id}`" class="wq-link me-2">{{ x.name }} ({{ x.item_code }}, {{ t(x.result) }})</RouterLink></p>
      <p v-if="i.production?.length" class="mb-2 text-ink-gray-8">{{ t('{n} production lots (held until this is signed):', { n: i.production.length }) }}
        <RouterLink v-for="x in i.production" :key="x.id" :to="`/quality/production/${x.id}`" class="wq-link me-2">{{ t('{name} ({item} lot {lot})', { name: x.name, item: x.item_code, lot: x.lot_no }) }}</RouterLink></p>
      <template v-if="g.can_configure">
        <label class="wq-field">{{ t('Were those results still valid? Conclusion') }}<textarea v-model="(imp[i.id] ||= {}).text" rows="2" class="wq-input" /></label>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <label class="inline-flex items-center gap-1.5"><input v-model="(imp[i.id] ||= {}).ncr" type="checkbox" class="form-checkbox"> {{ t('open a nonconformance report') }}</label>
          <input v-model="pw[`i${i.id}`]" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
          <Button variant="solid" :label="t('Sign the assessment')" :disabled="!pw[`i${i.id}`] || !(imp[i.id]?.text || '').trim()" @click="assess(i)" />
        </div>
      </template>
      <p v-else class="text-ink-gray-7">{{ t('Quality assesses this; until then the equipment stays out of service.') }}</p>
    </section>

    <section class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Calibrations') }}</h2>
      <form v-if="g.can_edit && g.status !== 'retired'" data-help="gauge-record" class="mb-4 grid gap-2 md:grid-cols-6" @submit.prevent="record">
        <label class="wq-field">{{ t('Date') }}<input v-model="cal.done_on" type="date" class="wq-input"></label>
        <label class="wq-field">{{ t('By (in house or laboratory)') }}<input v-model="cal.done_by" class="wq-input"></label>
        <label class="wq-field">{{ t('Certificate') }}<input v-model="cal.certificate" class="wq-input"></label>
        <label class="wq-field">{{ t('Result') }}<select v-model="cal.result" class="wq-select"><option value="pass">{{ t('pass') }}</option><option value="fail">{{ t('fail (out of tolerance)') }}</option></select></label>
        <label class="wq-field">{{ t('As found') }}<input v-model="cal.as_found" class="wq-input"></label>
        <label class="wq-field">{{ t('As left') }}<input v-model="cal.as_left" class="wq-input"></label>
        <div><Button type="submit" :label="t('Record')" :disabled="!cal.done_by.trim()" /></div>
      </form>
      <p v-if="!g.calibrations.length" class="wq-muted">{{ t('None yet.') }}</p>
      <table v-else data-help="gauge-calibrations" class="wq-table text-sm"><thead><tr><th>{{ t('Date') }}</th><th>{{ t('By') }}</th><th>{{ t('Certificate') }}</th><th>{{ t('Result') }}</th><th>{{ t('As found / as left') }}</th><th>{{ t('Status') }}</th><th /></tr></thead>
        <tbody><tr v-for="c in g.calibrations" :key="c.id">
          <td>{{ c.done_on }}</td><td>{{ c.done_by }}</td><td>{{ c.certificate }}</td>
          <td><Badge :theme="c.result === 'pass' ? 'green' : 'red'" :label="c.result === 'pass' ? t('pass') : t('out of tolerance')" /></td>
          <td>{{ [c.as_found, c.as_left].filter(Boolean).join(' / ') }}</td>
          <td>{{ c.status === 'approved' ? t('approved by {by} {when}', { by: c.approved_by, when: ago(c.approved_at) }) : t('recorded by {by}', { by: c.recorded_by }) }}</td>
          <td><div v-if="c.status === 'draft' && g.can_configure" class="flex items-center gap-1">
            <input v-model="pw[`c${c.id}`]" type="password" class="wq-input w-36" :placeholder="t('Your password')" autocomplete="current-password">
            <Button size="sm" variant="solid" :label="t('Approve (sign)')" :disabled="!pw[`c${c.id}`]" @click="approve(c)" /></div></td></tr></tbody></table>
    </section>

    <section v-if="g.impacts.some((x) => x.status === 'assessed')" class="wq-panel mb-5 p-5 text-sm">
      <h2 class="wq-h2">{{ t('Out-of-tolerance assessments') }}</h2>
      <ul><li v-for="i in g.impacts.filter((x) => x.status === 'assessed')" :key="i.id">{{ t('{when} by {by}: {conclusion} ({n} inspections)', { when: ago(i.assessed_at), by: i.assessed_by, conclusion: i.conclusion, n: i.inspections.length }) }}</li></ul>
    </section>
    <section v-if="g.can_configure && g.status !== 'retired'" class="wq-panel mb-5 p-5">
      <details><summary class="cursor-pointer text-sm text-ink-gray-7">{{ t('Retire this equipment') }}</summary>
        <div class="mt-2 flex gap-2"><input v-model="reason" class="wq-input w-96" :placeholder="t('Why')"><Button :label="t('Retire')" :disabled="!reason.trim()" @click="call(`/api/gauges/${g.id}/retire`, 'POST', { reason }, t('Retired.'))" /></div></details>
    </section>
    <section class="wq-panel p-5 text-sm">
      <h2 class="wq-h2">{{ t('History') }}</h2>
      <ul><li v-for="(x, k) in g.history" :key="k" class="text-ink-gray-7">{{ ago(x.at) }} · {{ x.email }} · {{ t(x.action) }}{{ x.note ? `: ${x.note}` : '' }}</li></ul>
    </section>
  </template>
</template>
