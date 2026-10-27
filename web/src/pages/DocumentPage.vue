<script setup>
// One document (ADR-0014): the proposal with the file's own words beside each field, then confirmation, approval
// with a signature, revisions and the append-only history.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import DocControl from '../components/DocControl.vue'
import { CONF, DOC_STATE, STATUS, label } from '../ui/themes'
import { api, apiForm } from '../api'
import { ago } from '../format'
import { t } from '../i18n'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const d = ref(null)
const meta = ref(null)
const error = ref('')
const done = ref('')
const form = ref({})
const x = ref({ password: '', reason: '', revision: '', file: null, showText: false, effective_on: '' })
const FIELDS = [['doc_type', 'Type'], ['process', 'Process'], ['number', 'Number'], ['title', 'Title'],
  ['revision', 'Revision'], ['effective_date', 'Effective date'], ['owner', 'Owner'], ['language', 'Language']]

const canEdit = computed(() => meta.value?.can_edit)
const reviewing = computed(() => d.value && ['to_review', 'to_classify'].includes(d.value.status))
const editable = computed(() => canEdit.value && (reviewing.value || d.value?.status === 'draft'))
const involved = computed(() => d.value?.involved.includes(ws.value?.user.email))
const typeName = (k) => meta.value?.types[k] || label(k || '—')
const procName = (p) => meta.value?.processes[p] || label(p || '—')
const shown = (k, v) => (k === 'doc_type' ? typeName(v) : k === 'process' ? procName(v) : v || '—')
const size = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)
const TEXT = { ok: 'text read', ocr: 'text read by OCR', no_text: 'no text', error: 'could not be read', pending: 'reading…' }

async function load() {
  error.value = ''
  try {
    meta.value ||= await api('/api/docs/meta')
    set(await api(`/api/docs/${route.params.id}`))
    ledgers.value = /\.(xlsx|xlsm|csv)$/i.test(d.value.original_name) ? await api(`/api/ledgers?document_id=${d.value.id}`) : null
  } catch (e) { error.value = e.message }
}
// a spreadsheet can be imported as a historical ledger (ADR-0014 item 10)
const ledgers = ref(null)
const ledgerKind = ref('')
const reading = ref(false)
async function readLedger() {
  reading.value = true; error.value = ''
  try {
    const r = await api('/api/ledgers', { method: 'POST', body: { document_id: d.value.id, target: ledgerKind.value || undefined } })
    router.push(`/documents/ledger/${r.id}`)
  } catch (e) { error.value = e.message } finally { reading.value = false }
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
function changed() {
  const fields = {}
  for (const k of [...FIELDS.map(([f]) => f), 'summary']) if ((form.value[k] ?? '') !== (d.value[k] ?? '')) fields[k] = form.value[k]
  return fields
}
function confirm() {
  const fields = changed()
  const controlled = meta.value.controlled.includes(form.value.doc_type)
  step('confirm', { fields }, controlled ? t('Confirmed. It is a draft now: send it for approval when it is right.')
    : t('Confirmed and kept in the library. Its file can no longer be replaced.'))
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
  <PageTop :crumbs="[{ label: t('Documents'), to: '/documents?tab=' + (reviewing ? 'review' : 'library') }]">
    <template #title>{{ d ? [d.number, d.title || d.original_name].filter(Boolean).join(' ') : t('Document') }}
      <span v-if="d?.revision" class="font-normal text-ink-gray-5">{{ t('rev {revision}', { revision: d.revision }) }}</span></template>
    <template v-if="d">
      <Badge v-if="d.confidence && reviewing" :theme="CONF[d.confidence]" variant="outline" size="lg" :label="t('{level} confidence', { level: t(d.confidence) })" />
      <Badge :theme="STATUS[d.status] || 'gray'" size="lg" :label="t(DOC_STATE[d.status] || label(d.status))" />
    </template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <div v-if="d && meta" class="grid gap-6 xl:grid-cols-[1fr_22rem]">
    <div class="min-w-0">
      <!-- problems the checks found for this document (14b) -->
      <section v-if="d.suggest.issues.length" class="mb-5 rounded-5 border border-outline-amber-2 bg-surface-amber-1 p-4">
        <h2 class="mb-2 text-base font-semibold text-ink-gray-9">{{ t('To look at') }}</h2>
        <ul class="flex flex-col gap-2 text-base">
          <li v-for="(i, n) in d.suggest.issues" :key="n"><span class="font-medium text-ink-gray-9">{{ i.title }}.&nbsp;</span>
            <span class="text-ink-gray-7">{{ i.detail.replace(/\.?$/, '.') }}</span>
            <RouterLink v-if="i.docs.length > 1" :to="`/documents?tab=problems&process=${i.process || ''}`" class="wq-link ms-1 text-sm">{{ t('see all') }}</RouterLink></li>
        </ul>
        <div v-if="editable && d.suggest.issues.some((i) => i.kind === 'revisions' && i.older.includes(d.id))" class="mt-3">
          <Button icon-left="lucide-archive" :label="t('Keep as obsolete (older revision)')"
                  @click="step('archive', { reason: 'older revision; ' + d.suggest.issues.find((i) => i.kind === 'revisions').title.split(', ')[1] }, t('Kept as obsolete; its history stays in the library.'))" />
          <span class="wq-muted ms-2">{{ t('It stays findable and is never used.') }}</span></div>
        <div v-if="editable && d.suggest.number && form.number !== d.suggest.number" class="mt-3">
          <Button icon-left="lucide-hash" :label="t('Use the suggested number {number}', { number: d.suggest.number })" @click="form.number = d.suggest.number" />
          <span class="wq-muted ms-2">{{ reviewing ? t('then confirm') : t('then save') }}</span></div>
      </section>

      <!-- the proposal, field by field, with the file's own words -->
      <section data-help="doc-proposal" class="wq-panel p-5">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <h2 class="text-base font-semibold text-ink-gray-9">{{ reviewing ? t('Proposal') : t('Details') }}</h2>
          <span v-if="d.engine" class="text-sm text-ink-gray-5">{{ d.engine === 'ai' ? t('by AI') : d.engine === 'rules' ? t('by rules (limited accuracy)') : t('by {engine}', { engine: d.engine }) }}</span>
          <Badge v-if="reviewing && d.batch_ok" theme="green" :label="t('every quote found in the file')" class="ms-auto" />
        </div>
        <div class="grid gap-x-6 gap-y-4 md:grid-cols-2">
          <div v-for="[k, l] in FIELDS" :key="k" class="min-w-0">
            <label class="wq-field">{{ t(l) }}
              <template v-if="editable">
                <select v-if="k === 'doc_type'" v-model="form.doc_type" class="wq-select"><option value="">{{ t('Choose…') }}</option>
                  <option v-for="(n, k) in meta.types" :key="k" :value="k">{{ n }}</option></select>
                <select v-else-if="k === 'process'" v-model="form.process" class="wq-select"><option value="">{{ t('Choose…') }}</option>
                  <option v-for="(n, p) in meta.processes" :key="p" :value="p">{{ n }}</option></select>
                <input v-else v-model="form[k]" class="wq-input" :type="k === 'effective_date' ? 'date' : 'text'" :placeholder="k === 'number' ? t('not in the file') : ''">
              </template>
              <span v-else class="text-base text-ink-gray-9">{{ shown(k, d[k]) }}</span>
            </label>
            <p v-if="d.evidence[k]" class="mt-1 flex items-start gap-1.5 text-sm"
               :class="d.evidence[k].verified ? 'text-ink-gray-5' : 'text-ink-amber-7'">
              <span :class="d.evidence[k].verified ? 'lucide-quote' : 'lucide-circle-alert'" class="mt-0.5 size-3.5 shrink-0" />
              <span><q class="italic">{{ d.evidence[k].quote || t('(no quote)') }}</q>
                <template v-if="!d.evidence[k].verified"> — {{ t('not found in the file as given; check it') }}</template></span></p>
          </div>
        </div>
        <label class="wq-field mt-4">{{ t('Summary') }}
          <textarea v-if="editable" v-model="form.summary" rows="2" class="wq-textarea" />
          <span v-else class="text-base text-ink-gray-8">{{ d.summary || '—' }}</span></label>
        <div v-if="d.refs.length" class="mt-4 text-sm text-ink-gray-6">{{ t('Names these documents:') }}
          <RouterLink v-for="r in d.refs" :key="r" :to="`/documents?tab=library&q=${encodeURIComponent(r)}`" class="wq-link ms-1.5">{{ r }}</RouterLink></div>

        <div v-if="reviewing && canEdit" data-help="doc-confirm" class="mt-5 flex flex-wrap items-center gap-2 border-t border-outline-gray-1 pt-4">
          <Button variant="solid" icon-left="lucide-check" :label="t('Confirm')" @click="confirm" />
          <span class="wq-muted">{{ meta.controlled.includes(form.doc_type) ? t('Procedures, work instructions and forms become drafts and need approval.') : t('Records, certificates and other documents are kept at once.') }}</span>
          <span class="ms-auto flex items-center gap-2">
            <input v-model="x.reason" class="wq-input w-56" :placeholder="t('Why not keep it')">
            <Button :label="t('Not a document to keep')" :disabled="!x.reason.trim()" @click="step('reject', { reason: x.reason }, t('Not kept.'))" /></span>
        </div>
      </section>

      <!-- controlled document steps -->
      <section v-if="canEdit && d.status === 'draft'" data-help="doc-send" class="wq-panel mt-5 p-5">
        <h2 class="wq-h2">{{ t('Approval') }}</h2>
        <p class="wq-muted mb-3">{{ t('Correct the details above if needed and save them. Someone other than the person who uploaded, confirmed or sends it approves it with their password. It then becomes effective and its file is frozen.') }}</p>
        <div class="flex flex-wrap gap-2">
          <Button :disabled="!Object.keys(changed()).length" icon-left="lucide-save" :label="t('Save changes')" @click="step('edit', { fields: changed() }, t('Saved.'))" />
          <Button variant="solid" icon-left="lucide-send" :disabled="!!Object.keys(changed()).length" :label="t('Send for approval')" @click="step('submit', {}, t('Sent for approval.'))" />
        </div>
      </section>
      <section v-if="canEdit && d.status === 'in_review'" data-help="doc-approve" class="wq-panel mt-5 p-5">
        <h2 class="wq-h2">{{ t('Approval') }}</h2>
        <p v-if="involved" class="wq-muted">{{ t('You uploaded, confirmed or sent this document, so someone else approves it.') }}</p>
        <div v-else class="flex flex-wrap items-center gap-2">
          <label class="wq-field">{{ t('Takes effect on') }}<input v-model="x.effective_on" type="date" class="wq-input w-44"></label>
          <input v-model="x.password" class="wq-input max-w-56 self-end" type="password" :placeholder="t('Your password to sign')" autocomplete="current-password">
          <Button class="self-end" variant="solid" icon-left="lucide-pen-line" :label="t('Approve (sign)')"
                  @click="step('approve', { password: x.password, effective_on: x.effective_on || undefined }, x.effective_on ? t('Approved. It takes effect on {date}.', { date: x.effective_on }) : t('Approved. The document is effective.'))" />
          <p class="wq-muted w-full">{{ t('Leave the day empty for today. A later day leaves time for people to read it; the revision in effect stays until then.') }}</p>
        </div>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <input v-model="x.reason" class="wq-input max-w-80" :placeholder="t('What needs to change')">
          <Button :label="t('Send back')" :disabled="!x.reason.trim()" @click="step('send-back', { reason: x.reason }, t('Sent back as a draft.'))" />
        </div>
      </section>
      <section v-if="canEdit && ['effective', 'confirmed'].includes(d.status)" data-help="doc-revise" class="wq-panel mt-5 p-5">
        <template v-if="d.status === 'effective' && d.controlled">
          <h2 class="wq-h2">{{ t('New revision') }}</h2>
          <p class="wq-muted mb-3">{{ t('Upload the next revision. It goes through approval; when it is approved this one becomes obsolete. This file is kept.') }}</p>
          <div class="flex flex-wrap items-center gap-2">
            <input type="file" class="text-sm" @change="x.file = $event.target.files[0]">
            <input v-model="x.revision" class="wq-input w-32" :placeholder="t('Revision')">
            <Button icon-left="lucide-upload" :label="t('Upload revision')" :disabled="!x.file || !x.revision.trim()" @click="newRevision" />
          </div>
        </template>
        <div class="mt-4 flex flex-wrap items-center gap-2">
          <input v-model="x.reason" class="wq-input max-w-80" :placeholder="t('Why it is obsolete')">
          <Button theme="red" :label="t('Make obsolete')" :disabled="!x.reason.trim()" @click="step('obsolete', { reason: x.reason }, t('Marked obsolete.'))" />
        </div>
      </section>
      <p v-if="d.status === 'obsolete'" class="mt-5 text-base text-ink-gray-7">{{ t('Obsolete: {reason}', { reason: d.obsolete_reason }) }}</p>
      <p v-if="d.status === 'approved'" class="mt-5 text-base text-ink-gray-7">{{ t('Approved by {name}; takes effect on {date}.', { name: d.approved_by, date: d.effective_date }) }}</p>
      <DocControl v-if="d.controlled && ['draft', 'in_review', 'approved', 'effective'].includes(d.status)" :d="d" :can-edit="canEdit" @changed="set" />

      <section class="mt-5">
        <div class="mb-2 flex items-center gap-3">
          <h2 class="text-base font-semibold text-ink-gray-9">{{ t('Text') }}</h2>
          <span class="text-sm text-ink-gray-5">{{ t('{status}, {n} characters', { status: t(TEXT[d.text_status] || d.text_status), n: d.text_chars.toLocaleString('en-US') }) }}</span>
          <Button v-if="d.text" variant="ghost" :label="x.showText ? t('Hide') : t('Show')" @click="x.showText = !x.showText" />
        </div>
        <pre v-if="x.showText" class="wq-panel max-h-[32rem] overflow-auto whitespace-pre-wrap p-4 text-sm text-ink-gray-8">{{ d.text }}<template v-if="d.text_more">

{{ t('… {n} more characters (open the file)', { n: d.text_more.toLocaleString('en-US') }) }}</template></pre>
      </section>
      <h2 class="wq-h2 mt-6">{{ t('Signatures') }}</h2>
      <Trail :items="d.signatures" kind="signatures" />
      <h2 class="wq-h2 mt-6">{{ t('History') }}</h2>
      <Trail :items="d.history" />
    </div>

    <aside class="flex flex-col gap-5">
      <section v-if="ledgers && Object.keys(ledgers.kinds).length" data-help="doc-ledger" class="ledger wq-panel p-4">
        <h2 class="wq-h2">{{ t('Import as a ledger') }}</h2>
        <p class="wq-muted mb-3">{{ meta.ai ? t("Bring this sheet's rows into WenQuest Ops: AI proposes which column is which; you check, then import with your password.") : t("Bring this sheet's rows into WenQuest Ops: the rules propose which column is which; you check, then import with your password.") }}</p>
        <div class="flex flex-wrap items-center gap-2">
          <select v-model="ledgerKind" class="wq-select" :aria-label="t('Kind of ledger')"><option value="">{{ meta.ai ? t('Let AI tell what it is') : t('Guess from the columns') }}</option>
            <option v-for="(l, k) in ledgers.kinds" :key="k" :value="k">{{ l }}</option></select>
          <Button icon-left="lucide-table" :loading="reading" :label="t('Read the ledger')" @click="readLedger" />
        </div>
        <ul v-if="ledgers.imports.length" class="mt-3 text-sm">
          <li v-for="l in ledgers.imports" :key="l.id" class="py-0.5"><RouterLink :to="`/documents/ledger/${l.id}`" class="wq-link">{{ ledgers.kinds[l.target] || l.target }}</RouterLink>
            <span class="text-ink-gray-5"> — {{ l.status === 'imported' ? t('imported {n} rows', { n: l.result.imported + l.result.drafted }) : t('to check') }}</span></li></ul>
      </section>
      <section data-help="doc-file" class="wq-panel p-4">
        <h2 class="wq-h2">{{ t('File') }}</h2>
        <p class="break-all text-base text-ink-gray-9">{{ d.original_name }}</p>
        <p class="break-all text-sm text-ink-gray-5">{{ d.path || t('(top folder)') }}</p>
        <p class="mt-1 text-sm text-ink-gray-6">{{ size(d.size_bytes) }} · {{ d.original_name.split('.').pop().toUpperCase() }}</p>
        <div class="mt-3 flex gap-2">
          <Button :href="`/api/docs/${d.id}/file?inline=1`" icon-left="lucide-eye" :label="t('Open')" />
          <Button :href="`/api/docs/${d.id}/file`" icon-left="lucide-download" :label="t('Download')" />
        </div>
        <p v-if="d.suggest.file_name && d.suggest.file_name !== d.original_name" class="mt-3 text-sm text-ink-gray-6">{{ t('Standard name:') }}
          <a :href="`/api/docs/${d.id}/file?standard=1`" class="wq-link break-all">{{ d.suggest.file_name }}</a>
          <span class="block text-ink-gray-5">{{ t('Downloads under this name; the stored original keeps its name.') }}</span></p>
        <p v-if="d.fingerprint" class="mt-3 text-sm text-ink-gray-5" :title="d.fingerprint">{{ t('Frozen: fingerprint {fp}…', { fp: d.fingerprint.slice(0, 12) }) }}</p>
        <p v-if="d.import" class="mt-2 text-sm text-ink-gray-5">{{ t('Uploaded by {name}, {when}', { name: d.import.created_by, when: ago(d.import.created_at) }) }}</p>
      </section>
      <section v-if="d.same_file.length" class="wq-panel p-4">
        <h2 class="wq-h2">{{ t('Same file elsewhere') }}</h2>
        <ul class="text-sm"><li v-for="s in d.same_file" :key="s.id" class="py-0.5">
          <RouterLink :to="`/documents/${s.id}`" class="wq-link">{{ s.path ? s.path + '/' : '' }}{{ s.original_name }}</RouterLink>
          <span class="text-ink-gray-5"> ({{ t(DOC_STATE[s.status] || label(s.status)) }})</span></li></ul>
      </section>
      <section v-if="d.revisions.length > 1" class="wq-panel p-4">
        <h2 class="wq-h2">{{ t('Revisions of {number}', { number: d.number }) }}</h2>
        <ul class="text-sm"><li v-for="r in d.revisions" :key="r.id" class="flex items-center gap-2 py-0.5">
          <RouterLink :to="`/documents/${r.id}`" class="wq-link" :class="{ 'font-semibold': r.id === d.id }">{{ t('rev {revision}', { revision: r.revision || '?' }) }}</RouterLink>
          <Badge :theme="STATUS[r.status] || 'gray'" :label="t(DOC_STATE[r.status] || label(r.status))" />
          <span class="ms-auto text-ink-gray-5">{{ r.effective_date || '' }}</span></li></ul>
      </section>
    </aside>
  </div>
</template>
