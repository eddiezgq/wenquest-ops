<script setup>
// Changing a quality workflow (ADR-0015, 15b): a draft from the enabled version, what may change, the red-line check
// and the changes from the enabled version; enabled with a password by someone who did not change it.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'
import { t } from '../i18n'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const v = ref(null)
const cfg = ref(null)
const error = ref('')
const done = ref('')
const password = ref('')
const reason = ref('')
const note = ref('')
const saved = ref('')
const KIND = { ncr: 'Nonconformance report', capa: 'Corrective or preventive action' }
const canConfigure = computed(() => ws.value?.user.permissions.includes('workflows:configure'))
const draft = computed(() => v.value?.status === 'draft')
const editable = computed(() => draft.value && canConfigure.value)
const iEdited = computed(() => v.value?.edited_by?.includes(ws.value?.user.email))
const dirty = computed(() => cfg.value && JSON.stringify(cfg.value) !== saved.value)
const o = computed(() => v.value?.options)

function set(x) {
  v.value = x
  cfg.value = JSON.parse(JSON.stringify(x.config))
  cfg.value.fields ||= {}
  cfg.value.approvals ||= []
  saved.value = JSON.stringify(cfg.value)
  note.value = x.note || ''
  password.value = ''
}
async function load() {
  error.value = ''
  try { set(await api(`/api/quality/workflows/versions/${route.params.id}`)) } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })

async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { set(await api(`/api/quality/workflows/versions/${v.value.id}${path}`, { method, body })); done.value = message }
  catch (e) { error.value = e.message }
}
const save = () => call('', 'PUT', { config: cfg.value, note: note.value }, t('Saved. Someone who did not change it enables it.'))
const enable = () => call('/enable', 'POST', { password: password.value }, t('Enabled. New records follow this version.'))
const discard = () => call('/discard', 'POST', { reason: reason.value }, t('Draft discarded.'))

function toggle(list, value, on) {
  const i = list.indexOf(value)
  if (on && i < 0) list.push(value)
  if (!on && i >= 0) list.splice(i, 1)
}
function listOf(obj, key) { return (obj[key] ||= []) }
// a company's own fields
const nf = ref({ name: '', label: '', type: 'text', choices: '' })
function addField() {
  if (cfg.value.fields[nf.value.name.trim()]) { error.value = t('There is already a field {name}', { name: nf.value.name.trim() }); return }
  error.value = ''
  const f = { label: nf.value.label.trim(), type: nf.value.type }
  if (f.type === 'choice') f.choices = nf.value.choices.split(',').map((c) => c.trim()).filter(Boolean)
  cfg.value.fields = { ...cfg.value.fields, [nf.value.name.trim()]: f }
  nf.value = { name: '', label: '', type: 'text', choices: '' }
}
function dropField(name) { const { [name]: _, ...rest } = cfg.value.fields; cfg.value.fields = rest }
// extra signed approvals
function addApproval() {
  let n = cfg.value.approvals.length + 1
  while (cfg.value.approvals.some((a) => a.name === `approval_${n}`)) n++
  cfg.value.approvals.push({ name: `approval_${n}`, label: 'Approval', before: 'close', roles: ['owner'], sign: 'Approved', when: {} })
}
function whenList(a, key) { a.when ||= {}; return (a.when[key] ||= []) }
function cleanWhen(a) { for (const k of Object.keys(a.when || {})) if (!a.when[k].length) delete a.when[k] }
const stepNames = computed(() => Object.keys(cfg.value?.steps || {}))
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality', to: '/quality?tab=workflows' }]">
    <template #title>{{ v ? t('{kind} workflow · version {v}', { kind: t(KIND[v.kind]), v: v.version }) : t('Workflow') }}</template>
    <Badge v-if="v" size="lg" :theme="{ draft: 'amber', enabled: 'green', retired: 'gray', discarded: 'gray' }[v.status]" :label="t(v.status)" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <template v-if="v && cfg">
    <div class="mb-5 grid gap-4 lg:grid-cols-2">
      <section data-help="workflow-changes" class="wq-panel p-4">
        <h2 class="wq-h2">{{ t('Changes from version {v}', { v: v.enabled_version }) }}</h2>
        <p v-if="!v.changes.length" class="wq-muted">{{ t('None yet.') }}</p>
        <ul class="list-disc ps-5 text-sm text-ink-gray-8"><li v-for="c in v.changes" :key="c">{{ c }}</li></ul>
        <p v-if="dirty" class="mt-2 text-sm text-ink-amber-7">{{ t('Unsaved changes on this page.') }}</p>
      </section>
      <section data-help="workflow-check" class="wq-panel p-4">
        <h2 class="wq-h2">{{ t('Check') }}</h2>
        <p v-if="!draft" class="wq-muted">{{ t('This version is {status}; it cannot change. Make a new draft to change the workflow.', { status: t(v.status) }) }}</p>
        <p v-else-if="!v.errors.length" class="flex items-center gap-1.5 text-sm text-ink-green-7"><span class="lucide-check size-4" />{{ t('Keeps every rule that cannot be switched off.') }}</p>
        <ul v-else class="list-disc ps-5 text-sm text-ink-red-7"><li v-for="e in v.errors" :key="e">{{ e }}</li></ul>
      </section>
    </div>

    <fieldset :disabled="!editable" class="flex flex-col gap-5">
      <section class="wq-panel p-5">
        <h2 class="wq-h2">{{ t('States and numbers') }}</h2>
        <div class="flex flex-wrap gap-3">
          <label v-for="(s, k) in cfg.states" :key="k" class="wq-field">{{ t(k.replaceAll('_', ' ')) }}<input v-model="s.label" class="wq-input w-48"></label>
        </div>
        <div class="mt-4 flex flex-wrap items-end gap-3">
          <label class="wq-field">{{ t('Number prefix') }}<input v-model="cfg.numbering.prefix" class="wq-input w-32"></label>
          <label class="wq-field">{{ t('Digits') }}<input v-model.number="cfg.numbering.digits" type="number" min="3" max="8" class="wq-input w-20"></label>
          <span class="wq-muted pb-2">{{ t('e.g.') }} {{ cfg.numbering.prefix }}-{{ String(1).padStart(cfg.numbering.digits || 1, '0') }}</span>
        </div>
      </section>

      <section data-help="workflow-steps" class="wq-panel p-5">
        <h2 class="wq-h2">{{ t('Steps') }}</h2>
        <p class="wq-muted mb-3">{{ t('Where each step starts and ends, and which steps are signed, stay as they are. You can rename steps, word the signature, add what a step needs, keep more people from doing it, and limit it to some roles. Grey ticks are part of the default and stay.') }}</p>
        <div class="flex flex-col gap-4">
          <article v-for="(s, k) in cfg.steps" :key="k" class="step rounded-4 border border-outline-gray-2 p-4">
            <div class="flex flex-wrap items-end gap-3">
              <label class="wq-field">{{ t('Step') }}<input v-model="s.label" class="wq-input w-56"></label>
              <label v-if="o.signed.includes(k)" class="wq-field">{{ t('Signature means') }}<input v-model="s.sign" class="wq-input w-72"></label>
              <span class="pb-2 text-sm text-ink-gray-5">{{ s.from.map((x) => cfg.states[x]?.label).join(', ') }} → {{ s.to ? cfg.states[s.to]?.label : t('(stays)') }}</span>
            </div>
            <div class="mt-3 grid gap-3 text-sm md:grid-cols-3">
              <div><p class="mb-1 text-ink-gray-6">{{ t('Needs') }}</p>
                <label v-for="(lbl, f) in o.needs" :key="f" class="me-3 inline-flex items-center gap-1.5">
                  <input type="checkbox" class="form-checkbox" :disabled="o.locked_required[k]?.includes(f)" :checked="(s.required || []).includes(f)"
                         @change="toggle(listOf(s, 'required'), f, $event.target.checked)">{{ t(lbl) }}</label></div>
              <div><p class="mb-1 text-ink-gray-6">{{ t('Not by') }}</p>
                <label v-for="(lbl, f) in o.not_by" :key="f" class="me-3 inline-flex items-center gap-1.5">
                  <input type="checkbox" class="form-checkbox" :disabled="o.locked_not_by[k]?.includes(f)" :checked="(s.not_by || []).includes(f)"
                         @change="toggle(listOf(s, 'not_by'), f, $event.target.checked)">{{ t(lbl) }}</label></div>
              <div><p class="mb-1 text-ink-gray-6">{{ t('Only these roles') }} <span class="text-ink-gray-4">{{ t('(none ticked: everyone allowed)') }}</span></p>
                <label v-for="r in o.roles" :key="r" class="me-3 inline-flex items-center gap-1.5">
                  <input type="checkbox" class="form-checkbox" :checked="(s.roles || []).includes(r)"
                         @change="toggle(listOf(s, 'roles'), r, $event.target.checked); if (!s.roles.length) delete s.roles">{{ t(r.replace('_', ' ')) }}</label></div>
            </div>
          </article>
        </div>
      </section>

      <section class="wq-panel p-5">
        <h2 class="wq-h2">{{ t('Your own fields') }}</h2>
        <p class="wq-muted mb-3">{{ t("Filled in on the record's page. Tick a step to make the field needed before it.") }}</p>
        <table v-if="Object.keys(cfg.fields).length" class="wq-table mb-3 text-sm">
          <thead><tr><th>{{ t('Name') }}</th><th>{{ t('Label') }}</th><th>{{ t('Type') }}</th><th>{{ t('Needed before') }}</th><th /></tr></thead>
          <tbody><tr v-for="(f, name) in cfg.fields" :key="name">
            <td class="font-mono">{{ name }}</td><td><input v-model="f.label" class="wq-input w-48"></td>
            <td>{{ t(f.type) }}<span v-if="f.choices" class="text-ink-gray-5">: {{ f.choices.join(', ') }}</span></td>
            <td><label v-for="st in o.gates" :key="st" class="me-2 inline-flex items-center gap-1">
              <input type="checkbox" class="form-checkbox" :checked="(f.required_at || []).includes(st)"
                     @change="toggle(listOf(f, 'required_at'), st, $event.target.checked)">{{ cfg.steps[st].label }}</label></td>
            <td><Button size="sm" variant="ghost" :label="t('Remove')" @click="dropField(name)" /></td></tr></tbody>
        </table>
        <form v-if="editable" class="flex flex-wrap items-end gap-2" @submit.prevent="addField">
          <label class="wq-field">{{ t('Name') }}<input v-model="nf.name" class="wq-input w-36 font-mono" placeholder="lot_no" required></label>
          <label class="wq-field">{{ t('Label') }}<input v-model="nf.label" class="wq-input w-48" :placeholder="t('Lot number')" required></label>
          <label class="wq-field">{{ t('Type') }}<select v-model="nf.type" class="wq-select"><option v-for="ft in o.field_types" :key="ft" :value="ft">{{ t(ft) }}</option></select></label>
          <label v-if="nf.type === 'choice'" class="wq-field">{{ t('Choices') }}<input v-model="nf.choices" class="wq-input w-56" :placeholder="t('Receiving, Shipping')"></label>
          <Button type="submit" icon-left="lucide-plus" :label="t('Add field')" />
        </form>
      </section>

      <section class="wq-panel p-5">
        <h2 class="wq-h2">{{ t('Extra signed approvals') }}</h2>
        <p class="wq-muted mb-3">{{ t('Before a step, someone with one of the roles signs an approval with their password, for example "the owner approves closing a major report".') }}</p>
        <article v-for="(a, i) in cfg.approvals" :key="i" class="approval mb-3 rounded-4 border border-outline-gray-2 p-4">
          <div class="flex flex-wrap items-end gap-3">
            <label class="wq-field">{{ t('Name') }}<input v-model="a.name" class="wq-input w-36 font-mono"></label>
            <label class="wq-field">{{ t('Label') }}<input v-model="a.label" class="wq-input w-56"></label>
            <label class="wq-field">{{ t('Before') }}<select v-model="a.before" class="wq-select"><option v-for="st in o.gates" :key="st" :value="st">{{ cfg.steps[st].label }}</option></select></label>
            <label class="wq-field">{{ t('Signature means') }}<input v-model="a.sign" class="wq-input w-64"></label>
            <Button v-if="editable" size="sm" variant="ghost" :label="t('Remove')" @click="cfg.approvals.splice(i, 1)" />
          </div>
          <div class="mt-3 grid gap-3 text-sm md:grid-cols-3">
            <div><p class="mb-1 text-ink-gray-6">{{ t('Signed by') }}</p>
              <label v-for="r in o.roles" :key="r" class="me-3 inline-flex items-center gap-1.5"><input type="checkbox" class="form-checkbox" :checked="a.roles.includes(r)"
                     @change="toggle(a.roles, r, $event.target.checked)">{{ t(r.replace('_', ' ')) }}</label></div>
            <div><p class="mb-1 text-ink-gray-6">{{ t('Not by') }}</p>
              <label v-for="(lbl, f) in o.not_by" :key="f" class="me-3 inline-flex items-center gap-1.5"><input type="checkbox" class="form-checkbox" :checked="(a.not_by || []).includes(f)"
                     @change="toggle(listOf(a, 'not_by'), f, $event.target.checked)">{{ t(lbl) }}</label></div>
            <div><p class="mb-1 text-ink-gray-6">{{ t('Only when') }} <span class="text-ink-gray-4">{{ t('(none ticked: always)') }}</span></p>
              <div v-for="(vals, key) in o.when" :key="key" class="mb-1">{{ t(key) }}:
                <label v-for="x in vals" :key="x" class="ms-2 inline-flex items-center gap-1"><input type="checkbox" class="form-checkbox" :checked="(a.when?.[key] || []).includes(x)"
                       @change="toggle(whenList(a, key), x, $event.target.checked); cleanWhen(a)">{{ t(x.replaceAll('_', ' ')) }}</label></div></div>
          </div>
        </article>
        <Button v-if="editable" icon-left="lucide-plus" :label="t('Add an approval')" @click="addApproval" />
      </section>

      <section v-if="v.kind === 'ncr'" data-help="workflow-rules" class="wq-panel p-5">
        <h2 class="wq-h2">{{ t('Rules') }}</h2>
        <p class="mb-2 text-sm text-ink-gray-7">{{ t('Close only after a linked corrective action is closed:') }}
          <label v-for="sv in ['minor', 'major']" :key="sv" class="ms-3 inline-flex items-center gap-1"><input type="checkbox" class="form-checkbox" :disabled="sv === 'major'"
                 :checked="cfg.rules.capa_closed_before_close.includes(sv)" @change="toggle(cfg.rules.capa_closed_before_close, sv, $event.target.checked)">{{ t(sv) }}</label></p>
        <p class="text-sm text-ink-gray-7">{{ t('Close only after the 8D is complete:') }}
          <label v-for="sv in ['minor', 'major']" :key="sv" class="ms-3 inline-flex items-center gap-1"><input type="checkbox" class="form-checkbox"
                 :checked="(cfg.rules.eight_d_before_close || []).includes(sv)" @change="toggle(listOf(cfg.rules, 'eight_d_before_close'), sv, $event.target.checked)">{{ t(sv) }}</label></p>
      </section>
    </fieldset>

    <section v-if="editable" data-help="workflow-save" class="wq-panel mt-5 flex flex-wrap items-end gap-3 p-5">
      <label class="wq-field">{{ t('Note') }}<input v-model="note" class="wq-input w-80" :placeholder="t('What this version is for')"></label>
      <Button variant="solid" icon-left="lucide-save" :label="t('Save draft')" @click="save" />
    </section>
    <section v-if="draft && canConfigure" data-help="workflow-enable" class="wq-panel mt-5 p-5">
      <h2 class="wq-h2">{{ t('Enable') }}</h2>
      <p v-if="iEdited" class="wq-muted">{{ t('You changed this draft, so someone else with the right to change workflows enables it.') }}</p>
      <div v-else class="flex flex-wrap items-center gap-2">
        <input v-model="password" class="wq-input max-w-56" type="password" :placeholder="t('Your password to sign')" autocomplete="current-password">
        <Button variant="solid" icon-left="lucide-pen-line" :label="t('Enable (sign)')" :disabled="!!v.errors.length || dirty || !v.changes.length" @click="enable" />
        <span v-if="dirty" class="text-sm text-ink-amber-7">{{ t('Save the changes first.') }}</span>
      </div>
      <div class="mt-4 flex flex-wrap items-center gap-2">
        <input v-model="reason" class="wq-input max-w-80" :placeholder="t('Why discard this draft')">
        <Button theme="red" :label="t('Discard draft')" :disabled="!reason.trim()" @click="discard" />
      </div>
    </section>

    <h2 class="wq-h2 mt-6">{{ t('Signatures') }}</h2>
    <Trail :items="v.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
    <Trail :items="v.history" />
  </template>
</template>
