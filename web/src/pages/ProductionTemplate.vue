<script setup>
// A production template (ADR-0017, 17i): the steps of making an item, activated with a signature and then fixed.
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const t = ref(null)
const error = ref('')
const done = ref('')
const f = ref({ title: '', documents: [], materials: [] })
const x = ref({ password: '', reason: '' })
const blank = () => ({ name: '', kind: 'check', instruction: '', low: '', high: '', unit: '', gauge_required: false })
const step = ref(blank())
const editing = ref(null)
const ST = { draft: 'gray', active: 'green', retired: 'gray', withdrawn: 'gray' }

function set(v) { t.value = v; f.value = { title: v.title, documents: [...v.documents], materials: [...v.materials] } }
async function load() { error.value = ''; try { set(await api(`/api/production/templates/${route.params.id}`)) } catch (e) { error.value = e.message } }
watch(() => route.params.id, load, { immediate: true })
async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { const v = await api(path, { method, body }); set(v); done.value = message; x.value = { password: '', reason: '' }; return v } catch (e) { error.value = e.message }
}
const draft = () => t.value?.status === 'draft' && t.value?.can_edit
const changed = () => JSON.stringify(f.value) !== JSON.stringify({ title: t.value.title, documents: t.value.documents, materials: t.value.materials })
async function saveStep() {
  const body = { ...step.value, low: step.value.low === '' ? null : step.value.low, high: step.value.high === '' ? null : step.value.high }
  const ok = editing.value
    ? await call(`/api/production/templates/${t.value.id}/steps/${editing.value}`, 'PUT', body, 'Saved.')
    : await call(`/api/production/templates/${t.value.id}/steps`, 'POST', body, 'Added.')
  if (ok) { step.value = blank(); editing.value = null }
}
function edit(s) { editing.value = s.id; step.value = { name: s.name, kind: s.kind, instruction: s.instruction, low: s.low ?? '', high: s.high ?? '', unit: s.unit, gauge_required: s.gauge_required } }
async function newVersion() {
  const v = await call(`/api/production/templates/${t.value.id}/new-version`, 'POST', {}, 'A new version is started.')
  if (v) router.push(`/quality/production/templates/${v.id}`)
}
const limits = (s) => s.kind !== 'measure' ? '' : [s.low ?? '…', s.high ?? '…'].join(' – ') + (s.unit ? ` ${s.unit}` : '')
</script>

<template>
  <PageTop :crumbs="[{ label: 'Production records', to: '/quality/production' }]">
    <template #title>{{ t ? `${t.code} v${t.version} · ${t.item_code}` : 'Template' }}</template>
    <Badge v-if="t" :theme="ST[t.status]" size="lg" :label="t.status" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="t">
    <section class="what wq-panel mb-5 grid gap-3 p-5 md:grid-cols-3">
      <label class="wq-field md:col-span-3">Title<input v-model="f.title" class="wq-input" :disabled="!draft()"></label>
      <label class="wq-field">Documents the steps follow (operators confirm reading them)<select v-model="f.documents" multiple class="wq-select h-24" :disabled="!draft()">
        <option v-for="d in t.documents_in_effect" :key="d" :value="d">{{ d }}</option></select></label>
      <label class="wq-field">Materials each lot must record<select v-model="f.materials" multiple class="wq-select h-24" :disabled="!draft()">
        <option v-for="i in t.items" :key="i.item_code" :value="i.item_code">{{ i.item_code }} · {{ i.name }}</option></select></label>
      <div v-if="draft()" class="self-end"><Button label="Save" :disabled="!changed()" @click="call(`/api/production/templates/${t.id}`, 'PUT', f, 'Saved.')" /></div>
    </section>

    <section class="steps wq-panel mb-5 p-5">
      <h2 class="wq-h2">Steps</h2>
      <p v-if="!t.steps.length" class="wq-muted">None yet.</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>#</th><th>Step</th><th>Kind</th><th>Limits</th><th>Equipment</th><th>Instruction</th><th /></tr></thead>
        <tbody><tr v-for="s in t.steps" :key="s.id"><td>{{ s.seq }}</td><td>{{ s.name }}</td><td>{{ s.kind }}</td><td>{{ limits(s) }}</td>
          <td>{{ s.gauge_required ? 'required' : '' }}</td><td>{{ s.instruction }}</td>
          <td class="whitespace-nowrap"><template v-if="draft()"><Button size="sm" label="Edit" @click="edit(s)" />
            <Button size="sm" variant="ghost" label="Remove" @click="call(`/api/production/templates/${t.id}/steps/${s.id}`, 'DELETE', null, 'Removed.')" /></template></td></tr></tbody></table>
      <form v-if="draft()" class="step mt-4 flex flex-wrap items-end gap-3" @submit.prevent="saveStep">
        <label class="wq-field grow">Step<input v-model="step.name" class="wq-input"></label>
        <label class="wq-field">Kind<select v-model="step.kind" class="wq-select"><option value="check">check (pass / fail)</option><option value="measure">measurement</option><option value="record">record (text)</option></select></label>
        <template v-if="step.kind === 'measure'">
          <label class="wq-field w-24">Lower<input v-model="step.low" class="wq-input"></label>
          <label class="wq-field w-24">Upper<input v-model="step.high" class="wq-input"></label>
          <label class="wq-field w-20">Unit<input v-model="step.unit" class="wq-input"></label>
          <label class="text-sm"><input v-model="step.gauge_required" type="checkbox"> equipment required</label>
        </template>
        <label class="wq-field basis-full">Instruction<textarea v-model="step.instruction" rows="2" class="wq-input" /></label>
        <Button type="submit" variant="solid" :label="editing ? 'Save the step' : 'Add the step'" :disabled="!step.name.trim()" />
        <Button v-if="editing" label="Stop editing" @click="editing = null; step = blank()" />
      </form>
    </section>

    <section v-if="t.can_edit && ['draft', 'active'].includes(t.status)" class="act wq-panel mb-5 p-5">
      <template v-if="t.status === 'draft'">
        <p v-if="t.to_activate.length" class="mb-2 text-sm text-ink-gray-6">To activate: {{ t.to_activate.join('; ') }}.</p>
        <div v-if="t.can_configure" class="flex flex-wrap items-end gap-2">
          <input v-model="x.password" type="password" class="wq-input w-44" placeholder="Your password" autocomplete="current-password">
          <Button variant="solid" label="Activate (sign)" :disabled="!x.password || !!t.to_activate.length || changed()" @click="call(`/api/production/templates/${t.id}/activate`, 'POST', { password: x.password }, 'Active: lots can start from it.')" />
        </div>
        <p class="mt-2 text-sm text-ink-gray-5">Activated by someone who did not draft or edit it; the version before it is retired.</p>
      </template>
      <Button v-else label="Start a new version" @click="newVersion" />
      <details v-if="t.status === 'draft' || t.can_configure" class="mt-3"><summary class="cursor-pointer text-sm text-ink-gray-7">{{ t.status === 'draft' ? 'Withdraw the draft' : 'Retire this version' }}</summary>
        <div class="mt-2 flex gap-2"><input v-model="x.reason" class="wq-input w-96" placeholder="Why"><Button :label="t.status === 'draft' ? 'Withdraw' : 'Retire'" :disabled="!x.reason.trim()" @click="call(`/api/production/templates/${t.id}/end`, 'POST', { reason: x.reason }, 'Done.')" /></div></details>
    </section>
    <p v-if="t.fingerprint" class="mb-4 text-xs text-ink-gray-5">Fingerprint {{ t.fingerprint }}<span v-if="t.intact === false" class="text-ink-red-7"> (no longer matches)</span></p>
    <h2 class="wq-h2 mt-6">Versions</h2>
    <ul class="mb-4 text-sm"><li v-for="ver in t.versions" :key="ver.id"><RouterLink :to="`/quality/production/templates/${ver.id}`" class="hover:underline">v{{ ver.version }}</RouterLink> · {{ ver.status }}<span v-if="ver.activated_by"> · {{ ver.activated_by }} {{ ver.activated_at?.slice(0, 10) }}</span></li></ul>
    <h2 class="wq-h2 mt-6">Signatures</h2>
    <Trail :items="t.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">History</h2>
    <Trail :items="t.history" />
  </template>
</template>
