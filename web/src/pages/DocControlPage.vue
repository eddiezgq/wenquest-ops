<script setup>
// My reading and document control (ADR-0017, 17d): what I must read and confirm, reviews due, everyone's reading,
// and how often each document type is reviewed.
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { ago } from '../format'

const route = useRoute()
const router = useRouter()
const v = ref(null)
const mine = ref([])
const error = ref('')
const done = ref('')
const pw = ref({})
const types = ref({})
const tab = computed({ get: () => route.query.tab || 'mine', set: (t) => router.replace({ query: { tab: t } }) })
const TR = { pending: 'amber', acknowledged: 'green', waived: 'gray', superseded: 'gray' }
const name = (t) => [t.number, t.title, t.revision ? `rev ${t.revision}` : ''].filter(Boolean).join(' ')

async function load() {
  error.value = ''
  try {
    mine.value = await api('/api/my-reading')
    try { v.value = await api('/api/doc-control') } catch { v.value = null }     // needs documents:view
    if (v.value) types.value = Object.fromEntries(Object.keys(v.value.doc_types).map((k) => [k, { review_months: v.value.types[k]?.review_months ?? '', training_days: v.value.types[k]?.training_days ?? 30 }]))
  } catch (e) { error.value = e.message }
}
load()
async function ack(t) {
  error.value = ''; done.value = ''
  const p = pw.value[t.id] || ''; pw.value[t.id] = ''
  try { mine.value = await api(`/api/my-reading/${t.id}/acknowledge`, { method: 'POST', body: { password: p } }); done.value = `Confirmed: you have read ${name(t)}.` } catch (e) { error.value = e.message }
}
async function saveType(k) {
  error.value = ''; done.value = ''
  const t = types.value[k]
  try {
    await api(`/api/doc-types/${k}`, { method: 'POST', body: { review_months: t.review_months === '' ? null : Number(t.review_months), training_days: Number(t.training_days) } })
    done.value = 'Saved.'; await load()
  } catch (e) { error.value = e.message }
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Documents', to: '/documents' }]">
    <template #title>Reading and review</template>
  </PageTop>
  <nav class="tabs -mt-2 mb-5 flex gap-5 overflow-x-auto border-b border-outline-gray-2">
    <a v-for="(l, k) in { mine: 'My reading', reviews: 'Reviews due', all: 'Everyone\'s reading', types: 'Settings' }" :key="k" href="#"
       v-show="k === 'mine' || v" class="-mb-px whitespace-nowrap border-b-2 pb-2 text-base"
       :class="tab === k ? 'border-outline-gray-9 font-medium text-ink-gray-9' : 'border-transparent text-ink-gray-5 hover:text-ink-gray-8'" @click.prevent="tab = k">{{ l }}</a>
  </nav>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <section v-if="tab === 'mine'" class="mine wq-panel p-5">
    <p class="wq-muted mb-3">Documents you are asked to read. Open each one, read it, then confirm with your password that you have read and understood it.</p>
    <p v-if="!mine.length" class="wq-muted">Nothing to read.</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>Document</th><th>Due</th><th>Status</th><th /></tr></thead>
      <tbody><tr v-for="t in mine" :key="t.id">
        <td><RouterLink :to="`/documents/${t.document_id}`" class="wq-link">{{ name(t) }}</RouterLink></td>
        <td :class="t.overdue ? 'text-ink-red-7' : ''">{{ t.due }}</td>
        <td><Badge :theme="t.overdue ? 'red' : TR[t.status]" :label="t.overdue ? 'overdue' : t.status" /> <span class="text-ink-gray-5">{{ t.done_at ? ago(t.done_at) : '' }}</span></td>
        <td><div v-if="t.status === 'pending'" class="flex items-center gap-1">
          <input v-model="pw[t.id]" type="password" class="wq-input w-40" placeholder="Your password" autocomplete="current-password">
          <Button size="sm" variant="solid" label="I have read and understood it" :disabled="!pw[t.id]" @click="ack(t)" /></div></td></tr></tbody></table>
  </section>

  <section v-if="v && tab === 'reviews'" class="wq-panel p-5">
    <p class="wq-muted mb-3">Documents in effect whose type is reviewed periodically, by when the next review is due. Record a review on the document's page; someone else approves it.</p>
    <p v-if="!v.reviews.length" class="wq-muted">None.</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>Document</th><th>In effect since</th><th>Review due</th><th>Waiting</th></tr></thead>
      <tbody><tr v-for="r in v.reviews" :key="r.id">
        <td><RouterLink :to="`/documents/${r.id}`" class="wq-link">{{ name(r) }}</RouterLink></td><td>{{ r.effective_date }}</td>
        <td :class="r.overdue ? 'font-medium text-ink-red-7' : ''">{{ r.due }}{{ r.overdue ? ' (overdue)' : '' }}</td>
        <td>{{ r.waiting ? `review by ${r.waiting.reviewed_by}, to approve` : '' }}</td></tr></tbody></table>
  </section>

  <section v-if="v && tab === 'all'" class="wq-panel p-5">
    <p v-if="!v.training.length" class="wq-muted">Nobody has been asked to read anything yet.</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>Person</th><th>Document</th><th>Due</th><th>Status</th></tr></thead>
      <tbody><tr v-for="t in v.training" :key="t.id"><td>{{ t.email }}</td>
        <td><RouterLink :to="`/documents/${t.document_id}`" class="wq-link">{{ name(t) }}</RouterLink></td>
        <td :class="t.overdue ? 'text-ink-red-7' : ''">{{ t.due }}</td>
        <td><Badge :theme="t.overdue ? 'red' : TR[t.status]" :label="t.overdue ? 'overdue' : t.status" /> <span class="text-ink-gray-5">{{ t.note }}</span></td></tr></tbody></table>
  </section>

  <section v-if="v && tab === 'types'" class="wq-panel p-5">
    <p class="wq-muted mb-3">How often each type of document is reviewed (empty: not periodically) and how many days people have to read a new revision. The starting values are defaults: set them to what your procedure says.</p>
    <table class="wq-table text-sm"><thead><tr><th>Type</th><th>Review every (months)</th><th>Days to read</th><th /></tr></thead>
      <tbody><tr v-for="(l, k) in v.doc_types" :key="k"><td>{{ l }}</td>
        <td><input v-model="types[k].review_months" type="number" min="1" max="120" class="wq-input w-24" :disabled="!v.can_configure"></td>
        <td><input v-model="types[k].training_days" type="number" min="1" max="365" class="wq-input w-24" :disabled="!v.can_configure"></td>
        <td><Button v-if="v.can_configure" size="sm" label="Save" @click="saveType(k)" /></td></tr></tbody></table>
  </section>
</template>
