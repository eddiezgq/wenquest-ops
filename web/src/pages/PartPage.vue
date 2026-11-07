<script setup>
// One part (ADR-0026, 26a): its revisions, the parameters of the draft revision, files, release (signed), a new
// revision under an approved product change, where it is used, and its BOM.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api, apiForm } from '../api'
import { t } from '../i18n'
import { fkl, stl } from '../plm'

const route = useRoute()
const router = useRouter()
const v = ref(null)
const changes = ref([])
const error = ref('')
const done = ref('')
const f = ref({ params: {}, description: '' })
const head = ref({})
const pw = ref('')
const change = ref('')
const kind = ref('model')
const file = ref(null)
const ST = { draft: 'gray', released: 'green', superseded: 'gray', obsolete: 'red' }
const draft = computed(() => v.value?.revisions.find((r) => r.status === 'draft'))
const shown = computed(() => draft.value || v.value?.revisions.at(-1))
const bomDraft = computed(() => v.value?.boms.find((b) => b.status === 'draft'))
const bomLatest = computed(() => bomDraft.value || v.value?.boms.at(-1))

function set(d) {
  v.value = d
  const r = d.revisions.find((x) => x.status === 'draft') || d.revisions.at(-1)
  f.value = { params: { ...(r?.params || {}) }, description: r?.description || '' }
  head.value = { name: d.part.name, source: d.part.source, uom: d.part.uom }
}
async function load() {
  error.value = ''
  try { set(await api(`/api/plm/parts/${route.params.id}`)); changes.value = (await api('/api/plm/changes')).changes } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
async function call(path, method, body, msg) {
  error.value = ''; done.value = ''
  try { set(await api(path, { method, body })); done.value = msg; pw.value = '' } catch (e) { error.value = e.message }
}
const id = () => v.value.part.id
function save() {
  const body = { params: f.value.params, description: f.value.description }
  if (v.value.part.status === 'draft') Object.assign(body, head.value)
  call(`/api/plm/parts/${id()}`, 'PUT', body, t('Saved.'))
}
const release = () => call(`/api/plm/parts/${id()}/release`, 'POST', { password: pw.value }, t('plm::Released.'))
const newRevision = () => call(`/api/plm/parts/${id()}/new-revision`, 'POST', { change_id: Number(change.value) }, t('New revision started.'))
const retry = () => call(`/api/plm/parts/${id()}/retry-erp`, 'POST', {}, t('Tried again.'))
async function upload() {
  error.value = ''; done.value = ''
  const form = new FormData(); form.append('kind', kind.value); form.append('file', file.value)
  try { set(await apiForm(`/api/plm/parts/${id()}/files`, form)); done.value = t('File added.'); file.value = null } catch (e) { error.value = e.message }
}
const removeFile = (fid) => call(`/api/plm/parts/${id()}/files/${fid}/remove`, 'POST', {}, t('File removed.'))
async function startBom() {
  error.value = ''
  try {
    const body = v.value.boms.length ? { change_id: Number(change.value) } : {}
    const b = await api(`/api/plm/parts/${id()}/bom`, { method: 'POST', body })
    router.push(`/plm/boms/${b.bom.id}`)
  } catch (e) { error.value = e.message }
}
const kb = (n) => (n / 1024).toFixed(n < 10240 ? 1 : 0) + ' KB'
</script>

<template>
  <PageTop :crumbs="[{ label: t('Parts'), to: '/plm/parts' }]">
    <template #title>{{ v ? `${v.part.item_code} · ${v.part.name}` : t('Part') }}</template>
    <Badge v-if="v" :theme="ST[v.part.status]" size="lg" :label="stl(v.part.status)" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="v">
    <section data-help="plm-part" class="wq-panel mb-5 grid gap-3 p-5 md:grid-cols-4">
      <label class="wq-field md:col-span-2">{{ t('Name') }}<input v-model="head.name" class="wq-input" :disabled="!v.can_edit || v.part.status !== 'draft'"></label>
      <label class="wq-field">{{ t('Made or bought') }}<select v-model="head.source" class="wq-select" :disabled="!v.can_edit || v.part.status !== 'draft'"><option value="make">{{ t('plm::Made') }}</option><option value="buy">{{ t('Bought') }}</option></select></label>
      <label class="wq-field">{{ t('Unit') }}<input v-model="head.uom" class="wq-input" :disabled="!v.can_edit || v.part.status !== 'draft'"></label>
      <p class="text-sm text-ink-gray-6 md:col-span-4">{{ t('Category') }}: {{ v.category.label }} ·
        ERPNext: <span v-if="['created', 'existing'].includes(v.part.erp_state)" class="text-ink-green-7">{{ t('item {code}', { code: v.part.item_code }) }}</span>
        <span v-else class="text-ink-red-7">{{ t('not made yet') }} {{ v.part.erp_error || '' }}
          <Button v-if="v.can_edit" size="sm" :label="t('Try again')" @click="retry" /></span></p>
    </section>

    <section data-help="plm-revision" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Revision {revision}', { revision: shown.revision }) }} <Badge :theme="ST[shown.status]" :label="stl(shown.status)" /></h2>
      <p v-if="shown.change" class="mb-2 text-sm">{{ t('Under change') }} <RouterLink :to="`/quality/changes/${shown.change_id}`" class="wq-link">{{ shown.change.name }}</RouterLink> {{ shown.change.title }}</p>
      <div class="grid gap-3 md:grid-cols-4">
        <label v-for="x in v.category.fields" :key="x.key" class="wq-field">{{ x.label }}{{ x.unit ? ` (${x.unit})` : '' }}{{ x.required ? ' *' : '' }}
          <input v-model="f.params[x.key]" class="wq-input" :disabled="!draft || !v.can_edit"></label>
        <label class="wq-field md:col-span-4">{{ t('Description') }}<textarea v-model="f.description" rows="2" class="wq-input" :disabled="!draft || !v.can_edit" /></label>
      </div>
      <h3 class="mt-4 mb-2 text-base font-medium">{{ t('Files') }}</h3>
      <p v-if="!shown.files.length" class="wq-muted">{{ t('None.') }}</p>
      <ul v-else class="text-sm"><li v-for="x in shown.files" :key="x.id" class="mb-1">
        <a :href="`/api/plm/parts/${v.part.id}/files/${x.id}`" class="wq-link">{{ x.name }}</a> · {{ fkl(x.kind) }} · {{ kb(x.size_bytes) }}
        <button v-if="draft && v.can_edit" class="ms-2 text-ink-red-7" @click="removeFile(x.id)">{{ t('Remove') }}</button></li></ul>
      <form v-if="draft && v.can_edit" class="mt-2 flex flex-wrap items-end gap-2" @submit.prevent="upload">
        <select v-model="kind" class="wq-select w-36"><option v-for="k in ['model', 'drawing', 'image', 'other']" :key="k" :value="k">{{ fkl(k) }}</option></select>
        <input type="file" class="text-sm" @change="file = $event.target.files[0]">
        <Button type="submit" :label="t('Add file')" :disabled="!file" />
      </form>
      <div v-if="draft" class="mt-4">
        <p v-for="c in draft.checks" :key="c.check" class="text-sm"><span :class="c.result === 'pass' ? 'text-ink-green-7' : c.result === 'fail' ? 'text-ink-red-7' : 'text-ink-amber-7'">{{ c.result === 'pass' ? '✓' : c.result === 'fail' ? '✗' : '?' }}</span>
          {{ c.check }}<span v-if="c.detail" class="text-ink-gray-5">: {{ c.detail }}</span></p>
      </div>
      <div class="mt-4 flex flex-wrap items-end gap-2">
        <Button v-if="draft && v.can_edit" :label="t('Save')" @click="save" />
        <template v-if="draft && v.can_release">
          <input v-model="pw" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
          <Button variant="solid" :label="t('plm::Release (sign)')" :disabled="!pw || !draft.ready" @click="release" />
        </template>
        <template v-if="!draft && v.can_edit && v.part.status === 'released'">
          <select v-model="change" class="wq-select w-72"><option value="">{{ t('Approved product change…') }}</option><option v-for="c in changes" :key="c.id" :value="c.id">{{ c.name }} {{ c.title }}</option></select>
          <Button :label="t('Start a new revision')" :disabled="!change" @click="newRevision" />
          <RouterLink v-if="!changes.length" to="/quality/changes" class="wq-link text-sm">{{ t('Raise a product change first') }}</RouterLink>
        </template>
      </div>
    </section>

    <section data-help="plm-revisions" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Revisions') }}</h2>
      <table class="wq-table text-sm"><thead><tr><th>{{ t('Revision') }}</th><th>{{ t('Status') }}</th><th>{{ t('Change') }}</th><th>{{ t('Released by') }}</th><th>{{ t('Released at') }}</th></tr></thead>
        <tbody><tr v-for="r in v.revisions" :key="r.id"><td>{{ r.revision }}</td><td><Badge :theme="ST[r.status]" :label="stl(r.status)" /></td>
          <td>{{ r.change?.name || '–' }}</td><td>{{ r.released_by || '–' }}</td><td>{{ r.released_at?.slice(0, 16).replace('T', ' ') || '–' }}</td></tr></tbody></table>
    </section>

    <section v-if="v.part.source === 'make'" data-help="plm-bom" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">BOM</h2>
      <p v-if="!v.boms.length" class="wq-muted">{{ t('No BOM yet.') }}</p>
      <p v-else class="text-sm"><RouterLink :to="`/plm/boms/${bomLatest.id}`" class="wq-link">{{ t('BOM revision {revision}', { revision: bomLatest.revision }) }}</RouterLink>
        <Badge class="ms-2" :theme="ST[bomLatest.status]" :label="stl(bomLatest.status)" /></p>
      <div v-if="v.can_edit && !bomDraft" class="mt-2 flex flex-wrap items-end gap-2">
        <select v-if="v.boms.length" v-model="change" class="wq-select w-72"><option value="">{{ t('Approved product change…') }}</option><option v-for="c in changes" :key="c.id" :value="c.id">{{ c.name }} {{ c.title }}</option></select>
        <Button :label="v.boms.length ? t('Start a new BOM revision') : t('Start the BOM')" :disabled="!!v.boms.length && !change" @click="startBom" />
      </div>
    </section>

    <section data-help="plm-where-used" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Where used') }}</h2>
      <p v-if="!v.where_used.length" class="wq-muted">{{ t('None.') }}</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Assembly') }}</th><th>{{ t('BOM revision') }}</th><th>{{ t('Quantity') }}</th><th>{{ t('Status') }}</th></tr></thead>
        <tbody><tr v-for="w in v.where_used" :key="w.bom_id"><td><RouterLink :to="`/plm/parts/${w.part_id}`" class="wq-link">{{ w.item_code }}</RouterLink> {{ w.name }}</td>
          <td><RouterLink :to="`/plm/boms/${w.bom_id}`" class="wq-link">{{ w.revision }}</RouterLink></td><td>{{ w.qty }} {{ w.uom }}</td><td>{{ stl(w.status) }}</td></tr></tbody></table>
    </section>
    <h2 class="wq-h2 mt-6">{{ t('Signatures') }}</h2>
    <Trail :items="v.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
    <Trail :items="v.history" />
  </template>
</template>
