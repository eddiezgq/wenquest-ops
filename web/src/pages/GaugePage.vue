<script setup>
// One piece of measuring equipment (ADR-0017, 17f): its details, calibrations (approved by someone else, signed),
// and what it measured when it was found out of tolerance (assessed, signed).
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { ago } from '../format'

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
const record = () => call(`/api/gauges/${g.value.id}/calibrations`, 'POST', cal.value, 'Calibration recorded: someone else approves it.')
const approve = (c) => call(`/api/gauge-calibrations/${c.id}/approve`, 'POST', { password: pw.value[`c${c.id}`] }, 'Approved.')
const assess = (i) => call(`/api/gauge-impacts/${i.id}/assess`, 'POST', { password: pw.value[`i${i.id}`], conclusion: imp.value[i.id]?.text || '', open_ncr: !!imp.value[i.id]?.ncr }, 'Assessed.')
</script>

<template>
  <PageTop :crumbs="[{ label: 'Measuring equipment', to: '/quality/gauges' }]">
    <template #title>{{ g ? `${g.code} · ${g.name}` : 'Equipment' }}</template>
    <Badge v-if="g" :theme="ST[g.status]" size="lg" :label="g.status.replaceAll('_', ' ')" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="g">
    <section class="wq-panel mb-5 p-5 text-sm">
      <p data-help="gauge-usable" class="mb-2 text-base" :class="g.usable ? 'text-ink-green-7' : 'text-ink-amber-7'">{{ g.usable ? 'Can be used: ' : 'Cannot be used: ' }}{{ g.why }}</p>
      <p class="text-ink-gray-7">{{ [g.kind, g.range_text, g.location, `calibrated every ${g.interval_months} months`].filter(Boolean).join(' · ') }}
        <template v-if="g.acceptance"> · acceptance: {{ g.acceptance }}</template><template v-if="g.traceability"> · traceable to {{ g.traceability }}</template></p>
      <p v-if="g.retired_reason" class="text-ink-gray-7">Retired: {{ g.retired_reason }}</p>
    </section>

    <section v-for="i in g.impacts.filter((x) => x.status === 'open')" :key="i.id" data-help="gauge-impact" class="impact mb-5 rounded-5 border border-outline-red-2 bg-surface-red-1 p-5 text-sm">
      <h2 class="wq-h2">Found out of tolerance: what it measured</h2>
      <p class="mb-2 text-ink-gray-8">{{ i.inspections.length }} incoming inspections since {{ i.since || 'it was registered' }}:
        <RouterLink v-for="x in i.inspections" :key="x.id" :to="`/quality/iqc/${x.id}`" class="wq-link me-2">{{ x.name }} ({{ x.item_code }}, {{ x.result }})</RouterLink></p>
      <p v-if="i.production?.length" class="mb-2 text-ink-gray-8">{{ i.production.length }} production lots (held until this is signed):
        <RouterLink v-for="x in i.production" :key="x.id" :to="`/quality/production/${x.id}`" class="wq-link me-2">{{ x.name }} ({{ x.item_code }} lot {{ x.lot_no }})</RouterLink></p>
      <template v-if="g.can_configure">
        <label class="wq-field">Were those results still valid? Conclusion<textarea v-model="(imp[i.id] ||= {}).text" rows="2" class="wq-input" /></label>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <label class="inline-flex items-center gap-1.5"><input v-model="(imp[i.id] ||= {}).ncr" type="checkbox" class="form-checkbox"> open a nonconformance report</label>
          <input v-model="pw[`i${i.id}`]" type="password" class="wq-input w-44" placeholder="Your password" autocomplete="current-password">
          <Button variant="solid" label="Sign the assessment" :disabled="!pw[`i${i.id}`] || !(imp[i.id]?.text || '').trim()" @click="assess(i)" />
        </div>
      </template>
      <p v-else class="text-ink-gray-7">Quality assesses this; until then the equipment stays out of service.</p>
    </section>

    <section class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">Calibrations</h2>
      <form v-if="g.can_edit && g.status !== 'retired'" data-help="gauge-record" class="mb-4 grid gap-2 md:grid-cols-6" @submit.prevent="record">
        <label class="wq-field">Date<input v-model="cal.done_on" type="date" class="wq-input"></label>
        <label class="wq-field">By (in house or laboratory)<input v-model="cal.done_by" class="wq-input"></label>
        <label class="wq-field">Certificate<input v-model="cal.certificate" class="wq-input"></label>
        <label class="wq-field">Result<select v-model="cal.result" class="wq-select"><option value="pass">pass</option><option value="fail">fail (out of tolerance)</option></select></label>
        <label class="wq-field">As found<input v-model="cal.as_found" class="wq-input"></label>
        <label class="wq-field">As left<input v-model="cal.as_left" class="wq-input"></label>
        <div><Button type="submit" label="Record" :disabled="!cal.done_by.trim()" /></div>
      </form>
      <p v-if="!g.calibrations.length" class="wq-muted">None yet.</p>
      <table v-else data-help="gauge-calibrations" class="wq-table text-sm"><thead><tr><th>Date</th><th>By</th><th>Certificate</th><th>Result</th><th>As found / as left</th><th>Status</th><th /></tr></thead>
        <tbody><tr v-for="c in g.calibrations" :key="c.id">
          <td>{{ c.done_on }}</td><td>{{ c.done_by }}</td><td>{{ c.certificate }}</td>
          <td><Badge :theme="c.result === 'pass' ? 'green' : 'red'" :label="c.result === 'pass' ? 'pass' : 'out of tolerance'" /></td>
          <td>{{ [c.as_found, c.as_left].filter(Boolean).join(' / ') }}</td>
          <td>{{ c.status === 'approved' ? `approved by ${c.approved_by} ${ago(c.approved_at)}` : `recorded by ${c.recorded_by}` }}</td>
          <td><div v-if="c.status === 'draft' && g.can_configure" class="flex items-center gap-1">
            <input v-model="pw[`c${c.id}`]" type="password" class="wq-input w-36" placeholder="Your password" autocomplete="current-password">
            <Button size="sm" variant="solid" label="Approve (sign)" :disabled="!pw[`c${c.id}`]" @click="approve(c)" /></div></td></tr></tbody></table>
    </section>

    <section v-if="g.impacts.some((x) => x.status === 'assessed')" class="wq-panel mb-5 p-5 text-sm">
      <h2 class="wq-h2">Out-of-tolerance assessments</h2>
      <ul><li v-for="i in g.impacts.filter((x) => x.status === 'assessed')" :key="i.id">{{ ago(i.assessed_at) }} by {{ i.assessed_by }}: {{ i.conclusion }} ({{ i.inspections.length }} inspections)</li></ul>
    </section>
    <section v-if="g.can_configure && g.status !== 'retired'" class="wq-panel mb-5 p-5">
      <details><summary class="cursor-pointer text-sm text-ink-gray-7">Retire this equipment</summary>
        <div class="mt-2 flex gap-2"><input v-model="reason" class="wq-input w-96" placeholder="Why"><Button label="Retire" :disabled="!reason.trim()" @click="call(`/api/gauges/${g.id}/retire`, 'POST', { reason }, 'Retired.')" /></div></details>
    </section>
    <section class="wq-panel p-5 text-sm">
      <h2 class="wq-h2">History</h2>
      <ul><li v-for="(x, k) in g.history" :key="k" class="text-ink-gray-7">{{ ago(x.at) }} · {{ x.email }} · {{ x.action }}{{ x.note ? `: ${x.note}` : '' }}</li></ul>
    </section>
  </template>
</template>
