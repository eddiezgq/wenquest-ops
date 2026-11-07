<script setup>
// One design BOM revision (ADR-0026, 26b): lines edited while it is a draft, the release checks, release (signed),
// the Draft BOM it becomes in ERPNext (submitted there by a person), and the difference from the revision before.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'
import { t } from '../i18n'
import { diffl, erpl, stl } from '../plm'

const route = useRoute()
const v = ref(null)
const parts = ref([])
const rows = ref([])
const note = ref('')
const error = ref('')
const done = ref('')
const pw = ref('')
const ST = { draft: 'gray', released: 'green', superseded: 'gray' }
const ERP = { draft: 'amber', submitted: 'green', cancelled: 'red', none: 'gray', unknown: 'gray' }
const draft = computed(() => v.value?.bom.status === 'draft')
const dirty = computed(() => JSON.stringify(rows.value.map(strip)) !== JSON.stringify((v.value?.lines || []).map(strip)) || note.value !== (v.value?.bom.note || ''))
const strip = (x) => ({ code: (x.code || '').trim(), qty: String(x.qty), uom: x.uom || '', note: x.note || '' })
const seen = ref({})          // parts found so far, by code (the list on the server can be longer than one page)
const byCode = computed(() => ({ ...seen.value, ...Object.fromEntries((v.value?.lines || []).map((x) => [x.code, { name: x.name, status: x.part_status, uom: x.uom }])) }))
let timer = null
function find(q) {
  clearTimeout(timer)
  timer = setTimeout(async () => {
    try {
      parts.value = (await api(`/api/plm/parts?q=${encodeURIComponent(q.trim())}`)).parts.slice(0, 50)
      seen.value = { ...seen.value, ...Object.fromEntries(parts.value.map((p) => [p.code, p])) }
    } catch { /* suggestions only */ }
  }, 250)
}

function set(d) {
  v.value = d
  rows.value = d.lines.map((x) => ({ code: x.code, qty: x.qty, uom: x.uom, note: x.note }))
  note.value = d.bom.note || ''
}
async function load() {
  error.value = ''
  try { set(await api(`/api/plm/boms/${route.params.id}`)) } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
async function call(path, method, body, msg) {
  error.value = ''; done.value = ''
  try { set(await api(path, { method, body })); done.value = msg; pw.value = '' } catch (e) { error.value = e.message }
}
const add = () => rows.value.push({ code: '', qty: 1, uom: '', note: '' })
function picked(r) { const p = byCode.value[r.code.trim()]; if (p && !r.uom) r.uom = p.uom }
const save = () => call(`/api/plm/boms/${v.value.bom.id}`, 'PUT', { lines: rows.value.filter((r) => r.code.trim()).map((r) => ({ ...r, code: r.code.trim(), uom: r.uom || undefined })), note: note.value }, t('Saved.'))
const release = () => call(`/api/plm/boms/${v.value.bom.id}/release`, 'POST', { password: pw.value }, t('Released. Submit the Draft BOM in ERPNext.'))
const toErp = () => call(`/api/plm/boms/${v.value.bom.id}/to-erp`, 'POST', {}, t('Tried again.'))
</script>

<template>
  <PageTop :crumbs="[{ label: t('Parts'), to: '/plm/parts' }, ...(v ? [{ label: v.part.code, to: `/plm/parts/${v.part.id}` }] : [])]">
    <template #title>{{ v ? t('BOM of {code}, revision {revision}', { code: v.part.code, revision: v.bom.revision }) : 'BOM' }}</template>
    <Badge v-if="v" :theme="ST[v.bom.status]" size="lg" :label="stl(v.bom.status)" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="v">
    <p class="mb-3 text-sm text-ink-gray-6">{{ v.part.name }}
      <span v-if="v.change"> · {{ t('Under change') }} <RouterLink :to="`/quality/changes/${v.change.id}`" class="wq-link">{{ v.change.name }}</RouterLink> {{ v.change.title }}</span></p>

    <section data-help="plm-bom-lines" class="wq-panel mb-5 p-5">
      <datalist id="plm-parts"><option v-for="p in parts" :key="p.id" :value="p.code">{{ p.name }}</option></datalist>
      <table class="wq-table text-sm"><thead><tr><th>#</th><th>{{ t('Part') }}</th><th>{{ t('Name') }}</th><th>{{ t('Quantity') }}</th><th>{{ t('Unit') }}</th><th>{{ t('Note') }}</th><th>{{ t('Status') }}</th><th /></tr></thead>
        <tbody><tr v-for="(r, i) in rows" :key="i">
          <td>{{ i + 1 }}</td>
          <td><input v-if="draft && v.can_edit" v-model="r.code" list="plm-parts" class="wq-input w-36" @input="find(r.code)" @change="picked(r)"><RouterLink v-else :to="`/plm/parts/${v.lines[i]?.part_id}`" class="wq-link">{{ r.code }}</RouterLink></td>
          <td>{{ byCode[r.code?.trim()]?.name || v.lines[i]?.name || '' }}</td>
          <td><input v-if="draft && v.can_edit" v-model="r.qty" class="wq-input w-20" inputmode="decimal"><span v-else>{{ r.qty }}</span></td>
          <td><input v-if="draft && v.can_edit" v-model="r.uom" class="wq-input w-20"><span v-else>{{ r.uom }}</span></td>
          <td><input v-if="draft && v.can_edit" v-model="r.note" class="wq-input w-40"><span v-else>{{ r.note }}</span></td>
          <td>{{ byCode[r.code?.trim()]?.status ? stl(byCode[r.code.trim()].status) : '' }}</td>
          <td><button v-if="draft && v.can_edit" class="text-ink-red-7" @click="rows.splice(i, 1)">{{ t('Remove') }}</button></td></tr></tbody></table>
      <p v-if="!rows.length" class="wq-muted mt-2">{{ t('No lines yet.') }}</p>
      <label class="wq-field mt-3">{{ t('Note') }}<textarea v-model="note" rows="2" class="wq-input" :disabled="!draft || !v.can_edit" /></label>
      <div v-if="draft && v.can_edit" class="mt-3 flex gap-2">
        <Button icon-left="lucide-plus" :label="t('Add a line')" @click="add" />
        <Button variant="solid" :label="t('Save')" :disabled="!dirty" @click="save" />
      </div>
    </section>

    <section v-if="draft" data-help="plm-bom-checks" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Before release') }}</h2>
      <p v-for="c in v.checks" :key="c.check" class="text-sm"><span :class="c.result === 'pass' ? 'text-ink-green-7' : c.result === 'fail' ? 'text-ink-red-7' : 'text-ink-amber-7'">{{ c.result === 'pass' ? '✓' : c.result === 'fail' ? '✗' : '?' }}</span>
        {{ c.check }}<span v-if="c.detail" class="text-ink-gray-5">: {{ c.detail }}</span></p>
      <p class="mt-2 text-sm text-ink-gray-5">{{ t('A check without the data it needs is unknown, and does not pass.') }}</p>
      <div v-if="v.can_release" class="mt-3 flex items-end gap-2">
        <input v-model="pw" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
        <Button variant="solid" :label="t('plm::Release (sign)')" :disabled="!pw || !v.ready || dirty" @click="release" />
      </div>
    </section>

    <section v-else data-help="plm-bom-erp" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">ERPNext</h2>
      <p class="text-sm"><span v-if="v.bom.erp_bom">{{ v.bom.erp_bom }} </span><Badge :theme="ERP[v.erp_status]" :label="erpl(v.erp_status)" /></p>
      <p v-if="v.erp_status === 'draft'" class="mt-2 text-sm text-ink-gray-6">{{ t('Open it in ERPNext and submit it: production uses it from then on.') }}</p>
      <p v-if="v.bom.erp_error" class="mt-2 text-sm text-ink-red-7">{{ v.bom.erp_error }} <Button v-if="v.can_edit" size="sm" :label="t('Try again')" @click="toErp" /></p>
    </section>

    <section v-if="v.previous" data-help="plm-bom-diff" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Changes from revision {revision}', { revision: v.previous.revision }) }}</h2>
      <p v-if="!v.previous.diff.length" class="wq-muted">{{ t('No difference.') }}</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Part') }}</th><th>{{ t('Name') }}</th><th>{{ t('Change') }}</th><th>{{ t('plm::Before') }}</th><th>{{ t('plm::After') }}</th></tr></thead>
        <tbody><tr v-for="d in v.previous.diff" :key="d.code"><td>{{ d.code }}</td><td>{{ d.name }}</td><td>{{ diffl(d.change) }}</td><td>{{ d.old || '–' }}</td><td>{{ d.new || '–' }}</td></tr></tbody></table>
    </section>

    <section class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Revisions') }}</h2>
      <p class="text-sm"><span v-for="r in v.revisions" :key="r.id" class="me-3"><RouterLink :to="`/plm/boms/${r.id}`" class="wq-link">{{ r.revision }}</RouterLink> ({{ stl(r.status) }})</span></p>
    </section>
    <h2 class="wq-h2 mt-6">{{ t('Signatures') }}</h2>
    <Trail :items="v.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
    <Trail :items="v.history" />
  </template>
</template>
