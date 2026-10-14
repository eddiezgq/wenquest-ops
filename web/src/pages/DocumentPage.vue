<script setup>
// One document (ADR-0014): the proposal with the file's own words beside each field, then confirmation, approval
// with a signature, revisions and the append-only history.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { CONF, DOC_STATE, STATUS, label } from '../ui/themes'
import { api, apiForm } from '../api'
import { ago } from '../format'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const d = ref(null)
const meta = ref(null)
const error = ref('')
const done = ref('')
const form = ref({})
const x = ref({ password: '', reason: '', revision: '', file: null, showText: false })
const FIELDS = [['doc_type', 'Type'], ['process', 'Process'], ['number', 'Number'], ['title', 'Title'],
  ['revision', 'Revision'], ['effective_date', 'Effective date'], ['owner', 'Owner'], ['language', 'Language']]

const canEdit = computed(() => meta.value?.can_edit)
const reviewing = computed(() => d.value && ['to_review', 'to_classify'].includes(d.value.status))
const involved = computed(() => d.value?.involved.includes(ws.value?.user.email))
const typeName = (t) => meta.value?.types[t] || label(t || '—')
const procName = (p) => meta.value?.processes[p] || label(p || '—')
const shown = (k, v) => (k === 'doc_type' ? typeName(v) : k === 'process' ? procName(v) : v || '—')
const size = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)
const TEXT = { ok: 'text read', ocr: 'text read by OCR', no_text: 'no text', error: 'could not be read', pending: 'reading…' }

async function load() {
  error.value = ''
  try {
    meta.value ||= await api('/api/docs/meta')
    set(await api(`/api/docs/${route.params.id}`))
  } catch (e) { error.value = e.message }
}
function set(doc) {
  d.value = doc
  form.value = Object.fromEntries(FIELDS.map(([k]) => [k, doc[k] ?? '']))
  form.value.summary = doc.summary ?? ''
  x.value.password = ''; x.value.reason = ''
}
watch(() => route.params.id, load, { immediate: true })

async function step(path, body, message) {
  error.value = ''; done.value = ''
  try { set(await api(`/api/docs/${d.value.id}/${path}`, { method: 'POST', body })); done.value = message }
  catch (e) { error.value = e.message }
}
function confirm() {
  const fields = {}
  for (const k of [...FIELDS.map(([f]) => f), 'summary']) if ((form.value[k] ?? '') !== (d.value[k] ?? '')) fields[k] = form.value[k]
  const controlled = meta.value.controlled.includes(form.value.doc_type)
  step('confirm', { fields }, controlled ? 'Confirmed. It is a draft now: send it for approval when it is right.'
    : 'Confirmed and kept in the library. Its file can no longer be replaced.')
}
async function newRevision() {
  error.value = ''
  try {
    const f = new FormData()
    f.append('file', x.value.file); f.append('revision', x.value.revision)
    const r = await apiForm(`/api/docs/${d.value.id}/revision`, f)
    router.push(`/documents/${r.id}`)
  } catch (e) { error.value = e.message }
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Documents', to: '/documents?tab=' + (reviewing ? 'review' : 'library') }]">
    <template #title>{{ d ? [d.number, d.title || d.original_name].filter(Boolean).join(' ') : 'Document' }}
      <span v-if="d?.revision" class="font-normal text-ink-gray-5">rev {{ d.revision }}</span></template>
    <template v-if="d">
      <Badge v-if="d.confidence && reviewing" :theme="CONF[d.confidence]" variant="outline" size="lg" :label="`${d.confidence} confidence`" />
      <Badge :theme="STATUS[d.status] || 'gray'" size="lg" :label="DOC_STATE[d.status] || label(d.status)" />
    </template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <div v-if="d && meta" class="grid gap-6 xl:grid-cols-[1fr_22rem]">
    <div class="min-w-0">
      <!-- the proposal, field by field, with the file's own words -->
      <section class="wq-panel p-5">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <h2 class="text-base font-semibold text-ink-gray-9">{{ reviewing ? 'Proposal' : 'Details' }}</h2>
          <span v-if="d.engine" class="text-sm text-ink-gray-5">by {{ d.engine === 'ai' ? 'AI' : d.engine === 'rules' ? 'rules (limited accuracy)' : d.engine }}</span>
          <Badge v-if="reviewing && d.batch_ok" theme="green" label="every quote found in the file" class="ms-auto" />
        </div>
        <div class="grid gap-x-6 gap-y-4 md:grid-cols-2">
          <div v-for="[k, l] in FIELDS" :key="k" class="min-w-0">
            <label class="wq-field">{{ l }}
              <template v-if="reviewing && canEdit">
                <select v-if="k === 'doc_type'" v-model="form.doc_type" class="wq-select"><option value="">Choose…</option>
                  <option v-for="(n, t) in meta.types" :key="t" :value="t">{{ n }}</option></select>
                <select v-else-if="k === 'process'" v-model="form.process" class="wq-select"><option value="">Choose…</option>
                  <option v-for="(n, p) in meta.processes" :key="p" :value="p">{{ n }}</option></select>
                <input v-else v-model="form[k]" class="wq-input" :type="k === 'effective_date' ? 'date' : 'text'" :placeholder="k === 'number' ? 'not in the file' : ''">
              </template>
              <span v-else class="text-base text-ink-gray-9">{{ shown(k, d[k]) }}</span>
            </label>
            <p v-if="d.evidence[k]" class="mt-1 flex items-start gap-1.5 text-sm"
               :class="d.evidence[k].verified ? 'text-ink-gray-5' : 'text-ink-amber-7'">
              <span :class="d.evidence[k].verified ? 'lucide-quote' : 'lucide-circle-alert'" class="mt-0.5 size-3.5 shrink-0" />
              <span><q class="italic">{{ d.evidence[k].quote || '(no quote)' }}</q>
                <template v-if="!d.evidence[k].verified"> — not found in the file as given; check it</template></span></p>
          </div>
        </div>
        <label class="wq-field mt-4">Summary
          <textarea v-if="reviewing && canEdit" v-model="form.summary" rows="2" class="wq-textarea" />
          <span v-else class="text-base text-ink-gray-8">{{ d.summary || '—' }}</span></label>
        <div v-if="d.refs.length" class="mt-4 text-sm text-ink-gray-6">Names these documents:
          <RouterLink v-for="r in d.refs" :key="r" :to="`/documents?tab=library&q=${encodeURIComponent(r)}`" class="wq-link ms-1.5">{{ r }}</RouterLink></div>

        <div v-if="reviewing && canEdit" class="mt-5 flex flex-wrap items-center gap-2 border-t border-outline-gray-1 pt-4">
          <Button variant="solid" icon-left="lucide-check" label="Confirm" @click="confirm" />
          <span class="wq-muted">{{ meta.controlled.includes(form.doc_type) ? 'Procedures, work instructions and forms become drafts and need approval.' : 'Records, certificates and other documents are kept at once.' }}</span>
          <span class="ms-auto flex items-center gap-2">
            <input v-model="x.reason" class="wq-input w-56" placeholder="Why not keep it">
            <Button label="Not a document to keep" :disabled="!x.reason.trim()" @click="step('reject', { reason: x.reason }, 'Not kept.')" /></span>
        </div>
      </section>

      <!-- controlled document steps -->
      <section v-if="canEdit && d.status === 'draft'" class="wq-panel mt-5 p-5">
        <h2 class="wq-h2">Approval</h2>
        <p class="wq-muted mb-3">Someone other than the person who uploaded, confirmed or sends it approves it with their password. It then becomes effective and its file is frozen.</p>
        <Button variant="solid" icon-left="lucide-send" label="Send for approval" @click="step('submit', {}, 'Sent for approval.')" />
      </section>
      <section v-if="canEdit && d.status === 'in_review'" class="wq-panel mt-5 p-5">
        <h2 class="wq-h2">Approval</h2>
        <p v-if="involved" class="wq-muted">You uploaded, confirmed or sent this document, so someone else approves it.</p>
        <div v-else class="flex flex-wrap items-center gap-2">
          <input v-model="x.password" class="wq-input max-w-56" type="password" placeholder="Your password to sign" autocomplete="current-password">
          <Button variant="solid" icon-left="lucide-pen-line" label="Approve (sign)" @click="step('approve', { password: x.password }, 'Approved. The document is effective.')" />
        </div>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <input v-model="x.reason" class="wq-input max-w-80" placeholder="What needs to change">
          <Button label="Send back" :disabled="!x.reason.trim()" @click="step('send-back', { reason: x.reason }, 'Sent back as a draft.')" />
        </div>
      </section>
      <section v-if="canEdit && ['effective', 'confirmed'].includes(d.status)" class="wq-panel mt-5 p-5">
        <template v-if="d.status === 'effective' && d.controlled">
          <h2 class="wq-h2">New revision</h2>
          <p class="wq-muted mb-3">Upload the next revision. It goes through approval; when it is approved this one becomes obsolete. This file is kept.</p>
          <div class="flex flex-wrap items-center gap-2">
            <input type="file" class="text-sm" @change="x.file = $event.target.files[0]">
            <input v-model="x.revision" class="wq-input w-32" placeholder="Revision">
            <Button icon-left="lucide-upload" label="Upload revision" :disabled="!x.file || !x.revision.trim()" @click="newRevision" />
          </div>
        </template>
        <div class="mt-4 flex flex-wrap items-center gap-2">
          <input v-model="x.reason" class="wq-input max-w-80" placeholder="Why it is obsolete">
          <Button theme="red" label="Make obsolete" :disabled="!x.reason.trim()" @click="step('obsolete', { reason: x.reason }, 'Marked obsolete.')" />
        </div>
      </section>
      <p v-if="d.status === 'obsolete'" class="mt-5 text-base text-ink-gray-7">Obsolete: {{ d.obsolete_reason }}</p>

      <section class="mt-5">
        <div class="mb-2 flex items-center gap-3">
          <h2 class="text-base font-semibold text-ink-gray-9">Text</h2>
          <span class="text-sm text-ink-gray-5">{{ TEXT[d.text_status] || d.text_status }}, {{ d.text_chars.toLocaleString('en-US') }} characters</span>
          <Button v-if="d.text" variant="ghost" :label="x.showText ? 'Hide' : 'Show'" @click="x.showText = !x.showText" />
        </div>
        <pre v-if="x.showText" class="wq-panel max-h-[32rem] overflow-auto whitespace-pre-wrap p-4 text-sm text-ink-gray-8">{{ d.text }}<template v-if="d.text_more">

… {{ d.text_more.toLocaleString('en-US') }} more characters (open the file)</template></pre>
      </section>
      <h2 class="wq-h2 mt-6">Signatures</h2>
      <Trail :items="d.signatures" kind="signatures" />
      <h2 class="wq-h2 mt-6">History</h2>
      <Trail :items="d.history" />
    </div>

    <aside class="flex flex-col gap-5">
      <section class="wq-panel p-4">
        <h2 class="wq-h2">File</h2>
        <p class="break-all text-base text-ink-gray-9">{{ d.original_name }}</p>
        <p class="break-all text-sm text-ink-gray-5">{{ d.path || '(top folder)' }}</p>
        <p class="mt-1 text-sm text-ink-gray-6">{{ size(d.size_bytes) }} · {{ d.original_name.split('.').pop().toUpperCase() }}</p>
        <div class="mt-3 flex gap-2">
          <Button :href="`/api/docs/${d.id}/file?inline=1`" icon-left="lucide-eye" label="Open" />
          <Button :href="`/api/docs/${d.id}/file`" icon-left="lucide-download" label="Download" />
        </div>
        <p v-if="d.fingerprint" class="mt-3 text-sm text-ink-gray-5" :title="d.fingerprint">Frozen: fingerprint {{ d.fingerprint.slice(0, 12) }}…</p>
        <p v-if="d.import" class="mt-2 text-sm text-ink-gray-5">Uploaded by {{ d.import.created_by }}, {{ ago(d.import.created_at) }}</p>
      </section>
      <section v-if="d.same_file.length" class="wq-panel p-4">
        <h2 class="wq-h2">Same file elsewhere</h2>
        <ul class="text-sm"><li v-for="s in d.same_file" :key="s.id" class="py-0.5">
          <RouterLink :to="`/documents/${s.id}`" class="wq-link">{{ s.path ? s.path + '/' : '' }}{{ s.original_name }}</RouterLink>
          <span class="text-ink-gray-5"> ({{ DOC_STATE[s.status] || label(s.status) }})</span></li></ul>
      </section>
      <section v-if="d.revisions.length > 1" class="wq-panel p-4">
        <h2 class="wq-h2">Revisions of {{ d.number }}</h2>
        <ul class="text-sm"><li v-for="r in d.revisions" :key="r.id" class="flex items-center gap-2 py-0.5">
          <RouterLink :to="`/documents/${r.id}`" class="wq-link" :class="{ 'font-semibold': r.id === d.id }">rev {{ r.revision || '?' }}</RouterLink>
          <Badge :theme="STATUS[r.status] || 'gray'" :label="DOC_STATE[r.status] || label(r.status)" />
          <span class="ms-auto text-ink-gray-5">{{ r.effective_date || '' }}</span></li></ul>
      </section>
    </aside>
  </div>
</template>
