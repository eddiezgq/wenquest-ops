<script setup>
// One complaint (ADR-0017, 17e). WenQuest Ops asks the three questions and shows the deadline; the person decides
// whether it must be reported and signs. Reports are made outside WenQuest Ops; their reference is entered here.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import CauseLinks from '../components/CauseLinks.vue'
import { api } from '../api'
import { label } from '../ui/themes'
import { t } from '../i18n'

const route = useRoute()
const c = ref(null)
const error = ref('')
const done = ref('')
const f = ref({})
const a = ref({ answers: {}, reportable: null, reason: '', deadline_id: null, password: '' })
const x = ref({ reason: '', cancel: '', password: '' })
const ST = { new: 'gray', investigation: 'amber', assessed: 'blue', closed: 'green', cancelled: 'gray' }
const EDIT = ['owner', 'item_code', 'lot_no', 'quantity', 'injury', 'malfunction', 'description', 'root_cause', 'investigation', 'response', 'report_ref', 'reported_on']
const open = computed(() => c.value && !['closed', 'cancelled'].includes(c.value.status))
const fixed = computed(() => c.value?.status === 'assessed')
const anyYes = computed(() => Object.values(a.value.answers).includes('yes'))
const people = ref([])

function set(v) {
  c.value = v
  f.value = Object.fromEntries(EDIT.map((k) => [k, v[k] ?? '']))
}
async function load() {
  error.value = ''
  try { set(await api(`/api/complaints/${route.params.id}`)); people.value = (await api('/api/complaints?status=open')).people } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { set(await api(path, { method, body })); done.value = message; a.value.password = ''; x.value = { reason: '', cancel: '', password: '' } } catch (e) { error.value = e.message }
}
function changes() {
  const out = {}
  for (const k of EDIT) if (String(f.value[k] ?? '') !== String(c.value[k] ?? '')) out[k] = f.value[k] === '' ? null : f.value[k]
  return out
}
const save = () => call(`/api/complaints/${c.value.id}`, 'PUT', changes(), t('Saved.'))
const act = (what, body, msg) => call(`/api/complaints/${c.value.id}/${what}`, 'POST', body, msg)
const assess = () => act('assess', { answers: a.value.answers, reportable: a.value.reportable, reason: a.value.reason,
  deadline_id: a.value.deadline_id || null, password: a.value.password }, t('Assessed and signed.'))
const editable = (k) => open.value && c.value.can_edit && !(fixed.value && ['item_code', 'injury', 'malfunction', 'description', 'root_cause', 'investigation'].includes(k))
</script>

<template>
  <PageTop :crumbs="[{ label: t('Complaints'), to: '/quality/complaints' }]">
    <template #title>{{ c ? `${c.name} · ${c.customer}` : t('Complaint') }}</template>
    <Badge v-if="c" :theme="ST[c.status]" size="lg" :label="t(c.status)" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="c">
    <section data-help="complaint-details" class="details wq-panel mb-5 p-5">
      <p class="mb-3 text-sm text-ink-gray-6">{{ t('Received {date} from {source} · company first knew {aware}', { date: c.received_on, source: c.source, aware: c.aware_on }) }}<template v-if="c.contact"> · {{ t('contact {contact}', { contact: c.contact }) }}</template></p>
      <div class="grid gap-3 md:grid-cols-3">
        <label class="wq-field">{{ t('Owner') }}<select v-model="f.owner" class="wq-select" :disabled="!editable('owner')"><option value="" /><option v-for="p in people" :key="p">{{ p }}</option></select></label>
        <label class="wq-field">{{ t('Product (item)') }}<input v-model="f.item_code" class="wq-input" :disabled="!editable('item_code')"></label>
        <label class="wq-field">{{ t('Lot or serial') }}<input v-model="f.lot_no" class="wq-input" :disabled="!editable('lot_no')"></label>
        <label class="wq-field">{{ t('Anyone hurt?') }}<select v-model="f.injury" class="wq-select" :disabled="!editable('injury')"><option value="unknown">{{ t('unknown') }}</option><option value="yes">{{ t('yes') }}</option><option value="no">{{ t('no') }}</option></select></label>
        <label class="wq-field">{{ t('Did the product fail?') }}<select v-model="f.malfunction" class="wq-select" :disabled="!editable('malfunction')"><option value="unknown">{{ t('unknown') }}</option><option value="yes">{{ t('yes') }}</option><option value="no">{{ t('no') }}</option></select></label>
        <label class="wq-field">{{ t('Quantity') }}<input v-model="f.quantity" class="wq-input" :disabled="!editable('quantity')"></label>
        <label class="wq-field md:col-span-3">{{ t('What happened') }}<textarea v-model="f.description" rows="2" class="wq-input" :disabled="!editable('description')" /></label>
        <template v-if="c.status !== 'new'">
          <label class="wq-field md:col-span-3">{{ t('Root cause') }}<textarea v-model="f.root_cause" rows="2" class="wq-input" :disabled="!editable('root_cause')" /></label>
          <label class="wq-field md:col-span-3">{{ t('Investigation and conclusion') }}<textarea v-model="f.investigation" rows="3" class="wq-input" :disabled="!editable('investigation')" /></label>
          <label class="wq-field md:col-span-3">{{ t('Reply to the customer') }}<textarea v-model="f.response" rows="2" class="wq-input" :disabled="!editable('response')" /></label>
        </template>
      </div>
      <p v-if="!c.investigate" class="mt-2 text-sm text-ink-gray-7">{{ t('Not investigated: {reason} (approved by {name})', { reason: c.no_investigation_reason, name: c.no_investigation_by }) }}</p>
      <div v-if="open && c.can_edit" class="mt-3 flex flex-wrap gap-2">
        <Button :label="t('Save')" :disabled="!Object.keys(changes()).length" @click="save" />
        <Button v-if="c.status === 'new'" data-help="complaint-start" variant="solid" :label="t('Start the investigation')" :disabled="!!Object.keys(changes()).length" @click="act('start', {}, t('Investigation started.'))" />
        <Button v-if="!c.ncr" :label="t('Open a nonconformance')" @click="act('ncr', {}, t('Nonconformance opened.'))" />
        <Button v-if="!c.capa" :label="t('Open a corrective action')" @click="act('capa', {}, t('Corrective action opened.'))" />
      </div>
      <p v-if="c.status === 'new' && c.to_investigate.length" class="mt-2 text-sm text-ink-gray-5">{{ t('To start the investigation: {list}.', { list: c.to_investigate.join(', ') }) }}</p>
      <p class="mt-2 text-sm"><template v-if="c.ncr">{{ t('Nonconformance') }} <RouterLink :to="`/quality/ncr/${c.ncr.id}`" class="wq-link">{{ c.ncr.name }}</RouterLink> ({{ t(label(c.ncr.status)) }}) </template>
        <template v-if="c.capa">{{ t('Corrective action') }} <RouterLink :to="`/quality/capa/${c.capa.id}`" class="wq-link">{{ c.capa.name }}</RouterLink> ({{ t(label(c.capa.status)) }})</template></p>
      <div v-if="c.status === 'investigation' && c.can_configure && c.investigate" class="mt-3 flex flex-wrap items-end gap-2 text-sm">
        <label class="wq-field">{{ t('Approve not investigating, because') }}<input v-model="x.reason" class="wq-input w-96"></label>
        <Button :label="t('No investigation')" :disabled="!x.reason.trim()" @click="act('no-investigation', { reason: x.reason }, t('Not investigating, approved.'))" />
      </div>
    </section>

    <section v-if="['investigation', 'assessed', 'closed'].includes(c.status)" data-help="complaint-assess" class="assess wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Must it be reported to a regulator?') }}</h2>
      <template v-if="c.status === 'investigation'">
        <p class="wq-muted mb-3">{{ t('Someone other than the owner answers and decides, with a password. WenQuest Ops does not decide: when a question is answered yes it usually means reporting, and it shows the deadline from the day the company first knew; check the time limits your regulations set.') }}</p>
        <template v-if="c.can_configure">
          <div v-for="(q, k) in c.questions" :key="k" class="mb-2 text-sm"><p class="text-ink-gray-8">{{ q }}</p>
            <label class="me-4"><input v-model="a.answers[k]" type="radio" value="yes"> {{ t('yes') }}</label><label><input v-model="a.answers[k]" type="radio" value="no"> {{ t('no') }}</label></div>
          <p v-if="anyYes" class="mb-2 rounded-3 bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-8">{{ t('A question is answered yes: this usually means it must be reported.') }}</p>
          <label v-if="anyYes || a.reportable === true" class="wq-field mb-2 w-fit">{{ t('Reporting deadline that applies') }}<select v-model="a.deadline_id" class="wq-select"><option :value="null">{{ t('Choose…') }}</option>
            <option v-for="d in c.deadlines.filter((d) => d.active)" :key="d.id" :value="d.id">{{ t('{label}: {n} days', { label: d.label, n: d.days }) }}</option></select></label>
          <div class="flex flex-wrap items-end gap-2 text-sm">
            <label class="me-2"><input v-model="a.reportable" type="radio" :value="true"> {{ t('must be reported') }}</label>
            <label class="me-2"><input v-model="a.reportable" type="radio" :value="false"> {{ t('need not be reported') }}</label>
            <label class="wq-field grow">{{ t('Reason') }}<input v-model="a.reason" class="wq-input"></label>
            <input v-model="a.password" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
            <Button variant="solid" :label="t('Decide (sign)')" :disabled="!a.password || a.reportable === null || !a.reason.trim() || ((anyYes || a.reportable) && !a.deadline_id)" @click="assess" />
          </div>
          <p v-if="anyYes && a.reportable === false" class="mt-2 text-sm text-ink-amber-7">{{ t('A yes with a decision not to report is allowed, with the reason, and counted as an exception.') }}</p>
        </template>
      </template>
      <template v-else>
        <ul class="mb-2 text-sm"><li v-for="(q, k) in c.questions" :key="k">{{ q }} <b>{{ t(c[k]) }}</b></li></ul>
        <p class="text-base"><b>{{ c.reportable ? t('Must be reported') : t('Need not be reported') }}</b> — {{ c.reportable_reason }} <span class="text-ink-gray-5">({{ c.assessed_by }})</span>
          <Badge v-if="c.exception" theme="amber" :label="t('exception: a yes, not reported')" /></p>
        <p v-if="c.deadline_on" class="text-sm" :class="c.report_late ? 'text-ink-red-7' : 'text-ink-gray-7'">{{ t('{label}: {n} days from {aware}, by {date}', { label: c.deadline_label, n: c.deadline_days, aware: c.aware_on, date: c.deadline_on }) }}{{ c.report_late ? t(' (late)') : '' }}</p>
        <div v-if="c.reportable && open && c.can_edit" class="mt-2 grid gap-2 md:grid-cols-3">
          <label class="wq-field">{{ t('Report reference') }}<input v-model="f.report_ref" class="wq-input"></label>
          <label class="wq-field">{{ t('Reported on') }}<input v-model="f.reported_on" type="date" class="wq-input"></label>
          <div class="flex items-end"><Button :label="t('Save')" :disabled="!Object.keys(changes()).length" @click="save" /></div>
        </div>
        <p v-else-if="c.report_ref" class="text-sm">{{ t('Reported on {date}, reference {ref}.', { date: c.reported_on, ref: c.report_ref }) }}</p>
      </template>
    </section>

    <section v-if="c.status === 'assessed' && c.can_configure" data-help="complaint-close" class="close wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Close') }}</h2>
      <p v-if="c.to_close.length" class="mb-2 text-sm text-ink-gray-7">{{ t('Still needed: {list}.', { list: c.to_close.join('; ') }) }}</p>
      <div class="flex flex-wrap items-end gap-2"><input v-model="x.password" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
        <Button variant="solid" :label="t('Close (sign)')" :disabled="!x.password || !!c.to_close.length" @click="act('close', { password: x.password }, t('Closed.'))" /></div>
      <p class="mt-1 text-sm text-ink-gray-5">{{ t('Someone other than the owner closes it.') }}</p>
    </section>
    <section v-if="['new', 'investigation'].includes(c.status) && c.can_edit" class="wq-panel mb-5 p-5">
      <details><summary class="cursor-pointer text-sm text-ink-gray-7">{{ t('Cancel (a duplicate, or not a complaint)') }}</summary>
        <div class="mt-2 flex gap-2"><input v-model="x.cancel" class="wq-input w-96" :placeholder="t('Why')"><Button :label="t('Cancel the complaint')" :disabled="!x.cancel.trim()" @click="act('cancel', { reason: x.cancel }, t('Cancelled.'))" /></div></details>
    </section>
    <CauseLinks kind="complaint" :id="c.id" :status="c.status" />
    <h2 class="wq-h2 mt-6">{{ t('Signatures') }}</h2>
    <Trail :items="c.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
    <Trail :items="c.history" />
  </template>
</template>
