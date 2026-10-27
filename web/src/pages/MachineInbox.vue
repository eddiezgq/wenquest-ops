<script setup>
// From machines (ADR-0020, 20d): what machines and other systems sent, waiting for a person. Accepting writes it into
// the incoming inspection or the production record, signed with your password; a machine never signs.
import { ref, watch } from 'vue'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { t } from '../i18n'

const v = ref(null)
const status = ref('pending')
const error = ref('')
const done = ref('')
const open = ref(null)
const detail = ref(null)
const password = ref('')
const note = ref('')
const busy = ref(false)
const ST = { pending: 'amber', accepted: 'green', rejected: 'gray' }
async function load() { try { v.value = await api(`/api/integrations/inbox?status=${status.value}`) } catch (e) { error.value = e.message } }
watch(status, load, { immediate: true })
async function show(x) {
  open.value = open.value === x.id ? null : x.id; password.value = ''; note.value = ''; detail.value = null
  if (!open.value) return
  const d = await api(`/api/integrations/inbox/${x.id}`)
  if (open.value === x.id) detail.value = d            // a slower answer for another item is dropped
}
async function decide(kind) {
  error.value = ''; done.value = ''; busy.value = true
  const body = kind === 'accept' ? { password: password.value, seen: detail.value.print } : { note: note.value }
  password.value = ''
  try {
    const r = await api(`/api/integrations/inbox/${open.value}/${kind}`, { method: 'POST', body })
    done.value = kind === 'accept' ? t('Accepted: {result}.', { result: r.result }) : t('Rejected.')
    open.value = null; await load()
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
const when = (s) => (s ? s.slice(0, 16).replace('T', ' ') : '')
function what(x) {
  const p = x.payload
  if (x.kind === 'measurements') return t('{n} reading(s) for {inspection}', { n: p.readings.length, inspection: p.inspection })
  return t('step {step} ({name}) of {record}: {value}', { step: p.step, name: p.name, record: p.record, value: p.value ?? p.result ?? p.text })
}
</script>

<template>
  <PageTop :title="t('From machines')">
    <select v-model="status" class="wq-select" :aria-label="t('Which')"><option value="pending">{{ t('Waiting') }}</option><option value="accepted">{{ t('Accepted') }}</option>
      <option value="rejected">{{ t('Rejected') }}</option><option value="all">{{ t('All') }}</option></select>
  </PageTop>
  <p class="mb-4 max-w-3xl text-base text-ink-gray-7">{{ t('Measurements and step results that machines and other systems sent. Nothing is in a record until someone accepts it with their password; it is then recorded as theirs, with the machine named.') }}</p>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <section v-if="v" data-help="inbox-list" class="wq-panel p-5">
    <p v-if="!v.items.length" class="wq-muted">{{ status === 'pending' ? t('Nothing waiting.') : t('Nothing here.') }}</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Received') }}</th><th>{{ t('From') }}</th><th>{{ t('What') }}</th><th>{{ t('Status') }}</th><th /></tr></thead>
      <tbody><template v-for="x in v.items" :key="x.id"><tr>
        <td>{{ when(x.received_at) }}</td><td>{{ x.sender }}</td><td>{{ what(x) }}</td>
        <td><Badge :theme="ST[x.status]" :label="t(x.status)" /><span v-if="x.decided_by" class="ms-1 text-ink-gray-5">{{ x.decided_by }}</span></td>
        <td><Button size="sm" variant="ghost" :label="open === x.id ? t('Close') : t('Open')" @click="show(x)" /></td></tr>
        <tr v-if="open === x.id && detail"><td colspan="5" class="bg-surface-gray-1">
          <p class="mb-2 text-sm">{{ t('For') }} <RouterLink :to="detail.link" class="wq-link">{{ detail.target }}</RouterLink> ({{ detail.target_status.replace('_', ' ') }})<template
            v-if="detail.payload.equipment">{{ t(', measured with {equipment}', { equipment: detail.payload.equipment }) }}</template><template v-if="detail.payload.note">{{ t('. Note: {note}', { note: detail.payload.note }) }}</template></p>
          <table v-if="detail.kind === 'measurements'" class="wq-table mb-2 w-auto text-sm"><thead><tr><th>{{ t('Sample') }}</th><th>{{ t('Characteristic') }}</th><th>{{ t('Value') }}</th></tr></thead>
            <tbody><tr v-for="r in detail.payload.readings" :key="r.sample + r.characteristic"><td>{{ r.sample }}</td><td>{{ r.characteristic }}</td><td class="font-mono">{{ r.value }}</td></tr></tbody></table>
          <p v-if="detail.replaces?.length" class="mb-2 text-sm text-ink-amber-8">{{ t('Replaces {n} reading(s) entered before:', { n: detail.replaces.length }) }}
            {{ detail.replaces.map((r) => t('sample {sample} {characteristic} {before} → {value}', { sample: r.sample, characteristic: r.characteristic, before: r.before, value: r.value })).join('; ') }}</p>
          <ul v-if="detail.blocks.length" class="mb-2 list-disc ps-5 text-sm font-medium text-ink-red-7"><li v-for="b in detail.blocks" :key="b">{{ b }}</li></ul>
          <p v-if="detail.status !== 'pending'" class="text-sm">{{ t('{status} by {by} {when}: {what}', { status: t(detail.status), by: detail.decided_by, when: when(detail.decided_at), what: detail.result || detail.note }) }}</p>
          <div v-else-if="v.can_decide" data-help="inbox-decide" class="flex flex-wrap items-end gap-2">
            <label class="wq-field">{{ t('Your password') }}<input v-model="password" type="password" class="wq-input w-48" autocomplete="current-password"></label>
            <Button variant="solid" :label="t('Accept (sign)')" :disabled="!password || detail.blocks.length > 0" :loading="busy" @click="decide('accept')" />
            <span class="mx-2 h-8 border-s border-outline-gray-2" />
            <label class="wq-field">{{ t('Why reject') }}<input v-model="note" class="wq-input w-72"></label>
            <Button :label="t('Reject')" :disabled="!note.trim()" @click="decide('reject')" />
          </div></td></tr>
      </template></tbody></table>
  </section>
</template>
