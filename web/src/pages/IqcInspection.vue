<script setup>
// One incoming inspection (ADR-0017, 17b): the readings for each sample unit, signed by the inspector (the lot is
// judged by code), then released or rejected by someone else; the result goes to ERPNext as a draft to confirm.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import MeasurementImport from '../components/MeasurementImport.vue'
import { api, objectPath } from '../api'
import { ago } from '../format'

const route = useRoute()
const v = ref(null)
const error = ref('')
const done = ref('')
const busy = ref('')
const vals = ref({})              // "sample|characteristic" -> value or 'pass' / 'fail' / ''
const password = ref('')
const note = ref('')
const reason = ref('')
const ST = { in_progress: { theme: 'gray', label: 'in progress' }, judged: { theme: 'amber', label: 'signed, to decide' },
  released: { theme: 'green', label: 'released' }, rejected: { theme: 'red', label: 'rejected' }, void: { theme: 'gray', label: 'void' } }
const open = computed(() => v.value?.status === 'in_progress')
const chars = computed(() => v.value?.plan.characteristics || [])
const samples = computed(() => Array.from({ length: v.value?.n || 0 }, (_, i) => i + 1))
const at = computed(() => Object.fromEntries((v.value?.readings || []).map((r) => [`${r.sample}|${r.characteristic}`, r])))
const k = (s, c) => `${s}|${c.name}`

function fill(x) {
  v.value = x
  vals.value = Object.fromEntries(x.readings.map((r) => [`${r.sample}|${r.characteristic}`,
    r.passed === true ? 'pass' : r.passed === false ? 'fail' : r.value ?? '']))
}
const imports = ref([])
async function load() {
  error.value = ''
  try {
    fill(await api(`/api/iqc/inspections/${route.params.id}`))
    imports.value = await api(`/api/iqc/inspections/${route.params.id}/measurements`)
  } catch (e) { error.value = e.message }
}
async function imported(message) { await load(); done.value = message }
const keep = async () => !changed().length || await save()   // readings typed so far are saved before an import
// a gauge that types its reading ends it with Enter: go to the next sample of the same characteristic
function next(s, c) {
  const measured = chars.value.filter((x) => x.kind === 'measured')
  const i = measured.findIndex((x) => x.name === c.name)
  const to = s < samples.value.length ? k(s + 1, c) : measured[i + 1] ? k(1, measured[i + 1]) : null
  if (to) document.querySelector(`[data-cell="${CSS.escape(to)}"]`)?.focus()
}
watch(() => route.params.id, load, { immediate: true })
async function call(key, path, method, body, message) {
  error.value = ''; done.value = ''; busy.value = key
  try { fill(await api(path, { method, body })); done.value = message; return true } catch (e) { error.value = e.message; return false } finally { busy.value = '' }
}
function changed() {
  const out = []
  for (const s of samples.value) {
    for (const c of chars.value) {
      const x = vals.value[k(s, c)]; const r = at.value[k(s, c)]
      const before = r.passed === true ? 'pass' : r.passed === false ? 'fail' : r.value ?? ''
      if (String(x ?? '') === String(before)) continue
      out.push(c.kind === 'attribute' ? { sample: s, characteristic: c.name, passed: x === '' ? null : x === 'pass' }
        : { sample: s, characteristic: c.name, value: String(x ?? '').trim() || null })   // the server checks the number
    }
  }
  return out
}
const save = () => call('save', `/api/iqc/inspections/${v.value.id}/readings`, 'PUT', { readings: changed() }, 'Readings saved.')
async function sign() {                       // the readings on screen are saved first, then signed
  const pw = password.value; password.value = ''
  if (changed().length && !(await save())) return
  await call('sign', `/api/iqc/inspections/${v.value.id}/sign`, 'POST', { password: pw }, 'Signed: the lot is judged.')
}
const decide = () => { const pw = password.value; password.value = ''; return call('decide', `/api/iqc/inspections/${v.value.id}/decide`, 'POST', { password: pw, note: note.value },
  v.value.result === 'accept' ? 'Released. The result is in Drafts for ERPNext.' : 'Rejected. A nonconformance report is open.') }
async function setGauge(c, id) {                  // readings typed so far are saved first, so none are lost
  if (changed().length && !(await save())) return
  await call('gauge', `/api/iqc/inspections/${v.value.id}/gauges`, 'PUT', { characteristic: c.name, gauge_id: id ? Number(id) : null }, 'Equipment noted.')
}
const voidIt = () => call('void', `/api/iqc/inspections/${v.value.id}/void`, 'POST', { reason: reason.value }, 'Void.')
function cls(s, c) {
  const r = at.value[k(s, c)]
  return r?.conforms === false ? 'bg-surface-red-2' : r?.conforms === true ? 'bg-surface-green-1' : ''
}
const limits = (c) => c.kind === 'attribute' ? 'pass / fail' : [c.lsl !== null ? `≥ ${c.lsl}` : '', c.usl !== null ? `≤ ${c.usl}` : ''].filter(Boolean).join(', ') + (c.unit ? ` ${c.unit}` : '')
</script>

<template>
  <PageTop :crumbs="[{ label: 'Incoming inspection', to: '/quality/iqc' }]">
    <template #title>{{ v ? `${v.name} · ${v.item_code}` : 'Inspection' }}</template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="v">
    <section data-help="iqc-summary" class="summary wq-panel mb-5 p-5">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <Badge v-bind="ST[v.status]" />
        <Badge v-if="v.result" :theme="v.result === 'accept' ? 'green' : 'red'" :label="v.result === 'accept' ? 'accept' : 'reject'" />
        <Badge v-if="v.unverified" theme="amber" label="sampling table row not checked" />
        <Badge v-if="v.supplier_standing && v.supplier_standing !== 'approved'" theme="amber" :label="v.supplier_standing" />
      </div>
      <dl class="grid gap-x-6 gap-y-1 text-sm md:grid-cols-3">
        <div><dt class="inline text-ink-gray-5">Lot </dt><dd class="inline">{{ v.lot_no || '–' }}, {{ v.lot_qty }} pieces</dd></div>
        <div><dt class="inline text-ink-gray-5">Supplier </dt><dd class="inline">{{ v.supplier || '–' }}</dd></div>
        <div><dt class="inline text-ink-gray-5">Receipt </dt><dd class="inline"><RouterLink v-if="v.receipt" :to="objectPath('PurchaseReceipt', v.receipt)" class="wq-link">{{ v.receipt }}</RouterLink><template v-else>–</template></dd></div>
        <div><dt class="inline text-ink-gray-5">Plan </dt><dd class="inline"><RouterLink :to="`/quality/iqc/plans/${v.plan.id}`" class="wq-link">version {{ v.plan.version }}</RouterLink>, AQL {{ v.plan.aql }}</dd></div>
        <div><dt class="inline text-ink-gray-5">Sampling </dt><dd class="inline">{{ v.level }} inspection: n {{ v.n }}, Ac {{ v.ac }}, Re {{ v.re }}</dd></div>
        <div v-if="v.defectives !== null"><dt class="inline text-ink-gray-5">Failing units </dt><dd class="inline">{{ v.defectives }} of {{ v.n }}</dd></div>
      </dl>
      <p v-if="v.sampling_row.verified_by" class="mt-1 text-sm text-ink-gray-5">Table row checked against {{ v.sampling_row.source }}.</p>
      <p v-if="v.draft" class="mt-2 text-sm">ERPNext: <RouterLink to="/drafts" class="wq-link">draft #{{ v.draft.id }}</RouterLink> {{ v.draft.status }}<template v-if="v.draft.erp_name"> as {{ v.draft.erp_name }}</template></p>
      <p v-if="v.ncr" class="mt-1 text-sm">Nonconformance: <RouterLink :to="`/quality/ncr/${v.ncr.id}`" class="wq-link">{{ v.ncr.name }}</RouterLink> ({{ v.ncr.status }})</p>
      <p v-if="v.void_reason" class="mt-1 text-sm text-ink-red-7">Void: {{ v.void_reason }}</p>
    </section>

    <section data-help="iqc-readings" class="readings wq-panel mb-5 p-5">
      <h2 class="wq-h2">Readings <span class="text-sm font-normal text-ink-gray-5">{{ v.entered }} of {{ v.readings.length }} entered</span></h2>
      <div class="overflow-x-auto"><table class="wq-table text-sm">
        <thead><tr><th>Sample</th><th v-for="c in chars" :key="c.name">{{ c.name }}<span class="block font-normal text-ink-gray-5">{{ limits(c) }}</span>
          <span v-if="c.kind === 'measured'" class="gauge block font-normal">
            <select v-if="open && v.can_edit" class="wq-select mt-1 w-40" :value="v.gauges[c.name]?.gauge_id ?? ''" @change="setGauge(c, $event.target.value)">
              <option value="">Equipment…</option>
              <option v-if="v.gauges[c.name] && !v.gauge_choices.some((g) => g.id === v.gauges[c.name].gauge_id)" :value="v.gauges[c.name].gauge_id">{{ v.gauges[c.name].gauge_code }} (no longer usable)</option>
              <option v-for="g in v.gauge_choices" :key="g.id" :value="g.id">{{ g.code }} · {{ g.name }}</option></select>
            <span v-else-if="v.gauges[c.name]" class="text-ink-gray-5">with {{ v.gauges[c.name].gauge_code }} (due {{ v.gauges[c.name].next_due }})</span></span></th></tr></thead>
        <tbody><tr v-for="s in samples" :key="s"><td>{{ s }}</td>
          <td v-for="c in chars" :key="c.name" :class="cls(s, c)">
            <template v-if="open && v.can_edit">
              <select v-if="c.kind === 'attribute'" v-model="vals[k(s, c)]" class="wq-select w-24"><option value="" /><option value="pass">pass</option><option value="fail">fail</option></select>
              <input v-else v-model="vals[k(s, c)]" class="wq-input w-24" inputmode="decimal" :data-cell="k(s, c)" @keydown.enter.prevent="next(s, c)">
              <span v-if="at[k(s, c)]?.inbox_id" class="lucide-cpu ms-1 inline-block size-3.5 align-middle text-ink-gray-5" title="Sent by a machine, accepted by a person" aria-label="sent by a machine" />
              <span v-if="at[k(s, c)]?.import_id" class="lucide-file-input ms-1 inline-block size-3.5 align-middle text-ink-gray-5" title="From a measurement file" aria-label="from a measurement file" />
            </template>
            <template v-else>{{ vals[k(s, c)] === '' ? '–' : vals[k(s, c)] }}</template>
          </td></tr></tbody></table></div>
      <div v-if="open && v.can_edit" class="mt-3 flex flex-wrap items-end gap-2">
        <Button label="Save the readings" :loading="busy === 'save'" @click="save" />
        <span class="mx-2 h-8 border-s border-outline-gray-2" />
        <label class="wq-field">Your password to sign<input v-model="password" type="password" class="wq-input w-48" autocomplete="current-password"></label>
        <Button variant="solid" label="Sign (judge the lot)" :disabled="!password" :loading="busy === 'sign'" @click="sign" />
      </div>
    </section>

    <MeasurementImport v-if="open && v.can_edit" :inspection-id="v.id" :gauges="v.gauge_choices" :imports="imports" :before-import="keep" @imported="imported" />
    <section v-else-if="imports.length" class="wq-panel mb-5 p-5 text-sm"><h2 class="wq-h2">Measurement files</h2>
      <p v-for="m in imports" :key="m.id"><a :href="`/api/measurements/${m.id}/file`" class="wq-link">{{ m.file_name }}</a>: {{ m.readings }} readings by {{ m.imported_by }}</p></section>

    <section v-if="v.status === 'judged' && v.can_edit" data-help="iqc-decide" class="decide wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ v.result === 'accept' ? 'Release the lot' : 'Reject the lot' }}</h2>
      <p class="wq-muted mb-3">Signed by {{ v.signed_by }}. Someone other than the inspector decides; the result goes to ERPNext as a draft to confirm<template v-if="v.result !== 'accept'">, and a nonconformance report is opened</template>.
        <template v-if="v.unverified && v.result === 'accept'"> The sampling table row was not checked against its source: say why it is released anyway.</template></p>
      <div class="flex flex-wrap items-end gap-2">
        <label class="wq-field">Note<input v-model="note" class="wq-input w-96"></label>
        <label class="wq-field">Your password<input v-model="password" type="password" class="wq-input w-48" autocomplete="current-password"></label>
        <Button variant="solid" :theme="v.result === 'accept' ? 'green' : 'red'" :label="v.result === 'accept' ? 'Release (sign)' : 'Reject (sign)'" :disabled="!password" :loading="busy === 'decide'" @click="decide" />
      </div>
    </section>

    <section v-if="['in_progress', 'judged'].includes(v.status) && v.can_edit" class="wq-panel mb-5 p-5">
      <details><summary class="cursor-pointer text-sm text-ink-gray-7">Void this inspection (started by mistake)</summary>
        <div class="mt-2 flex flex-wrap items-end gap-2"><label class="wq-field">Reason<input v-model="reason" class="wq-input w-96"></label>
          <Button label="Void" :disabled="!reason.trim()" :loading="busy === 'void'" @click="voidIt" /></div></details>
    </section>

    <section class="wq-panel p-5 text-sm">
      <h2 class="wq-h2">History</h2>
      <ul><li v-for="(x, i) in v.history" :key="i" class="text-ink-gray-7">{{ ago(x.at) }} · {{ x.email }} · {{ x.action }}{{ x.note ? `: ${x.note}` : '' }}</li>
        <li v-for="(s, i) in v.signatures" :key="`s${i}`" class="text-ink-gray-7">{{ ago(s.at) }} · signed by {{ s.name }} ({{ s.email }}): {{ s.meaning }}</li></ul>
      <p v-if="v.level_now" class="mt-3 text-ink-gray-6">{{ v.supplier }} · {{ v.item_code }} is now at {{ v.level_now.level }} inspection<template v-if="v.level_now.suggestion">; the rules suggest: {{ v.level_now.suggestion.reason }}</template>.</p>
    </section>
  </template>
</template>
