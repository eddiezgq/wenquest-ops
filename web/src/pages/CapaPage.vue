<script setup>
// One corrective / preventive action: its steps, actions with owners and due dates, effectiveness check (ADR-0009).
import { computed, inject, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, objectPath } from '../api'
import { ago } from '../format'

const ws = inject('workspace')
const route = useRoute()
const c = ref(null)
const error = ref('')
const add = ref({ text: '', owner: '', due: '' })
const check = ref({ method: '' })
const me = computed(() => ws.value?.user.email)
const canEdit = computed(() => ws.value?.user.permissions.includes('quality:edit'))

async function load() { try { c.value = await api(`/api/quality/capas/${route.params.id}`) } catch (e) { error.value = e.message } }
async function step(s, body = {}) {
  error.value = ''
  try { c.value = await api(`/api/quality/capas/${c.value.id}/${s}`, { method: 'POST', body }) } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
const today = new Date().toISOString().slice(0, 10)
</script>

<template>
  <p v-if="error" class="err">{{ error }}</p>
  <template v-if="c">
    <p class="muted small"><RouterLink to="/quality?tab=capas">Corrective actions</RouterLink> · <RouterLink :to="objectPath('Capa', c.name)">object page</RouterLink></p>
    <h1>{{ c.name }} {{ c.title }} <span class="tag">{{ c.kind }}</span> <span class="tag">{{ c.status.replace('_', ' ') }}</span></h1>
    <p v-if="c.description">{{ c.description }}</p>
    <p v-if="c.ncr">For <RouterLink :to="`/quality/ncr/${c.ncr.id}`">{{ c.ncr.name }} {{ c.ncr.title }}</RouterLink></p>
    <p v-if="c.verification_result"><b>Effectiveness:</b> {{ c.verification_result }} — {{ c.verification_method }} ({{ c.verified_by }})</p>
    <h2>Actions</h2>
    <table class="grid"><thead><tr><th>Action</th><th>Owner</th><th>Due</th><th>Done</th></tr></thead>
      <tbody><tr v-for="a in c.actions" :key="a.id" :class="{ warn: !a.done && a.due && a.due < today }">
        <td>{{ a.text }}</td><td class="small">{{ a.owner }}</td><td class="small">{{ a.due }}</td>
        <td><template v-if="a.done">✓ {{ a.done_by }}</template>
          <button v-else-if="canEdit || a.owner === me" @click="step('action-done', { action_id: a.id })">Mark done</button></td></tr></tbody></table>
    <form v-if="canEdit && ['open', 'in_progress'].includes(c.status)" class="actions" @submit.prevent="step('action', add); add = { text: '', owner: '', due: '' }">
      <input v-model="add.text" placeholder="New action" required><input v-model="add.owner" placeholder="Owner email"><input v-model="add.due" type="date"><button>Add</button></form>
    <div v-if="canEdit" class="actions">
      <button v-if="c.status === 'open'" @click="step('start')">Start work</button>
      <button v-if="c.status === 'in_progress'" @click="step('verification')">Ready for effectiveness check</button>
      <template v-if="c.status === 'verification'">
        <input v-model="check.method" placeholder="How effectiveness was checked (data, period)">
        <button @click="step('verify', { result: 'effective', method: check.method })">Effective — close</button>
        <button @click="step('verify', { result: 'ineffective', method: check.method })">Not effective — back to work</button>
      </template>
    </div>
    <h2>History</h2>
    <ul class="list small"><li v-for="(h, i) in c.history" :key="i">{{ ago(h.at) }} — <b>{{ h.action }}</b> {{ h.email }} <span class="muted">{{ h.note }}</span></li></ul>
  </template>
</template>
