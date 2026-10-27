<script setup>
// A production template (ADR-0017, 17i): the steps of making an item, activated with a signature and then fixed.
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'
import { t } from '../i18n'

const route = useRoute()
const router = useRouter()
const tpl = ref(null)
const error = ref('')
const done = ref('')
const f = ref({ title: '', documents: [], materials: [] })
const x = ref({ password: '', reason: '' })
const blank = () => ({ name: '', kind: 'check', instruction: '', low: '', high: '', unit: '', gauge_required: false })
const step = ref(blank())
const editing = ref(null)
const ST = { draft: 'gray', active: 'green', retired: 'gray', withdrawn: 'gray' }

function set(v) { tpl.value = v; f.value = { title: v.title, documents: [...v.documents], materials: [...v.materials] } }
async function load() { error.value = ''; try { set(await api(`/api/production/templates/${route.params.id}`)) } catch (e) { error.value = e.message } }
watch(() => route.params.id, load, { immediate: true })
async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { const v = await api(path, { method, body }); set(v); done.value = message; x.value = { password: '', reason: '' }; return v } catch (e) { error.value = e.message }
}
const draft = () => tpl.value?.status === 'draft' && tpl.value?.can_edit
const changed = () => JSON.stringify(f.value) !== JSON.stringify({ title: tpl.value.title, documents: tpl.value.documents, materials: tpl.value.materials })
async function saveStep() {
  const body = { ...step.value, low: step.value.low === '' ? null : step.value.low, high: step.value.high === '' ? null : step.value.high }
  const ok = editing.value
    ? await call(`/api/production/templates/${tpl.value.id}/steps/${editing.value}`, 'PUT', body, t('Saved.'))
    : await call(`/api/production/templates/${tpl.value.id}/steps`, 'POST', body, t('Added.'))
  if (ok) { step.value = blank(); editing.value = null }
}
function edit(s) { editing.value = s.id; step.value = { name: s.name, kind: s.kind, instruction: s.instruction, low: s.low ?? '', high: s.high ?? '', unit: s.unit, gauge_required: s.gauge_required } }
async function newVersion() {
  const v = await call(`/api/production/templates/${tpl.value.id}/new-version`, 'POST', {}, t('A new version is started.'))
  if (v) router.push(`/quality/production/templates/${v.id}`)
}
const limits = (s) => s.kind !== 'measure' ? '' : [s.low ?? '…', s.high ?? '…'].join(' – ') + (s.unit ? ` ${s.unit}` : '')
</script>

<template>
  <PageTop :crumbs="[{ label: t('Production records'), to: '/quality/production' }]">
    <template #title>{{ tpl ? `${tpl.code} v${tpl.version} · ${tpl.item_code}` : t('Template') }}</template>
    <Badge v-if="tpl" :theme="ST[tpl.status]" size="lg" :label="t(tpl.status)" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="tpl">
    <section class="what wq-panel mb-5 grid gap-3 p-5 md:grid-cols-3">
      <label class="wq-field md:col-span-3">{{ t('Title') }}<input v-model="f.title" class="wq-input" :disabled="!draft()"></label>
      <label class="wq-field">{{ t('Documents the steps follow (operators confirm reading them)') }}<select v-model="f.documents" multiple class="wq-select h-24" :disabled="!draft()">
        <option v-for="d in tpl.documents_in_effect" :key="d" :value="d">{{ d }}</option></select></label>
      <label class="wq-field">{{ t('Materials each lot must record') }}<select v-model="f.materials" multiple class="wq-select h-24" :disabled="!draft()">
        <option v-for="i in tpl.items" :key="i.item_code" :value="i.item_code">{{ i.item_code }} · {{ i.name }}</option></select></label>
      <div v-if="draft()" class="self-end"><Button :label="t('Save')" :disabled="!changed()" @click="call(`/api/production/templates/${tpl.id}`, 'PUT', f, t('Saved.'))" /></div>
    </section>

    <section class="steps wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Steps') }}</h2>
      <p v-if="!tpl.steps.length" class="wq-muted">{{ t('None yet.') }}</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>#</th><th>{{ t('Step') }}</th><th>{{ t('Kind') }}</th><th>{{ t('Limits') }}</th><th>{{ t('Equipment') }}</th><th>{{ t('Instruction') }}</th><th /></tr></thead>
        <tbody><tr v-for="s in tpl.steps" :key="s.id"><td>{{ s.seq }}</td><td>{{ s.name }}</td><td>{{ t(s.kind) }}</td><td>{{ limits(s) }}</td>
          <td>{{ s.gauge_required ? t('required') : '' }}</td><td>{{ s.instruction }}</td>
          <td class="whitespace-nowrap"><template v-if="draft()"><Button size="sm" :label="t('Edit')" @click="edit(s)" />
            <Button size="sm" variant="ghost" :label="t('Remove')" @click="call(`/api/production/templates/${tpl.id}/steps/${s.id}`, 'DELETE', null, t('Removed.'))" /></template></td></tr></tbody></table>
      <form v-if="draft()" class="step mt-4 flex flex-wrap items-end gap-3" @submit.prevent="saveStep">
        <label class="wq-field grow">{{ t('Step') }}<input v-model="step.name" class="wq-input"></label>
        <label class="wq-field">{{ t('Kind') }}<select v-model="step.kind" class="wq-select"><option value="check">{{ t('check (pass / fail)') }}</option><option value="measure">{{ t('measurement') }}</option><option value="record">{{ t('record (text)') }}</option></select></label>
        <template v-if="step.kind === 'measure'">
          <label class="wq-field w-24">{{ t('Lower') }}<input v-model="step.low" class="wq-input"></label>
          <label class="wq-field w-24">{{ t('Upper') }}<input v-model="step.high" class="wq-input"></label>
          <label class="wq-field w-20">{{ t('Unit') }}<input v-model="step.unit" class="wq-input"></label>
          <label class="text-sm"><input v-model="step.gauge_required" type="checkbox"> {{ t('equipment required') }}</label>
        </template>
        <label class="wq-field basis-full">{{ t('Instruction') }}<textarea v-model="step.instruction" rows="2" class="wq-input" /></label>
        <Button type="submit" variant="solid" :label="editing ? t('Save the step') : t('Add the step')" :disabled="!step.name.trim()" />
        <Button v-if="editing" :label="t('Stop editing')" @click="editing = null; step = blank()" />
      </form>
    </section>

    <section v-if="tpl.can_edit && ['draft', 'active'].includes(tpl.status)" class="act wq-panel mb-5 p-5">
      <template v-if="tpl.status === 'draft'">
        <p v-if="tpl.to_activate.length" class="mb-2 text-sm text-ink-gray-6">{{ t('To activate: {what}.', { what: tpl.to_activate.join('; ') }) }}</p>
        <div v-if="tpl.can_configure" class="flex flex-wrap items-end gap-2">
          <input v-model="x.password" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
          <Button variant="solid" :label="t('Activate (sign)')" :disabled="!x.password || !!tpl.to_activate.length || changed()" @click="call(`/api/production/templates/${tpl.id}/activate`, 'POST', { password: x.password }, t('Active: lots can start from it.'))" />
        </div>
        <p class="mt-2 text-sm text-ink-gray-5">{{ t('Activated by someone who did not draft or edit it; the version before it is retired.') }}</p>
      </template>
      <Button v-else :label="t('Start a new version')" @click="newVersion" />
      <details v-if="tpl.status === 'draft' || tpl.can_configure" class="mt-3"><summary class="cursor-pointer text-sm text-ink-gray-7">{{ tpl.status === 'draft' ? t('Withdraw the draft') : t('Retire this version') }}</summary>
        <div class="mt-2 flex gap-2"><input v-model="x.reason" class="wq-input w-96" :placeholder="t('Why')"><Button :label="tpl.status === 'draft' ? t('Withdraw') : t('Retire')" :disabled="!x.reason.trim()" @click="call(`/api/production/templates/${tpl.id}/end`, 'POST', { reason: x.reason }, t('Done.'))" /></div></details>
    </section>
    <p v-if="tpl.fingerprint" class="mb-4 text-xs text-ink-gray-5">{{ t('Fingerprint {code}', { code: tpl.fingerprint }) }}<span v-if="tpl.intact === false" class="text-ink-red-7"> {{ t('(no longer matches)') }}</span></p>
    <h2 class="wq-h2 mt-6">{{ t('Versions') }}</h2>
    <ul class="mb-4 text-sm"><li v-for="ver in tpl.versions" :key="ver.id"><RouterLink :to="`/quality/production/templates/${ver.id}`" class="hover:underline">v{{ ver.version }}</RouterLink> · {{ t(ver.status) }}<span v-if="ver.activated_by"> · {{ ver.activated_by }} {{ ver.activated_at?.slice(0, 10) }}</span></li></ul>
    <h2 class="wq-h2 mt-6">{{ t('Signatures') }}</h2>
    <Trail :items="tpl.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
    <Trail :items="tpl.history" />
  </template>
</template>
