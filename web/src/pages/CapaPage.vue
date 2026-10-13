<script setup>
// One corrective / preventive action in stages (ADR-0010): draft, investigation, implementation, effectiveness
// check, closed (signed by someone other than the owner) or cancelled.
import { computed, inject, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
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
  <p v-if="error" class="err">{{ error }}</p>
  <template v-if="c">
    <p class="muted small"><RouterLink to="/quality?tab=capas">Corrective actions</RouterLink></p>
    <h1>{{ c.name }} {{ c.title }} <span class="tag">{{ c.kind }}</span> <span class="tag" v-if="c.risk">{{ c.risk }} risk</span></h1>
    <nav class="stages"><span v-for="s in STAGES" :key="s" :class="{ on: c.status === s, done: STAGES.indexOf(s) < STAGES.indexOf(c.status) }">{{ s.replace('_', ' ') }}</span>
      <span v-if="c.status === 'cancelled'" class="on">cancelled</span></nav>
    <p v-if="c.ncrs.length">For <template v-for="(x, i) in c.ncrs" :key="x.id"><span v-if="i">, </span><RouterLink :to="`/quality/ncr/${x.id}`">{{ x.name }} {{ x.title }}</RouterLink></template></p>
    <table class="props">
      <tr v-for="k in ['description', 'owner', 'containment', 'root_cause']" :key="k" v-show="c[k]"><th>{{ LABELS[k] }}</th><td>{{ c[k] }}</td></tr>
      <tr v-if="c.verification_result"><th>Effectiveness</th><td>{{ c.verification_result }} — {{ c.verification_method }} ({{ c.verified_by }})</td></tr>
      <tr v-if="c.cancel_reason"><th>Cancelled because</th><td>{{ c.cancel_reason }}</td></tr>
    </table>

    <form v-if="canEdit && FIELDS[c.status]" class="card form" @submit.prevent="step('update', edit)">
      <label v-for="k in FIELDS[c.status]" :key="k" class="small muted">{{ LABELS[k] }}
        <select v-if="k === 'risk'" v-model="edit.risk"><option value="">—</option><option>low</option><option>medium</option><option>high</option></select>
        <textarea v-else-if="['description', 'containment', 'root_cause'].includes(k)" v-model="edit[k]" rows="2"></textarea>
        <input v-else v-model="edit[k]"></label>
      <div class="actions"><button>Save</button><button type="button" @click="step(NEXT[c.status][0])">{{ NEXT[c.status][1] }}</button></div>
    </form>

    <h2>Actions</h2>
    <table class="grid"><thead><tr><th>Kind</th><th>Action</th><th>Owner</th><th>Due</th><th>Done</th></tr></thead>
      <tbody><tr v-for="a in c.actions" :key="a.id" :class="{ warn: !a.done && a.due && a.due < today }">
        <td class="small">{{ a.kind }}</td><td>{{ a.text }}</td><td class="small">{{ a.owner }}</td><td class="small">{{ a.due }}</td>
        <td><template v-if="a.done">✓ {{ a.done_by }} <div class="muted small">{{ a.evidence }}</div></template>
          <div v-else-if="(canEdit || a.owner === me) && ['investigation', 'implementation'].includes(c.status)" class="row">
            <input v-model="evidence[a.id]" placeholder="Evidence"><button @click="step('action-done', { action_id: a.id, evidence: evidence[a.id] })">Done</button></div></td></tr></tbody></table>
    <form v-if="canEdit && ['draft', 'investigation', 'implementation'].includes(c.status)" class="actions" @submit.prevent="step('action', add); add = { text: '', owner: '', due: '', kind: 'corrective' }">
      <select v-model="add.kind"><option value="correction">Correction</option><option value="corrective">Corrective</option><option value="preventive">Preventive</option></select>
      <input v-model="add.text" placeholder="New action" required><input v-model="add.owner" placeholder="Owner email"><input v-model="add.due" type="date" :min="today"><button>Add</button></form>

    <div v-if="canEdit && c.status === 'effectiveness'" class="card">
      <h3>Effectiveness check</h3>
      <p v-if="c.owner === me" class="muted small">You own this action; someone else must close it as effective.</p>
      <div class="actions"><input v-model="check.evidence" placeholder="Evidence: data and period checked">
        <input v-if="c.owner !== me" v-model="check.password" type="password" placeholder="Your password to sign" autocomplete="current-password">
        <button v-if="c.owner !== me" @click="step('effectiveness', { result: 'effective', ...check })">Effective — close (sign)</button>
        <button @click="step('effectiveness', { result: 'ineffective', evidence: check.evidence })">Not effective — back to implementation</button></div>
    </div>
    <div v-if="canEdit && !['closed', 'cancelled'].includes(c.status)" class="actions"><input v-model="cancel" placeholder="Reason to cancel"><button @click="step('cancel', { reason: cancel })">Cancel</button></div>

    <h2>Signatures</h2>
    <p v-if="!c.signatures.length" class="muted small">None yet.</p>
    <ul class="list small"><li v-for="(s, i) in c.signatures" :key="i">{{ s.meaning }} — {{ s.name }} ({{ s.email }}), {{ ago(s.at) }}</li></ul>
    <h2>History</h2>
    <ul class="list small"><li v-for="(h, i) in c.history" :key="i">{{ ago(h.at) }} — <b>{{ h.action }}</b> {{ h.email }} <span class="muted">{{ h.note }}</span></li></ul>
  </template>
</template>
