<script setup>
// Document control on one document (ADR-0017, 17d): who must read it, its periodic review (approved by someone
// other than the reviewer) and who has read the revision in effect.
import { computed, inject, ref, watch } from 'vue'
import { Badge, Button } from 'frappe-ui'
import { api } from '../api'
import { ago } from '../format'

const props = defineProps({ d: { type: Object, required: true }, canEdit: Boolean })
const emit = defineEmits(['changed'])
const ws = inject('workspace')
const canConfigure = computed(() => ws.value?.user.permissions.includes('qms:configure'))
const me = computed(() => ws.value?.user.email)
const error = ref('')
const done = ref('')
const roles = ref([])
const people = ref([])
const needs = ref(false)
const rv = ref({ outcome: 'no_change', note: '', revision_id: '', next_due: '' })
const pw = ref('')
const note = ref('')
const waive = ref({})
const TR = { pending: 'amber', acknowledged: 'green', waived: 'gray', superseded: 'gray' }
watch(() => props.d, (d) => { roles.value = [...d.trainees.roles]; people.value = [...d.trainees.people]; needs.value = d.needs_training }, { immediate: true })
const drafts = computed(() => props.d.revisions.filter((r) => ['draft', 'in_review', 'approved'].includes(r.status) && r.id !== props.d.id))
const waiting = computed(() => props.d.reviews.find((r) => r.status === 'submitted'))
const overdue = computed(() => props.d.review_overdue)

async function call(path, method, body, message) {
  error.value = ''; done.value = ''
  try { emit('changed', await api(path, { method, body })); done.value = message; pw.value = '' } catch (e) { error.value = e.message }
}
const saveReaders = () => call(`/api/docs/${props.d.id}/readers`, 'PUT', { trainees: { roles: roles.value, people: people.value }, needs_training: needs.value }, 'Saved.')
const review = () => call(`/api/docs/${props.d.id}/reviews`, 'POST', { ...rv.value, revision_id: rv.value.revision_id ? Number(rv.value.revision_id) : null }, 'Review recorded: someone else approves it.')
const decide = (how) => call(`/api/doc-reviews/${waiting.value.id}/${how}`, 'POST', { password: pw.value, note: note.value }, how === 'approve' ? 'Review approved.' : 'Review sent back.')
async function doWaive(t) {
  error.value = ''
  try { await api(`/api/doc-training/${t.id}/waive`, { method: 'POST', body: { reason: waive.value[t.id] || '' } }); emit('changed', await api(`/api/docs/${props.d.id}`)); done.value = 'Waived.' } catch (e) { error.value = e.message }
}
</script>

<template>
  <section class="doc-control wq-panel mt-5 p-5">
    <h2 class="wq-h2">Reading and review</h2>
    <p v-if="error" class="wq-error mb-3">{{ error }}</p>
    <p v-if="done" class="mb-3 text-sm text-ink-green-7">{{ done }}</p>

    <h3 class="mb-1 text-sm font-semibold text-ink-gray-8">Who must read it</h3>
    <template v-if="canEdit">
      <div class="mb-2 flex flex-wrap gap-3 text-sm">
        <label v-for="r in d.roles" :key="r" class="inline-flex items-center gap-1.5"><input v-model="roles" type="checkbox" class="form-checkbox" :value="r">{{ r.replace('_', ' ') }}</label>
      </div>
      <label class="wq-field mb-2">People (besides the roles)<select v-model="people" multiple class="wq-select h-24">
        <option v-for="p in d.people" :key="p" :value="p">{{ p }}</option></select></label>
      <label class="mb-2 flex items-center gap-2 text-sm"><input v-model="needs" type="checkbox" class="form-checkbox" :disabled="d.status === 'effective'">
        This revision needs reading{{ d.status === 'effective' ? ' (set before it takes effect)' : ': each of them confirms when it takes effect' }}</label>
      <Button size="sm" label="Save" @click="saveReaders" />
    </template>
    <p v-else class="text-sm text-ink-gray-7">{{ [...d.trainees.roles, ...d.trainees.people].join(', ') || 'Nobody named.' }}</p>
    <p class="mt-1 text-sm text-ink-gray-5">Now that is {{ d.readers_now.length }} people.</p>

    <template v-if="d.training.length">
      <h3 class="mb-1 mt-4 text-sm font-semibold text-ink-gray-8">Reading of this revision</h3>
      <table class="wq-table text-sm"><thead><tr><th>Person</th><th>Due</th><th>Status</th><th /></tr></thead>
        <tbody><tr v-for="t in d.training" :key="t.id"><td>{{ t.email }}</td><td :class="t.overdue ? 'text-ink-red-7' : ''">{{ t.due }}</td>
          <td><Badge :theme="t.overdue ? 'red' : TR[t.status]" :label="t.overdue ? 'overdue' : t.status" /> <span class="text-ink-gray-5">{{ t.done_at ? ago(t.done_at) : '' }} {{ t.note }}</span></td>
          <td><div v-if="canConfigure && t.status === 'pending' && t.email !== me" class="flex items-center gap-1">
            <input v-model="waive[t.id]" class="wq-input w-48" placeholder="Why it is waived"><Button size="sm" label="Waive" :disabled="!(waive[t.id] || '').trim()" @click="doWaive(t)" /></div>
            <RouterLink v-else-if="t.status === 'pending' && t.email === me" to="/documents/control" class="wq-link">confirm</RouterLink></td></tr></tbody></table>
    </template>

    <template v-if="d.status === 'effective'">
      <h3 class="mb-1 mt-5 text-sm font-semibold text-ink-gray-8">Periodic review</h3>
      <p class="text-sm" :class="overdue ? 'text-ink-red-7' : 'text-ink-gray-7'">{{ d.next_review ? `Next review due ${d.next_review}${overdue ? ' (overdue)' : ''}.` : 'Its type is not reviewed periodically.' }}</p>
      <div v-if="waiting" class="mt-2 rounded-3 border border-outline-gray-2 p-3 text-sm">
        <p><b>{{ d.review_outcomes[waiting.outcome] }}</b> · reviewed by {{ waiting.reviewed_by }} on {{ waiting.reviewed_on }}<template v-if="waiting.next_due"> · new date {{ waiting.next_due }}</template></p>
        <p v-if="waiting.note" class="text-ink-gray-7">{{ waiting.note }}</p>
        <div v-if="canConfigure && waiting.reviewed_by !== me" class="mt-2 flex flex-wrap items-end gap-2">
          <input v-model="note" class="wq-input w-64" placeholder="Note (needed to send back)">
          <input v-model="pw" type="password" class="wq-input w-44" placeholder="Your password" autocomplete="current-password">
          <Button size="sm" variant="solid" label="Approve the review (sign)" :disabled="!pw" @click="decide('approve')" />
          <Button size="sm" label="Send back" :disabled="!note.trim()" @click="decide('send-back')" />
        </div>
        <p v-else class="mt-1 text-ink-gray-5">Waiting for someone other than the reviewer to approve it.</p>
      </div>
      <form v-else-if="canEdit" class="mt-2 flex flex-wrap items-end gap-2" @submit.prevent="review">
        <label class="wq-field">Outcome<select v-model="rv.outcome" class="wq-select">
          <option v-for="(l, k) in d.review_outcomes" :key="k" :value="k">{{ l }}</option></select></label>
        <label v-if="rv.outcome === 'change'" class="wq-field">New revision<select v-model="rv.revision_id" class="wq-select"><option value="" />
          <option v-for="r in drafts" :key="r.id" :value="r.id">rev {{ r.revision }} ({{ r.status }})</option></select></label>
        <label v-if="rv.outcome === 'postponed'" class="wq-field">New date<input v-model="rv.next_due" type="date" class="wq-input"></label>
        <label class="wq-field grow">Note<input v-model="rv.note" class="wq-input"></label>
        <Button type="submit" label="Record the review" />
      </form>
      <ul v-if="d.reviews.length" class="mt-3 text-sm text-ink-gray-6"><li v-for="r in d.reviews" :key="r.id">
        {{ r.reviewed_on }} · {{ d.review_outcomes[r.outcome] }} by {{ r.reviewed_by }} · {{ r.status }}<template v-if="r.approved_by"> by {{ r.approved_by }}</template>{{ r.note ? ` · ${r.note}` : '' }}</li></ul>
    </template>
  </section>
</template>
