<script setup>
// One batch of design data (ADR-0026, 26e): match each part or make it new, pick the approved design change for an
// assembly whose BOM is released, then write it with a signature (parts and draft BOMs; nothing is released).
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'
import { t } from '../i18n'
import { stl } from '../plm'

const route = useRoute()
const v = ref(null)
const plan = ref({})
const changes = ref({})
const saved = ref('')
const approved = ref([])
const error = ref('')
const done = ref('')
const pw = ref('')
const note = ref('')
const codes = ref({})
const dirty = computed(() => JSON.stringify([plan.value, changes.value]) !== saved.value)
const pending = computed(() => v.value?.status === 'pending')

function set(d) {
  v.value = d
  plan.value = Object.fromEntries(d.rows.map((r) => [r.key, { ...(r.plan || { action: 'new', category: 'other', source: 'make', uom: 'Nos' }) }]))
  changes.value = { ...d.changes }
  codes.value = Object.fromEntries(d.rows.map((r) => [r.key, r.part?.item_code || '']))
  saved.value = JSON.stringify([plan.value, changes.value])
}
async function load() {
  error.value = ''
  try { set(await api(`/api/plm/intake/${route.params.id}`)); approved.value = (await api('/api/plm/changes')).changes } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
async function matchCode(key) {
  const code = (codes.value[key] || '').trim()
  if (!code) return
  try {
    const r = await api(`/api/plm/parts?q=${encodeURIComponent(code)}`)
    const p = r.parts.find((x) => x.code === code)
    if (p) plan.value[key] = { action: 'match', part_id: p.id }
    else error.value = t('No part {code}.', { code })
  } catch (e) { error.value = e.message }
}
async function call(method, path, body, msg) {
  error.value = ''; done.value = ''
  try { set(await api(path, { method, body })); done.value = msg; pw.value = '' } catch (e) { error.value = e.message }
}
const save = () => call('PUT', `/api/plm/intake/${v.value.id}`, { plan: plan.value, changes: changes.value }, t('Saved.'))
const write = () => call('POST', `/api/plm/intake/${v.value.id}/write`, { password: pw.value }, t('Written: the parts and draft BOMs are made.'))
const reject = () => call('POST', `/api/plm/intake/${v.value.id}/reject`, { note: note.value }, t('Not taken.'))
const istl = (s) => ({ pending: t('intake::pending'), written: t('intake::written'), rejected: t('intake::rejected') })[s] || s
const catL = (k) => v.value?.categories.find((c) => c.key === k)?.label || k
</script>

<template>
  <PageTop :crumbs="[{ label: t('Design data'), to: '/plm/intake' }]">
    <template #title>{{ v ? t('Design data #{id}', { id: v.id }) : t('Design data') }}</template>
    <Badge v-if="v" size="lg" :theme="v.status === 'written' ? 'green' : v.status === 'rejected' ? 'red' : 'orange'" :label="istl(v.status)" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="v">
    <p class="mb-3 text-sm text-ink-gray-6">{{ t('From {who}', { who: v.sent_by }) }} · {{ v.source }} <a v-if="v.file_name" :href="`/api/plm/intake/${v.id}/file`" class="wq-link">{{ v.file_name }}</a></p>
    <section data-help="plm-intake-rows" class="wq-panel mb-5 p-5">
      <table class="wq-table text-sm"><thead><tr><th>{{ t('Name') }}</th><th>{{ t('plm::Code') }}</th><th>{{ t('Under it') }}</th><th>{{ t('It is') }}</th><th /></tr></thead>
        <tbody><tr v-for="r in v.rows" :key="r.key">
          <td>{{ r.name }}<span v-if="r.file" class="ms-1 text-ink-gray-5">· {{ r.file.name }}</span><span v-if="r.material" class="ms-1 text-ink-gray-5">· {{ r.material }}</span></td>
          <td>{{ r.code || '–' }}</td><td>{{ r.children || '' }}</td>
          <td>
            <template v-if="pending && v.can_edit">
              <select v-model="plan[r.key].action" class="wq-select w-36"><option value="match">{{ t('An existing part') }}</option><option value="new">{{ t('A new part') }}</option></select>
              <template v-if="plan[r.key].action === 'match'">
                <input v-model="codes[r.key]" class="wq-input ms-1 w-36" :placeholder="t('Part code')" @change="matchCode(r.key)">
                <span v-if="r.like?.length" class="ms-1 text-ink-gray-5">{{ t('maybe') }}: <button v-for="l in r.like" :key="l.id" class="wq-link me-1" @click="codes[r.key] = l.item_code; plan[r.key] = { action: 'match', part_id: l.id }">{{ l.item_code }}</button></span>
              </template>
              <template v-else>
                <select v-model="plan[r.key].category" class="wq-select ms-1 w-40"><option v-for="c in v.categories" :key="c.key" :value="c.key">{{ c.label }}</option></select>
                <select v-model="plan[r.key].source" class="wq-select ms-1 w-24"><option value="make">{{ t('plm::Made') }}</option><option value="buy">{{ t('Bought') }}</option></select>
                <input v-model="plan[r.key].uom" class="wq-input ms-1 w-20">
              </template>
            </template>
            <template v-else>
              <span v-if="r.part"><RouterLink :to="`/plm/parts/${r.part.id}`" class="wq-link">{{ r.part.item_code }}</RouterLink> {{ r.part.name }}</span>
              <span v-else-if="r.plan?.action === 'new'">{{ t('A new part') }} · {{ catL(r.plan.category) }}</span>
            </template>
          </td>
          <td><template v-if="r.bom?.status === 'released' && pending">
            <select v-model="changes[r.key]" class="wq-select w-56"><option :value="undefined">{{ t('Approved product change…') }}</option><option v-for="c in approved" :key="c.id" :value="c.id">{{ c.name }} {{ c.title }}</option></select></template>
            <span v-else-if="r.bom">BOM {{ r.bom.revision }} ({{ stl(r.bom.status) }})</span></td></tr></tbody></table>
      <div v-if="pending && v.can_edit" class="mt-3"><Button :label="t('Save')" :disabled="!dirty" @click="save" /></div>
    </section>
    <section v-if="pending && v.can_edit" class="wq-panel mb-5 p-5">
      <p v-for="p in v.problems" :key="p" class="text-sm text-ink-red-7">✗ {{ p }}</p>
      <p v-if="!v.problems.length" class="text-sm text-ink-green-7">✓ {{ t('Ready to write. New parts and their ERPNext items are made; BOMs become drafts; nothing is released.') }}</p>
      <div class="mt-3 flex flex-wrap items-end gap-2">
        <input v-model="pw" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
        <Button variant="solid" :label="t('Write (sign)')" :disabled="!pw || dirty || v.problems.length > 0" @click="write" />
        <span v-if="dirty" class="text-sm text-ink-amber-7">{{ t('Save first.') }}</span>
        <input v-model="note" class="wq-input ms-6 w-64" :placeholder="t('Why it is not taken')">
        <Button :label="t('Do not take it')" :disabled="!note.trim()" @click="reject" />
      </div>
    </section>
    <section v-if="v.result" class="wq-panel mb-5 p-5 text-sm">
      <p>{{ t('Parts made: {list}', { list: v.result.parts_made.join(', ') || '–' }) }}</p>
      <p>{{ t('Draft BOMs:') }} <RouterLink v-for="b in v.result.boms" :key="b" :to="`/plm/boms/${b}`" class="wq-link me-2">#{{ b }}</RouterLink></p>
      <p v-for="n in v.result.notes" :key="n" class="text-ink-amber-7">{{ n }}</p>
    </section>
    <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
    <Trail :items="v.history" />
  </template>
</template>
