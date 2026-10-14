<script setup>
// Document library (ADR-0014): drop files or folders in, let AI classify them, review the proposals, and keep
// procedures, forms and records under control. AI proposes; people confirm and approve.
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { CONF, DOC_STATE, STATUS, label } from '../ui/themes'
import { api, apiForm } from '../api'
import { ago, fmt } from '../format'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const TABS = { overview: 'Overview', problems: 'Problems', review: 'To review', library: 'Library', imports: 'Imports' }
const tab = computed({ get: () => route.query.tab || 'overview', set: (t) => router.replace({ query: { tab: t } }) })
const meta = ref(null)
const error = ref('')
const notice = ref('')
const overview = ref(null)
const rows = ref([])
const imports = ref([])
const picked = ref([])
const chosen = ref(new Set())
const busy = ref(false)
const dragging = ref(false)
const uploadLabel = ref('')
const f = ref({ q: route.query.q || '', status: route.query.status || 'library', process: route.query.process || '', type: route.query.type || '' })
const problems = ref(null)
const issueProcess = ref(route.query.process || '')
const rules = ref({})
const reasons = ref({})
let timer = null

const canEdit = computed(() => meta.value?.can_edit)
const typeName = (t) => meta.value?.types[t] || label(t || 'unknown')
const procName = (p) => meta.value?.processes[p] || label(p || 'unknown')
const size = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)
const unverified = (d) => Object.values(d.evidence || {}).filter((e) => !e.verified).length
const how = (d) => (d.engine === 'ai' ? 'AI' : d.engine === 'rules' ? 'rules' : d.engine === 'person' ? 'person' : 'same as earlier file')

async function load() {
  error.value = ''
  try {
    meta.value ||= await api('/api/docs/meta')
    if (tab.value === 'overview') overview.value = await api('/api/docs/overview')
    if (tab.value === 'problems') {
      problems.value = await api(`/api/docs/issues?process=${encodeURIComponent(issueProcess.value)}`)
      rules.value = Object.fromEntries(Object.entries(problems.value.conventions).map(([t, c]) => [t, { template: c.template, digits: c.digits }]))
    }
    if (tab.value === 'review') { rows.value = await api('/api/docs?status=to_review'); chosen.value = new Set() }
    if (tab.value === 'library') {
      const q = new URLSearchParams({ status: f.value.status, process: f.value.process, type: f.value.type, q: f.value.q })
      rows.value = await api(`/api/docs?${q}`)
    }
    if (tab.value === 'imports' || tab.value === 'overview') imports.value = await api('/api/docs/imports')
  } catch (e) { error.value = e.message }
  poll()
}
function poll() {
  clearTimeout(timer)
  if (imports.value.some((i) => ['extracting', 'classifying'].includes(i.status))) {
    timer = setTimeout(async () => {
      imports.value = await api('/api/docs/imports').catch(() => imports.value)
      if (!imports.value.some((i) => ['extracting', 'classifying'].includes(i.status))) load()
      else poll()
    }, 2000)
  }
}
onBeforeUnmount(() => clearTimeout(timer))
watch(tab, load, { immediate: true })
watch(() => [f.value.status, f.value.process, f.value.type], () => tab.value === 'library' && load())

// ---------------------------------------------------------------- picking files and folders
async function walk(entry, path) {
  if (entry.isFile) return [await new Promise((ok, no) => entry.file((file) => ok({ file, name: path + file.name }), no))]
  const reader = entry.createReader()
  const all = []
  for (;;) {
    const batch = await new Promise((ok, no) => reader.readEntries(ok, no))
    if (!batch.length) break
    all.push(...batch)
  }
  const out = []
  for (const e of all) out.push(...(await walk(e, `${path}${entry.name}/`)))
  return out
}
async function drop(e) {
  dragging.value = false
  const entries = [...(e.dataTransfer.items || [])].map((i) => i.webkitGetAsEntry?.()).filter(Boolean)
  const got = []
  if (entries.length) for (const en of entries) got.push(...(await walk(en, '')))
  else for (const file of e.dataTransfer.files) got.push({ file, name: file.name })
  add(got)
}
function choose(e) {
  add([...e.target.files].map((file) => ({ file, name: file.webkitRelativePath || file.name })))
  e.target.value = ''
}
function add(list) {
  const skip = /(^|\/)(\.|__MACOSX\/|Thumbs\.db$|desktop\.ini$)/i
  picked.value = [...picked.value, ...list.filter((x) => !skip.test(x.name))]
}
const pickedSize = computed(() => picked.value.reduce((s, x) => s + x.file.size, 0))
async function upload() {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const form = new FormData()
    for (const x of picked.value) form.append('files', x.file, x.name)
    form.append('label', uploadLabel.value)
    await apiForm('/api/docs/imports', form)
    picked.value = []; uploadLabel.value = ''
    notice.value = 'Uploaded. The text is being read; then choose how to classify the files.'
    if (tab.value === 'imports') await load(); else tab.value = 'imports'
  } catch (e) { error.value = e.message } finally { busy.value = false }
}

// ---------------------------------------------------------------- classifying and confirming
async function classify(imp, engine) {
  error.value = ''
  try { await api(`/api/docs/imports/${imp.id}/classify`, { method: 'POST', body: { engine } }); await load() }
  catch (e) { error.value = e.message }
}
const batchable = computed(() => rows.value.filter((d) => d.batch_ok))
function toggle(d) {
  const s = new Set(chosen.value)
  s.has(d.id) ? s.delete(d.id) : s.add(d.id)
  chosen.value = s
}
async function confirmChosen() {
  error.value = ''; notice.value = ''
  try {
    const r = await api('/api/docs/confirm-batch', { method: 'POST', body: { ids: [...chosen.value] } })
    notice.value = `Confirmed ${r.confirmed.length}.` + (r.left.length ? ` ${r.left.length} need a look one by one.` : '')
    await load()
  } catch (e) { error.value = e.message }
}
// search hits come back as text with << >> around the matches; shown as text, never as HTML
function marks(s) {
  const out = []
  let hit = false
  for (const part of s.split(/(<<|>>)/)) {
    if (part === '<<') hit = true
    else if (part === '>>') hit = false
    else if (part) out.push({ text: part, hit })
  }
  return out
}
function search() {
  if (f.value.q && f.value.status === 'library') f.value.status = 'all'      // search every file, also those to review
  tab.value === 'library' ? load() : (tab.value = 'library')
}
const cell = (p, t) => overview.value?.grid[p]?.[t] || 0
const rowTotal = (p) => Object.values(overview.value?.grid[p] || {}).reduce((a, b) => a + b, 0)
// problems (ADR-0014 item 4): the checks find them, people decide
const SEV_THEME = { high: 'red', medium: 'amber', info: 'gray' }
const SOURCE = { rule: 'your rule', learned: 'learned from your numbers', default: 'default (no numbers yet)' }
const canAct = (id) => ['to_review', 'to_classify', 'draft'].includes(problems.value?.docs[id]?.status)
async function act(path, id, body, message) {
  error.value = ''; notice.value = ''
  try { await api(`/api/docs/${id}/${path}`, { method: 'POST', body }); notice.value = message; await load() }
  catch (e) { error.value = e.message }
}
async function saveRule(t) {
  error.value = ''; notice.value = ''
  try {
    await api(`/api/docs/numbering/${t}`, { method: 'PUT', body: { template: rules.value[t].template, digits: Number(rules.value[t].digits) } })
    notice.value = 'Numbering rule saved.'; await load()
  } catch (e) { error.value = e.message }
}
async function clearRule(t) {
  try { await api(`/api/docs/numbering/${t}`, { method: 'DELETE' }); notice.value = 'Back to the convention learned from your numbers.'; await load() }
  catch (e) { error.value = e.message }
}
watch(issueProcess, () => tab.value === 'problems' && load())
const toProblems = (p) => { issueProcess.value = p || ''; tab.value = 'problems' }
const toLibrary = (p, t) => { f.value = { ...f.value, process: p || '', type: t || '', status: 'library', q: '' }; tab.value = 'library'; load() }
</script>

<template>
  <PageTop title="Documents">
    <form class="hidden items-center sm:flex" @submit.prevent="search">
      <input v-model="f.q" class="wq-input w-64" type="search" placeholder="Search titles, numbers and text" aria-label="Search documents">
    </form>
  </PageTop>

  <p v-if="meta && !meta.ai" class="mb-4 rounded-3 border border-outline-amber-2 bg-surface-amber-1 px-3 py-2 text-base text-ink-amber-8">
    No AI model is set up for this company, so files are classified by rules (file names, folders and labels such as
    “Doc No.”), with limited accuracy. Add the company's model key to use AI.</p>

  <section v-if="canEdit" class="drop mb-5 rounded-5 border-2 border-dashed p-5 transition-colors"
           :class="dragging ? 'border-outline-gray-5 bg-surface-gray-2' : 'border-outline-gray-2 bg-surface-gray-1'"
           @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="drop">
    <div class="flex flex-wrap items-center gap-3">
      <span class="lucide-upload size-5 text-ink-gray-5" />
      <p class="text-base text-ink-gray-8">Drop files, folders or zip files here</p>
      <label class="cursor-pointer text-base text-ink-gray-8 underline underline-offset-2">choose files
        <input type="file" multiple class="sr-only" accept=".pdf,.docx,.doc,.xlsx,.xlsm,.xls,.csv,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.gif,.webp,.zip" @change="choose"></label>
      <label class="cursor-pointer text-base text-ink-gray-8 underline underline-offset-2">choose a folder
        <input type="file" webkitdirectory multiple class="sr-only" @change="choose"></label>
      <span class="wq-muted">PDF, Word, Excel, CSV, text and scans; up to {{ meta?.max_mb }} MB a file. Folder names are kept.</span>
    </div>
    <div v-if="picked.length" class="mt-4 flex flex-wrap items-center gap-3">
      <span class="text-base font-medium text-ink-gray-9">{{ picked.length }} file{{ picked.length === 1 ? '' : 's' }}, {{ size(pickedSize) }}</span>
      <input v-model="uploadLabel" class="wq-input w-64" placeholder="Name this import (optional)">
      <Button variant="solid" icon-left="lucide-upload" :loading="busy" label="Upload" @click="upload" />
      <Button variant="ghost" label="Clear" @click="picked = []" />
      <span class="wq-muted">Nothing is sent to the AI until you choose to classify.</span>
    </div>
  </section>

  <nav class="tabs mb-5 flex gap-5 overflow-x-auto border-b border-outline-gray-2">
    <a v-for="(l, k) in TABS" :key="k" href="#" @click.prevent="tab = k"
       class="-mb-px whitespace-nowrap border-b-2 py-2.5 text-base transition-colors"
       :class="tab === k ? 'border-outline-gray-9 font-medium text-ink-gray-9' : 'border-transparent text-ink-gray-5 hover:text-ink-gray-8'">{{ l }}</a>
  </nav>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="notice" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ notice }}</p>

  <!-- overview -->
  <template v-if="tab === 'overview' && overview && meta">
    <section class="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <article v-for="(n, k) in { 'In the library': overview.totals.library, 'To review': overview.totals.to_review, 'Waiting for approval': overview.totals.in_review, 'Problems to look at': overview.issues.high + overview.issues.medium }"
               :key="k" class="rounded-5 border border-outline-gray-2 bg-surface-base p-4">
        <h3 class="text-sm font-medium text-ink-gray-5">{{ k }}</h3>
        <p class="mt-1 text-3xl font-semibold tracking-tight text-ink-gray-9">{{ n }}</p>
      </article>
    </section>
    <p v-if="overview.totals.to_review" class="mb-4 text-base text-ink-gray-7">
      {{ overview.totals.to_review }} file{{ overview.totals.to_review === 1 ? ' waits' : 's wait' }} for review.
      <a href="#" class="wq-link" @click.prevent="tab = 'review'">Review them</a></p>
    <p v-if="overview.issues.high + overview.issues.medium" class="mb-4 text-base text-ink-gray-7">
      The checks found {{ overview.issues.high + overview.issues.medium }} problem{{ overview.issues.high + overview.issues.medium === 1 ? '' : 's' }}
      (duplicates, revisions, numbers, missing forms). <a href="#" class="wq-link" @click.prevent="toProblems('')">See them</a></p>
    <h2 class="wq-h2">By process and type</h2>
    <p class="wq-muted mb-3">Documents in the library (confirmed, drafts, waiting for approval, effective). Click a number to see them.</p>
    <div class="wq-panel overflow-x-auto">
      <table class="wq-table">
        <thead><tr><th>Process</th><th v-for="(n, t) in meta.types" :key="t" class="text-right">{{ n }}</th><th class="text-right">All</th><th class="text-right">Problems</th></tr></thead>
        <tbody><tr v-for="(pn, p) in overview.processes" :key="p">
          <td class="whitespace-nowrap">{{ pn }}
            <Badge v-if="overview.empty_processes.includes(p)" theme="amber" label="none yet" class="ms-2" /></td>
          <td v-for="(n, t) in meta.types" :key="t" class="text-right">
            <a v-if="cell(p, t)" href="#" class="wq-link" @click.prevent="toLibrary(p, t)">{{ cell(p, t) }}</a>
            <span v-else class="text-ink-gray-4">·</span></td>
          <td class="text-right font-medium"><a v-if="rowTotal(p)" href="#" class="wq-link" @click.prevent="toLibrary(p, '')">{{ rowTotal(p) }}</a>
            <span v-else class="text-ink-gray-4">0</span></td>
          <td class="text-right"><a v-if="overview.issues_by_process[p]" href="#" class="font-medium text-ink-red-7 underline underline-offset-2"
                                    @click.prevent="toProblems(p)">{{ overview.issues_by_process[p] }}</a><span v-else class="text-ink-gray-4">·</span></td>
        </tr></tbody>
      </table>
    </div>
  </template>

  <!-- problems -->
  <template v-if="tab === 'problems' && problems && meta">
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <select v-model="issueProcess" class="wq-select" aria-label="Process"><option value="">Every process</option>
        <option v-for="(n, p) in meta.processes" :key="p" :value="p">{{ n }}</option></select>
      <span class="wq-muted">Found by fixed checks of the library; you decide what to do. Nothing changes by itself.</span>
    </div>
    <p v-if="!problems.issues.length" class="wq-muted">No problems found.</p>
    <article v-for="(i, n) in problems.issues" :key="n" class="issue wq-panel mb-3 p-4">
      <div class="flex flex-wrap items-center gap-2">
        <Badge :theme="SEV_THEME[i.severity]" :label="i.severity === 'info' ? 'note' : i.severity" />
        <h3 class="text-base font-medium text-ink-gray-9">{{ i.title }}</h3>
        <span v-if="i.process" class="ms-auto text-sm text-ink-gray-5">{{ meta.processes[i.process] }}</span>
      </div>
      <p class="mt-1.5 text-base text-ink-gray-7">{{ i.detail }}</p>
      <ul v-if="i.docs.length" class="mt-2 divide-y divide-outline-gray-1 text-sm">
        <li v-for="id in i.docs" :key="id" class="flex flex-wrap items-center gap-2 py-1.5">
          <RouterLink :to="`/documents/${id}`" class="wq-link">{{ problems.docs[id].label }}</RouterLink>
          <span class="text-ink-gray-5">{{ problems.docs[id].path }}/{{ problems.docs[id].file }}</span>
          <Badge :theme="STATUS[problems.docs[id].status] || 'gray'" :label="DOC_STATE[problems.docs[id].status] || label(problems.docs[id].status)" />
          <Badge v-if="i.keep === id" theme="green" variant="outline" :label="i.kind === 'revisions' ? 'current' : 'keep this one'" />
          <template v-if="canEdit && canAct(id) && i.keep && i.keep !== id">
            <span class="ms-auto" />
            <Button v-if="i.kind === 'revisions'" size="sm" label="Keep as obsolete"
                    @click="act('archive', id, { reason: `older revision; current is ${problems.docs[i.keep].label}` }, 'Kept as obsolete.')" />
            <Button v-if="i.kind === 'duplicate' && problems.docs[id].status !== 'draft'" size="sm" label="Not keep this copy"
                    @click="act('reject', id, { reason: `same file as ${problems.docs[i.keep].path}/${problems.docs[i.keep].file}` }, 'Copy not kept.')" />
          </template>
          <span v-if="i.suggest && i.docs.length === 1" class="ms-auto text-ink-gray-6">suggested number <b class="text-ink-gray-9">{{ i.suggest }}</b>
            (open it to use)</span>
        </li>
      </ul>
    </article>

    <h2 class="wq-h2 mt-8">Numbering</h2>
    <p class="wq-muted mb-3 max-w-3xl">How suggested numbers are made. Without a rule of your own, the convention is learned from the numbers
      your documents already have. Write a rule as a prefix and <code>{seq}</code>, optionally with <code>{process}</code> for the process code
      (for example <code>F-{process}-{seq}</code> with 3 digits gives F-QA-013). Original file names are never changed.</p>
    <div class="wq-panel overflow-x-auto">
      <table class="wq-table">
        <thead><tr><th>Type</th><th>Convention</th><th>From</th><th v-if="canEdit">Your rule</th></tr></thead>
        <tbody><tr v-for="(c, t) in problems.conventions" :key="t">
          <td class="whitespace-nowrap">{{ meta.types[t] }}</td>
          <td class="whitespace-nowrap font-mono text-sm">{{ c.template }} · {{ c.digits }} digits
            <div v-if="c.examples" class="font-sans text-ink-gray-5">e.g. {{ c.examples.join(', ') }}</div></td>
          <td class="text-sm text-ink-gray-6">{{ SOURCE[c.source] }}</td>
          <td v-if="canEdit"><form class="flex items-center gap-2" @submit.prevent="saveRule(t)">
            <input v-model="rules[t].template" class="wq-input w-44 font-mono" aria-label="Rule">
            <input v-model="rules[t].digits" class="wq-input w-16" type="number" min="1" max="6" aria-label="Digits">
            <Button type="submit" size="sm" label="Save" />
            <Button v-if="c.source === 'rule'" size="sm" variant="ghost" label="Use learned" @click="clearRule(t)" />
          </form></td>
        </tr></tbody>
      </table>
    </div>
    <p class="wq-muted mt-2">Process codes in numbers: <span v-for="(code, p) in problems.codes" :key="p" class="me-3 whitespace-nowrap">{{ meta.processes[p] }} {{ code }}</span></p>
  </template>

  <!-- review queue -->
  <template v-if="tab === 'review'">
    <p class="wq-muted mb-3 max-w-3xl">Each proposal shows where it came from (AI or rules) and how sure it is. Every field quotes the
      file; quotes the system could not find in the file are marked. High-confidence proposals with every quote found can be
      confirmed together; open the others to check and correct them. Your corrections teach the next classification.</p>
    <div v-if="canEdit && rows.length" class="mb-3 flex flex-wrap items-center gap-2">
      <Button :disabled="!batchable.length" :label="`Select the ${batchable.length} high-confidence`" @click="chosen = new Set(batchable.map((d) => d.id))" />
      <Button variant="solid" :disabled="!chosen.size" icon-left="lucide-check" :label="`Confirm ${chosen.size} selected`" @click="confirmChosen" />
    </div>
    <p v-if="!rows.length" class="wq-muted">Nothing to review.</p>
    <div v-else class="wq-panel overflow-x-auto">
      <table class="wq-table">
        <thead><tr><th v-if="canEdit"></th><th>File</th><th>Type</th><th>Process</th><th>Number</th><th>Title</th><th>Proposal</th></tr></thead>
        <tbody><tr v-for="d in rows" :key="d.id">
          <td v-if="canEdit"><input type="checkbox" class="form-checkbox" :disabled="!d.batch_ok" :checked="chosen.has(d.id)"
                                    :title="d.batch_ok ? 'Can be confirmed with others' : 'Open it to check'" @change="toggle(d)"></td>
          <td><RouterLink :to="`/documents/${d.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ d.original_name }}</RouterLink>
            <div class="text-sm text-ink-gray-5">{{ d.path }}</div>
            <Badge v-if="d.duplicate_of" theme="gray" label="same file as another" class="mt-1" /></td>
          <td class="whitespace-nowrap">{{ typeName(d.doc_type) }}</td>
          <td class="whitespace-nowrap">{{ procName(d.process) }}</td>
          <td class="whitespace-nowrap">{{ d.number || '—' }}<span v-if="d.revision" class="text-ink-gray-5"> rev {{ d.revision }}</span></td>
          <td>{{ d.title }}</td>
          <td class="whitespace-nowrap"><Badge :theme="CONF[d.confidence] || 'gray'" :label="`${d.confidence || 'low'} · ${how(d)}`" />
            <div v-if="unverified(d)" class="mt-1 text-sm text-ink-amber-7">{{ unverified(d) }} not found in the file</div></td>
        </tr></tbody>
      </table>
    </div>
  </template>

  <!-- library -->
  <template v-if="tab === 'library' && meta">
    <form class="mb-3 flex flex-wrap items-center gap-2" @submit.prevent="load">
      <input v-model="f.q" class="wq-input w-64 sm:hidden" type="search" placeholder="Search">
      <select v-model="f.status" class="wq-select" aria-label="Status">
        <option value="library">In the library</option><option value="effective">Effective</option><option value="confirmed">Kept records</option>
        <option value="in_review">Waiting for approval</option><option value="draft">Drafts</option><option value="obsolete">Obsolete</option>
        <option value="all">All files</option></select>
      <select v-model="f.process" class="wq-select" aria-label="Process"><option value="">Every process</option>
        <option v-for="(n, p) in meta.processes" :key="p" :value="p">{{ n }}</option></select>
      <select v-model="f.type" class="wq-select" aria-label="Type"><option value="">Every type</option>
        <option v-for="(n, t) in meta.types" :key="t" :value="t">{{ n }}</option></select>
      <Button v-if="f.q" variant="ghost" :label="`Clear “${f.q}”`" @click="f.q = ''; load()" />
    </form>
    <p v-if="!rows.length" class="wq-muted">No documents.</p>
    <div v-else class="wq-panel overflow-x-auto">
      <table class="wq-table">
        <thead><tr><th>Number</th><th>Title</th><th>Rev</th><th>Type</th><th>Process</th><th>Status</th><th>Effective</th></tr></thead>
        <tbody><tr v-for="d in rows" :key="d.id">
          <td class="whitespace-nowrap">{{ d.number || '—' }}</td>
          <td><RouterLink :to="`/documents/${d.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ d.title || d.original_name }}</RouterLink>
            <div v-if="d.snippet" class="snippet mt-0.5 text-sm text-ink-gray-5">…<template v-for="(p, n) in marks(d.snippet)" :key="n"><mark v-if="p.hit">{{ p.text }}</mark><template v-else>{{ p.text }}</template></template>…</div></td>
          <td>{{ d.revision || '—' }}</td>
          <td class="whitespace-nowrap">{{ typeName(d.doc_type) }}</td>
          <td class="whitespace-nowrap">{{ procName(d.process) }}</td>
          <td><Badge :theme="STATUS[d.status] || 'gray'" :label="DOC_STATE[d.status] || label(d.status)" /></td>
          <td class="whitespace-nowrap text-sm text-ink-gray-6">{{ d.effective_date || '—' }}</td>
        </tr></tbody>
      </table>
    </div>
  </template>

  <!-- imports -->
  <template v-if="tab === 'imports'">
    <p v-if="!imports.length" class="wq-muted">No imports yet.</p>
    <article v-for="i in imports" :key="i.id" class="wq-panel mb-4 p-4">
      <div class="flex flex-wrap items-center gap-2">
        <h3 class="text-base font-semibold text-ink-gray-9">{{ i.label || `Import ${i.id}` }}</h3>
        <Badge :theme="STATUS[i.status] || 'gray'" :label="i.status === 'extracting' ? 'reading text' : i.status === 'ready' ? 'ready to classify' : label(i.status)" />
        <Badge v-if="i.engine" :label="i.engine === 'ai' ? 'AI' : i.engine" variant="outline" />
        <span class="ms-auto text-sm text-ink-gray-5">{{ i.created_by }} · {{ ago(i.created_at) }}</span>
      </div>
      <p class="mt-2 text-base text-ink-gray-7">{{ i.files }} file{{ i.files === 1 ? '' : 's' }}<span v-if="i.duplicates">, {{ i.duplicates }} identical to another file</span><span v-if="i.text.ocr">, {{ i.text.ocr }} read by OCR</span><span v-if="i.text.no_text">, {{ i.text.no_text }} without text</span><span v-if="i.text.error">, {{ i.text.error }} could not be read</span>.
        <template v-for="(n, s) in i.counts" :key="s"><Badge :theme="STATUS[s] || 'gray'" :label="`${n} ${DOC_STATE[s] || label(s)}`" class="ms-1" /></template></p>
      <p v-if="i.error" class="wq-error mt-2">{{ i.error }}</p>
      <details v-if="i.skipped.length" class="mt-2 text-sm text-ink-gray-6"><summary class="cursor-pointer">{{ i.skipped.length }} not taken</summary>
        <ul class="mt-1 list-disc ps-5"><li v-for="s in i.skipped" :key="s.name">{{ s.name }}: {{ s.reason }}</li></ul></details>
      <div v-if="canEdit && i.status !== 'extracting' && i.status !== 'classifying' && i.counts.to_classify" class="mt-3 flex flex-wrap items-center gap-2">
        <Button v-if="meta?.ai" variant="solid" icon-left="lucide-sparkles" label="Classify with AI" @click="classify(i, 'ai')" />
        <Button :variant="meta?.ai ? 'subtle' : 'solid'" label="Classify with rules" @click="classify(i, 'rules')" />
        <span v-if="meta?.ai" class="wq-muted">The AI reads {{ i.estimate.files }} file{{ i.estimate.files === 1 ? '' : 's' }}, about {{ fmt(i.estimate.tokens) }} tokens with the company's key ({{ meta.model }}).</span>
        <span v-else class="wq-muted">Rules classify with limited accuracy; every proposal still waits for a person.</span>
      </div>
      <p v-if="i.status === 'done' && i.counts.to_review" class="mt-3 text-base">
        <a href="#" class="wq-link" @click.prevent="tab = 'review'">Review {{ i.counts.to_review }} proposal{{ i.counts.to_review === 1 ? '' : 's' }}</a></p>
    </article>
  </template>
</template>

<style scoped>
.snippet mark { background: var(--surface-amber-2, #fff3d6); color: inherit; border-radius: 2px; padding: 0 1px; }
</style>
