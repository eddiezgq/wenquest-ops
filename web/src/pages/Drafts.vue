<script setup>
// Drafts waiting for a person (ADR-0006, ADR-0008). Nothing is written to ERPNext or sent before "Confirm".
import { inject, ref, watch } from 'vue'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { STATUS, label } from '../ui/themes'
import { api, objectPath } from '../api'
import { fmt } from '../format'
import { t } from '../i18n'

const ws = inject('workspace')
const status = ref('pending')
const rows = ref([])
const error = ref('')
const notes = ref({})
const copied = ref(null)

async function load() {
  error.value = ''
  try { rows.value = await api(`/api/erp/drafts${status.value === 'all' ? '' : '?status=' + status.value}`) }
  catch (e) { error.value = e.message }
}
async function act(d, what) {
  error.value = ''
  try {
    await api(`/api/erp/drafts/${d.id}/${what}`, { method: 'POST', body: what === 'reject' ? { reason: notes.value[d.id] || '' } : undefined })
    await load()
  } catch (e) { error.value = e.message }
}
async function copy(d) {
  await navigator.clipboard.writeText(`Subject: ${d.payload.subject}\n\n${d.payload.body}`)
  copied.value = d.id
}
watch(status, load, { immediate: true })
const WHAT = { 'Purchase Order': 'Creates a draft purchase order in ERPNext; submit it there.',
  Supplier: 'Creates the supplier in ERPNext.',
  'Material Request': 'Creates a draft material request in ERPNext.', 'Quality Inspection': 'Creates a draft inspection in ERPNext.',
  'Customer Message': 'Marks the message ready; you send it yourself.', 'Nonconformance Report': 'Opens a nonconformance report (NCR).' }
</script>

<template>
  <PageTop :title="t('Drafts')">
    <select v-model="status" data-help="drafts-show" class="wq-select" :aria-label="t('Show')">
      <option value="pending">{{ t('Waiting for you') }}</option><option value="confirmed">{{ t('Confirmed') }}</option>
      <option value="rejected">{{ t('Rejected') }}</option><option value="failed">{{ t('Failed') }}</option><option value="all">{{ t('All') }}</option></select>
  </PageTop>
  <p class="wq-muted mb-4">{{ t('Drafts are prepared by the assistant or by people. Nothing is written to ERPNext or sent until someone with the right role confirms.') }}</p>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="!rows.length" class="wq-muted">{{ t('None.') }}</p>
  <article v-for="d in rows" :key="d.id" data-help="drafts-item" class="draft wq-panel mb-4 p-5">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <h3 class="text-base font-semibold text-ink-gray-9">{{ d.doctype }}</h3>
        <Badge :theme="STATUS[d.status] || 'gray'" :label="t(label(d.status))" />
        <Badge v-if="d.source === 'ai'" theme="violet" variant="outline" :label="t('AI draft')" />
      </div>
      <span class="wq-muted">{{ t('#{id} by {name}', { id: d.id, name: d.proposed_by }) }}</span>
    </div>
    <p class="mt-2 text-p-base text-ink-gray-8">{{ d.summary }}</p>
    <template v-if="d.doctype === 'Purchase Order'">
      <p class="mt-3 text-sm text-ink-gray-6">{{ t('Supplier') }} <RouterLink :to="objectPath('Supplier', d.payload.supplier)" class="wq-link">{{ d.payload.supplier }}</RouterLink>,
        {{ t('required by {date}', { date: d.payload.schedule_date }) }}</p>
      <div class="mt-2 overflow-x-auto rounded-3 border border-outline-gray-2">
        <table class="wq-table text-sm"><thead><tr><th>{{ t('Item') }}</th><th>{{ t('Qty') }}</th><th>{{ t('Rate') }}</th><th>{{ t('Warehouse') }}</th></tr></thead>
          <tbody><tr v-for="(l, i) in d.payload.items" :key="i">
            <td><RouterLink :to="objectPath('Item', l.item_code)" class="wq-link">{{ l.item_code }}</RouterLink></td><td>{{ fmt(l.qty) }}</td>
            <td>{{ l.rate === undefined ? t('from ERPNext') : fmt(l.rate, 'currency') }}</td><td>{{ l.warehouse }}</td></tr></tbody></table>
      </div>
      <div v-if="d.asl?.length" class="mt-2 rounded-3 border border-outline-amber-3 bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-8">
        <p class="font-medium">{{ t('Approved supplier list') }}</p>
        <ul class="list-disc ps-5"><li v-for="(x, i) in d.asl" :key="i">{{ x.item_code }}: {{ x.why }}{{ x.outcome === 'block' ? t(' (its lots cannot be inspected until it is approved)') : '' }}</li></ul>
        <RouterLink to="/quality/suppliers" class="wq-link">{{ t('Approved suppliers') }}</RouterLink>
      </div>
    </template>
    <template v-else-if="d.doctype === 'Customer Message'">
      <p class="mt-3 text-sm text-ink-gray-6"><b class="text-ink-gray-8">{{ t('To:') }}</b> {{ d.payload.customer }} · <b class="text-ink-gray-8">{{ t('Subject:') }}</b> {{ d.payload.subject }}</p>
      <pre class="mt-2 whitespace-pre-wrap rounded-3 bg-surface-gray-1 p-3 font-sans text-p-sm text-ink-gray-8">{{ d.payload.body }}</pre>
      <Button v-if="d.status === 'confirmed'" class="mt-3" icon-left="lucide-copy" :label="copied === d.id ? t('Copied') : t('Copy to send')" @click="copy(d)" />
    </template>
    <template v-else-if="d.doctype === 'Nonconformance Report'">
      <p class="mt-3 text-base font-medium text-ink-gray-8">{{ d.payload.title }}</p><p class="mt-1 text-p-sm text-ink-gray-7">{{ d.payload.description }}</p>
    </template>
    <template v-else-if="d.doctype === 'Supplier'">
      <p class="mt-3 text-base font-medium text-ink-gray-8">{{ d.payload.supplier_name }}</p>
      <pre class="mt-1 whitespace-pre-wrap font-sans text-p-sm text-ink-gray-7">{{ d.payload.supplier_details }}</pre>
    </template>
    <pre v-else class="mt-3 whitespace-pre-wrap rounded-3 bg-surface-gray-1 p-3 text-xs text-ink-gray-7">{{ JSON.stringify(d.payload, null, 2) }}</pre>
    <p v-if="d.erp_url" class="mt-3 text-sm text-ink-gray-6">{{ t('In ERPNext:') }} <a :href="d.erp_url" target="_blank" rel="noopener" class="wq-link">{{ d.erp_name }} ↗</a> {{ t('(submit it there)') }}</p>
    <p v-if="d.record" class="mt-3 text-sm text-ink-gray-6">{{ t('Recorded as {record}', { record: d.record }) }}</p>
    <p v-if="d.error" class="wq-error mt-3 text-sm">{{ d.error }}</p>
    <div v-if="d.status === 'pending' || d.status === 'failed'" data-help="drafts-decide" class="mt-4 flex flex-wrap items-center gap-2 border-t border-outline-gray-1 pt-4">
      <Button variant="solid" :label="t('Confirm')" @click="act(d, 'confirm')" />
      <input v-model="notes[d.id]" class="wq-input max-w-xs" :placeholder="t('Reason, if rejecting')">
      <Button :label="t('Reject')" @click="act(d, 'reject')" />
      <span class="wq-muted">{{ t(WHAT[d.doctype]) }}</span>
    </div>
  </article>
</template>
