<script setup>
// One quality workflow, read-only (ADR-0015, 15a): its states in order and every step with who may do it, what it
// needs, whether it is signed and who may not do it.
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import { api } from '../api'
import { ago } from '../format'
import { t } from '../i18n'
import WorkflowProposals from './WorkflowProposals.vue'

const props = defineProps({ data: Object, kind: String })
const router = useRouter()
const error = ref('')
const draft = computed(() => props.data.versions.find((x) => x.status === 'draft'))
async function newDraft() {
  error.value = ''
  try { const d = await api(`/api/quality/workflows/${props.kind}/drafts`, { method: 'POST' }); router.push(`/quality/workflows/${d.id}`) }
  catch (e) { error.value = e.message }
}
const wf = computed(() => props.data.workflow)
// states in the order a record meets them (breadth first from the first state)
const order = computed(() => {
  const out = [wf.value.initial]
  for (let i = 0; i < out.length; i++) {
    for (const s of Object.values(wf.value.steps)) {
      if (!s.from.includes(out[i])) continue
      for (const to of [s.to, s.to_when_approval_needed]) if (to && !out.includes(to)) out.push(to)
    }
  }
  const all = [...out, ...Object.keys(wf.value.states).filter((s) => !out.includes(s))]
  return [...all.filter((s) => !wf.value.states[s].final), ...all.filter((s) => wf.value.states[s].final)]
})
const stateLabel = (s) => wf.value.states[s]?.label || s
const orList = (xs) => xs.join(` ${t('or')} `)
const andList = (xs) => xs.join(` ${t('and')} `)
</script>

<template>
  <section data-help="workflow-card" class="wq-panel mb-6 p-5">
    <div class="mb-1 flex flex-wrap items-center gap-2">
      <h2 class="text-base font-semibold text-ink-gray-9">{{ wf.label }}</h2>
      <Badge theme="green" :label="t('version {n} in use', { n: data.enabled.version })" />
      <span class="text-sm text-ink-gray-5">{{ t('{note} · enabled by {name} {when} · numbers {numbers}', { note: data.enabled.note, name: data.enabled.enabled_by, when: ago(data.enabled.enabled_at), numbers: `${wf.numbering.prefix}-${'0'.repeat(wf.numbering.digits - 1)}1` }) }}</span>
    </div>
    <p class="wq-muted mb-2">{{ t('Fingerprint {fp}… Records keep the version they started under.', { fp: data.enabled.fingerprint.slice(0, 12) }) }}</p>
    <div class="mb-4 flex flex-wrap items-center gap-2 text-sm">
      <template v-if="data.can_configure">
        <Button v-if="draft" data-help="workflow-open-draft" icon-left="lucide-file-pen-line" :label="t('Open the draft (version {n})', { n: draft.version })" :route="`/quality/workflows/${draft.id}`" />
        <Button v-else data-help="workflow-change" icon-left="lucide-plus" :label="t('Change this workflow')" @click="newDraft" />
      </template>
      <RouterLink v-else-if="draft" :to="`/quality/workflows/${draft.id}`" class="wq-link">{{ t('Draft version {n}', { n: draft.version }) }}</RouterLink>
      <span class="text-ink-gray-5">{{ t('Versions:') }}</span>
      <RouterLink v-for="x in data.versions" :key="x.id" :to="`/quality/workflows/${x.id}`" class="wq-link">v{{ x.version }} {{ t(x.status) }}</RouterLink>
      <span v-if="error" class="wq-error">{{ error }}</span>
    </div>

    <ol class="states mb-5 flex flex-wrap items-center gap-2">
      <template v-for="(s, i) in order" :key="s">
        <li class="rounded-3 border px-3 py-1.5 text-sm"
            :class="wf.states[s].final ? 'border-outline-gray-2 bg-surface-gray-2 text-ink-gray-7' : 'border-outline-gray-3 bg-surface-base text-ink-gray-9'">
          {{ stateLabel(s) }}<span v-if="data.counts[s]" class="ms-1.5 text-ink-gray-5">{{ data.counts[s] }}</span></li>
        <span v-if="i < order.length - 1" class="size-4 text-ink-gray-4" :class="wf.states[order[i + 1]].final && !wf.states[s].final ? 'lucide-dot' : 'lucide-chevron-right'" />
      </template>
    </ol>

    <div class="overflow-x-auto">
      <table class="wq-table text-sm">
        <thead><tr><th>{{ t('Step') }}</th><th>{{ t('From') }}</th><th>{{ t('To') }}</th><th>{{ t('Needs') }}</th><th>{{ t('Signed') }}</th><th>{{ t('Not by') }}</th><th>{{ t('Who') }}</th></tr></thead>
        <tbody><tr v-for="s in wf.steps" :key="s.name">
          <td class="whitespace-nowrap font-medium text-ink-gray-9">{{ s.label }}</td>
          <td>{{ s.from.map(stateLabel).join(', ') }}</td>
          <td class="whitespace-nowrap">{{ s.to ? stateLabel(s.to) : t('(stays)') }}<span v-if="s.to_when_approval_needed" class="block text-ink-gray-5">{{ t('or {state} when the disposition needs approval', { state: stateLabel(s.to_when_approval_needed) }) }}</span></td>
          <td>{{ s.needs.join(', ') || (s.reason ? t('a reason') : '—') }}</td>
          <td><span v-if="s.sign" class="inline-flex items-center gap-1"><span class="lucide-pen-line size-3.5" />{{ s.sign }}</span><span v-else class="text-ink-gray-4">—</span></td>
          <td>{{ s.not_by_text.join(', ') || '—' }}</td>
          <td class="min-w-36 text-ink-gray-6" :title="s.permission_text">{{ s.who.map((r) => t(r.replace('_', ' '))).join(', ') }}</td>
        </tr></tbody>
      </table>
    </div>
    <div v-if="Object.keys(wf.fields).length || wf.approvals.length" class="mt-4 grid gap-4 text-sm md:grid-cols-2">
      <div v-if="Object.keys(wf.fields).length"><p class="mb-1 font-medium text-ink-gray-8">{{ t('Own fields') }}</p>
        <ul class="list-disc ps-5 text-ink-gray-7"><li v-for="(f, n) in wf.fields" :key="n">{{ f.required_at?.length ? t('{label} ({type}), needed before {steps}', { label: f.label, type: f.type, steps: f.required_at.map((s) => wf.steps[s].label.toLowerCase()).join(', ') }) : `${f.label} (${f.type})` }}</li></ul></div>
      <div v-if="wf.approvals.length"><p class="mb-1 font-medium text-ink-gray-8">{{ t('Extra signed approvals') }}</p>
        <ul class="list-disc ps-5 text-ink-gray-7"><li v-for="a in wf.approvals" :key="a.name">{{ t('{label} before {step}, by {roles}', { label: a.label, step: wf.steps[a.before].label.toLowerCase(), roles: orList(a.roles.map((r) => t(r.replace('_', ' ')))) }) }}<span v-for="(vals, k) in a.when || {}" :key="k">{{ t(', when {field} is {values}', { field: k, values: orList(vals) }) }}</span></li></ul></div>
    </div>
    <ul v-if="wf.rules" class="mt-4 list-disc ps-5 text-sm text-ink-gray-7">
      <li v-if="wf.rules.capa_closed_before_close?.length">{{ t('{kinds} reports close only after a linked corrective action is closed', { kinds: andList(wf.rules.capa_closed_before_close) }) }}</li>
      <li v-if="wf.rules.eight_d_before_close?.length">{{ t('{kinds} reports close only after their 8D is complete', { kinds: andList(wf.rules.eight_d_before_close) }) }}</li>
      <li v-if="wf.rules.one_open_capa_per_ncr">{{ t('one open corrective action per nonconformance report') }}</li>
    </ul>
    <WorkflowProposals v-if="data.can_configure" :kind="kind" />
  </section>
</template>
