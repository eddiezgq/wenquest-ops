<script setup>
// One change (ADR-0017, 17g). The four questions are answered by a person; WenQuest Ops checks that each step has
// what it needs and who may sign.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'
import { label } from '../ui/themes'
import { t } from '../i18n'

const route = useRoute()
const c = ref(null)
const meta = ref(null)
const error = ref('')
const done = ref('')
const f = ref({})
const x = ref({ password: '', reason: '', cancel: '' })
const ST = { draft: 'gray', submitted: 'amber', approved: 'blue', implemented: 'violet', closed: 'green', cancelled: 'gray' }
const TEXT = ['title', 'description', 'reason', 'assessment', 'regulatory_decision', 'validation_plan', 'validation_result', 'implementation', 'effectiveness']
const ALL = [...TEXT, 'kind', 'owner', 'target_date', 'documents', 'revisions', 'q_product', 'q_regulatory', 'q_risk', 'q_validation']
const draft = computed(() => c.value?.status === 'draft')
const can = (k) => c.value?.can_edit && ({ draft: ['title', 'description', 'reason', 'assessment', 'regulatory_decision', 'validation_plan', 'kind', 'owner', 'target_date', 'documents', 'q_product', 'q_regulatory', 'q_risk', 'q_validation'],
  submitted: ['target_date'], approved: ['target_date', 'revisions', 'validation_result', 'implementation'], implemented: ['target_date', 'effectiveness'] }[c.value.status] || []).includes(k)
const newRevs = computed(() => (meta.value?.documents || []).filter((d) => (f.value.documents || []).includes(d.supersedes)))

function set(v) { c.value = v; f.value = Object.fromEntries(ALL.map((k) => [k, Array.isArray(v[k]) ? [...v[k]] : v[k] ?? ''])) }
async function load() {
  error.value = ''
  try { meta.value = await api('/api/changes?status=all'); set(await api(`/api/changes/${route.params.id}`)) } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
function changes() {
  const out = {}
  for (const k of ALL) {
    if (!can(k)) continue
    const a = f.value[k]; const b = c.value[k]
    if (JSON.stringify(a ?? '') !== JSON.stringify(b ?? '')) out[k] = a === '' ? null : a
  }
  return out
}
async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { set(await api(path, { method, body })); done.value = message; x.value = { password: '', reason: '', cancel: '' } } catch (e) { error.value = e.message }
}
const save = () => call(`/api/changes/${c.value.id}`, 'PUT', changes(), t('Saved.'))
const act = (a, body, msg) => call(`/api/changes/${c.value.id}/${a}`, 'POST', body, msg)
const docName = (d) => [d.number, d.title, d.revision ? t('rev {revision}', { revision: d.revision }) : ''].filter(Boolean).join(' ')
</script>

<template>
  <PageTop :crumbs="[{ label: t('Changes'), to: '/quality/changes' }]">
    <template #title>{{ c ? `${c.name} · ${c.title}` : t('Change') }}</template>
    <Badge v-if="c" :theme="ST[c.status]" size="lg" :label="t(c.status)" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="c && meta">
    <section class="what wq-panel mb-5 grid gap-3 p-5 md:grid-cols-3">
      <label class="wq-field md:col-span-2">{{ t('Title') }}<input v-model="f.title" class="wq-input" :disabled="!can('title')"></label>
      <label class="wq-field">{{ t('Kind') }}<select v-model="f.kind" class="wq-select" :disabled="!can('kind')"><option v-for="k in c.kinds" :key="k" :value="k">{{ t(k) }}</option></select></label>
      <label class="wq-field md:col-span-3">{{ t('What changes') }}<textarea v-model="f.description" rows="2" class="wq-input" :disabled="!can('description')" /></label>
      <label class="wq-field md:col-span-3">{{ t('Why') }}<textarea v-model="f.reason" rows="2" class="wq-input" :disabled="!can('reason')" /></label>
      <label class="wq-field">{{ t('Owner') }}<select v-model="f.owner" class="wq-select" :disabled="!can('owner')"><option value="" /><option v-for="p in meta.people" :key="p">{{ p }}</option></select></label>
      <label class="wq-field">{{ t('Target date') }}<input v-model="f.target_date" type="date" class="wq-input" :disabled="!can('target_date')"></label>
      <label class="wq-field">{{ t('Documents it changes') }}<select v-model="f.documents" multiple class="wq-select h-24" :disabled="!can('documents')">
        <option v-for="d in meta.documents.filter((d) => d.status === 'effective')" :key="d.id" :value="d.id">{{ docName(d) }}</option></select></label>
    </section>

    <section data-help="change-assess" class="assess wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Assessment') }}</h2>
      <div v-for="(q, k) in c.questions" :key="k" class="mb-2 text-sm"><p class="text-ink-gray-8">{{ q }}</p>
        <label class="me-4"><input v-model="f[k]" type="radio" value="yes" :disabled="!can(k)"> {{ t('yes') }}</label><label><input v-model="f[k]" type="radio" value="no" :disabled="!can(k)"> {{ t('no') }}</label></div>
      <label class="wq-field mt-2">{{ t('Assessment notes') }}<textarea v-model="f.assessment" rows="2" class="wq-input" :disabled="!can('assessment')" /></label>
      <label v-if="f.q_regulatory === 'yes'" class="wq-field mt-2">{{ t('Regulatory decision (what will be submitted or notified, or why not)') }}<textarea v-model="f.regulatory_decision" rows="2" class="wq-input" :disabled="!can('regulatory_decision')" /></label>
      <label v-if="f.q_validation === 'yes'" class="wq-field mt-2">{{ t('Verification or validation plan') }}<textarea v-model="f.validation_plan" rows="2" class="wq-input" :disabled="!can('validation_plan')" /></label>
    </section>

    <section v-if="['approved', 'implemented', 'closed'].includes(c.status)" data-help="change-impl" class="impl wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Implementation') }}</h2>
      <label v-if="c.documents.length" class="wq-field mb-2">{{ t('The new revisions') }}<select v-model="f.revisions" multiple class="wq-select h-24" :disabled="!can('revisions')">
        <option v-for="d in newRevs" :key="d.id" :value="d.id">{{ docName(d) }} ({{ t(label(d.status)) }})</option></select></label>
      <label v-if="c.q_validation === 'yes'" class="wq-field mb-2">{{ t('Verification or validation result') }}<textarea v-model="f.validation_result" rows="2" class="wq-input" :disabled="!can('validation_result')" /></label>
      <label class="wq-field mb-2">{{ t('How it was implemented') }}<textarea v-model="f.implementation" rows="2" class="wq-input" :disabled="!can('implementation')" /></label>
      <label v-if="c.status !== 'approved'" class="wq-field">{{ t('Effectiveness check') }}<textarea v-model="f.effectiveness" rows="2" class="wq-input" :disabled="!can('effectiveness')" /></label>
    </section>

    <section v-if="c.can_edit && !['closed', 'cancelled'].includes(c.status)" data-help="change-steps" class="steps wq-panel mb-5 p-5">
      <div class="flex flex-wrap items-end gap-2">
        <Button :label="t('Save')" :disabled="!Object.keys(changes()).length" @click="save" />
        <Button v-if="draft" variant="solid" :label="t('Submit')" :disabled="!!Object.keys(changes()).length || !!c.to_submit.length" @click="act('submit', {}, t('Submitted: what was assessed is fixed now.'))" />
        <Button v-if="c.status === 'approved'" variant="solid" :label="t('Mark implemented')" :disabled="!!Object.keys(changes()).length || !!c.to_implement.length" @click="act('implement', {}, t('Implemented.'))" />
        <template v-if="c.can_configure && c.status === 'submitted'">
          <input v-model="x.password" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
          <Button variant="solid" :label="t('Approve (sign)')" :disabled="!x.password" @click="act('approve', { password: x.password }, t('Approved.'))" />
          <input v-model="x.reason" class="wq-input w-64" :placeholder="t('What needs to change')">
          <Button :label="t('Send back')" :disabled="!x.reason.trim()" @click="act('send-back', { reason: x.reason }, t('Sent back as a draft.'))" />
        </template>
        <template v-if="c.can_configure && c.status === 'implemented'">
          <input v-model="x.password" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
          <Button variant="solid" :label="t('Close (sign)')" :disabled="!x.password || !!Object.keys(changes()).length || !!c.to_close.length" @click="act('close', { password: x.password }, t('Closed.'))" />
        </template>
      </div>
      <p v-for="(list, what) in { 'To submit': c.to_submit, 'To implement': c.to_implement, 'To close': c.to_close }" v-show="list.length" :key="what" class="mt-2 text-sm text-ink-gray-6">{{ t(what) }}: {{ list.join('; ') }}.</p>
      <p v-if="c.status === 'submitted'" class="mt-2 text-sm text-ink-gray-5">{{ t('Approved by someone who did not raise, own, submit or edit it.') }}</p>
      <p v-if="c.status === 'implemented'" class="mt-2 text-sm text-ink-gray-5">{{ t('Closed by someone other than the owner.') }}</p>
      <details v-if="['draft', 'submitted', 'approved'].includes(c.status)" class="mt-3"><summary class="cursor-pointer text-sm text-ink-gray-7">{{ t('Cancel the change') }}</summary>
        <div class="mt-2 flex gap-2"><input v-model="x.cancel" class="wq-input w-96" :placeholder="t('Why')"><Button :label="t('Cancel')" :disabled="!x.cancel.trim()" @click="act('cancel', { reason: x.cancel }, t('Cancelled.'))" /></div></details>
    </section>
    <h2 class="wq-h2 mt-6">{{ t('Signatures') }}</h2>
    <Trail :items="c.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
    <Trail :items="c.history" />
  </template>
</template>
