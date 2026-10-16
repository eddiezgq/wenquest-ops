<script setup>
// One management review (ADR-0017, 17j). The inputs are counted by WenQuest Ops and frozen; people write the meeting,
// the conclusion and the actions; the chair signs. Prints as the review's report.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'
import { fmt } from '../format'

const route = useRoute()
const r = ref(null)
const error = ref('')
const done = ref('')
const f = ref({})
const notes = ref({})
const x = ref({ password: '', reason: '', text: '', owner: '', due: '' })
const evidence = ref({})
const ST = { draft: 'gray', frozen: 'blue', closed: 'green', cancelled: 'gray' }
const STATUS = { draft: 'draft', frozen: 'inputs collected', closed: 'signed', cancelled: 'cancelled' }
const FIELDS = ['title', 'period_start', 'period_end', 'meeting_on', 'chair', 'attendees', 'conclusion']
const editing = computed(() => r.value?.can_configure && ['draft', 'frozen'].includes(r.value.status))

function set(v) { r.value = v; f.value = Object.fromEntries(FIELDS.map((k) => [k, v[k] ?? ''])); notes.value = { ...v.notes } }
async function load() { error.value = ''; try { set(await api(`/api/reviews/${route.params.id}`)) } catch (e) { error.value = e.message } }
watch(() => route.params.id, load, { immediate: true })
function changes() {
  const out = Object.fromEntries(FIELDS.filter((k) => (f.value[k] ?? '') !== (r.value[k] ?? '')).map((k) => [k, f.value[k] === '' ? null : f.value[k]]))
  // only the inputs whose note changed: someone else's notes on other inputs are kept
  const n = Object.fromEntries(Object.entries(notes.value).filter(([k, v]) => (v ?? '') !== (r.value.notes[k] ?? '')).map(([k, v]) => [k, v ?? '']))
  if (Object.keys(n).length) out.notes = n
  return out
}
const dirty = computed(() => r.value && Object.keys(changes()).length > 0)
async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { set(await api(path, { method, body })); done.value = message; return true } catch (e) { error.value = e.message }
}
const value = (fg) => fg.value === null || fg.value === undefined ? 'unknown' : fmt(fg.value, fg.unit)
function print() { window.print() }
async function addAction() {
  if (await call(`/api/reviews/${r.value.id}/actions`, 'POST', { text: x.value.text, owner: x.value.owner, due: x.value.due }, 'Action added.')) x.value = { ...x.value, text: '', owner: '', due: '' }
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Management reviews', to: '/quality/reviews' }]">
    <template #title>{{ r ? `${r.name} · ${r.title}` : 'Management review' }}</template>
    <Button v-if="r?.inputs" icon-left="lucide-printer" label="Print the report" class="no-print" @click="print" />
    <Badge v-if="r" :theme="ST[r.status]" size="lg" :label="STATUS[r.status]" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4 no-print">{{ error }}</p>
  <p v-if="done" class="no-print mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="r">
    <p v-if="r.intact === false" class="wq-error mb-4">The inputs no longer match their fingerprint.</p>
    <section class="what wq-panel mb-5 grid gap-3 p-5 md:grid-cols-4">
      <label class="wq-field md:col-span-2">Title<input v-model="f.title" class="wq-input" :disabled="!editing"></label>
      <label class="wq-field">Period from<input v-model="f.period_start" type="date" class="wq-input" :disabled="!editing || r.status !== 'draft'"></label>
      <label class="wq-field">to<input v-model="f.period_end" type="date" class="wq-input" :disabled="!editing || r.status !== 'draft'"></label>
      <label class="wq-field">Meeting date<input v-model="f.meeting_on" type="date" class="wq-input" :disabled="!editing"></label>
      <label class="wq-field">Chair (signs)<select v-model="f.chair" class="wq-select" :disabled="!editing"><option value="" /><option v-for="p in r.people" :key="p">{{ p }}</option></select></label>
      <label class="wq-field md:col-span-2">Attendees<input v-model="f.attendees" class="wq-input" :disabled="!editing"></label>
    </section>

    <section class="wq-panel mb-5 p-5">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 class="wq-h2">Inputs</h2>
        <div v-if="editing" class="no-print flex items-center gap-2">
          <span v-if="r.collected_at" class="text-sm text-ink-gray-5">Counted {{ r.inputs?.counted_on }} by {{ r.collected_by }}</span>
          <Button :variant="r.inputs ? 'subtle' : 'solid'" :label="r.inputs ? 'Count again' : 'Collect the inputs'" :disabled="dirty" @click="call(`/api/reviews/${r.id}/collect`, 'POST', {}, 'Inputs counted and frozen.')" />
        </div>
      </div>
      <p v-if="!r.inputs" class="wq-muted">Collect the inputs: WenQuest Ops counts them from the records for the period and freezes them.</p>
      <div v-else class="grid gap-4 md:grid-cols-2">
        <article v-for="(s, k) in r.inputs.sections" :key="k" class="input rounded-4 border border-outline-gray-2 p-4">
          <h3 class="mb-2 text-base font-semibold text-ink-gray-9">{{ s.label }}</h3>
          <table class="w-full text-sm"><tbody><tr v-for="fg in s.figures" :key="fg.label" class="border-b border-outline-gray-1 last:border-0">
            <td class="py-1 text-ink-gray-7">{{ fg.label }}</td><td class="py-1 text-right font-medium text-ink-gray-9">{{ value(fg) }}</td></tr></tbody></table>
          <ul v-for="(rows, name) in s.lists || {}" v-show="rows.length" :key="name" class="mt-2 list-disc ps-5 text-sm text-ink-gray-7">
            <li v-for="(row, i) in rows" :key="i">{{ Object.values(row).filter(Boolean).join(' · ') }}</li></ul>
          <label v-if="editing" class="wq-field mt-2">The meeting's assessment<textarea v-model="notes[k]" rows="2" class="wq-input" /></label>
          <p v-else-if="r.notes[k]" class="mt-2 whitespace-pre-line border-l-2 border-outline-gray-3 ps-3 text-sm text-ink-gray-8">{{ r.notes[k] }}</p>
        </article>
      </div>
      <p v-if="r.fingerprint" class="mt-3 text-xs text-ink-gray-5">Fingerprint {{ r.fingerprint }}</p>
    </section>

    <section class="wq-panel mb-5 p-5">
      <label v-if="editing" class="wq-field">Conclusion: is the system suitable, adequate and effective?<textarea v-model="f.conclusion" rows="3" class="wq-input" /></label>
      <template v-else><h2 class="wq-h2">Conclusion</h2><p class="whitespace-pre-line text-base text-ink-gray-8">{{ r.conclusion || 'None.' }}</p></template>
      <div v-if="editing" class="no-print mt-3"><Button label="Save" :disabled="!dirty" @click="call(`/api/reviews/${r.id}`, 'PUT', changes(), 'Saved.')" />
        <span v-if="dirty" class="ms-2 text-sm text-ink-amber-7">Save your changes before counting, adding actions or signing.</span></div>
    </section>

    <section class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">Actions decided</h2>
      <p v-if="!r.actions.length" class="wq-muted">None.</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>Action</th><th>Owner</th><th>Due</th><th>Status</th><th /></tr></thead>
        <tbody><tr v-for="a in r.actions" :key="a.id"><td>{{ a.text }}</td><td>{{ a.owner }}</td><td>{{ a.due }}</td>
          <td><Badge :theme="a.status === 'done' ? 'green' : 'amber'" :label="a.status" /><span v-if="a.evidence" class="ms-2 text-ink-gray-6">{{ a.evidence }}</span></td>
          <td class="no-print"><div v-if="a.status === 'open' && (a.owner === r.me || r.can_configure)" class="flex gap-2">
            <input v-model="evidence[a.id]" class="wq-input w-48" placeholder="What shows it is done">
            <Button size="sm" label="Done" :disabled="!evidence[a.id]?.trim() || dirty" @click="call(`/api/review-actions/${a.id}/done`, 'POST', { evidence: evidence[a.id] }, 'Marked done.')" /></div></td></tr></tbody></table>
      <form v-if="editing" class="no-print mt-3 flex flex-wrap items-end gap-2" @submit.prevent="addAction">
        <label class="wq-field grow">Action<input v-model="x.text" class="wq-input"></label>
        <label class="wq-field">Owner<select v-model="x.owner" class="wq-select"><option value="" /><option v-for="p in r.people" :key="p">{{ p }}</option></select></label>
        <label class="wq-field">Due<input v-model="x.due" type="date" class="wq-input"></label>
        <Button type="submit" label="Add" :disabled="!x.text.trim() || !x.owner || !x.due || dirty" />
      </form>
    </section>

    <section v-if="['draft', 'frozen'].includes(r.status)" class="no-print wq-panel mb-5 p-5">
      <p v-if="r.to_sign.length" class="mb-2 text-sm text-ink-gray-6">To sign: {{ r.to_sign.join('; ') }}.</p>
      <div v-if="r.chair === r.me" class="flex flex-wrap items-end gap-2">
        <input v-model="x.password" type="password" class="wq-input w-44" placeholder="Your password" autocomplete="current-password">
        <Button variant="solid" label="Sign the review" :disabled="!x.password || !!r.to_sign.length || dirty" @click="call(`/api/reviews/${r.id}/sign`, 'POST', { password: x.password }, 'Signed: the review is fixed.')" />
      </div>
      <p class="mt-2 text-sm text-ink-gray-5">The chair signs, and not someone who collected the inputs or wrote the notes or actions.</p>
      <details v-if="r.can_configure" class="mt-3"><summary class="cursor-pointer text-sm text-ink-gray-7">Cancel the review</summary>
        <div class="mt-2 flex gap-2"><input v-model="x.reason" class="wq-input w-96" placeholder="Why"><Button label="Cancel" :disabled="!x.reason.trim() || dirty" @click="call(`/api/reviews/${r.id}/cancel`, 'POST', { reason: x.reason }, 'Cancelled.')" /></div></details>
    </section>
    <h2 class="wq-h2 mt-6">Signatures</h2>
    <Trail :items="r.signatures" kind="signatures" />
    <div class="no-print"><h2 class="wq-h2 mt-6">History</h2><Trail :items="r.history" /></div>
  </template>
</template>

<style>
@media print {
  .no-print, aside, nav { display: none !important; }
  .wq-panel { break-inside: avoid; border: 1px solid #ccc; }
  textarea { border: none !important; resize: none; }
}
</style>
