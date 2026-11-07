<script setup>
// PLM parts (ADR-0026, 26a): the part master is the ERPNext item; here its revisions, status, category parameters
// and files. A new part gets the next number of its category; parts with the same required values are shown first.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { t } from '../i18n'
import { stl } from '../plm'

const router = useRouter()
const v = ref(null)
const cat = ref(null)
const error = ref('')
const done = ref('')
const show = ref(false)
const q = ref('')
const fcat = ref('')
const fstatus = ref('')
const f = ref({ name: '', category: 'other', source: 'make', uom: 'Nos', code: '', params: {}, link_existing: false })
const similar = ref([])
const num = ref({ category: '', prefix: '', digits: 5 })
const ST = { draft: 'gray', released: 'green', obsolete: 'red' }
const fields = computed(() => cat.value?.categories.find((c) => c.key === f.value.category)?.fields || [])
const catLabel = (k) => cat.value?.categories.find((c) => c.key === k)?.label || k

async function load() {
  error.value = ''
  try {
    if (!cat.value) cat.value = await api('/api/plm/catalog')
    const p = new URLSearchParams({ q: q.value, category: fcat.value, status: fstatus.value })
    v.value = await api(`/api/plm/parts?${p}`)
  } catch (e) { error.value = e.message }
}
watch([fcat, fstatus], load, { immediate: true })
watch(() => f.value.category, () => { f.value.params = {}; similar.value = [] })
watch(() => JSON.stringify(f.value.params), () => { similar.value = [] })

async function create(confirmNew = false) {
  error.value = ''
  const body = { ...f.value, confirm_new: confirmNew }
  if (!body.code.trim()) delete body.code
  let r, d
  try {
    r = await fetch('/api/plm/parts', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), credentials: 'same-origin' })
    d = r.headers.get('content-type')?.includes('json') ? await r.json() : { detail: await r.text() }
  } catch (e) { error.value = e.message; return }
  if (r.status === 409 && d.similar?.length) { similar.value = d.similar; error.value = d.detail; return }
  if (!r.ok) { error.value = d.detail; return }
  router.push(`/plm/parts/${d.id}`)
}
async function setNumbering() {
  error.value = ''; done.value = ''
  try {
    cat.value.numbering = (await api(`/api/plm/numbering/${num.value.category}`, { method: 'PUT', body: { prefix: num.value.prefix, digits: Number(num.value.digits) } })).numbering
    done.value = t('Saved.')
  } catch (e) { error.value = e.message }
}
watch(() => num.value.category, (k) => { if (k && cat.value) Object.assign(num.value, cat.value.numbering[k]) })
</script>

<template>
  <PageTop>
    <template #title>{{ t('Parts') }}</template>
    <Button v-if="v?.can_edit" variant="solid" icon-left="lucide-plus" :label="t('New part')" @click="show = !show" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <form v-if="show && cat" data-help="plm-new-part" class="wq-panel mb-5 grid gap-3 p-5 md:grid-cols-4" @submit.prevent="create(false)">
    <label class="wq-field md:col-span-2">{{ t('Name') }}<input v-model="f.name" class="wq-input"></label>
    <label class="wq-field">{{ t('Category') }}<select v-model="f.category" class="wq-select"><option v-for="c in cat.categories" :key="c.key" :value="c.key">{{ c.label }}</option></select></label>
    <label class="wq-field">{{ t('Made or bought') }}<select v-model="f.source" class="wq-select"><option value="make">{{ t('plm::Made') }}</option><option value="buy">{{ t('Bought') }}</option></select></label>
    <label class="wq-field">{{ t('Unit') }}<input v-model="f.uom" class="wq-input"></label>
    <label class="wq-field">{{ t('Code (empty: next number)') }}<input v-model="f.code" class="wq-input" :placeholder="cat.numbering[f.category]?.prefix + '-…'"></label>
    <label v-if="f.code.trim()" class="flex items-end gap-2 text-sm"><input v-model="f.link_existing" type="checkbox"> {{ t('ERPNext already has this item: link it') }}</label>
    <label v-for="x in fields" :key="x.key" class="wq-field">{{ x.label }}{{ x.unit ? ` (${x.unit})` : '' }}{{ x.required ? ' *' : '' }}
      <input v-model="f.params[x.key]" class="wq-input" :inputmode="x.min === null ? 'text' : 'decimal'"></label>
    <div class="flex items-end gap-2 md:col-span-4">
      <Button type="submit" variant="solid" :label="t('Create')" :disabled="!f.name.trim()" />
      <span class="text-sm text-ink-gray-5">{{ t('The item is made in ERPNext when you create the part.') }}</span>
    </div>
    <div v-if="similar.length" class="rounded border border-outline-amber-2 bg-surface-amber-1 p-3 text-sm md:col-span-4">
      <p class="mb-2">{{ t('These parts have the same required values:') }}</p>
      <ul class="mb-2 list-disc ps-5"><li v-for="s in similar" :key="s.id"><RouterLink :to="`/plm/parts/${s.id}`" class="wq-link">{{ s.code }}</RouterLink> {{ s.name }} ({{ t('rev {revision}', { revision: s.revision }) }})</li></ul>
      <Button :label="t('It is a new part: create it')" @click="create(true)" />
    </div>
  </form>

  <section v-if="v" data-help="plm-parts" class="wq-panel p-5">
    <form class="mb-3 flex flex-wrap gap-2" @submit.prevent="load">
      <input v-model="q" class="wq-input w-56" :placeholder="t('Code or name')">
      <select v-model="fcat" class="wq-select w-48"><option value="">{{ t('All categories') }}</option><option v-for="c in cat?.categories" :key="c.key" :value="c.key">{{ c.label }}</option></select>
      <select v-model="fstatus" class="wq-select w-40"><option value="">{{ t('All') }}</option><option value="draft">{{ t('plm::draft') }}</option><option value="released">{{ t('plm::released') }}</option><option value="obsolete">{{ t('plm::obsolete') }}</option></select>
      <Button type="submit" :label="t('Search')" />
    </form>
    <p v-if="!v.parts.length" class="wq-muted">{{ t('None.') }}</p>
    <p v-if="v.more" class="mb-2 text-sm text-ink-amber-7">{{ t('Only the first 500 are shown: search by code or name, or choose a category.') }}</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('plm::Code') }}</th><th>{{ t('Name') }}</th><th>{{ t('Category') }}</th><th>{{ t('Made or bought') }}</th><th>{{ t('Revision') }}</th><th>{{ t('Status') }}</th><th>ERPNext</th></tr></thead>
      <tbody><tr v-for="p in v.parts" :key="p.id">
        <td><RouterLink :to="`/plm/parts/${p.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ p.code }}</RouterLink></td>
        <td>{{ p.name }}</td><td>{{ catLabel(p.category) }}</td><td>{{ p.source === 'buy' ? t('Bought') : t('plm::Made') }}</td>
        <td>{{ p.revision }}<span v-if="p.rev_status === 'draft' && p.status !== 'draft'" class="text-ink-gray-5"> ({{ t('plm::draft') }})</span></td>
        <td><Badge :theme="ST[p.status]" :label="stl(p.status)" /></td>
        <td><Badge v-if="p.erp_state === 'failed'" theme="red" :label="t('failed')" /><span v-else-if="p.erp_state === 'pending'" class="text-ink-gray-5">–</span><span v-else class="text-ink-green-7">✓</span></td></tr></tbody></table>
  </section>

  <details v-if="cat?.can_release" class="wq-panel mt-5 p-5"><summary class="cursor-pointer text-base font-medium">{{ t('Part numbering') }}</summary>
    <table class="wq-table mt-3 text-sm"><thead><tr><th>{{ t('Category') }}</th><th>{{ t('Prefix') }}</th><th>{{ t('Digits') }}</th></tr></thead>
      <tbody><tr v-for="c in cat.categories" :key="c.key"><td>{{ c.label }}</td><td>{{ cat.numbering[c.key].prefix }}</td><td>{{ cat.numbering[c.key].digits }}</td></tr></tbody></table>
    <form class="mt-3 flex flex-wrap items-end gap-2" @submit.prevent="setNumbering">
      <label class="wq-field">{{ t('Category') }}<select v-model="num.category" class="wq-select"><option v-for="c in cat.categories" :key="c.key" :value="c.key">{{ c.label }}</option></select></label>
      <label class="wq-field">{{ t('Prefix') }}<input v-model="num.prefix" class="wq-input w-28"></label>
      <label class="wq-field">{{ t('Digits') }}<input v-model="num.digits" type="number" min="3" max="8" class="wq-input w-20"></label>
      <Button type="submit" :label="t('Save')" :disabled="!num.category" />
    </form>
  </details>
</template>
