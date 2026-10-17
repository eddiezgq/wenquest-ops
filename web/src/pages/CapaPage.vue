<script setup>
// One corrective / preventive action in stages (ADR-0010): draft, investigation, implementation, effectiveness
// check, closed (signed by someone other than the owner) or cancelled.
import { computed, inject, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import OwnFields from '../components/OwnFields.vue'
import CauseLinks from '../components/CauseLinks.vue'
import { api } from '../api'
import { ago } from '../format'

const ws = inject('workspace')
const route = useRoute()
const c = ref(null)
const error = ref('')
const edit = ref({})
const add = ref({ text: '', owner: '', due: '', kind: 'corrective' })
const evidence = ref({})
const check = ref({ evidence: '', password: '' })
const cancel = ref('')
const me = computed(() => ws.value?.user.email)
const canEdit = computed(() => ws.value?.user.permissions.includes('quality:edit'))
const STAGES = ['draft', 'investigation', 'implementation', 'effectiveness', 'closed']
const FIELDS = { draft: ['title', 'description', 'owner', 'risk'], investigation: ['description', 'owner', 'risk', 'containment', 'root_cause'], implementation: ['owner'] }
const LABELS = { title: 'Title', description: 'Problem description', owner: 'Owner (email)', risk: 'Risk level', containment: 'Containment', root_cause: 'Root cause' }

function set(v) {
  c.value = v
  edit.value = Object.fromEntries((FIELDS[v.status] || []).map((k) => [k, v[k] || '']))
  check.value.password = ''
}
async function load() { try { set(await api(`/api/quality/capas/${route.params.id}`)) } catch (e) { error.value = e.message } }
async function step(s, body = {}) {
  error.value = ''
  try { set(await api(`/api/quality/capas/${c.value.id}/${s}`, { method: 'POST', body })) } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
const today = new Date().toISOString().slice(0, 10)
const NEXT = { draft: ['submit', 'Start investigation'], investigation: ['plan', 'Actions planned — start implementation'], implementation: ['effectiveness-check', 'All actions done — check effectiveness'] }
</script>

<template>
  <PageTop :title="c ? `${c.name} ${c.title}` : 'Corrective action'" :crumbs="[{ label: 'Quality', to: '/quality?tab=capas' }]">
    <template v-if="c">
      <Badge :label="c.kind" variant="outline" size="lg" class="capitalize" />
      <Badge v-if="c.risk" :theme="c.risk === 'high' ? 'red' : c.risk === 'medium' ? 'amber' : 'gray'" :label="`${c.risk} risk`" size="lg" />
    </template>
    <RouterLink v-if="c?.workflow" to="/quality?tab=workflows" class="hidden text-sm text-ink-gray-5 hover:underline sm:inline">workflow v{{ c.workflow.version }}</RouterLink>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <template v-if="c">
    <ol data-help="capa-stages" class="stages mb-6 flex flex-wrap items-center gap-1">
      <template v-for="(s, i) in STAGES" :key="s">
        <li class="flex items-center gap-1.5 rounded-full px-3 py-1 text-sm capitalize"
            :class="c.status === s ? 'bg-surface-gray-7 font-medium text-ink-base' : STAGES.indexOf(s) < STAGES.indexOf(c.status) ? 'bg-surface-gray-2 text-ink-gray-8' : 'text-ink-gray-4'">
          <span v-if="STAGES.indexOf(s) < STAGES.indexOf(c.status)" class="lucide-check size-3.5" />{{ s }}</li>
        <span v-if="i < STAGES.length - 1" class="lucide-chevron-right size-3.5 text-ink-gray-4" />
      </template>
      <li v-if="c.status === 'cancelled'" class="ms-2 rounded-full bg-surface-red-2 px-3 py-1 text-sm text-ink-red-7">cancelled</li>
    </ol>
    <div class="grid gap-6 lg:grid-cols-[3fr_2fr]">
      <section class="wq-panel p-5">
        <p v-if="c.ncrs.length" class="mb-3 text-sm text-ink-gray-6">For <template v-for="(x, i) in c.ncrs" :key="x.id"><span v-if="i">, </span><RouterLink :to="`/quality/ncr/${x.id}`" class="wq-link">{{ x.name }} {{ x.title }}</RouterLink></template></p>
        <dl class="wq-dl">
          <template v-for="k in ['description', 'owner', 'containment', 'root_cause']" :key="k"><template v-if="c[k]"><dt>{{ LABELS[k] }}</dt><dd>{{ c[k] }}</dd></template></template>
          <template v-if="c.verification_result"><dt>Effectiveness</dt><dd>{{ c.verification_result }} — {{ c.verification_method }} ({{ c.verified_by }})</dd></template>
          <template v-if="c.cancel_reason"><dt>Cancelled because</dt><dd>{{ c.cancel_reason }}</dd></template>
        </dl>
      </section>
      <form v-if="canEdit && FIELDS[c.status]" data-help="capa-next-step" class="form wq-panel grid h-fit gap-3 p-5" @submit.prevent="step('update', edit)">
        <label v-for="k in FIELDS[c.status]" :key="k" class="wq-field">{{ LABELS[k] }}
          <select v-if="k === 'risk'" v-model="edit.risk" class="wq-select"><option value="">—</option><option>low</option><option>medium</option><option>high</option></select>
          <textarea v-else-if="['description', 'containment', 'root_cause'].includes(k)" v-model="edit[k]" class="wq-textarea" rows="2"></textarea>
          <input v-else v-model="edit[k]" class="wq-input"></label>
        <div class="flex flex-wrap gap-2"><Button type="submit" label="Save" /><Button variant="solid" :label="NEXT[c.status][1]" @click="step(NEXT[c.status][0])" /></div>
      </form>
      <section v-if="canEdit && c.status === 'effectiveness'" data-help="capa-effectiveness" class="wq-panel grid h-fit gap-2 p-5">
        <h3 class="text-base font-semibold text-ink-gray-9">Effectiveness check</h3>
        <p v-if="c.owner === me" class="wq-muted">You own this action; someone else must close it as effective.</p>
        <input v-model="check.evidence" class="wq-input" placeholder="Evidence: data and period checked">
        <input v-if="c.owner !== me" v-model="check.password" class="wq-input" type="password" placeholder="Your password to sign" autocomplete="current-password">
        <div class="flex flex-wrap gap-2">
          <Button v-if="c.owner !== me" variant="solid" icon-left="lucide-pen-line" label="Effective — close (sign)" @click="step('effectiveness', { result: 'effective', ...check })" />
          <Button label="Not effective — back to implementation" @click="step('effectiveness', { result: 'ineffective', evidence: check.evidence })" /></div>
      </section>
    </div>

    <h2 class="wq-h2 mt-8">Actions</h2>
    <div data-help="capa-actions" class="wq-panel overflow-x-auto">
      <table class="wq-table">
        <thead><tr><th>Kind</th><th>Action</th><th>Owner</th><th>Due</th><th>Done</th></tr></thead>
        <tbody><tr v-for="a in c.actions" :key="a.id">
          <td class="text-sm capitalize">{{ a.kind }}</td><td>{{ a.text }}</td><td class="text-sm text-ink-gray-6">{{ a.owner }}</td>
          <td class="whitespace-nowrap text-sm" :class="!a.done && a.due && a.due < today ? 'font-medium text-ink-red-7' : ''">{{ a.due }}
            <Badge v-if="!a.done && a.due && a.due < today" theme="red" label="overdue" class="ms-1" /></td>
          <td><template v-if="a.done"><span class="text-ink-green-7">✓</span> {{ a.done_by }} <div class="text-sm text-ink-gray-5">{{ a.evidence }}</div></template>
            <div v-else-if="(canEdit || a.owner === me) && ['investigation', 'implementation'].includes(c.status)" class="flex gap-2">
              <input v-model="evidence[a.id]" class="wq-input w-48" placeholder="Evidence"><Button label="Done" @click="step('action-done', { action_id: a.id, evidence: evidence[a.id] })" /></div></td></tr></tbody>
      </table>
    </div>
    <form v-if="canEdit && ['draft', 'investigation', 'implementation'].includes(c.status)" data-help="capa-add-action" class="mt-3 flex flex-wrap gap-2"
          @submit.prevent="step('action', add); add = { text: '', owner: '', due: '', kind: 'corrective' }">
      <select v-model="add.kind" class="wq-select"><option value="correction">Correction</option><option value="corrective">Corrective</option><option value="preventive">Preventive</option></select>
      <input v-model="add.text" class="wq-input max-w-80" placeholder="New action" required><input v-model="add.owner" class="wq-input max-w-56" placeholder="Owner email">
      <input v-model="add.due" class="wq-input w-40" type="date" :min="today"><Button type="submit" icon-left="lucide-plus" label="Add" /></form>

    <div v-if="canEdit && !['closed', 'cancelled'].includes(c.status)" class="mt-6 flex max-w-xl gap-2">
      <input v-model="cancel" class="wq-input flex-1" placeholder="Reason to cancel"><Button theme="red" label="Cancel" @click="step('cancel', { reason: cancel })" /></div>

    <OwnFields :record="c" kind="capa" :can-edit="canEdit" @changed="set" />
    <CauseLinks kind="capa" :id="c.id" :status="c.status" />
    <h2 data-help="capa-signatures" class="wq-h2 mt-8">Signatures</h2>
    <Trail :items="c.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-8">History</h2>
    <Trail :items="c.history" />
  </template>
</template>
