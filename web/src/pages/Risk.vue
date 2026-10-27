<script setup>
// Risk management (ADR-0017, 17h): risk management files per product, and the company's own criteria (severity and
// probability levels, and the matrix that decides acceptability). Acceptability is looked up, never typed.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'
import { t } from '../i18n'

const router = useRouter()
const v = ref(null)
const error = ref('')
const status = ref('current')
const show = ref(false)
const f = ref({ product: '', scope: '', owner: '' })
const lv = ref({ kind: 'severity', rank: '', name: '', description: '' })
const ST = { draft: 'gray', approved: 'green', superseded: 'gray', withdrawn: 'gray' }
const VT = { acceptable: 'green', reduce: 'amber', unacceptable: 'red' }
async function load() { try { v.value = await api(`/api/risk?status=${status.value}`) } catch (e) { error.value = e.message } }
watch(status, load, { immediate: true })
const sev = computed(() => (v.value?.levels || []).filter((l) => l.kind === 'severity' && l.active).sort((a, b) => b.rank - a.rank))
const prob = computed(() => (v.value?.levels || []).filter((l) => l.kind === 'probability' && l.active).sort((a, b) => a.rank - b.rank))
const cell = (s, p) => v.value.matrix.find((m) => m.severity === s && m.probability === p)?.verdict || ''

async function call(path, method, body) {
  error.value = ''
  try { const r = await api(path, { method, body }); Object.assign(v.value, r); return r } catch (e) { error.value = e.message; load() }
}
async function create() {
  error.value = ''
  try { const r = await api('/api/risk/files', { method: 'POST', body: f.value }); router.push(`/quality/risk/${r.id}`) } catch (e) { error.value = e.message }
}
const setCell = (s, p, verdict) => call('/api/risk/matrix', 'PUT', { severity: s, probability: p, verdict: verdict || null })
async function addLevel() {
  if (await call('/api/risk/levels', 'POST', { ...lv.value, rank: Number(lv.value.rank) })) lv.value = { kind: lv.value.kind, rank: '', name: '', description: '' }
  load()
}
const changeLevel = async (l, body) => { await call(`/api/risk/levels/${l.id}`, 'PUT', body); load() }
const example = async () => { await call('/api/risk/example', 'POST'); load() }
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality', to: '/quality' }]">
    <template #title>Risk management</template>
    <Button v-if="v?.can_edit" variant="solid" icon-left="lucide-plus" :label="t('New risk file')" @click="show = !show" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <form v-if="show" class="new wq-panel mb-5 flex flex-wrap items-end gap-3 p-5" @submit.prevent="create">
    <label class="wq-field grow">{{ t('Product or product family') }}<input v-model="f.product" class="wq-input"></label>
    <label class="wq-field">{{ t('Owner') }}<select v-model="f.owner" class="wq-select"><option value="" /><option v-for="p in v?.people" :key="p">{{ p }}</option></select></label>
    <label class="wq-field basis-full">{{ t('Scope') }}<textarea v-model="f.scope" rows="2" class="wq-input" /></label>
    <Button type="submit" variant="solid" :label="t('Start')" :disabled="!f.product.trim()" />
  </form>

  <template v-if="v">
    <section data-help="risk-files" class="files wq-panel mb-5 p-5">
      <div class="mb-3"><select v-model="status" class="wq-select w-40"><option value="current">{{ t('Current') }}</option><option value="draft">{{ t('Drafts') }}</option><option value="approved">{{ t('Approved') }}</option><option value="all">{{ t('All versions') }}</option></select></div>
      <p v-if="!v.files.length" class="wq-muted">{{ t('None.') }}</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Number') }}</th><th>{{ t('Version') }}</th><th>{{ t('Product') }}</th><th>{{ t('Status') }}</th><th>{{ t('Owner') }}</th><th>{{ t('Hazards') }}</th><th>{{ t('Approved') }}</th></tr></thead>
        <tbody><tr v-for="r in v.files" :key="r.id">
          <td><RouterLink :to="`/quality/risk/${r.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ r.name }}</RouterLink></td>
          <td>{{ r.version }}</td><td>{{ r.product }}</td><td><Badge :theme="ST[r.status]" :label="t(r.status)" /></td><td>{{ r.owner }}</td>
          <td>{{ r.items }}</td><td>{{ r.approved_at ? `${r.approved_at.slice(0, 10)} · ${r.approved_by}` : '' }}</td></tr></tbody></table>
    </section>

    <section data-help="risk-criteria" class="criteria wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t("The company's risk criteria") }}</h2>
      <p class="wq-muted mb-3 max-w-3xl">{{ t('Your own severity and probability levels, and which combinations are acceptable. Set them to what your risk management procedure says; they are not standard values. Approved risk files keep the criteria they were approved with.') }}</p>
      <div v-if="!v.levels.length" class="mb-3">
        <p class="mb-2 text-sm text-ink-gray-7">{{ t('No criteria yet.') }}</p>
        <Button v-if="v.can_configure" :label="t('Load an example 5 × 5 to replace')" @click="example" />
      </div>
      <p v-if="v.levels.some((l) => l.description === v.example_note)" class="mb-3 text-sm text-ink-amber-7">{{ v.example_note }}.</p>
      <p v-if="v.gaps.length" class="mb-3 text-sm text-ink-amber-7">{{ t('Not decided by the matrix: {gaps}.', { gaps: v.gaps.join(', ') }) }}</p>

      <div v-if="sev.length && prob.length" class="mb-4 overflow-x-auto"><table class="matrix wq-table w-auto text-sm">
        <thead><tr><th>{{ t('Severity \\ Probability') }}</th><th v-for="p in prob" :key="p.id">P{{ p.rank }} {{ p.name }}</th></tr></thead>
        <tbody><tr v-for="s in sev" :key="s.id"><th class="text-left">S{{ s.rank }} {{ s.name }}</th>
          <td v-for="p in prob" :key="p.id">
            <select v-if="v.can_configure" class="wq-select" :value="cell(s.rank, p.rank)" @change="setCell(s.rank, p.rank, $event.target.value)">
              <option value="">{{ t('not decided') }}</option><option v-for="(label, k) in v.verdicts" :key="k" :value="k">{{ label }}</option></select>
            <Badge v-else-if="cell(s.rank, p.rank)" :theme="VT[cell(s.rank, p.rank)]" :label="v.verdicts[cell(s.rank, p.rank)]" />
          </td></tr></tbody></table></div>

      <table v-if="v.levels.length" class="levels wq-table mb-3 text-sm"><thead><tr><th>{{ t('Kind') }}</th><th>{{ t('Rank') }}</th><th>{{ t('Name') }}</th><th>{{ t('Description') }}</th><th>{{ t('In use') }}</th></tr></thead>
        <tbody><tr v-for="l in v.levels" :key="l.id">
          <td>{{ t(l.kind) }}</td><td>{{ l.rank }}</td>
          <td><input v-if="v.can_configure" class="wq-input" :value="l.name" @change="changeLevel(l, { name: $event.target.value })"><span v-else>{{ l.name }}</span></td>
          <td><input v-if="v.can_configure" class="wq-input" :value="l.description" @change="changeLevel(l, { description: $event.target.value })"><span v-else>{{ l.description }}</span></td>
          <td><input type="checkbox" :checked="l.active" :disabled="!v.can_configure" @change="changeLevel(l, { active: $event.target.checked })"></td></tr></tbody></table>
      <form v-if="v.can_configure" class="flex flex-wrap items-end gap-2" @submit.prevent="addLevel">
        <label class="wq-field">{{ t('Kind') }}<select v-model="lv.kind" class="wq-select"><option value="severity">{{ t('severity') }}</option><option value="probability">{{ t('probability') }}</option></select></label>
        <label class="wq-field w-20">{{ t('Rank') }}<input v-model="lv.rank" type="number" min="1" max="20" class="wq-input"></label>
        <label class="wq-field">{{ t('Name') }}<input v-model="lv.name" class="wq-input"></label>
        <label class="wq-field grow">{{ t('Description') }}<input v-model="lv.description" class="wq-input"></label>
        <Button type="submit" :label="t('Add level')" :disabled="!lv.rank || !lv.name.trim()" />
      </form>
      <details class="mt-4"><summary class="cursor-pointer text-sm text-ink-gray-7">{{ t('Changes to the criteria') }}</summary><Trail :items="v.criteria_history" /></details>
    </section>
  </template>
</template>
