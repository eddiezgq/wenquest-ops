<script setup>
// The quality system against ISO 9001 (ADR-0016, 16a): each control point met, not met or unknown, from the records,
// with the records it rests on. Adopting the standard and saying what does not apply are signed.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { ago } from '../format'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const v = ref(null)
const error = ref('')
const done = ref('')
const busy = ref(false)
const edition = ref('2015')
const password = ref('')
const docs = ref([])
const open = ref(null)            // the control point whose actions are shown
const form = ref({ reason: '', password: '', doc: '' })
const filter = ref('all')
const S = { met: { theme: 'green', label: 'met' }, not_met: { theme: 'red', label: 'not met' },
  unknown: { theme: 'gray', label: 'unknown' }, not_applicable: { theme: 'blue', label: 'does not apply' } }
const ORDER = ['not_met', 'unknown', 'met', 'not_applicable']
const can = computed(() => v.value?.can_configure)
const canDocs = computed(() => ws.value?.user.permissions.includes('documents:view'))
const latest = computed(() => !route.query.evaluation)
const counts = computed(() => v.value?.evaluation?.counts || {})

async function load() {
  error.value = ''
  try {
    v.value = await api(`/api/qms/iso9001${route.query.evaluation ? `?evaluation=${route.query.evaluation}` : ''}`)
    if (can.value && canDocs.value && !docs.value.length) docs.value = (await api('/api/docs?status=library')).filter((d) => d.status !== 'obsolete')
  } catch (e) { error.value = e.message }
}
watch(() => route.query.evaluation, load, { immediate: true })

async function post(path, body, message) {
  error.value = ''; done.value = ''; busy.value = true
  try { v.value = await api(`/api/qms/iso9001${path}`, { method: 'POST', body }); done.value = message; open.value = null; form.value = { reason: '', password: '', doc: '' } }
  catch (e) { error.value = e.message } finally { busy.value = false; password.value = '' }
}
const adopt = () => post('/enable', { edition: edition.value, password: password.value }, 'Adopted and checked against your records.')
const evaluate = () => post('/evaluate', {}, 'Checked again against your records.')
const declare = (c, applies) => post(`/controls/${c.id}/applies`, { applies, reason: form.value.reason, password: form.value.password },
  applies ? 'Recorded: it applies.' : 'Recorded: it does not apply.')
const link = (c, id, linked) => post(`/controls/${c.id}/evidence`, { document_id: Number(id), linked }, linked ? 'Document linked.' : 'Link removed.')

const docName = (d) => [d.number, d.title].filter(Boolean).join(' ') || d.original_name
const shown = (c) => filter.value === 'all' || c.result?.status === filter.value
const sorted = (cs) => [...cs].sort((a, b) => ORDER.indexOf(a.result?.status) - ORDER.indexOf(b.result?.status))
function to(p) {
  if (p.kind === 'ncr') return `/quality/ncr/${p.id}`
  if (p.kind === 'capa') return `/quality/capa/${p.id}`
  if (p.kind === 'document') return `/documents/${p.id}`
  if (p.kind === 'inspection') return `/o/QualityInspection/${p.id}`
  return null
}
</script>

<template>
  <PageTop>
    <template #title>Quality system</template>
    <Button v-if="v?.enabled && latest" icon-left="lucide-refresh-cw" label="Check now" :loading="busy" @click="evaluate" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <template v-if="v && !v.enabled">
    <section class="wq-panel max-w-3xl p-5">
      <h2 class="wq-h2">{{ v.label }}</h2>
      <p class="mb-3 text-base text-ink-gray-7">WenQuest Ops turns the standard into control points and checks each one against your records: nonconformances,
        corrective actions, inspections and the document library. Each answer is met, not met or unknown, with the records behind it.
        Where there is nothing to look at yet, the answer is unknown, never met. The requirement summaries are our own words, not the
        standard's text, and this is not a certification.</p>
      <template v-if="can">
        <div class="flex flex-wrap items-end gap-3">
          <label class="wq-field">Edition<select v-model="edition" class="wq-select">
            <option v-for="(e, k) in v.editions" :key="k" :value="k" :disabled="!e.ready">{{ e.label }}{{ e.ready ? '' : ` (${e.note})` }}</option></select></label>
          <label class="wq-field">Your password to sign<input v-model="password" type="password" class="wq-input w-56" autocomplete="current-password"></label>
          <Button variant="solid" label="Adopt the standard (sign)" :loading="busy" :disabled="!password" @click="adopt" />
        </div>
      </template>
      <p v-else class="wq-muted">The owner or Quality adopts the standard.</p>
    </section>
  </template>

  <template v-if="v?.enabled">
    <section class="wq-panel mb-5 p-5">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <h2 class="text-base font-semibold text-ink-gray-9">{{ v.edition_label }}</h2>
        <span class="text-sm text-ink-gray-5">pack version {{ v.enabled.version }} · adopted by {{ v.enabled.enabled_by }} {{ ago(v.enabled.enabled_at) }}
          · fingerprint {{ v.enabled.fingerprint.slice(0, 12) }}…</span>
        <Badge v-if="v.newer_pack" theme="amber" label="a newer pack is available" />
      </div>
      <p v-if="v.evaluation" class="mb-3 text-sm text-ink-gray-6">
        <template v-if="!latest">Showing the check of {{ v.evaluation.day }} ({{ v.evaluation.trigger }}).
          <RouterLink to="/system" class="wq-link">Show the latest</RouterLink></template>
        <template v-else>Checked {{ ago(v.evaluation.at) }} ({{ v.evaluation.trigger }}). Looks at the last {{ v.settings.window_days }} days; checked again every day.</template></p>
      <div class="flex flex-wrap gap-2">
        <button v-for="k in ['all', ...ORDER]" :key="k" class="rounded-3 border px-3 py-1.5 text-sm"
                :class="filter === k ? 'border-outline-gray-4 bg-surface-gray-3 text-ink-gray-9' : 'border-outline-gray-2 text-ink-gray-7'" @click="filter = k">
          {{ k === 'all' ? 'All' : S[k].label }} <span class="ms-1 font-semibold">{{ k === 'all' ? Object.values(counts).reduce((a, b) => a + b, 0) : counts[k] || 0 }}</span></button>
      </div>
    </section>

    <section v-for="p in v.processes" v-show="p.controls.some(shown)" :key="p.id" class="process wq-panel mb-4 p-5">
      <h2 class="wq-h2">{{ p.label }}</h2>
      <article v-for="c in sorted(p.controls).filter(shown)" :key="c.id" class="control border-t border-outline-gray-1 py-3 first:border-t-0">
        <div class="flex flex-wrap items-start gap-2">
          <Badge v-if="c.result" v-bind="S[c.result.status]" class="mt-0.5" />
          <div class="min-w-0 flex-1">
            <p class="text-base text-ink-gray-9">{{ c.summary }}</p>
            <p class="text-sm text-ink-gray-5">ISO 9001 {{ c.clauses.join(', ') }}<template v-if="c.hint"> · evidence: {{ c.hint }}</template></p>
            <p v-if="c.result" class="mt-1 text-sm text-ink-gray-7">{{ c.result.detail }}</p>
            <ul v-if="c.result?.problems.length" class="mt-1 flex flex-col gap-0.5 text-sm">
              <li v-for="x in c.result.problems" :key="`${x.kind}${x.id}${x.why}`">
                <RouterLink v-if="to(x)" :to="to(x)" class="wq-link">{{ x.label }}</RouterLink><span v-else>{{ x.label }}</span>
                <span class="text-ink-gray-6"> — {{ x.why }}</span></li>
              <li v-if="c.result.problem_count > c.result.problems.length" class="text-ink-gray-5">and {{ c.result.problem_count - c.result.problems.length }} more</li>
            </ul>
            <p v-if="c.result?.evidence.length && c.result.status === 'met' && c.rule !== 'linked_document'" class="mt-1 text-sm text-ink-gray-6">Records:
              <template v-for="(x, i) in c.result.evidence" :key="x.id"><RouterLink :to="to(x)" class="wq-link">{{ x.label }}</RouterLink>{{ i < c.result.evidence.length - 1 ? ', ' : '' }}</template>
              <span v-if="c.result.evidence_count > c.result.evidence.length"> and {{ c.result.evidence_count - c.result.evidence.length }} more</span></p>
          </div>
          <Button v-if="can && latest && (c.rule === 'linked_document' || c.may_exclude)" size="sm" variant="ghost"
                  :label="open === c.id ? 'Close' : 'Change'" @click="open = open === c.id ? null : c.id" />
        </div>
        <div v-if="open === c.id" class="mt-3 flex flex-col gap-3 rounded-4 bg-surface-gray-1 p-4 text-sm">
          <div v-if="c.rule === 'linked_document'">
            <p class="mb-1 text-ink-gray-7">Documents linked as evidence:</p>
            <ul class="mb-2"><li v-for="d in v.evidence[c.id] || []" :key="d.id">
              <RouterLink :to="`/documents/${d.id}`" class="wq-link">{{ d.name }}</RouterLink> <span class="text-ink-gray-5">{{ d.status.replace('_', ' ') }}, by {{ d.email }}</span>
              <Button size="sm" variant="ghost" label="Remove" @click="link(c, d.id, false)" /></li>
              <li v-if="!(v.evidence[c.id] || []).length" class="text-ink-gray-5">None yet.</li></ul>
            <div v-if="canDocs" class="flex flex-wrap items-end gap-2">
              <label class="wq-field">Document<select v-model="form.doc" class="wq-select max-w-md">
                <option value="" disabled>Choose a document</option>
                <option v-for="d in docs" :key="d.id" :value="d.id">{{ docName(d) }} ({{ d.status.replace('_', ' ') }})</option></select></label>
              <Button label="Link" :disabled="!form.doc" @click="link(c, form.doc, true)" />
            </div>
          </div>
          <div v-if="c.may_exclude">
            <p class="mb-1 text-ink-gray-7">{{ v.applicability[c.id] ? `Now: ${v.applicability[c.id].applies ? 'applies' : 'does not apply'} (${v.applicability[c.id].reason})` : 'Say whether this applies to your company. Signed, with the reason.' }}</p>
            <div class="flex flex-wrap items-end gap-2">
              <label class="wq-field">Reason<input v-model="form.reason" class="wq-input w-80" placeholder="e.g. we distribute; we do not design products"></label>
              <label class="wq-field">Your password<input v-model="form.password" type="password" class="wq-input w-44" autocomplete="current-password"></label>
              <Button label="Does not apply (sign)" :disabled="!form.reason || !form.password" @click="declare(c, false)" />
              <Button label="Applies (sign)" :disabled="!form.reason || !form.password" @click="declare(c, true)" />
            </div>
          </div>
        </div>
      </article>
    </section>

    <section class="wq-panel p-5">
      <h2 class="wq-h2">Earlier checks</h2>
      <table class="wq-table text-sm"><thead><tr><th>Day</th><th>Why</th><th>Met</th><th>Not met</th><th>Unknown</th><th>Does not apply</th></tr></thead>
        <tbody><tr v-for="h in v.history" :key="h.id" class="cursor-pointer" @click="router.push(`/system?evaluation=${h.id}`)">
          <td><RouterLink :to="`/system?evaluation=${h.id}`" class="wq-link">{{ h.day }}</RouterLink> <span class="text-ink-gray-5">{{ ago(h.at) }}</span></td>
          <td>{{ h.trigger }}<span v-if="h.email" class="text-ink-gray-5"> by {{ h.email }}</span></td>
          <td>{{ h.counts.met }}</td><td>{{ h.counts.not_met }}</td><td>{{ h.counts.unknown }}</td><td>{{ h.counts.not_applicable }}</td></tr></tbody></table>
    </section>
  </template>
</template>
