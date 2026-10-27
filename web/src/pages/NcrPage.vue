<script setup>
// One nonconformance report (ADR-0009, ADR-0010): the next step, signed approval and closing, 8D, corrective
// actions, signatures and history.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import Trail from '../ui/Trail.vue'
import OwnFields from '../components/OwnFields.vue'
import CauseLinks from '../components/CauseLinks.vue'
import { STATUS } from '../ui/themes'
import { api, objectPath } from '../api'
import { ago, fmt } from '../format'
import { t } from '../i18n'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const n = ref(null)
const error = ref('')
const f = ref({ containment: '', disposition: '', quantity: '', reason: '', note: '', password: '', cancel: '' })
const eight = ref({})
const capa = ref({ kind: 'corrective', title: '', description: '', risk: 'medium' })
const canEdit = computed(() => ws.value?.user.permissions.includes('quality:edit'))
const me = computed(() => ws.value?.user.email)
const activeTypes = computed(() => Object.entries(n.value?.dispositions || {}).filter(([, d]) => d.active))

async function load() {
  try { set(await api(`/api/quality/ncrs/${route.params.id}`)) } catch (e) { error.value = e.message }
}
function set(v) {
  n.value = v
  eight.value = { ...(v.eightd?.sections || {}) }
  f.value.password = ''
}
async function step(s, body = {}) {
  error.value = ''
  try { set(await api(`/api/quality/ncrs/${n.value.id}/${s}`, { method: 'POST', body })) } catch (e) { error.value = e.message }
}
async function newCapa() {
  error.value = ''
  try {
    const out = await api('/api/quality/capas', { method: 'POST', body: { ...capa.value, ncr_id: n.value.id } })
    router.push(`/quality/capa/${out.id}`)
  } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
const label = (s) => s.replaceAll('_', ' ')
</script>

<template>
  <PageTop :title="n ? `${n.name} ${n.title}` : t('Nonconformance')" :crumbs="[{ label: t('Quality'), to: '/quality?tab=ncrs' }]">
    <template v-if="n">
      <Badge :theme="n.severity === 'major' ? 'red' : n.severity ? 'gray' : 'amber'" variant="outline" :label="t(n.severity || 'severity unknown')" size="lg" />
      <Badge :theme="STATUS[n.status] || 'gray'" :label="t(label(n.status))" size="lg" />
    </template>
    <RouterLink v-if="n?.workflow" to="/quality?tab=workflows" class="hidden text-sm text-ink-gray-5 hover:underline sm:inline">{{ t('workflow v{n}', { n: n.workflow.version }) }}</RouterLink>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <template v-if="n">
    <div class="grid gap-6 lg:grid-cols-[3fr_2fr]">
      <section class="wq-panel p-5">
        <p class="text-p-base text-ink-gray-9">{{ n.description }}</p>
        <dl class="wq-dl mt-4">
          <template v-if="n.item_code"><dt>{{ t('Item') }}</dt><dd><RouterLink :to="objectPath('Item', n.item_code)" class="wq-link">{{ n.item_code }}</RouterLink></dd></template>
          <template v-if="n.supplier"><dt>{{ t('Supplier') }}</dt><dd><RouterLink :to="objectPath('Supplier', n.supplier)" class="wq-link">{{ n.supplier }}</RouterLink></dd></template>
          <template v-if="n.receipt"><dt>{{ t('Receipt') }}</dt><dd><RouterLink :to="objectPath('PurchaseReceipt', n.receipt)" class="wq-link">{{ n.receipt }}</RouterLink></dd></template>
          <template v-if="n.inspection"><dt>{{ t('Inspection') }}</dt><dd><RouterLink :to="objectPath('QualityInspection', n.inspection)" class="wq-link">{{ n.inspection }}</RouterLink></dd></template>
          <template v-if="n.quantity !== null"><dt>{{ t('Quantity') }}</dt><dd>{{ fmt(n.quantity) }}</dd></template>
          <dt>{{ t('Owner') }}</dt><dd>{{ n.owner || t('not assigned') }} <span class="text-sm text-ink-gray-5">{{ t('(opened by {name})', { name: n.created_by }) }}</span></dd>
          <template v-if="n.containment"><dt>{{ t('Containment') }}</dt><dd>{{ n.containment }}</dd></template>
          <template v-if="n.disposition"><dt>{{ t('Disposition') }}</dt><dd>{{ n.dispositions[n.disposition]?.name }}, {{ fmt(n.disposition_qty) }} — {{ n.disposition_reason }}
            <span class="text-sm text-ink-gray-5">{{ n.approved_by ? t('(submitted by {name}, approved by {approver})', { name: n.disposition_by, approver: n.approved_by }) : t('(submitted by {name})', { name: n.disposition_by }) }}</span></dd></template>
          <template v-if="n.cancel_reason"><dt>{{ t('Cancelled because') }}</dt><dd>{{ n.cancel_reason }}</dd></template>
          <template v-if="n.source_doc"><dt>{{ t('From the ledger') }}</dt><dd><RouterLink :to="`/documents/${n.source_doc}`" class="wq-link">{{ t('row {n}', { n: n.source_row }) }}</RouterLink>
            <span v-if="n.external_no" class="text-sm text-ink-gray-5"> {{ n.reported_on ? t('(there: {no}, reported {date})', { no: n.external_no, date: n.reported_on }) : t('(there: {no})', { no: n.external_no }) }}</span></dd></template>
          <template v-if="!n.severity && canEdit && !['closed', 'cancelled'].includes(n.status)"><dt>{{ t('Severity') }}</dt><dd class="flex items-center gap-2">
            <span class="text-ink-amber-7">{{ t('unknown —') }}</span>
            <Button size="sm" :label="t('Minor')" @click="step('update', { severity: 'minor' })" /><Button size="sm" :label="t('Major')" @click="step('update', { severity: 'major' })" /></dd></template>
        </dl>
        <p class="mt-4 text-sm"><RouterLink :to="objectPath('Nonconformance', n.name)" class="wq-link">{{ t('Object page and links') }}</RouterLink></p>
      </section>

      <section v-if="canEdit && !['closed', 'cancelled'].includes(n.status)" data-help="ncr-next-step" class="wq-panel h-fit p-5">
        <template v-if="n.status === 'open'">
          <h3 class="text-base font-semibold text-ink-gray-9">{{ t('Contain') }}</h3><p class="wq-muted mt-1">{{ t('What was done so bad parts go no further?') }}</p>
          <div class="mt-3 grid gap-2"><input v-model="f.containment" class="wq-input" :placeholder="t('e.g. lot moved to QC Hold, open orders checked')">
            <div><Button variant="solid" :label="t('Save containment')" @click="step('contain', { containment: f.containment })" /></div></div>
        </template>
        <template v-if="n.status === 'contained'">
          <h3 class="text-base font-semibold text-ink-gray-9">{{ t('Disposition') }}</h3>
          <div class="mt-3 grid gap-2"><select v-model="f.disposition" class="wq-select"><option value="" disabled>{{ t('Type') }}</option>
            <option v-for="[k, d] in activeTypes" :key="k" :value="k">{{ d.requires_approval ? t('{name} (needs approval)', { name: d.name }) : d.name }}</option></select>
            <input v-model="f.quantity" class="wq-input" type="number" min="0" step="any" :placeholder="t('Quantity')">
            <input v-model="f.reason" class="wq-input" :placeholder="t('Reason')">
            <div><Button variant="solid" :label="t('Submit disposition')" @click="step('disposition', { disposition: f.disposition, quantity: f.quantity === '' ? null : Number(f.quantity), reason: f.reason })" /></div></div>
        </template>
        <template v-if="n.status === 'pending_approval'">
          <h3 class="text-base font-semibold text-ink-gray-9">{{ t('Approve the disposition') }}</h3>
          <p v-if="n.disposition_by === me" class="wq-muted mt-1">{{ t('You submitted it; someone else must approve it.') }}</p>
          <div v-else class="mt-3 grid gap-2"><input v-model="f.password" class="wq-input" type="password" :placeholder="t('Your password to sign')" autocomplete="current-password">
            <div><Button variant="solid" icon-left="lucide-pen-line" :label="t('Approve (sign)')" @click="step('approve', { password: f.password })" /></div>
            <input v-model="f.reason" class="wq-input mt-2" :placeholder="t('Reason, if not approving')"><div><Button :label="t('Not approved')" @click="step('reject-disposition', { reason: f.reason })" /></div></div>
        </template>
        <template v-if="n.status === 'dispositioned'">
          <h3 class="text-base font-semibold text-ink-gray-9">{{ t('Close') }}</h3><p v-if="n.severity === 'major'" class="wq-muted mt-1">{{ t('A major report closes when a linked corrective action is closed.') }}</p>
          <div class="mt-3 grid gap-2"><input v-model="f.note" class="wq-input" :placeholder="t('Closing note')"><input v-model="f.password" class="wq-input" type="password" :placeholder="t('Your password to sign')" autocomplete="current-password">
            <div><Button variant="solid" icon-left="lucide-pen-line" :label="t('Close (sign)')" @click="step('close', { note: f.note, password: f.password })" /></div></div>
        </template>
        <div class="mt-5 flex gap-2 border-t border-outline-gray-1 pt-4"><input v-model="f.cancel" class="wq-input flex-1" :placeholder="t('Reason to cancel')">
          <Button theme="red" :label="t('Cancel the report')" @click="step('cancel', { reason: f.cancel })" /></div>
      </section>
    </div>

    <h2 data-help="ncr-8d" class="wq-h2 mt-8 flex items-center gap-2">8D <Badge v-if="n.eightd?.complete" theme="green" :label="t('complete')" /></h2>
    <div class="wq-panel p-5">
      <div class="grid gap-4 md:grid-cols-2">
        <label v-for="(lbl, k) in n.sections" :key="k" class="wq-field">{{ lbl }}
          <textarea v-model="eight[k]" class="wq-textarea" :disabled="!canEdit || n.eightd?.complete || ['closed', 'cancelled'].includes(n.status)" rows="2"></textarea></label>
      </div>
      <div v-if="canEdit && !n.eightd?.complete && !['closed', 'cancelled'].includes(n.status)" class="mt-4 flex flex-wrap items-center gap-2 border-t border-outline-gray-1 pt-4">
        <Button :label="t('Save 8D')" @click="step('8d', { sections: eight })" />
        <input v-model="f.password" class="wq-input max-w-56" type="password" :placeholder="t('Your password to sign')" autocomplete="current-password">
        <Button variant="solid" icon-left="lucide-pen-line" :label="t('Mark 8D complete (sign)')" @click="step('8d-complete', { password: f.password })" />
      </div>
    </div>

    <h2 class="wq-h2 mt-8">{{ t('Corrective and preventive actions') }}</h2>
    <ul v-if="n.capas.length" class="wq-panel mb-3 divide-y divide-outline-gray-1">
      <li v-for="c in n.capas" :key="c.id" class="flex items-center gap-3 px-4 py-2.5">
        <RouterLink :to="`/quality/capa/${c.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ c.name }} {{ c.title }}</RouterLink>
        <span class="text-sm capitalize text-ink-gray-5">{{ t(c.kind) }}</span>
        <Badge :theme="STATUS[c.status] || 'gray'" :label="t(label(c.status))" class="ms-auto" /></li>
    </ul>
    <form v-if="canEdit && !['closed', 'cancelled'].includes(n.status)" data-help="ncr-open-capa" class="flex flex-wrap gap-2" @submit.prevent="newCapa">
      <select v-model="capa.kind" class="wq-select"><option value="corrective">{{ t('Corrective') }}</option><option value="preventive">{{ t('Preventive') }}</option></select>
      <input v-model="capa.title" class="wq-input max-w-64" :placeholder="t('Title')" required><input v-model="capa.description" class="wq-input max-w-80" :placeholder="t('Problem')">
      <select v-model="capa.risk" class="wq-select"><option value="low">{{ t('Low risk') }}</option><option value="medium">{{ t('Medium risk') }}</option><option value="high">{{ t('High risk') }}</option></select>
      <Button type="submit" icon-left="lucide-plus" :label="t('Open corrective action')" />
    </form>

    <OwnFields :record="n" kind="ncr" :can-edit="canEdit" @changed="set" />
    <CauseLinks kind="ncr" :id="n.id" :status="n.status" />
    <h2 data-help="ncr-signatures" class="wq-h2 mt-8">{{ t('Signatures') }}</h2>
    <Trail :items="n.signatures" kind="signatures" />
    <h2 class="wq-h2 mt-8">{{ t('History') }}</h2>
    <Trail :items="n.history" />
  </template>
</template>
