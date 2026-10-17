<script setup>
// A fishbone or a 5 Why (ADR-0022, 22b). People add causes citing records; the AI may suggest some, each citing the
// records it was shown, and a person accepts, edits or removes every one. Each why is confirmed before the next. The
// conclusion is signed and added to the record's root cause; then only addenda are added.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import { api } from '../api'
import { ago } from '../format'

const route = useRoute()
const p = ref(null)
const error = ref('')
const done = ref('')
const busy = ref(false)
const ai = ref(null)
const ctx = ref(null)
const editing = ref(null)
const editText = ref('')
const form = ref({ category: '', text: '', refs: '' })
const end = ref({ conclusion: '', password: '' })
const extra = ref('')
const cancelWhy = ref('')
const METHODS = { fishbone: 'Fishbone', five_why: '5 Why' }
const KINDS = { ncr: 'Nonconformance', capa: 'Corrective action', complaint: 'Complaint' }
const THEME = { open: 'blue', concluded: 'green', cancelled: 'gray' }

const a = computed(() => p.value?.analysis)
const open = computed(() => a.value?.status === 'open')
const edit = computed(() => p.value?.can_edit && open.value)
const live = computed(() => (p.value?.items || []).filter((i) => i.status !== 'removed'))
const removed = computed(() => (p.value?.items || []).filter((i) => i.status === 'removed'))
const proposed = computed(() => live.value.filter((i) => i.status === 'proposed').length)
const half = computed(() => Math.ceil((a.value?.categories.length || 0) / 2))
const bones = computed(() => (a.value?.categories || []).map((c, k) => ({ c, top: k < half.value, items: live.value.filter((i) => i.category === c) })))
const levels = computed(() => {
  if (a.value?.method !== 'five_why') return []
  const top = Math.max(open.value ? p.value.next_level || 1 : 1, ...live.value.map((i) => i.level))
  return Array.from({ length: top }, (_, k) => ({ level: k + 1, items: live.value.filter((i) => i.level === k + 1) }))
})
const deepest = computed(() => {
  const acc = live.value.filter((i) => i.status === 'accepted' && i.level).sort((x, y) => y.level - x.level)
  return acc[0]?.text || ''
})

function set(v) {
  p.value = v
  if (!form.value.category && v.analysis.categories.length) form.value.category = v.analysis.categories[0]
}
async function load() {
  try { set(await api(`/api/quality/causes/${route.params.id}`)); error.value = '' } catch (e) { error.value = e.message }
}
watch(() => route.params.id, () => { ai.value = null; ctx.value = null; load() }, { immediate: true })

async function post(path, body, msg = '') {
  error.value = ''; done.value = ''; busy.value = true
  try { const out = await api(`/api/quality/causes/${a.value.id}/${path}`, { method: 'POST', body }); set(out); done.value = msg; return out }
  catch (e) { error.value = e.message } finally { busy.value = false }
}
const refList = (s) => s.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean)
async function add() {
  const body = { text: form.value.text, refs: refList(form.value.refs) }
  if (a.value.method === 'fishbone') body.category = form.value.category
  else body.level = p.value.next_level
  if (await post('items', body, 'Cause added.')) form.value = { ...form.value, text: '', refs: '' }
}
const decide = (i, action, text) => post(`items/${i.id}`, { action, text }, '').then(() => { editing.value = null })
function startEdit(i) { editing.value = i.id; editText.value = i.text }
async function suggest() {
  const out = await post('suggest', undefined, '')
  if (out) ai.value = out.suggested
}
async function showContext(ev) {
  if (ev.target.open && !ctx.value) {
    try { ctx.value = await api(`/api/quality/causes/${a.value.id}/context`) } catch (e) { error.value = e.message }
  }
}
async function conclude() {
  if (await post('conclude', { ...end.value }, 'Concluded and signed. The root cause of the record now includes it.')) end.value = { conclusion: '', password: '' }
}
async function addendum() { if (await post('addenda', { text: extra.value }, 'Addendum added.')) extra.value = '' }
async function cancel() { if (await post('cancel', { reason: cancelWhy.value }, 'Cancelled.')) cancelWhy.value = '' }
// the deepest accepted answer is the usual root cause of a 5 Why: offered until the person writes their own
watch(deepest, (d, before) => {
  if (a.value?.method === 'five_why' && (!end.value.conclusion || end.value.conclusion === before)) end.value.conclusion = d
})
const recordLink = computed(() => p.value?.links[a.value.ref_name])
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality tools', to: '/quality/tools?tab=causes' }]">
    <template #title>{{ a ? `${a.name} · ${METHODS[a.method]}` : 'Cause analysis' }}</template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="a">
    <div class="mb-5 flex flex-wrap items-center gap-x-3 gap-y-1 text-base">
      <Badge :theme="THEME[a.status]" :label="a.status" />
      <span class="text-ink-gray-6">{{ KINDS[a.ref_kind] }}</span>
      <RouterLink v-if="recordLink" :to="recordLink" class="wq-link font-medium">{{ a.ref_name }}</RouterLink><span v-else>{{ a.ref_name }}</span>
      <span class="text-ink-gray-5">started by {{ a.created_by }} {{ ago(a.created_at) }}</span>
    </div>

    <!-- Fishbone: bones above and below the spine, the problem at the head -->
    <section v-if="a.method === 'fishbone'" data-help="cause-diagram" class="fish" :style="{ '--cols': half }">
      <div v-for="b in bones" :key="b.c" class="bone" :class="b.top ? 'top' : 'bottom'">
        <h3 class="bone-name">{{ b.c }}</h3>
        <ul class="causes">
          <li v-for="i in b.items" :key="i.id" class="cause" :class="i.status">
            <template v-if="editing === i.id">
              <textarea v-model="editText" rows="2" class="wq-input w-full" />
              <div class="mt-1 flex gap-1"><Button size="sm" variant="solid" label="Save" :disabled="!editText.trim()" @click="decide(i, 'edit', editText)" /><Button size="sm" label="Back" @click="editing = null" /></div>
            </template>
            <template v-else>
              <p>{{ i.text }}</p>
              <p class="meta">
                <span v-if="i.origin === 'ai'" class="tag ai" :title="i.status === 'proposed' ? 'Suggested by AI; not yet checked' : 'Suggested by AI, checked by ' + i.decided_by">AI</span>
                <span v-if="i.edited" class="tag">edited</span>
                <template v-for="r in i.refs" :key="r"><RouterLink v-if="p.links[r]" :to="p.links[r]" class="ref">{{ r }}</RouterLink><span v-else class="ref">{{ r }}</span></template>
              </p>
              <div v-if="edit" class="acts">
                <Button v-if="i.status === 'proposed'" size="sm" variant="solid" label="Accept" @click="decide(i, 'accept')" />
                <Button size="sm" label="Edit" @click="startEdit(i)" />
                <Button size="sm" label="Remove" @click="decide(i, 'remove')" />
              </div>
            </template>
          </li>
          <li v-if="!b.items.length" class="empty">No cause yet</li>
        </ul>
      </div>
      <div class="spine" aria-hidden="true" />
      <div class="head"><span class="text-sm text-ink-gray-5">Problem</span><p>{{ a.problem }}</p></div>
    </section>

    <!-- 5 Why: one confirmed answer per level, each resting on the one above -->
    <section v-else data-help="cause-whys" class="whys">
      <div class="why-problem"><span class="text-sm text-ink-gray-5">Problem</span><p>{{ a.problem }}</p></div>
      <div v-for="l in levels" :key="l.level" class="why">
        <h3>Why {{ l.level }}?</h3>
        <ul class="flex flex-col gap-2">
          <li v-for="i in l.items" :key="i.id" class="cause" :class="i.status">
            <template v-if="editing === i.id">
              <textarea v-model="editText" rows="2" class="wq-input w-full" />
              <div class="mt-1 flex gap-1"><Button size="sm" variant="solid" label="Save" :disabled="!editText.trim()" @click="decide(i, 'edit', editText)" /><Button size="sm" label="Back" @click="editing = null" /></div>
            </template>
            <template v-else>
              <p>{{ i.text }}</p>
              <p class="meta">
                <span v-if="i.origin === 'ai'" class="tag ai">AI</span><span v-if="i.edited" class="tag">edited</span>
                <template v-for="r in i.refs" :key="r"><RouterLink v-if="p.links[r]" :to="p.links[r]" class="ref">{{ r }}</RouterLink><span v-else class="ref">{{ r }}</span></template>
              </p>
              <div v-if="edit" class="acts">
                <Button v-if="i.status === 'proposed'" size="sm" variant="solid" label="Accept" @click="decide(i, 'accept')" />
                <Button size="sm" label="Edit" @click="startEdit(i)" />
                <Button size="sm" label="Remove" @click="decide(i, 'remove')" />
              </div>
            </template>
          </li>
          <li v-if="!l.items.length" class="empty">{{ l.level === p.next_level ? 'Answer this why, or ask the AI for suggestions.' : '' }}</li>
        </ul>
      </div>
    </section>

    <div class="mt-6 grid gap-5 lg:grid-cols-2">
      <section v-if="edit" data-help="cause-add" class="wq-panel p-5">
        <h3 class="mb-3 text-base font-semibold text-ink-gray-9">{{ a.method === 'fishbone' ? 'Add a cause' : `Answer why ${p.next_level}` }}</h3>
        <form class="grid gap-3" @submit.prevent="add">
          <label v-if="a.method === 'fishbone'" class="wq-field">Category<select v-model="form.category" class="wq-select"><option v-for="c in a.categories" :key="c">{{ c }}</option></select></label>
          <label class="wq-field">{{ a.method === 'fishbone' ? 'Cause' : 'Because…' }}<textarea v-model="form.text" rows="2" class="wq-input" maxlength="500" /></label>
          <label class="wq-field">Records it rests on (numbers, optional)<input v-model="form.refs" class="wq-input" placeholder="NCR-00002, IQC-00004"></label>
          <div><Button type="submit" icon-left="lucide-plus" label="Add" :disabled="!form.text.trim() || busy" /></div>
        </form>
      </section>

      <section v-if="open" data-help="cause-suggest" class="wq-panel p-5">
        <h3 class="mb-2 text-base font-semibold text-ink-gray-9">Suggestions from the AI</h3>
        <p class="mb-3 text-sm text-ink-gray-6">The AI reads this record and related ones, and must cite them. Suggestions that cite no record it was shown are dropped. You decide each one.</p>
        <Button v-if="p.can_ask && edit" icon-left="lucide-sparkles" :label="a.method === 'fishbone' ? 'Suggest causes' : `Suggest answers to why ${p.next_level}`"
                :loading="busy" :disabled="busy || proposed > 0" @click="suggest" />
        <p v-if="proposed" class="mt-2 text-sm text-ink-amber-7">{{ proposed }} suggestion{{ proposed > 1 ? 's' : '' }} to accept, edit or remove.</p>
        <p v-else-if="!p.can_ask" class="wq-muted">Suggestions need a model key and a role that may use the AI. You can add causes yourself.</p>
        <div v-if="ai" class="mt-3 text-sm">
          <p>{{ ai.kept }} kept from {{ ai.shown }} records shown<span v-if="ai.dropped.length || ai.unusable">; {{ ai.dropped.length + ai.unusable }} dropped</span>.</p>
          <ul v-if="ai.dropped.length" class="mt-1 list-disc ps-5 text-ink-gray-6"><li v-for="(d, k) in ai.dropped" :key="k">“{{ d.text }}”: {{ d.reason }}<span v-if="d.refs.length"> ({{ d.refs.join(', ') }})</span></li></ul>
          <p v-if="ai.note" class="mt-1 text-ink-gray-6">AI note: {{ ai.note }}</p>
        </div>
        <details data-help="cause-records" class="mt-3 text-sm" @toggle="showContext">
          <summary class="cursor-pointer text-ink-gray-7">Records the AI reads</summary>
          <p v-if="!ctx" class="wq-muted mt-2">Loading…</p>
          <ul v-else class="mt-2 flex flex-col gap-1.5">
            <li v-for="r in ctx.records" :key="r.ref"><RouterLink v-if="ctx.links[r.ref]" :to="ctx.links[r.ref]" class="ref">{{ r.ref }}</RouterLink><span v-else class="ref">{{ r.ref }}</span>
              <span class="text-ink-gray-5"> {{ r.kind }}:</span> {{ r.summary }}</li>
          </ul>
        </details>
      </section>

      <section v-if="edit" data-help="cause-conclude" class="wq-panel p-5 lg:col-span-2">
        <h3 class="mb-2 text-base font-semibold text-ink-gray-9">Conclude</h3>
        <p class="mb-3 text-sm text-ink-gray-6">The conclusion is signed and added to the root cause of {{ a.ref_name }}{{ a.ref_kind === 'ncr' ? ' (8D, D4)' : '' }}. The analysis is then kept as it is; later findings go in addenda.</p>
        <ul v-if="p.to_conclude.length" class="mb-3 list-disc ps-5 text-sm text-ink-amber-7"><li v-for="t in p.to_conclude" :key="t">{{ t }}</li></ul>
        <form class="grid gap-3" @submit.prevent="conclude">
          <label class="wq-field">Root cause<textarea v-model="end.conclusion" rows="2" class="wq-input" maxlength="2000" /></label>
          <div class="flex flex-wrap items-end gap-2"><label class="wq-field">Your password (signs it)<input v-model="end.password" type="password" class="wq-input" autocomplete="current-password"></label>
            <Button type="submit" variant="solid" label="Conclude and sign" :disabled="busy || !!p.to_conclude.length || !end.conclusion.trim() || !end.password" /></div>
        </form>
      </section>
    </div>

    <section v-if="a.status === 'concluded'" class="wq-panel mt-5 p-5">
      <h3 class="mb-2 text-base font-semibold text-ink-gray-9">Root cause</h3>
      <p class="text-base text-ink-gray-9">{{ a.conclusion }}</p>
      <p class="mt-1 text-sm text-ink-gray-5">Signed by {{ a.concluded_by }} {{ ago(a.concluded_at) }}; written to the {{ a.written_to }}.</p>
      <h3 class="mb-2 mt-5 text-base font-semibold text-ink-gray-9">Addenda</h3>
      <p v-if="!p.addenda.length" class="wq-muted">None.</p>
      <ul class="flex flex-col gap-1 text-base"><li v-for="x in p.addenda" :key="x.id">{{ x.text }} <span class="text-sm text-ink-gray-5">· {{ x.email }} {{ ago(x.at) }}</span></li></ul>
      <form v-if="p.can_edit" class="mt-3 flex flex-wrap gap-2" @submit.prevent="addendum"><input v-model="extra" class="wq-input min-w-0 flex-1" placeholder="A later finding" maxlength="2000"><Button type="submit" label="Add" :disabled="!extra.trim() || busy" /></form>
    </section>
    <p v-if="a.status === 'cancelled'" class="wq-panel mt-5 p-5 text-base">Cancelled: {{ a.cancel_reason }}</p>

    <details v-if="removed.length" class="mt-5 text-sm"><summary class="cursor-pointer text-ink-gray-7">Removed ({{ removed.length }})</summary>
      <ul class="mt-2 flex flex-col gap-1"><li v-for="i in removed" :key="i.id" class="text-ink-gray-6"><s>{{ i.text }}</s> · {{ i.origin === 'ai' ? 'AI suggestion' : i.created_by }}, removed by {{ i.decided_by }}</li></ul></details>
    <details v-if="edit" class="mt-3 text-sm"><summary class="cursor-pointer text-ink-gray-7">Cancel this analysis</summary>
      <div class="mt-2 flex gap-2"><input v-model="cancelWhy" class="wq-input w-96" placeholder="Why"><Button label="Cancel the analysis" :disabled="!cancelWhy.trim()" @click="cancel" /></div></details>

    <h2 class="wq-h2 mt-8">Signatures</h2>
    <Trail :items="p.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-8">History</h2>
    <Trail :items="p.history" />
  </template>
</template>

<style scoped>
.fish { display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)) 13rem; grid-template-rows: auto 1.5rem auto; column-gap: .75rem; }
.bone { position: relative; padding: .25rem .5rem .25rem 1.5rem; min-height: 9rem; display: flex; flex-direction: column; }
.bone.top { grid-row: 1; justify-content: flex-start; }
.bone.bottom { grid-row: 3; flex-direction: column-reverse; justify-content: flex-start; }
.bone::before { content: ''; position: absolute; inset: 0; pointer-events: none; }
.bone.top::before { background: linear-gradient(to top right, transparent calc(50% - 1px), var(--line) calc(50% - 1px), var(--line) calc(50% + 1px), transparent calc(50% + 1px)); }
.bone.bottom::before { background: linear-gradient(to bottom right, transparent calc(50% - 1px), var(--line) calc(50% - 1px), var(--line) calc(50% + 1px), transparent calc(50% + 1px)); }
.bone-name { position: relative; font-weight: 600; color: var(--ink-gray-9); font-size: .95rem; margin: .25rem 0; }
.causes { position: relative; display: flex; flex-direction: column; gap: .4rem; }
.spine { grid-row: 2; grid-column: 1 / span var(--cols); align-self: center; height: 3px; background: var(--ink-gray-7); position: relative; }
.spine::after { content: ''; position: absolute; right: -2px; top: -6px; border-left: 10px solid var(--ink-gray-7); border-top: 7.5px solid transparent; border-bottom: 7.5px solid transparent; }
.head { grid-column: calc(var(--cols) + 1); grid-row: 1 / span 3; align-self: center; border: 2px solid var(--ink-gray-7); border-radius: 10px; padding: .6rem .75rem; background: var(--panel); }
.head p, .why-problem p { color: var(--ink-gray-9); font-weight: 500; }
.cause { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: .45rem .6rem; font-size: .9rem; color: var(--ink-gray-9); }
.cause.proposed { border-style: dashed; border-color: var(--warn); background: var(--surface-amber-1, var(--panel)); }
.meta { display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .25rem; }
.tag { font-size: .72rem; border-radius: 4px; padding: 0 .3rem; background: var(--surface-gray-2); color: var(--ink-gray-6); }
.tag.ai { background: var(--surface-amber-2, var(--surface-gray-2)); color: var(--warn); font-weight: 600; }
.ref { font-size: .75rem; border: 1px solid var(--line); border-radius: 4px; padding: 0 .3rem; color: var(--accent); white-space: nowrap; }
.acts { display: flex; gap: .25rem; margin-top: .35rem; }
.empty { position: relative; font-size: .85rem; color: var(--muted); }
.whys { display: flex; flex-direction: column; gap: 0; max-width: 46rem; }
.why-problem { border: 2px solid var(--ink-gray-7); border-radius: 10px; padding: .6rem .75rem; }
.why { border-left: 3px solid var(--line); margin-left: 1.25rem; padding: .75rem 0 .5rem 1.25rem; }
.why h3 { font-weight: 600; color: var(--ink-gray-8); margin-bottom: .4rem; }
.why .cause.accepted { border-color: var(--ink-gray-7); }
@media (max-width: 900px) {
  .fish { grid-template-columns: 1fr; grid-template-rows: none; }
  .bone, .bone.top, .bone.bottom { grid-row: auto; flex-direction: column; min-height: 0; padding-left: .5rem; border-left: 3px solid var(--line); }
  .bone::before, .spine { display: none; }
  .head { grid-column: 1; grid-row: 1; }
}
</style>
