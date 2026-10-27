<script setup>
// One process FMEA (ADR-0022, 22c). People write rows and give the ranks on the company's scales; RPN and whether a
// row needs action are computed. The AI may draft rows citing records, without ranks; a person confirms or removes
// each. Approval is signed by someone who does not own and did not edit it; the PFMEA is then fixed.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'
import { t } from '../i18n'

const route = useRoute()
const router = useRouter()
const r = ref(null)
const error = ref('')
const done = ref('')
const busy = ref(false)
const ai = ref(null)
const ctx = ref(null)
const f = ref({})
const x = ref({ password: '', reason: '' })
const FIELDS = ['process', 'item_code', 'scope', 'owner']
const TEXT = ['step', 'requirement', 'failure_mode', 'effect', 'cause', 'prevention', 'detection_controls', 'action', 'action_owner', 'action_due']
const RANKS = ['severity', 'occurrence', 'detection', 'res_severity', 'res_occurrence', 'res_detection']
const blank = () => Object.fromEntries([...TEXT, ...RANKS, 'refs'].map((k) => [k, '']))
const row = ref(blank())
const editing = ref(null)
const ST = { draft: 'gray', approved: 'green', superseded: 'gray', withdrawn: 'gray' }
const draft = computed(() => r.value?.status === 'draft' && r.value?.can_edit)
const unconfirmed = computed(() => (r.value?.rows || []).filter((x) => !x.confirmed).length)
const editingRow = computed(() => r.value?.rows.find((x) => x.id === editing.value))
const scale = (kind) => (r.value?.scales || []).filter((s) => s.kind === kind.replace('res_', '')).sort((a, b) => a.rank - b.rank)
const rankName = (kind, n) => (r.value?.scales || []).find((s) => s.kind === kind && s.rank === n)?.name || ''
const capasOf = (seq) => (r.value?.capas || []).filter((c) => c.row_seq === seq)

function set(v) { r.value = v; f.value = Object.fromEntries(FIELDS.map((k) => [k, v[k] ?? ''])) }
async function load() { error.value = ''; try { set(await api(`/api/fmea/files/${route.params.id}`)) } catch (e) { error.value = e.message } }
watch(() => route.params.id, () => { ai.value = null; ctx.value = null; editing.value = null; row.value = blank(); load() }, { immediate: true })
const changed = () => Object.fromEntries(FIELDS.filter((k) => (f.value[k] ?? '') !== (r.value[k] ?? '')).map((k) => [k, f.value[k]]))
async function call(path, method, body, message) {
  error.value = ''; done.value = ''; busy.value = true
  try { const v = await api(path, { method, body }); if (v.rows) set(v); done.value = message; return v } catch (e) { error.value = e.message } finally { busy.value = false }
}
function payload() {
  const out = {}
  for (const k of TEXT) out[k] = row.value[k] === '' && (k === 'action_owner' || k === 'action_due') ? null : row.value[k]
  for (const k of RANKS) out[k] = row.value[k] === '' ? null : Number(row.value[k])
  out.refs = String(row.value.refs || '').split(/[,\s]+/).map((s) => s.trim()).filter(Boolean)
  return out
}
async function saveRow() {
  const confirm = editingRow.value && !editingRow.value.confirmed
  const ok = editing.value
    ? await call(`/api/fmea/files/${r.value.id}/rows/${editing.value}`, 'PUT', { ...payload(), confirm }, confirm ? t('Confirmed and saved.') : t('Saved.'))
    : await call(`/api/fmea/files/${r.value.id}/rows`, 'POST', payload(), t('Row added.'))
  if (ok) { row.value = blank(); editing.value = null }
}
function edit(it) {
  editing.value = it.id
  row.value = Object.fromEntries(Object.keys(blank()).map((k) => [k, k === 'refs' ? (it.refs || []).join(', ') : it[k] ?? '']))
  setTimeout(() => document.querySelector('[data-help="fmea-row-form"]')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
}
const remove = (it) => call(`/api/fmea/files/${r.value.id}/rows/${it.id}`, 'DELETE', null, t('Row removed.'))
async function suggest() { const v = await call(`/api/fmea/files/${r.value.id}/suggest`, 'POST', undefined, ''); if (v) ai.value = v.suggested }
async function showContext(ev) {
  if (ev.target.open && !ctx.value) { try { ctx.value = await api(`/api/fmea/files/${r.value.id}/context`) } catch (e) { error.value = e.message } }
}
async function capa(it) {
  const c = await call(`/api/fmea/files/${r.value.id}/rows/${it.seq}/capa`, 'POST', { kind: 'preventive' }, '')
  if (c) router.push(`/quality/capa/${c.id}`)
}
async function revise() {
  const v = await call(`/api/fmea/files/${r.value.id}/revise`, 'POST', {}, t('A new version is started.'))
  if (v) router.push(`/quality/fmea/${v.id}`)
}
const afterText = (k) => t('{rank} after action', { rank: t(k.replace('res_', '')).replace(/^./, (c) => c.toUpperCase()) })
const ruleText = computed(() => {
  const c = r.value?.status === 'draft' ? r.value?.rule : r.value?.criteria?.rule
  if (!c) return t('no rule yet')
  return c.method === 'rpn' ? (c.severity_action ? t('action when RPN ≥ {rpn} or S ≥ {s}', { rpn: c.rpn_action, s: c.severity_action }) : t('action when RPN ≥ {rpn}', { rpn: c.rpn_action })) : t('lookup table; action for {list}', { list: c.needs_action.map((v) => t(v)).join(', ') })
})
</script>

<template>
  <PageTop :crumbs="[{ label: t('Process FMEA'), to: '/quality/fmea' }]">
    <template #title>{{ r ? `${r.name} v${r.version} · ${r.process}` : t('PFMEA') }}</template>
    <Badge v-if="r" :theme="ST[r.status]" size="lg" :label="t(r.status)" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="r">
    <p v-if="r.intact === false" class="wq-error mb-4">{{ t('This PFMEA no longer matches what was approved.') }}</p>
    <section v-if="r.ncrs_since.length" data-help="fmea-since" class="mb-5 rounded-3 border border-outline-amber-2 bg-surface-amber-1 p-4 text-base">
      <p class="font-medium text-ink-amber-8">{{ r.ncrs_since.length > 1 ? t('{n} nonconformance reports on {item} since this PFMEA was approved. Does the occurrence of a failure mode need re-rating? If so, start a new version.', { n: r.ncrs_since.length, item: r.item_code }) : t('{n} nonconformance report on {item} since this PFMEA was approved. Does the occurrence of a failure mode need re-rating? If so, start a new version.', { n: r.ncrs_since.length, item: r.item_code }) }}</p>
      <p class="mt-1 flex flex-wrap gap-2 text-sm"><RouterLink v-for="n in r.ncrs_since" :key="n.id" :to="`/quality/ncr/${n.id}`" class="wq-link">{{ n.name }} {{ n.title }}</RouterLink></p>
    </section>

    <section class="wq-panel mb-5 grid gap-3 p-5 md:grid-cols-4">
      <label class="wq-field md:col-span-2">{{ t('Process (and the product it makes)') }}<input v-model="f.process" class="wq-input" :disabled="!draft"></label>
      <label class="wq-field">{{ t('Item code') }}<input v-model="f.item_code" class="wq-input" :disabled="!draft"></label>
      <label class="wq-field">{{ t('Owner') }}<select v-model="f.owner" class="wq-select" :disabled="!draft"><option value="" /><option v-for="p in r.people" :key="p">{{ p }}</option></select></label>
      <label class="wq-field md:col-span-4">{{ t('Scope') }}<input v-model="f.scope" class="wq-input" :disabled="!draft"></label>
      <div v-if="draft" class="md:col-span-4"><Button :label="t('Save')" :disabled="!Object.keys(changed()).length" @click="call(`/api/fmea/files/${r.id}`, 'PUT', changed(), t('Saved.'))" /></div>
    </section>

    <section data-help="fmea-rows" class="wq-panel mb-5 p-5">
      <div class="mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-1"><h2 class="wq-h2 mb-0">{{ t('Failure modes') }}</h2><span class="text-sm text-ink-gray-5">{{ t('RPN = S × O × D, computed; {rule}', { rule: ruleText }) }}</span></div>
      <p v-if="!r.rows.length" class="wq-muted">{{ t('None yet.') }}</p>
      <div v-else class="overflow-x-auto"><table class="rows wq-table text-sm">
        <thead><tr><th>#</th><th>{{ t('Step') }}</th><th>{{ t('Failure mode') }}</th><th>{{ t('Effect') }}</th><th class="n">S</th><th>{{ t('Cause') }}</th><th class="n">O</th><th>{{ t('Prevention · detection in place') }}</th><th class="n">D</th><th class="n">RPN</th><th>{{ t('Action') }}</th><th>{{ t('After') }}</th><th /></tr></thead>
        <tbody><tr v-for="it in r.rows" :key="it.id" :class="{ ai: !it.confirmed, needs: it.action_needed }">
          <td>{{ it.seq }}</td>
          <td class="min-w-28">{{ it.step }}<div v-if="it.requirement" class="text-ink-gray-5">{{ it.requirement }}</div></td>
          <td class="min-w-32 font-medium text-ink-gray-9">{{ it.failure_mode }}
            <div class="mt-0.5 flex flex-wrap gap-1"><span v-if="it.origin === 'ai'" class="tag" :title="it.confirmed ? t('Drafted by AI, confirmed by a person') : t('Drafted by AI; not yet confirmed')">AI</span>
              <template v-for="ref_ in it.refs" :key="ref_"><RouterLink v-if="r.links[ref_]" :to="r.links[ref_]" class="ref">{{ ref_ }}</RouterLink><span v-else class="ref">{{ ref_ }}</span></template></div></td>
          <td class="min-w-28">{{ it.effect }}</td>
          <td class="n" :title="rankName('severity', it.severity)">{{ it.severity ?? '–' }}</td>
          <td class="min-w-28">{{ it.cause }}</td>
          <td class="n" :title="rankName('occurrence', it.occurrence)">{{ it.occurrence ?? '–' }}</td>
          <td class="min-w-32">{{ it.prevention }}<span v-if="it.prevention && it.detection_controls"> · </span>{{ it.detection_controls }}</td>
          <td class="n" :title="rankName('detection', it.detection)">{{ it.detection ?? '–' }}</td>
          <td class="n font-semibold">{{ it.rpn ?? '–' }}<div v-if="it.priority" class="text-xs font-normal" :class="it.action_needed ? 'text-ink-red-7' : 'text-ink-gray-5'">{{ t(it.priority) }}</div>
            <div v-else-if="it.rpn != null && r.status === 'draft'" class="text-xs font-normal text-ink-amber-7">{{ t('not decided') }}</div></td>
          <td class="min-w-40">{{ it.action }}<div v-if="it.action_owner" class="text-ink-gray-5">{{ it.action_owner }}{{ it.action_due ? ' · ' + t('by {date}', { date: it.action_due }) : '' }}</div>
            <div v-for="c in capasOf(it.seq)" :key="c.id"><RouterLink :to="`/quality/capa/${c.id}`" class="wq-link">{{ c.name }}</RouterLink> <span class="text-ink-gray-5">{{ t(c.status) }}</span></div></td>
          <td class="whitespace-nowrap"><template v-if="it.res_severity">{{ it.res_severity }}·{{ it.res_occurrence }}·{{ it.res_detection }} = <b>{{ it.res_rpn }}</b></template></td>
          <td class="whitespace-nowrap">
            <template v-if="draft"><Button size="sm" :variant="it.confirmed ? 'subtle' : 'solid'" :label="it.confirmed ? t('Edit') : t('Check and confirm')" @click="edit(it)" />
              <Button size="sm" variant="ghost" :label="t('Remove')" @click="remove(it)" /></template>
            <Button v-else-if="r.can_edit && r.status === 'approved' && it.action_needed" size="sm" :label="t('Open CAPA')" @click="capa(it)" />
          </td>
        </tr></tbody></table></div>
      <ul v-if="r.status === 'draft' && r.rows.some((x) => x.needs?.length)" class="mt-3 list-disc ps-5 text-sm text-ink-amber-7">
        <template v-for="it in r.rows" :key="it.id"><li v-for="n in it.needs" :key="n">{{ n }}</li></template></ul>

      <form v-if="draft" data-help="fmea-row-form" class="mt-5 grid gap-3 border-t border-outline-gray-1 pt-4 md:grid-cols-3" @submit.prevent="saveRow">
        <h3 class="font-semibold text-ink-gray-9 md:col-span-3">{{ editing ? (editingRow && !editingRow.confirmed ? t('Check row {n} (drafted by the AI) and give its ranks', { n: editingRow.seq }) : t('Row {n}', { n: editingRow?.seq })) : t('Add a row') }}</h3>
        <label class="wq-field">{{ t('Process step') }}<input v-model="row.step" class="wq-input"></label>
        <label class="wq-field">{{ t('What the step must achieve') }}<input v-model="row.requirement" class="wq-input"></label>
        <label class="wq-field">{{ t('Failure mode') }}<input v-model="row.failure_mode" class="wq-input"></label>
        <label class="wq-field">{{ t('Effect') }}<input v-model="row.effect" class="wq-input"></label>
        <label class="wq-field">{{ t('Cause') }}<input v-model="row.cause" class="wq-input"></label>
        <label class="wq-field">{{ t('Records it rests on (numbers)') }}<input v-model="row.refs" class="wq-input" placeholder="NCR-00001, CMP-00002"></label>
        <label class="wq-field">{{ t('Prevention in place') }}<input v-model="row.prevention" class="wq-input"></label>
        <label class="wq-field">{{ t('Detection in place') }}<input v-model="row.detection_controls" class="wq-input"></label>
        <span class="hidden md:block" />
        <label v-for="k in ['severity', 'occurrence', 'detection']" :key="k" class="wq-field capitalize">{{ t(k) }}
          <select v-model="row[k]" class="wq-select"><option value="" /><option v-for="s in scale(k)" :key="s.id" :value="s.rank" :disabled="!s.active">{{ s.rank }} {{ s.name }}</option></select></label>
        <label class="wq-field">{{ t('Recommended action') }}<input v-model="row.action" class="wq-input"></label>
        <label class="wq-field">{{ t('Action owner') }}<select v-model="row.action_owner" class="wq-select"><option value="" /><option v-for="p in r.people" :key="p">{{ p }}</option></select></label>
        <label class="wq-field">{{ t('Due') }}<input v-model="row.action_due" type="date" class="wq-input"></label>
        <label v-for="k in ['res_severity', 'res_occurrence', 'res_detection']" :key="k" class="wq-field">{{ afterText(k) }}
          <select v-model="row[k]" class="wq-select"><option value="" /><option v-for="s in scale(k)" :key="s.id" :value="s.rank" :disabled="!s.active">{{ s.rank }} {{ s.name }}</option></select></label>
        <div class="flex gap-2 md:col-span-3"><Button type="submit" variant="solid" :disabled="busy" :label="editing ? (editingRow && !editingRow.confirmed ? t('Confirm and save') : t('Save the row')) : t('Add the row')" />
          <Button v-if="editing" :label="t('Stop editing')" @click="editing = null; row = blank()" /></div>
      </form>
    </section>

    <div class="mb-5 grid gap-5 lg:grid-cols-2">
      <section v-if="draft" data-help="fmea-suggest" class="wq-panel p-5">
        <h3 class="mb-2 text-base font-semibold text-ink-gray-9">{{ t('Rows drafted by the AI') }}</h3>
        <p class="mb-3 text-sm text-ink-gray-6">{{ t('The AI reads the records about {item} and proposes failure modes, effects and causes, citing them. It gives no ranks; you check each row and rank it on your scales.', { item: r.item_code || t('the item') }) }}</p>
        <Button v-if="r.can_ask" icon-left="lucide-sparkles" :label="t('Draft rows')" :loading="busy" :disabled="busy || unconfirmed > 0 || !r.item_code" @click="suggest" />
        <p v-if="unconfirmed" class="mt-2 text-sm text-ink-amber-7">{{ unconfirmed > 1 ? t('{n} rows drafted by the AI to check.', { n: unconfirmed }) : t('{n} row drafted by the AI to check.', { n: unconfirmed }) }}</p>
        <p v-else-if="!r.can_ask" class="wq-muted">{{ t('Drafting needs a model key and a role that may use the AI.') }}</p>
        <div v-if="ai" class="mt-3 text-sm">
          <p>{{ ai.kept === 1 ? t('{kept} row kept from {shown} records shown', { kept: ai.kept, shown: ai.shown }) : t('{kept} rows kept from {shown} records shown', { kept: ai.kept, shown: ai.shown }) }}<span v-if="ai.dropped.length || ai.unusable">{{ t('; {n} dropped', { n: ai.dropped.length + ai.unusable }) }}</span>.</p>
          <ul v-if="ai.dropped.length" class="mt-1 list-disc ps-5 text-ink-gray-6"><li v-for="(d, k) in ai.dropped" :key="k">“{{ d.failure_mode }}”: {{ d.reason }}<span v-if="d.refs.length"> ({{ d.refs.join(', ') }})</span></li></ul>
          <p v-if="ai.note" class="mt-1 text-ink-gray-6">{{ t('AI note: {note}', { note: ai.note }) }}</p>
        </div>
        <details class="mt-3 text-sm" @toggle="showContext"><summary class="cursor-pointer text-ink-gray-7">{{ t('Records the AI reads') }}</summary>
          <p v-if="!ctx" class="wq-muted mt-2">{{ t('Loading…') }}</p>
          <p v-else-if="!ctx.records.length" class="wq-muted mt-2">{{ t('None: give the item code.') }}</p>
          <ul v-else class="mt-2 flex flex-col gap-1.5"><li v-for="x_ in ctx.records" :key="x_.ref"><RouterLink v-if="ctx.links[x_.ref]" :to="ctx.links[x_.ref]" class="ref">{{ x_.ref }}</RouterLink><span v-else class="ref">{{ x_.ref }}</span>
            <span class="text-ink-gray-5"> {{ x_.kind }}:</span> {{ x_.summary }}</li></ul></details>
      </section>

      <section v-if="r.status === 'draft' || (r.status === 'approved' && r.can_edit)" data-help="fmea-approve" class="wq-panel p-5">
        <template v-if="r.status === 'draft'">
          <h3 class="mb-2 text-base font-semibold text-ink-gray-9">{{ t('Approve') }}</h3>
          <ul v-if="r.to_approve.length" class="mb-3 list-disc ps-5 text-sm text-ink-gray-6"><li v-for="a in r.to_approve.slice(0, 8)" :key="a">{{ a }}</li><li v-if="r.to_approve.length > 8">{{ t('and {n} more', { n: r.to_approve.length - 8 }) }}</li></ul>
          <div v-if="r.can_configure" class="flex flex-wrap items-end gap-2">
            <input v-model="x.password" type="password" class="wq-input w-44" :placeholder="t('Your password')" autocomplete="current-password">
            <Button variant="solid" :label="t('Approve (sign)')" :disabled="!x.password || !!r.to_approve.length || !!Object.keys(changed()).length" @click="call(`/api/fmea/files/${r.id}/approve`, 'POST', { password: x.password }, t('Approved: the PFMEA is fixed now.')).then(() => { x.password = '' })" />
          </div>
          <p class="mt-2 text-sm text-ink-gray-5">{{ t('Approved by someone who does not own and did not edit it. RPNs and results are computed again under the current criteria and kept with them.') }}</p>
          <details v-if="r.can_edit" class="mt-3"><summary class="cursor-pointer text-sm text-ink-gray-7">{{ t('Withdraw the draft') }}</summary>
            <div class="mt-2 flex gap-2"><input v-model="x.reason" class="wq-input w-80" :placeholder="t('Why')"><Button :label="t('Withdraw')" :disabled="!x.reason.trim()" @click="call(`/api/fmea/files/${r.id}/withdraw`, 'POST', { reason: x.reason }, t('Withdrawn.'))" /></div></details>
        </template>
        <template v-else><h3 class="mb-2 text-base font-semibold text-ink-gray-9">{{ t('Change it') }}</h3><p class="mb-3 text-sm text-ink-gray-6">{{ t('An approved PFMEA is fixed. A new version starts as a copy; approving it supersedes this one.') }}</p><Button :label="t('Start a new version')" @click="revise" /></template>
      </section>
    </div>

    <section v-if="r.flow_steps?.length" class="mb-5 text-sm"><b class="text-ink-gray-8">{{ t('Process flow steps citing this PFMEA:') }}</b>
      <RouterLink v-for="s in r.flow_steps" :key="s.chart_id + s.step" :to="`/quality/flow/${s.chart_id}`" class="wq-link ms-2">{{ s.name }} v{{ s.version }} {{ s.code }} {{ s.step }}</RouterLink></section>
    <p v-if="r.fingerprint" class="mb-4 text-xs text-ink-gray-5">{{ t('Fingerprint {fp}', { fp: r.fingerprint }) }}</p>
    <h2 class="wq-h2 mt-6">{{ t('Versions') }}</h2>
    <ul class="mb-4 text-sm"><li v-for="ver in r.versions" :key="ver.id"><RouterLink :to="`/quality/fmea/${ver.id}`" class="hover:underline">v{{ ver.version }}</RouterLink> · {{ t(ver.status) }}<span v-if="ver.approved_by"> · {{ ver.approved_by }} {{ ver.approved_at?.slice(0, 10) }}</span></li></ul>
    <h2 class="wq-h2 mt-6">{{ t('Signatures') }}</h2>
    <Trail :items="r.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
    <Trail :items="r.history" />
  </template>
</template>

<style scoped>
.rows td, .rows th { vertical-align: top; }
.rows .n { text-align: center; font-variant-numeric: tabular-nums; width: 2.5rem; }
.rows tr.ai td { background: var(--surface-amber-1, transparent); }
.rows tr.ai td:first-child { box-shadow: inset 3px 0 0 var(--warn); }
.rows tr.needs td:nth-child(10) { color: var(--critical); }
.tag { font-size: .7rem; border-radius: 4px; padding: 0 .3rem; background: var(--surface-amber-2, var(--surface-gray-2)); color: var(--warn); font-weight: 600; }
.ref { font-size: .72rem; border: 1px solid var(--line); border-radius: 4px; padding: 0 .3rem; color: var(--accent); white-space: nowrap; font-weight: 400; }
</style>
