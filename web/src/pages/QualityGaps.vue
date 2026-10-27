<script setup>
// The gap report (ADR-0016, 16c): every control point not met or unknown, with its to-do. The check closes a to-do
// once the point is met. A missing document can be drafted by the AI into the library for review.
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, objectPath } from '../api'
import { ago } from '../format'
import { standard } from '../standard'
import { t } from '../i18n'

const router = useRouter()
const g = ref(null)
const error = ref('')
const print = () => window.print()
const done = ref('')
const busy = ref('')
const form = ref({})
const showClosed = ref(false)
const S = { not_met: { theme: 'red', label: 'not met' }, unknown: { theme: 'gray', label: 'unknown' } }

async function load() {
  try { g.value = await api(`/api/qms/${standard.value}/gaps`) } catch (e) { error.value = e.message }
}
load()
async function call(path, method, body, message, key = 'x') {
  error.value = ''; done.value = ''; busy.value = key
  try { g.value = await api(path, { method, body }); done.value = message; form.value = {} } catch (e) { error.value = e.message } finally { busy.value = '' }
}
const f = (id) => (form.value[id] ||= { owner: '', due: '', note: '' })
const addTodo = (gap) => call(`/api/qms/${standard.value}/todos`, 'POST', { control: gap.id, owner: f(gap.id).owner, due: f(gap.id).due }, t('To-do added.'), gap.id)
const addAll = () => call(`/api/qms/${standard.value}/todos/all`, 'POST', {}, t('A to-do for every gap.'))
const setTodo = (t, body, message) => call(`/api/qms-todos/${t.id}`, 'PUT', body, message, `t${t.id}`)
async function draft(gap) {
  error.value = ''; done.value = ''; busy.value = `d${gap.id}`
  try {
    const d = await api(`/api/qms/${standard.value}/controls/${gap.id}/draft`, { method: 'POST' })
    router.push(`/documents/${d.document_id}`)
  } catch (e) { error.value = e.message } finally { busy.value = '' }
}
const closed = computed(() => (g.value?.todos || []).filter((t) => t.status !== 'open'))
function to(p, gap) {
  if (p.kind === 'ncr') return `/quality/ncr/${p.id}`
  if (p.kind === 'capa') return `/quality/capa/${p.id}`
  if (p.kind === 'document') return `/documents/${p.id}`
  if (p.kind === 'inspection') return objectPath('QualityInspection', p.id)
  if (p.kind === 'supplier') return objectPath('Supplier', p.id)
  if (p.kind === 'asl') return `/quality/suppliers#a${p.id}`
  if (p.kind === 'reading') return '/documents/control'
  if (p.kind === 'entry' && String(p.id).startsWith('c')) return `/quality/complaints/${String(p.id).slice(1)}`
  if (p.kind === 'entry' && String(p.id).startsWith('g')) return `/quality/gauges/${String(p.id).slice(1)}`
  if (p.kind === 'entry') return `/system/registers/${gap.register}#e${p.id}`
  return null
}
</script>

<template>
  <PageTop :crumbs="[{ label: t('Quality system'), to: '/system' }]">
    <template #title>{{ t('Gap report') }}{{ g ? ` · ${g.name}` : '' }}</template>
    <Button v-if="g?.can_edit" data-help="gaps-todo-all" icon-left="lucide-list-plus" :label="t('A to-do for every gap')" @click="addAll" />
    <Button icon-left="lucide-printer" :label="t('Print')" @click="print" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <template v-if="g">
    <p data-help="gaps-summary" class="wq-muted mb-4 max-w-3xl">{{ t('{edition}, checked {when}: {met} not met, {unknown} unknown, {todo} with a to-do.', { edition: g.edition_label, when: ago(g.evaluation?.at), met: g.counts.not_met, unknown: g.counts.unknown, todo: g.counts.with_todo }) }} {{ t('A to-do is closed by the check once its point is met.') }}</p>
    <p v-if="!g.processes.length" class="wq-panel p-5 text-base text-ink-green-7">{{ t('No gaps: every control point is met or does not apply.') }}</p>
    <section v-for="p in g.processes" :key="p.id" class="wq-panel mb-4 p-5">
      <h2 class="wq-h2">{{ p.label }}</h2>
      <article v-for="gap in p.gaps" :key="gap.id" class="gap border-t border-outline-gray-1 py-3 first:border-t-0">
        <div class="flex flex-wrap items-start gap-2">
          <Badge :theme="S[gap.status].theme" :label="t(S[gap.status].label)" class="mt-0.5" />
          <div class="min-w-0 flex-1">
            <p class="text-base text-ink-gray-9">{{ gap.summary }}</p>
            <p class="text-sm text-ink-gray-5">{{ g.name }} {{ gap.clauses.join(', ') }}</p>
            <p class="mt-1 text-sm text-ink-gray-7">{{ gap.detail }}</p>
            <ul v-if="gap.problems.length" class="mt-1 text-sm">
              <li v-for="x in gap.problems.slice(0, 5)" :key="`${x.kind}${x.id}${x.why}`">
                <RouterLink v-if="to(x, gap)" :to="to(x, gap)" class="wq-link">{{ x.label }}</RouterLink><span v-else>{{ x.label }}</span>
                <span class="text-ink-gray-6"> — {{ x.why }}</span></li>
              <li v-if="gap.problem_count > 5" class="text-ink-gray-5">{{ t('and {n} more', { n: gap.problem_count - 5 }) }}</li>
            </ul>
            <p class="mt-1 flex flex-wrap gap-3 text-sm">
              <RouterLink v-if="gap.register" :to="`/system/registers/${gap.register}`" class="wq-link">{{ t('Open the register') }}</RouterLink>
              <RouterLink v-if="['linked_document', 'scope_declared'].includes(gap.rule)" to="/system" class="wq-link">{{ t('Link a document') }}</RouterLink>
            </p>
          </div>
        </div>
        <div data-help="gaps-todo" class="mt-2 ms-0 rounded-4 bg-surface-gray-1 p-3 text-sm">
          <template v-if="gap.todo">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-medium text-ink-gray-8">{{ t('To-do:') }}</span><span>{{ gap.todo.title }}</span>
              <span class="text-ink-gray-5">{{ gap.todo.owner || t('no owner') }} · {{ gap.todo.due ? t('due {date}', { date: gap.todo.due }) : t('no due date') }}</span>
            </div>
            <div v-if="g.can_edit" class="mt-2 flex flex-wrap items-end gap-2">
              <input v-model="f(`t${gap.todo.id}`).owner" class="wq-input w-40" :placeholder="t('Owner')">
              <input v-model="f(`t${gap.todo.id}`).due" type="date" class="wq-input w-40">
              <Button size="sm" :label="t('Save')" @click="setTodo(gap.todo, { owner: f(`t${gap.todo.id}`).owner || gap.todo.owner || '', due: f(`t${gap.todo.id}`).due || gap.todo.due || '' }, t('To-do changed.'))" />
              <input v-model="f(`t${gap.todo.id}`).note" class="wq-input w-64" :placeholder="t('Note, or why it is dropped')">
              <Button size="sm" :label="t('Done')" @click="setTodo(gap.todo, { status: 'done', note: f(`t${gap.todo.id}`).note }, t('To-do done.'))" />
              <Button size="sm" :label="t('Drop')" @click="setTodo(gap.todo, { status: 'dropped', note: f(`t${gap.todo.id}`).note }, t('To-do dropped.'))" />
            </div>
          </template>
          <div v-else-if="g.can_edit" class="flex flex-wrap items-end gap-2">
            <input v-model="f(gap.id).owner" class="wq-input w-40" :placeholder="t('Owner')">
            <input v-model="f(gap.id).due" type="date" class="wq-input w-40">
            <Button size="sm" icon-left="lucide-plus" :label="t('Add a to-do')" :loading="busy === gap.id" @click="addTodo(gap)" />
          </div>
          <p v-else class="text-ink-gray-5">{{ t('No to-do yet.') }}</p>
          <div v-if="g.draftable.includes(gap.id)" class="mt-2 flex flex-wrap items-center gap-2">
            <Button size="sm" icon-left="lucide-sparkles" :label="t('Draft the document with AI')" :loading="busy === `d${gap.id}`" @click="draft(gap)" />
            <span class="text-ink-gray-5">{{ t('Goes into Documents to review, fill in and approve; nothing takes effect by itself.') }}</span>
          </div>
        </div>
      </article>
    </section>

    <section class="wq-panel p-5">
      <label data-help="gaps-closed" class="inline-flex items-center gap-1.5 text-sm text-ink-gray-7"><input v-model="showClosed" type="checkbox" class="form-checkbox">{{ t('Show closed to-dos ({n})', { n: closed.length }) }}</label>
      <table v-if="showClosed && closed.length" class="wq-table mt-3 text-sm"><thead><tr><th>{{ t('To-do') }}</th><th>{{ t('Status') }}</th><th>{{ t('By') }}</th><th>{{ t('Note') }}</th></tr></thead>
        <tbody><tr v-for="c in closed" :key="c.id"><td>{{ c.title }}</td><td>{{ t(c.status) }}</td><td>{{ c.closed_by }} {{ ago(c.closed_at) }}</td><td>{{ c.note }}</td></tr></tbody></table>
    </section>
  </template>
</template>
