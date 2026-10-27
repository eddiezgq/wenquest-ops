<script setup>
// The production record of one lot (ADR-0017, 17i): steps recorded in order with the operator's password and judged
// by code; materials from released incoming lots; released or rejected by Quality with a signature.
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import DeviceLabel from '../components/DeviceLabel.vue'
import { api } from '../api'
import { t } from '../i18n'

const route = useRoute()
const r = ref(null)
const error = ref('')
const done = ref('')
const q = ref({ good_qty: 0, scrap_qty: 0, work_order: '' })
const s = ref({ value: '', result: 'pass', text: '', gauge_id: '', password: '' })
const m = ref({ inspection_id: '', qty: '' })
const x = ref({ password: '', reason: '', cancel: '' })
const ST = { in_production: 'blue', qa_review: 'amber', released: 'green', rejected: 'red', cancelled: 'gray' }
const VT = { pass: 'green', fail: 'red' }

function set(v) { r.value = v; q.value = { good_qty: v.good_qty, scrap_qty: v.scrap_qty, work_order: v.work_order || '' } }
async function load() { error.value = ''; try { set(await api(`/api/production/records/${route.params.id}`)) } catch (e) { error.value = e.message } }
watch(() => route.params.id, load, { immediate: true })
async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { set(await api(path, { method, body })); done.value = message; return true } catch (e) { error.value = e.message }
}
const producing = () => r.value?.status === 'in_production' && r.value?.can_edit
const next = () => r.value?.steps.find((st) => st.seq === r.value.next_step)
async function record() {
  const st = next()
  const body = { password: s.value.password }
  if (st.kind === 'measure') { body.value = s.value.value; if (s.value.gauge_id) body.gauge_id = Number(s.value.gauge_id) }
  if (st.kind === 'check') body.result = s.value.result
  if (st.kind === 'record') body.text = s.value.text
  if (await call(`/api/production/records/${r.value.id}/steps/${st.seq}`, 'POST', body, t('Step {n} recorded.', { n: st.seq }))) s.value = { value: '', result: 'pass', text: '', gauge_id: '', password: '' }
}
async function material() {
  if (await call(`/api/production/records/${r.value.id}/materials`, 'POST', { inspection_id: Number(m.value.inspection_id), qty: m.value.qty }, t('Material recorded.'))) m.value = { inspection_id: '', qty: '' }
}
const saveQty = () => call(`/api/production/records/${r.value.id}`, 'PUT', { good_qty: Number(q.value.good_qty), scrap_qty: Number(q.value.scrap_qty), work_order: q.value.work_order }, t('Saved.'))
const act = async (a, body, msg) => { if (await call(`/api/production/records/${r.value.id}/${a}`, 'POST', body, msg)) x.value = { password: '', reason: '', cancel: '' } }
</script>

<template>
  <PageTop :crumbs="[{ label: t('Production records'), to: '/quality/production' }]">
    <template #title>{{ r ? t('{name} · {item} lot {lot}', { name: r.name, item: r.item_code, lot: r.lot_no }) : t('Production record') }}</template>
    <RouterLink v-if="r" :to="`/quality/trace?record=${r.id}`"><Button icon-left="lucide-route" :label="t('Trace')" /></RouterLink>
    <Badge v-if="r" :theme="ST[r.status]" size="lg" :label="t(r.status.replace('_', ' '))" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="r">
    <p v-if="r.on_hold.length" class="wq-error mb-4">{{ t('Held: equipment it used was found out of tolerance ({list}); the assessment must be signed first.', { list: r.on_hold.join(', ') }) }}</p>
    <p v-if="r.intact === false" class="wq-error mb-4">{{ t('This record no longer matches what was signed.') }}</p>
    <p v-if="r.recalls?.length" class="wq-error mb-4">{{ t('In a recall:') }} <RouterLink v-for="rc in r.recalls" :key="rc.id" :to="`/quality/recalls/${rc.id}`" class="wq-link me-2">{{ rc.name }} ({{ t(rc.status) }})</RouterLink></p>
    <p class="mb-4 text-sm text-ink-gray-6">{{ t('Template') }} <RouterLink :to="`/quality/production/templates/${r.template.id}`" class="wq-link">{{ r.template.code }} v{{ r.template.version }}</RouterLink>
      <span v-if="r.template.documents.length"> · {{ t('follows {list}', { list: r.template.documents.join(', ') }) }}</span></p>

    <section class="steps wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Steps') }}</h2>
      <table class="wq-table text-sm"><thead><tr><th>#</th><th>{{ t('Step') }}</th><th>{{ t('Limits') }}</th><th>{{ t('Result') }}</th><th>{{ t('Equipment') }}</th><th>{{ t('By') }}</th><th>{{ t('Nonconformance') }}</th></tr></thead>
        <tbody><tr v-for="st in r.steps" :key="st.id" :class="st.seq === r.next_step ? 'bg-surface-gray-2' : ''">
          <td>{{ st.seq }}</td><td>{{ st.name }}<p v-if="st.instruction" class="text-xs text-ink-gray-5">{{ st.instruction }}</p></td><td>{{ st.limits }}</td>
          <td><template v-if="st.verdict"><span v-if="st.kind === 'measure'">{{ st.value }} {{ st.unit }} </span><span v-if="st.kind === 'record'">{{ st.text_value }} </span><Badge :theme="VT[st.verdict]" :label="t(st.verdict)" /></template></td>
          <td>{{ st.gauge_code }}</td><td>{{ st.done_by }}<span v-if="st.done_at" class="text-xs text-ink-gray-5"> {{ st.done_at.slice(0, 16).replace('T', ' ') }}</span></td>
          <td><RouterLink v-if="st.ncr_id" :to="`/quality/ncr/${st.ncr_id}`" class="wq-link me-2">{{ st.ncr_name }} ({{ t(st.ncr_status) }})</RouterLink>
            <Button v-if="st.verdict === 'fail' && (!st.ncr_id || st.ncr_status === 'cancelled') && r.can_edit && ['in_production', 'qa_review'].includes(r.status)" size="sm" :label="t('Open a nonconformance')" @click="call(`/api/production/records/${r.id}/steps/${st.seq}/ncr`, 'POST', null, t('Nonconformance report opened.'))" /></td>
        </tr></tbody></table>
      <form v-if="producing() && next()" data-help="production-record-step" class="record mt-4 flex flex-wrap items-end gap-3" @submit.prevent="record">
        <span class="text-sm font-medium">{{ t('Step {n}: {name}', { n: next().seq, name: next().name }) }}</span>
        <template v-if="next().kind === 'measure'">
          <label class="wq-field w-32">{{ t('Reading {unit}', { unit: next().unit }) }}<input v-model="s.value" class="wq-input" inputmode="decimal"></label>
          <label class="wq-field">{{ t('Equipment') }}<select v-model="s.gauge_id" class="wq-select"><option value="">{{ next().gauge_required ? t('(required)') : '' }}</option><option v-for="g in r.gauges" :key="g.id" :value="g.id">{{ g.code }} {{ g.name }}</option></select></label>
        </template>
        <label v-if="next().kind === 'check'" class="wq-field">{{ t('Result') }}<select v-model="s.result" class="wq-select"><option value="pass">{{ t('pass') }}</option><option value="fail">{{ t('fail') }}</option></select></label>
        <label v-if="next().kind === 'record'" class="wq-field grow">{{ t('What was done') }}<input v-model="s.text" class="wq-input"></label>
        <input v-model="s.password" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
        <Button type="submit" variant="solid" :label="t('Record (sign)')" :disabled="!s.password" />
      </form>
    </section>

    <section data-help="production-materials" class="materials wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Materials') }}</h2>
      <p v-if="r.template.materials.length" class="mb-2 text-sm text-ink-gray-6">{{ t('Each lot records: {list}.', { list: r.template.materials.join(', ') }) }}</p>
      <p v-if="!r.materials.length" class="wq-muted">{{ t('None recorded.') }}</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Item') }}</th><th>{{ t('Incoming lot') }}</th><th>{{ t('Supplier') }}</th><th>{{ t('Quantity') }}</th><th>{{ t('By') }}</th></tr></thead>
        <tbody><tr v-for="mm in r.materials" :key="mm.id"><td>{{ mm.item_code }}</td><td><RouterLink :to="`/quality/iqc/${mm.inspection_id}`" class="wq-link">{{ mm.lot_no || mm.inspection_id }}</RouterLink></td><td>{{ mm.supplier }}</td><td>{{ mm.qty }}</td><td>{{ mm.added_by }}</td></tr></tbody></table>
      <form v-if="producing()" class="mt-3 flex flex-wrap items-end gap-3" @submit.prevent="material">
        <label class="wq-field">{{ t('Released incoming lot') }}<select v-model="m.inspection_id" class="wq-select"><option value="" />
          <option v-for="l in r.lots" :key="l.id" :value="l.id">{{ l.item_code }} · {{ l.lot_no || l.name }} · {{ l.supplier }} ({{ t('{n} left', { n: l.left_qty }) }})</option></select></label>
        <label class="wq-field w-28">{{ t('Quantity used') }}<input v-model="m.qty" class="wq-input" inputmode="decimal"></label>
        <Button type="submit" :label="t('Add')" :disabled="!m.inspection_id || !m.qty" />
      </form>
    </section>

    <section data-help="production-qty" class="qty wq-panel mb-5 flex flex-wrap items-end gap-3 p-5">
      <span class="text-sm">{{ t('Planned {n}', { n: r.planned_qty }) }}</span>
      <label class="wq-field w-28">{{ t('Good') }}<input v-model="q.good_qty" type="number" min="0" class="wq-input" :disabled="!producing()"></label>
      <label class="wq-field w-28">{{ t('Scrapped') }}<input v-model="q.scrap_qty" type="number" min="0" class="wq-input" :disabled="!producing()"></label>
      <label class="wq-field">{{ t('ERPNext work order') }}<input v-model="q.work_order" class="wq-input" :disabled="!producing()"></label>
      <Button v-if="producing()" :label="t('Save')" @click="saveQty" />
    </section>

    <section v-if="r.can_edit && ['in_production', 'qa_review'].includes(r.status)" data-help="production-decide" class="decide wq-panel mb-5 p-5">
      <template v-if="r.status === 'in_production'">
        <p v-if="r.to_submit.length" class="mb-2 text-sm text-ink-gray-6">{{ t('To submit: {list}.', { list: r.to_submit.join('; ') }) }}</p>
        <Button variant="solid" :label="t('Submit for review')" :disabled="!!r.to_submit.length" @click="act('submit', {}, t('Submitted for review.'))" />
        <details v-if="r.can_configure" class="mt-3"><summary class="cursor-pointer text-sm text-ink-gray-7">{{ t('Cancel the record') }}</summary>
          <div class="mt-2 flex gap-2"><input v-model="x.cancel" class="wq-input w-96" :placeholder="t('Why')"><Button :label="t('Cancel')" :disabled="!x.cancel.trim()" @click="act('cancel', { reason: x.cancel }, t('Cancelled.'))" /></div></details>
      </template>
      <template v-else-if="r.can_configure">
        <p v-if="r.to_release.length" class="mb-2 text-sm text-ink-gray-6">{{ t('To release: {list}.', { list: r.to_release.join('; ') }) }}</p>
        <div class="flex flex-wrap items-end gap-2">
          <input v-model="x.password" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
          <input v-model="x.reason" class="wq-input w-72" :placeholder="t('Note (the reason, to reject)')">
          <Button variant="solid" :label="t('Release (sign)')" :disabled="!x.password || !!r.to_release.length" @click="act('release', { password: x.password, reason: x.reason }, t('Released.'))" />
          <Button theme="red" :label="t('Reject (sign)')" :disabled="!x.password || !x.reason.trim()" @click="act('reject', { password: x.password, reason: x.reason }, t('Rejected.'))" />
          <Button :label="t('Send back')" :disabled="!x.reason.trim()" @click="act('send-back', { reason: x.reason }, t('Sent back to production.'))" />
        </div>
        <p class="mt-2 text-sm text-ink-gray-5">{{ t('Released or rejected by someone who recorded no step or material in it.') }}</p>
      </template>
    </section>
    <p v-if="r.decision_note" class="mb-4 text-sm">{{ t('Decision: {note}', { note: r.decision_note }) }}</p>
    <DeviceLabel v-if="r.status === 'released'" :record-id="r.id" />
    <p v-if="r.fingerprint" class="mb-4 text-xs text-ink-gray-5">{{ t('Fingerprint {fp}', { fp: r.fingerprint }) }}</p>
    <h2 class="wq-h2 mt-6">{{ t('Signatures') }}</h2>
    <Trail :items="r.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
    <Trail :items="r.history" />
  </template>
</template>
