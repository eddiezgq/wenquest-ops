<script setup>
// The approved supplier list (ADR-0017, 17c): which supplier may deliver which item. Approving and re-evaluating are
// signed by someone other than the person who entered the supplier; lots from a supplier not approved for the item
// are not inspected.
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, objectPath } from '../api'
import { ago } from '../format'
import { t } from '../i18n'

const route = useRoute()
const v = ref(null)
const error = ref('')
const done = ref('')
const busy = ref('')
const form = ref({ supplier: '', item_code: '', risk: 'medium', basis: '', review_due: '' })
const open = ref(null)             // entry id whose actions are shown
const act = ref({})
const hist = ref({})
const pw = ref('')
const ST = { draft: 'gray', approved: 'green', conditional: 'amber', suspended: 'orange', disqualified: 'red' }
const supplierName = computed(() => Object.fromEntries((v.value?.suppliers || []).map((s) => [s.key, s.name])))

async function load() {
  try { v.value = await api('/api/asl') } catch (e) { error.value = e.message }
  if (route.hash) setTimeout(() => document.querySelector(route.hash)?.scrollIntoView({ block: 'center' }), 100)
}
load()
async function run(key, fn, message) {
  error.value = ''; done.value = ''; busy.value = key
  try { v.value = await fn(); done.value = message; open.value = null; pw.value = '' } catch (e) { error.value = e.message } finally { busy.value = '' }
}
const add = () => run('add', () => api('/api/asl', { method: 'POST', body: { ...form.value, item_code: form.value.item_code || null } }), t('Entered as a draft: someone else approves it.'))
function toggle(e) {
  open.value = open.value === e.id ? null : e.id
  act.value = { basis: e.basis, condition: e.condition, review_due: e.review_due || '', risk: e.risk, reason: '' }
  if (open.value) api(`/api/asl/${e.id}/history`).then((h) => { hist.value[e.id] = h }).catch(() => {})
}
const approve = (e) => run(`a${e.id}`, () => { const p = pw.value; pw.value = ''; return api(`/api/asl/${e.id}/approve`, { method: 'POST', body: { ...act.value, password: p } }) },
  e.status === 'approved' || e.status === 'conditional' ? t('Re-evaluated.') : t('Approved.'))
const save = (e) => run(`s${e.id}`, () => api(`/api/asl/${e.id}`, { method: 'PUT', body: { basis: act.value.basis, condition: act.value.condition, review_due: act.value.review_due, risk: act.value.risk } }), t('Saved.'))
const move = (e, what) => run(`m${e.id}`, () => api(`/api/asl/${e.id}/${what}`, { method: 'POST', body: { reason: act.value.reason } }),
  { suspend: t('Suspended.'), disqualify: t('Disqualified.'), requalify: t('Back to a draft, to approve again.') }[what])
const bring = () => run('bring', () => api('/api/asl/from-register', { method: 'POST' }),
  t('Brought in from the supplier approval register as drafts: someone other than you approves each one.'))
const editable = (e) => ['draft', 'suspended'].includes(e.status)
const approvable = (e) => ['draft', 'suspended', 'approved', 'conditional'].includes(e.status)
</script>

<template>
  <PageTop :crumbs="[{ label: t('Quality'), to: '/quality' }]">
    <template #title>{{ t('Approved suppliers') }}</template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="v">
    <p class="wq-muted mb-4 max-w-4xl">{{ t('Which supplier may deliver which item. An entry for an item counts before one for all the supplier\'s items.') }}
      <template v-if="v.settings.asl_enforced">{{ t('Lots from a supplier with no approved entry for the item cannot be inspected; conditional suppliers and overdue re-evaluations are flagged on the inspection.') }}</template>
      <template v-else>{{ t('The list is not enforced at incoming inspection (see the settings below).') }}</template>
      {{ t('Purchase order drafts show any item the supplier is not approved for.') }}</p>

    <section v-if="v.can_configure" data-help="asl-enter" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Enter a supplier') }}</h2>
      <form class="grid gap-3 md:grid-cols-5" @submit.prevent="add">
        <label class="wq-field">{{ t('Supplier') }}<select v-model="form.supplier" class="wq-select"><option value="" /><option v-for="s in v.suppliers" :key="s.key" :value="s.key">{{ s.name }}</option></select></label>
        <label class="wq-field">{{ t('Item') }}<select v-model="form.item_code" class="wq-select"><option value="">{{ t('All its items') }}</option><option v-for="i in v.items" :key="i.item_code" :value="i.item_code">{{ i.item_code }}</option></select></label>
        <label class="wq-field">{{ t('Risk') }}<select v-model="form.risk" class="wq-select"><option value="low">{{ t('low') }}</option><option value="medium">{{ t('medium') }}</option><option value="high">{{ t('high') }}</option></select></label>
        <label class="wq-field">{{ t('Re-evaluate by') }}<input v-model="form.review_due" type="date" class="wq-input"></label>
        <label class="wq-field md:col-span-5">{{ t('What the approval rests on') }}<textarea v-model="form.basis" rows="2" class="wq-input" :placeholder="t('Certificate, audit, first-article or sample inspection')" /></label>
        <div><Button type="submit" variant="solid" :label="t('Enter (draft)')" :disabled="!form.supplier" :loading="busy === 'add'" /></div>
      </form>
      <div v-if="v.register_entries" class="mt-4 flex flex-wrap items-end gap-2 border-t border-outline-gray-1 pt-4 text-sm">
        <p class="w-full text-ink-gray-7">{{ t('The supplier approval register (Quality system) has {n} entries. Bring the latest one per supplier in as a draft for all its items, with its basis and next review, for someone else to approve (a removed supplier comes in disqualified).', { n: v.register_entries }) }}</p>
        <Button :label="t('Bring in from the register')" :loading="busy === 'bring'" @click="bring" />
      </div>
    </section>

    <section data-help="asl-list" class="wq-panel mb-5 p-5">
      <p v-if="!v.entries.length" class="wq-muted">{{ t('No suppliers on the list yet.') }}</p>
      <div v-else class="overflow-x-auto"><table class="wq-table text-sm">
        <thead><tr><th>{{ t('Supplier') }}</th><th>{{ t('Item') }}</th><th>{{ t('Status') }}</th><th>{{ t('Risk') }}</th><th>{{ t('Re-evaluate by') }}</th><th>{{ t('Lots') }}</th><th>{{ t('Rejected') }}</th><th>{{ t('Open NCRs') }}</th><th /></tr></thead>
        <tbody><template v-for="e in v.entries" :key="e.id">
          <tr :id="`a${e.id}`" :class="route.hash === `#a${e.id}` ? 'bg-surface-amber-1' : ''">
            <td><RouterLink :to="objectPath('Supplier', e.supplier)" class="wq-link">{{ supplierName[e.supplier] || e.supplier }}</RouterLink></td>
            <td>{{ e.item_code || t('all items') }}</td>
            <td><Badge :theme="ST[e.status]" :label="t(e.status)" /></td><td>{{ t(e.risk) }}</td>
            <td class="whitespace-nowrap">{{ e.review_due || '–' }} <Badge v-if="e.review" :theme="e.review === 'overdue' ? 'red' : 'amber'" :label="e.review === 'overdue' ? t('overdue') : t('due soon')" /></td>
            <td>{{ e.lots }}</td><td>{{ e.reject_rate === null ? '–' : `${e.reject_rate}%` }}</td><td>{{ e.open_ncrs }}</td>
            <td><Button size="sm" variant="ghost" :label="open === e.id ? t('Close') : t('Open')" @click="toggle(e)" /></td>
          </tr>
          <tr v-if="open === e.id"><td colspan="9" data-help="asl-entry" class="bg-surface-gray-1">
            <p class="mb-2 text-ink-gray-7"><b>{{ t('Basis:') }}</b> {{ e.basis || '–' }}<template v-if="e.condition"> · <b>{{ t('Conditions:') }}</b> {{ e.condition }}</template>
              <template v-if="e.approved_by"> · {{ t('approved by {name} {when}', { name: e.approved_by, when: ago(e.approved_at) }) }}</template><template v-if="e.source"> · {{ e.source }}</template></p>
            <template v-if="v.can_configure">
              <div v-if="approvable(e)" class="mb-2 grid gap-2 md:grid-cols-4">
                <label class="wq-field md:col-span-2">{{ t('Basis') }}<textarea v-model="act.basis" rows="2" class="wq-input" /></label>
                <label class="wq-field">{{ t('Conditions (makes it conditional)') }}<textarea v-model="act.condition" rows="2" class="wq-input" /></label>
                <label class="wq-field">{{ t('Re-evaluate by *') }}<input v-model="act.review_due" type="date" class="wq-input"></label>
                <label class="wq-field">{{ t('Risk') }}<select v-model="act.risk" class="wq-select"><option value="low">{{ t('low') }}</option><option value="medium">{{ t('medium') }}</option><option value="high">{{ t('high') }}</option></select></label>
              </div>
              <div class="flex flex-wrap items-end gap-2">
                <label class="wq-field">{{ t('Reason') }}<input v-model="act.reason" class="wq-input w-72"></label>
                <template v-if="approvable(e)">
                  <label class="wq-field">{{ t('Your password') }}<input v-model="pw" type="password" class="wq-input w-40" autocomplete="current-password"></label>
                  <Button variant="solid" :label="['approved', 'conditional'].includes(e.status) ? t('Re-evaluate (sign)') : t('Approve (sign)')" :disabled="!pw || !act.reason.trim() || !act.review_due" :loading="busy === `a${e.id}`" @click="approve(e)" />
                </template>
                <Button v-if="editable(e)" :label="t('Save changes')" :loading="busy === `s${e.id}`" @click="save(e)" />
                <Button v-if="['approved', 'conditional'].includes(e.status)" :label="t('Suspend')" :disabled="!act.reason.trim()" @click="move(e, 'suspend')" />
                <Button v-if="e.status !== 'disqualified'" theme="red" :label="t('Disqualify')" :disabled="!act.reason.trim()" @click="move(e, 'disqualify')" />
                <Button v-if="e.status === 'disqualified'" :label="t('Qualify again (to a draft)')" :disabled="!act.reason.trim()" @click="move(e, 'requalify')" />
              </div>
            </template>
            <ul v-if="hist[e.id]" class="mt-3 text-ink-gray-6"><li v-for="(x, i) in hist[e.id].history" :key="i">{{ ago(x.at) }} · {{ x.email }} · {{ x.action }}{{ x.note ? `: ${x.note}` : '' }}</li>
              <li v-for="(s, i) in hist[e.id].signatures" :key="`s${i}`">{{ ago(s.at) }} · {{ t('signed by {name}', { name: s.name }) }}: {{ s.meaning }}</li></ul>
          </td></tr>
        </template></tbody></table></div>
    </section>

    <section data-help="asl-settings" class="wq-panel p-5">
      <h2 class="wq-h2">{{ t('Settings') }}</h2>
      <label v-for="(label, k) in v.setting_labels" :key="k" class="mb-2 flex items-center gap-2 text-sm">
        <input type="checkbox" class="form-checkbox" :checked="v.settings[k]" :disabled="!v.can_configure"
               @change="run(k, async () => { await api('/api/iqc/settings', { method: 'POST', body: { key: k, value: $event.target.checked } }); return api('/api/asl') }, t('Setting saved.'))">{{ label }}</label>
    </section>
  </template>
</template>
