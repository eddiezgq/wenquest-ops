<script setup>
// Importing a historical ledger (ADR-0014 item 10): AI proposes which column is which field; a person checks the
// mapping and the rows, then imports them with a signature. Code does the import; every record names its row.
import { computed, inject, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { CONF } from '../ui/themes'
import { api } from '../api'

const ws = inject('workspace')
const route = useRoute()
const L = ref(null)
const error = ref('')
const done = ref('')
const pick = ref({})
const vals = ref({})
const sheet = ref('')
const header = ref(1)
const password = ref('')
const busy = ref(false)
const pv = computed(() => L.value?.preview)
const ENGINE = { ai: 'AI', rules: 'rules (limited accuracy)', person: 'you' }
const KEYS = { ncr: ['external_no', 'reported_on', 'title', 'description', 'severity', 'disposition', 'status'],
  capa: ['external_no', 'reported_on', 'kind', 'title', 'ncr', 'owner', 'status'],
  supplier: ['supplier_name', 'supplies', 'approved_on', 'certificate', 'approval'] }
const PERM = { ncr: 'quality:edit', capa: 'quality:edit', supplier: 'purchasing:draft' }
// a quality register (ADR-0016, 16b) is kept by those who edit quality records; its columns are its first fields
const permOf = (t) => PERM[t] || (t?.startsWith('reg_') ? 'quality:edit' : null)
const keysOf = (t) => KEYS[t] || Object.keys(pv.value?.fields || {}).slice(0, 6)
const canImport = computed(() => L.value && ws.value?.user.permissions.includes(permOf(L.value.target)) && L.value.status === 'proposed')
const REF = (r) => (r?.startsWith('NCR-') ? '/quality?tab=ncrs' : r?.startsWith('CAPA-') ? '/quality?tab=capas' : r?.startsWith('draft') ? '/drafts'
  : r?.startsWith('entry ') && L.value?.target?.startsWith('reg_') ? `/system/registers/${L.value.target.slice(4)}#e${r.slice(6)}` : null)

function set(x) {
  L.value = x
  pick.value = Object.fromEntries(Object.keys(x.preview.fields).map((f) => {
    const m = x.mapping[f]
    return [f, m ? (m.column !== undefined ? `c:${m.column}` : `v:${m.value}`) : '']
  }))
  vals.value = JSON.parse(JSON.stringify(x.values_map || {}))
  sheet.value = x.preview.sheet
  header.value = x.preview.header_row
  password.value = ''
  saved.value = snapshot()
}
// the import uses the saved mapping: what is on screen must be saved before signing
const saved = ref('')
const snapshot = () => JSON.stringify([pick.value, vals.value])
const dirty = computed(() => L.value?.status === 'proposed' && snapshot() !== saved.value)
async function load() {
  error.value = ''
  try { set(await api(`/api/ledgers/${route.params.id}`)) } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })

function columnOf(f) { return pick.value[f]?.startsWith('c:') ? pick.value[f].slice(2) : null }
function setVal(f, w, v) { vals.value = { ...vals.value, [f]: { ...(vals.value[f] || {}), [w]: v } } }
async function save(extra = {}) {
  error.value = ''; done.value = ''
  const mapping = {}
  for (const [f, p] of Object.entries(pick.value)) {
    if (p.startsWith('c:')) mapping[f] = { column: p.slice(2) }
    else if (p.startsWith('v:')) mapping[f] = { value: p.slice(2) }
  }
  const values = {}
  for (const [f, vm] of Object.entries(vals.value)) if (columnOf(f)) values[f] = Object.fromEntries(Object.entries(vm).filter(([, v]) => v))
  try {
    set(await api(`/api/ledgers/${L.value.id}`, { method: 'PUT', body: { mapping, values, sheet: sheet.value, header_row: header.value, ...extra } }))
    done.value = 'Saved. Check the rows below.'
  } catch (e) { error.value = e.message }
}
async function retable(headerRow) {
  // other columns: the mapping starts again from the column names
  error.value = ''
  try { set(await api(`/api/ledgers/${L.value.id}`, { method: 'PUT', body: { mapping: {}, values: {}, sheet: sheet.value, header_row: headerRow } })) }
  catch (e) { error.value = e.message }
}
const changeSheet = () => retable(null)
async function doImport() {
  busy.value = true; error.value = ''; done.value = ''
  try {
    set(await api(`/api/ledgers/${L.value.id}/import`, { method: 'POST', body: { password: password.value } }))
    const r = L.value.result
    done.value = `Imported: ${r.imported} records, ${r.drafted} drafts, ${r.skipped} rows skipped.`
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
const show = (r, f) => r.values[f] ?? ''
</script>

<template>
  <PageTop :title="pv ? `Import ${pv.target_label.toLowerCase()}` : 'Import a ledger'"
           :crumbs="pv ? [{ label: 'Documents', to: '/documents?tab=library' }, { label: pv.document.name, to: `/documents/${pv.document.id}` }] : []">
    <Badge v-if="L" :theme="L.status === 'imported' ? 'green' : 'amber'" size="lg" :label="L.status === 'imported' ? 'imported' : 'to check'" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <template v-if="L && pv">
    <section class="wq-panel mb-5 p-5">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <h2 class="text-base font-semibold text-ink-gray-9">Which column is which</h2>
        <span class="text-sm text-ink-gray-5">proposed by {{ ENGINE[L.engine] || L.engine }}</span>
        <Badge v-if="L.confidence && L.engine !== 'person'" :theme="CONF[L.confidence]" variant="outline" :label="`${L.confidence} confidence`" />
      </div>
      <p v-if="L.notes" class="mb-3 whitespace-pre-line text-base text-ink-gray-7">{{ L.notes }}</p>
      <div class="mb-4 flex flex-wrap items-center gap-3 text-sm text-ink-gray-6">
        <label class="flex items-center gap-2">Sheet
          <select v-model="sheet" class="wq-select" :disabled="L.status !== 'proposed'" @change="changeSheet"><option v-for="s in pv.sheets" :key="s">{{ s }}</option></select></label>
        <label class="flex items-center gap-2">Header row
          <input v-model.number="header" class="wq-input w-20" type="number" min="1" :disabled="L.status !== 'proposed'" @change="retable(header)"></label>
        <span>{{ pv.total }} rows under it</span>
      </div>
      <div class="overflow-x-auto">
        <table class="wq-table">
          <thead><tr><th>Field</th><th>Column in the ledger</th><th>The ledger's words</th></tr></thead>
          <tbody><tr v-for="(spec, f) in pv.fields" :key="f">
            <td class="whitespace-nowrap">{{ spec.label }}<span v-if="spec.required" class="text-ink-red-6"> *</span></td>
            <td><select v-model="pick[f]" class="wq-select" :disabled="L.status !== 'proposed'" :aria-label="spec.label">
              <option value="">— not in the ledger</option>
              <option v-for="h in pv.headers" :key="h" :value="`c:${h}`">{{ h }}</option>
              <template v-if="spec.kind === 'choice'"><option v-for="ch in spec.choices" :key="ch" :value="`v:${ch}`">every row: {{ ch.replaceAll('_', ' ') }}</option></template>
            </select></td>
            <td><div v-if="spec.kind === 'choice' && columnOf(f) && pv.choice_values[f]" class="flex flex-wrap gap-x-4 gap-y-1.5">
              <label v-for="w in pv.choice_values[f]" :key="w" class="flex items-center gap-1.5 text-sm">
                <span class="text-ink-gray-8">“{{ w }}”</span> →
                <select :value="(vals[f] || {})[w] || ''" class="wq-select" :disabled="L.status !== 'proposed'"
                        @change="setVal(f, w, $event.target.value)">
                  <option value="">unknown</option><option v-for="ch in spec.choices" :key="ch" :value="ch">{{ ch.replaceAll('_', ' ') }}</option></select></label>
            </div>
              <span v-else-if="spec.kind === 'choice' && columnOf(f)" class="text-sm text-ink-gray-5">save to match the column's words</span></td>
          </tr></tbody>
        </table>
      </div>
      <div v-if="L.status === 'proposed'" class="mt-4"><Button :variant="dirty ? 'solid' : 'subtle'" icon-left="lucide-save" label="Save the mapping" @click="save()" />
        <span class="wq-muted ms-2">Words left “unknown” stay empty on the record; nothing is guessed.</span></div>
    </section>

    <section class="mb-5">
      <h2 class="wq-h2">Rows</h2>
      <p class="wq-muted mb-2">{{ pv.ready }} ready to import · {{ pv.with_problems }} with notes · {{ pv.already }} already imported<span v-if="pv.total > pv.rows.length"> · first {{ pv.rows.length }} shown</span></p>
      <div class="wq-panel overflow-x-auto">
        <table class="wq-table text-sm">
          <thead><tr><th>Row</th><th v-for="k in keysOf(L.target)" :key="k">{{ pv.fields[k]?.label }}</th><th>Notes</th></tr></thead>
          <tbody><tr v-for="r in pv.rows" :key="r.row" :class="{ 'opacity-60': r.done || !r.ok }">
            <td>{{ r.row }}</td>
            <td v-for="k in keysOf(L.target)" :key="k" class="max-w-64">{{ show(r, k) }}</td>
            <td class="max-w-80"><span v-if="r.done" class="text-ink-gray-6">imported as {{ r.done }}</span>
              <span v-for="(p, i) in r.problems" :key="i" class="block" :class="r.ok ? 'text-ink-amber-7' : 'text-ink-red-7'">{{ p }}</span></td>
          </tr></tbody>
        </table>
      </div>
    </section>

    <section v-if="canImport" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">Import</h2>
      <p class="wq-muted mb-3">{{ L.target === 'supplier' ? 'Each new supplier becomes a draft in Drafts; it is created in ERPNext when someone confirms it. Suppliers already in ERPNext are skipped.'
        : 'Each ready row becomes a record that names this file and row. Rows closed in the ledger are kept as closed before WenQuest Ops; open ones continue here.' }}
        Sign with your password.</p>
      <div class="flex flex-wrap items-center gap-2">
        <input v-model="password" class="wq-input max-w-56" type="password" placeholder="Your password to sign" autocomplete="current-password">
        <Button variant="solid" icon-left="lucide-pen-line" :loading="busy" :label="`Import ${pv.ready} rows (sign)`" :disabled="!pv.ready || dirty" @click="doImport" />
      </div>
      <p v-if="dirty" class="mt-2 text-sm text-ink-amber-7">You changed the mapping: save it first, so the rows above show what will be imported.</p>
    </section>

    <template v-if="L.outcomes">
      <h2 class="wq-h2">What happened to each row</h2>
      <div class="wq-panel mb-5 overflow-x-auto">
        <table class="wq-table text-sm"><thead><tr><th>Row</th><th>Outcome</th><th>Record</th><th>Note</th></tr></thead>
          <tbody><tr v-for="o in L.outcomes" :key="o.row_no"><td>{{ o.row_no }}</td>
            <td><Badge :theme="o.outcome === 'skipped' ? 'gray' : 'green'" :label="o.outcome" /></td>
            <td><RouterLink v-if="REF(o.ref)" :to="REF(o.ref)" class="wq-link">{{ o.ref }}</RouterLink></td>
            <td class="text-ink-gray-6">{{ o.note }}</td></tr></tbody></table>
      </div>
      <h2 class="wq-h2">Signature</h2>
      <Trail :items="L.signatures" kind="signatures" />
    </template>
  </template>
</template>
