<script setup>
// One risk management file (ADR-0017, 17h). People name hazards, situations and harm and rank them; the matrix
// decides acceptability; approval is signed by someone who does not own and did not edit the file.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const r = ref(null)
const error = ref('')
const done = ref('')
const f = ref({})
const x = ref({ password: '', reason: '' })
const blank = () => ({ hazard: '', situation: '', harm: '', severity: '', probability: '', controls: '', verification: '', res_severity: '', res_probability: '', benefit_risk: '' })
const item = ref(blank())
const editing = ref(null)
const FIELDS = ['product', 'scope', 'owner', 'conclusion', 'benefit_risk']
const ST = { draft: 'gray', approved: 'green', superseded: 'gray', withdrawn: 'gray' }
const VT = { acceptable: 'green', reduce: 'amber', unacceptable: 'red' }
const draft = computed(() => r.value?.status === 'draft' && r.value?.can_edit)
const ranks = (kind) => (r.value?.levels || []).filter((l) => l.kind === kind).sort((a, b) => a.rank - b.rank)
const levelName = (kind, rank) => { const l = (r.value?.levels || []).find((l) => l.kind === kind && l.rank === rank); return rank ? `${rank}${l ? ' ' + l.name : ''}` : '–' }

function set(v) { r.value = v; f.value = Object.fromEntries(FIELDS.map((k) => [k, v[k] ?? ''])) }
async function load() { error.value = ''; try { set(await api(`/api/risk/files/${route.params.id}`)) } catch (e) { error.value = e.message } }
watch(() => route.params.id, load, { immediate: true })
const changed = () => Object.fromEntries(FIELDS.filter((k) => (f.value[k] ?? '') !== (r.value[k] ?? '')).map((k) => [k, f.value[k]]))
async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { const v = await api(path, { method, body }); set(v); done.value = message; x.value = { password: '', reason: '' }; return v } catch (e) { error.value = e.message }
}
const clean = (it) => Object.fromEntries(Object.entries(it).map(([k, v]) => [k, v === '' ? null : v]))
async function saveItem() {
  const body = clean(item.value)
  const ok = editing.value
    ? await call(`/api/risk/files/${r.value.id}/items/${editing.value}`, 'PUT', body, 'Saved.')
    : await call(`/api/risk/files/${r.value.id}/items`, 'POST', body, 'Added.')
  if (ok) { item.value = blank(); editing.value = null }
}
function edit(it) { editing.value = it.id; item.value = Object.fromEntries(Object.keys(blank()).map((k) => [k, it[k] ?? ''])) }
async function revise() {
  const v = await call(`/api/risk/files/${r.value.id}/revise`, 'POST', {}, 'A new version is started.')
  if (v) router.push(`/quality/risk/${v.id}`)
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Risk management', to: '/quality/risk' }]">
    <template #title>{{ r ? `${r.name} v${r.version} · ${r.product}` : 'Risk file' }}</template>
    <Badge v-if="r" :theme="ST[r.status]" size="lg" :label="r.status" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="r">
    <p v-if="r.intact === false" class="wq-error mb-4">This file no longer matches what was approved.</p>
    <section class="what wq-panel mb-5 grid gap-3 p-5 md:grid-cols-3">
      <label class="wq-field md:col-span-2">Product or product family<input v-model="f.product" class="wq-input" :disabled="!draft"></label>
      <label class="wq-field">Owner<select v-model="f.owner" class="wq-select" :disabled="!draft"><option value="" /><option v-for="p in r.people" :key="p">{{ p }}</option></select></label>
      <label class="wq-field md:col-span-3">Scope<textarea v-model="f.scope" rows="2" class="wq-input" :disabled="!draft" /></label>
      <label data-help="risk-conclusion" class="wq-field md:col-span-3">Overall residual risk<textarea v-model="f.conclusion" rows="2" class="wq-input" :disabled="!draft" /></label>
      <label class="wq-field md:col-span-3">Benefit-risk conclusion<textarea v-model="f.benefit_risk" rows="2" class="wq-input" :disabled="!draft" /></label>
      <div v-if="draft"><Button label="Save" :disabled="!Object.keys(changed()).length" @click="call(`/api/risk/files/${r.id}`, 'PUT', changed(), 'Saved.')" /></div>
    </section>

    <section data-help="risk-hazards" class="items wq-panel mb-5 p-5">
      <h2 class="wq-h2">Hazards</h2>
      <p v-if="r.gaps.length && draft" class="mb-2 text-sm text-ink-amber-7">The matrix does not decide: {{ r.gaps.join(', ') }}.</p>
      <p v-if="!r.items.length" class="wq-muted">None yet.</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>#</th><th>Hazard → situation → harm</th><th>Initial</th><th>Controls · verification</th><th>Residual</th><th>Benefit-risk</th><th /></tr></thead>
        <tbody><tr v-for="it in r.items" :key="it.id">
          <td>{{ it.seq }}</td>
          <td><b>{{ it.hazard }}</b><span v-if="it.situation"> → {{ it.situation }}</span> → {{ it.harm }}</td>
          <td>S{{ levelName('severity', it.severity) }} · P{{ levelName('probability', it.probability) }}<br>
            <Badge v-if="it.initial_verdict" :theme="VT[it.initial_verdict]" :label="r.verdicts[it.initial_verdict]" /><span v-else class="text-ink-amber-7">not determined</span></td>
          <td>{{ it.controls }}<span v-if="it.verification"> · {{ it.verification }}</span></td>
          <td><template v-if="it.res_severity">S{{ levelName('severity', it.res_severity) }} · P{{ levelName('probability', it.res_probability) }}<br></template>
            <Badge v-if="it.residual_verdict" :theme="VT[it.residual_verdict]" :label="r.verdicts[it.residual_verdict]" /></td>
          <td>{{ it.benefit_risk }}</td>
          <td class="whitespace-nowrap"><template v-if="draft"><Button size="sm" label="Edit" @click="edit(it)" />
            <Button size="sm" variant="ghost" label="Remove" @click="call(`/api/risk/files/${r.id}/items/${it.id}`, 'DELETE', null, 'Removed.')" /></template></td>
        </tr></tbody></table>

      <form v-if="draft" data-help="risk-hazard-form" class="item mt-4 grid gap-3 md:grid-cols-3" @submit.prevent="saveItem">
        <label class="wq-field">Hazard<input v-model="item.hazard" class="wq-input"></label>
        <label class="wq-field">Hazardous situation<input v-model="item.situation" class="wq-input"></label>
        <label class="wq-field">Harm<input v-model="item.harm" class="wq-input"></label>
        <label class="wq-field">Severity<select v-model.number="item.severity" class="wq-select"><option value="" /><option v-for="l in ranks('severity')" :key="l.id" :value="l.rank" :disabled="!l.active">{{ l.rank }} {{ l.name }}{{ l.active ? '' : ' (not in use)' }}</option></select></label>
        <label class="wq-field">Probability<select v-model.number="item.probability" class="wq-select"><option value="" /><option v-for="l in ranks('probability')" :key="l.id" :value="l.rank" :disabled="!l.active">{{ l.rank }} {{ l.name }}{{ l.active ? '' : ' (not in use)' }}</option></select></label>
        <span />
        <label class="wq-field">Risk controls<textarea v-model="item.controls" rows="2" class="wq-input" /></label>
        <label class="wq-field">How they were verified<textarea v-model="item.verification" rows="2" class="wq-input" /></label>
        <span />
        <label class="wq-field">Residual severity<select v-model.number="item.res_severity" class="wq-select"><option value="" /><option v-for="l in ranks('severity')" :key="l.id" :value="l.rank" :disabled="!l.active">{{ l.rank }} {{ l.name }}{{ l.active ? '' : ' (not in use)' }}</option></select></label>
        <label class="wq-field">Residual probability<select v-model.number="item.res_probability" class="wq-select"><option value="" /><option v-for="l in ranks('probability')" :key="l.id" :value="l.rank" :disabled="!l.active">{{ l.rank }} {{ l.name }}{{ l.active ? '' : ' (not in use)' }}</option></select></label>
        <label class="wq-field">Benefit-risk (when the residual risk is unacceptable)<textarea v-model="item.benefit_risk" rows="2" class="wq-input" /></label>
        <div class="flex gap-2 md:col-span-3"><Button type="submit" variant="solid" :label="editing ? 'Save the hazard' : 'Add the hazard'" :disabled="!item.hazard.trim()" />
          <Button v-if="editing" label="Stop editing" @click="editing = null; item = blank()" /></div>
      </form>
    </section>

    <section v-if="r.status === 'draft' || (r.status === 'approved' && r.can_edit)" data-help="risk-approve" class="steps wq-panel mb-5 p-5">
      <template v-if="r.status === 'draft'">
        <p v-if="r.to_approve.length" class="mb-2 text-sm text-ink-gray-6">To approve: {{ r.to_approve.join('; ') }}.</p>
        <div v-if="r.can_configure" class="flex flex-wrap items-end gap-2">
          <input v-model="x.password" type="password" class="wq-input w-44" placeholder="Your password" autocomplete="current-password">
          <Button variant="solid" label="Approve (sign)" :disabled="!x.password || !!r.to_approve.length || !!Object.keys(changed()).length" @click="call(`/api/risk/files/${r.id}/approve`, 'POST', { password: x.password }, 'Approved: the file is fixed now.')" />
        </div>
        <p class="mt-2 text-sm text-ink-gray-5">Approved by someone who does not own and did not edit it. Acceptability is looked up again in the matrix at approval and kept.</p>
        <details v-if="r.can_edit" class="mt-3"><summary class="cursor-pointer text-sm text-ink-gray-7">Withdraw the draft</summary>
          <div class="mt-2 flex gap-2"><input v-model="x.reason" class="wq-input w-96" placeholder="Why"><Button label="Withdraw" :disabled="!x.reason.trim()" @click="call(`/api/risk/files/${r.id}/withdraw`, 'POST', { reason: x.reason }, 'Withdrawn.')" /></div></details>
      </template>
      <Button v-else label="Start a new version" @click="revise" />
    </section>

    <p v-if="r.fingerprint" class="mb-4 text-xs text-ink-gray-5">Fingerprint {{ r.fingerprint }}</p>
    <h2 class="wq-h2 mt-6">Versions</h2>
    <ul class="mb-4 text-sm"><li v-for="ver in r.versions" :key="ver.id"><RouterLink :to="`/quality/risk/${ver.id}`" class="hover:underline">v{{ ver.version }}</RouterLink> · {{ ver.status }}<span v-if="ver.approved_by"> · {{ ver.approved_by }} {{ ver.approved_at?.slice(0, 10) }}</span></li></ul>
    <h2 class="wq-h2 mt-6">Signatures</h2>
    <Trail :items="r.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">History</h2>
    <Trail :items="r.history" />
  </template>
</template>
