<script setup>
// The quality system against a standard, ISO 9001 or ISO 13485 (ADR-0016, ADR-0017): each control point met, not
// met or unknown, from the records, with the records it rests on. Adopting a standard and saying what does not apply
// are signed.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, objectPath } from '../api'
import { ago } from '../format'
import { setStandard, standard } from '../standard'
import { t } from '../i18n'

const ws = inject('workspace')
const route = useRoute()
const router = useRouter()
const v = ref(null)
const error = ref('')
const done = ref('')
const busy = ref(false)
const edition = ref('2015')
const password = ref('')
const docs = ref([])
const open = ref(null)            // the control point whose actions are shown
const form = ref({ reason: '', password: '', doc: '' })
const filter = ref('all')
const S = { met: { theme: 'green', label: 'met' }, not_met: { theme: 'red', label: 'not met' },
  unknown: { theme: 'gray', label: 'unknown' }, not_applicable: { theme: 'blue', label: 'does not apply' } }
const ORDER = ['not_met', 'unknown', 'met', 'not_applicable']
const can = computed(() => v.value?.can_configure)
const canDocs = computed(() => ws.value?.user.permissions.includes('documents:view'))
const latest = computed(() => !route.query.evaluation && !route.query.day)
const pickDay = ref('')
const regs = ref([])
// rules that take linked documents; the last four read the module records first (17k)
const LINKED = ['linked_document', 'scope_declared', 'risk_managed', 'production_recorded', 'lots_traceable', 'release_signed']
const counts = computed(() => v.value?.evaluation?.counts || {})
const stds = ref([])

let asked = 0                     // only the latest load is shown, so a slow answer for another standard is dropped
async function load() {
  const mine = ++asked
  error.value = ''
  try {
    const q = route.query.evaluation ? `?evaluation=${route.query.evaluation}` : route.query.day ? `?day=${route.query.day}` : ''
    const list = await api('/api/qms')
    if (mine !== asked) return
    stds.value = list
    if (!list.some((s) => s.standard === standard.value)) { setStandard(list[0].standard); return }
    const page = await api(`/api/qms/${standard.value}${q}`)
    const rs = await api('/api/registers')
    if (mine !== asked) return
    v.value = page; regs.value = rs
    const ready = Object.entries(page.editions).filter(([, e]) => e.ready).map(([k]) => k)
    if (!ready.includes(edition.value)) edition.value = ready[ready.length - 1] || ''
  } catch (e) { if (mine === asked) error.value = e.message }
}
watch(() => [route.query.evaluation, route.query.day, standard.value], load, { immediate: true })
async function choose(s) {
  if (s === standard.value) return
  open.value = null; done.value = ''; error.value = ''; v.value = null
  if (!latest.value) await router.replace({ path: '/system' })      // an earlier check belongs to the old standard
  setStandard(s)
}
async function toggle(c) {
  open.value = open.value === c.id ? null : c.id
  if (open.value && LINKED.includes(ruleOf(c)) && canDocs.value) {
    try { docs.value = (await api('/api/docs?status=library')).filter((d) => d.status !== 'obsolete') } catch (e) { error.value = e.message }
  }
}

async function post(path, body, message) {
  error.value = ''; done.value = ''; busy.value = true
  try { v.value = await api(`/api/qms/${standard.value}${path}`, { method: 'POST', body }); stds.value = await api('/api/qms'); done.value = message; open.value = null; form.value = { reason: '', password: '', doc: '' } }
  catch (e) { error.value = e.message } finally { busy.value = false; password.value = '' }
}
const adopt = () => post('/enable', { edition: edition.value, password: password.value }, t('Adopted and checked against your records.'))
const evaluate = () => post('/evaluate', {}, t('Checked again against your records.'))
const declare = (c, applies) => post(`/controls/${c.id}/applies`, { applies, reason: form.value.reason, password: form.value.password },
  applies ? t('Recorded: it applies.') : t('Recorded: it does not apply.'))
const saveSetting = (key, value) => post('/settings', { key, value }, t('Setting saved and checked again.'))
const ruleOf = (c) => c.result?.rule || c.rule
const ruleOn = (c) => !c.switch || v.value.settings[c.switch]
const link = (c, id, linked) => post(`/controls/${c.id}/evidence`, { document_id: Number(id), linked }, linked ? t('Document linked.') : t('Link removed.'))

const docName = (d) => [d.number, d.title].filter(Boolean).join(' ') || d.original_name
const shown = (c) => filter.value === 'all' || c.result?.status === filter.value
const sorted = (cs) => [...cs].sort((a, b) => ORDER.indexOf(a.result?.status) - ORDER.indexOf(b.result?.status))
function to(p, c) {
  if (p.kind === 'ncr') return `/quality/ncr/${p.id}`
  if (p.kind === 'capa') return `/quality/capa/${p.id}`
  if (p.kind === 'document') return `/documents/${p.id}`
  if (p.kind === 'inspection') return objectPath('QualityInspection', p.id)
  if (p.kind === 'supplier') return objectPath('Supplier', p.id)
  if (p.kind === 'asl') return `/quality/suppliers#a${p.id}`
  if (p.kind === 'reading') return '/documents/control'
  if (p.kind === 'risk_file') return `/quality/risk/${p.id}`
  if (p.kind === 'production') return `/quality/production/${p.id}`
  if (p.kind === 'iqc') return `/quality/iqc/${p.id}`
  if (p.kind === 'entry' && String(p.id).startsWith('c')) return `/quality/complaints/${String(p.id).slice(1)}`
  if (p.kind === 'entry' && String(p.id).startsWith('g')) return `/quality/gauges/${String(p.id).slice(1)}`
  if (p.kind === 'entry' && String(p.id).startsWith('m')) return `/quality/reviews/${String(p.id).slice(1)}`
  if (p.kind === 'entry') return `/system/registers/${c?.register}#e${p.id}`
  return null
}
</script>

<template>
  <PageTop>
    <template #title>{{ t('Quality system') }}</template>
    <Button data-help="qms-setup" icon-left="lucide-settings-2" :label="t('Set up')" route="/system/setup" />
    <Button v-if="v?.enabled" data-help="qms-gaps" icon-left="lucide-list-todo" :label="t('Gap report')" route="/system/gaps" />
    <Button v-if="v?.enabled" data-help="qms-audit" icon-left="lucide-clipboard-check" :label="t('Audit checklist')" route="/system/audit" />
    <Button v-if="v?.enabled && latest && v.can_check" data-help="qms-check-now" icon-left="lucide-refresh-cw" :label="t('Check now')" :loading="busy" @click="evaluate" />
  </PageTop>
  <div v-if="stds.length > 1" data-help="qms-standards" class="standards mb-4 flex flex-wrap items-center gap-2" role="tablist" :aria-label="t('Standard')">
    <Button v-for="s in stds" :key="s.standard" :variant="s.standard === standard ? 'solid' : 'subtle'" role="tab"
            :aria-selected="s.standard === standard" @click="choose(s.standard)">
      {{ s.name }}<span v-if="s.adopted" class="ms-1 opacity-70">· {{ s.edition }}</span></Button>
  </div>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <template v-if="v && !v.enabled">
    <section data-help="qms-adopt" class="wq-panel max-w-3xl p-5">
      <h2 class="wq-h2">{{ v.label }}</h2>
      <p class="mb-3 text-base text-ink-gray-7">{{ t('WenQuest Ops turns the standard into control points and checks each one against your records: nonconformances, corrective actions, inspections and the document library. Each answer is met, not met or unknown, with the records behind it. Where there is nothing to look at yet, the answer is unknown, never met. The requirement summaries are our own words, not the standard\'s text, and this is not a certification.') }}</p>
      <template v-if="can">
        <div class="flex flex-wrap items-end gap-3">
          <label class="wq-field">{{ t('Edition') }}<select v-model="edition" class="wq-select">
            <option v-for="(e, k) in v.editions" :key="k" :value="k" :disabled="!e.ready">{{ e.label }}{{ e.ready ? '' : ` (${e.note})` }}</option></select></label>
          <label class="wq-field">{{ t('Your password to sign') }}<input v-model="password" type="password" class="wq-input w-56" autocomplete="current-password"></label>
          <Button variant="solid" :label="t('Adopt the standard (sign)')" :loading="busy" :disabled="!password" @click="adopt" />
        </div>
      </template>
      <p v-else class="wq-muted">{{ t('The owner or Quality adopts the standard.') }}</p>
    </section>
  </template>

  <template v-if="v?.enabled">
    <section class="wq-panel mb-5 p-5">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <h2 class="text-base font-semibold text-ink-gray-9">{{ v.edition_label }}</h2>
        <span class="text-sm text-ink-gray-5">{{ t('pack version {version} · adopted by {by} {when} · fingerprint {fp}…', { version: v.enabled.version, by: v.enabled.enabled_by, when: ago(v.enabled.enabled_at), fp: v.enabled.fingerprint.slice(0, 12) }) }}</span>
        <Badge v-if="v.newer_pack" theme="amber" :label="t('a newer pack is available')" />
      </div>
      <div v-if="v.newer_pack && can && latest" class="mb-3 flex flex-wrap items-end gap-2 text-sm">
        <span class="pb-2 text-ink-gray-7">{{ t('Pack version {version} adds checks; adopting it keeps everything you recorded.', { version: v.pack_version }) }}</span>
        <label class="wq-field">{{ t('Your password') }}<input v-model="password" type="password" class="wq-input w-44" autocomplete="current-password"></label>
        <Button :label="t('Adopt the newer pack (sign)')" :disabled="!password" :loading="busy" @click="edition = v.enabled.edition; adopt()" />
      </div>
      <p v-if="v.evaluation" class="mb-3 text-sm text-ink-gray-6">
        <template v-if="!latest">{{ t('Showing the check of {day} ({trigger})', { day: v.evaluation.day, trigger: t(v.evaluation.trigger) }) }}{{ v.shown_pack.id !== v.enabled.id ? t(', made under pack version {version}', { version: v.shown_pack.version }) : '' }}.
          <RouterLink to="/system" class="wq-link">{{ t('Show the latest') }}</RouterLink></template>
        <template v-else>{{ t('Checked {when} ({trigger}). Looks at the last {days} days; checked again every day.', { when: ago(v.evaluation.at), trigger: t(v.evaluation.trigger), days: v.settings.window_days }) }}</template></p>
      <div data-help="qms-filter" class="flex flex-wrap gap-2">
        <button v-for="k in ['all', ...ORDER]" :key="k" class="rounded-3 border px-3 py-1.5 text-sm"
                :class="filter === k ? 'border-outline-gray-4 bg-surface-gray-3 text-ink-gray-9' : 'border-outline-gray-2 text-ink-gray-7'" @click="filter = k">
          {{ k === 'all' ? t('All') : t(S[k].label) }} <span class="ms-1 font-semibold">{{ k === 'all' ? Object.values(counts).reduce((a, b) => a + b, 0) : counts[k] || 0 }}</span></button>
      </div>
    </section>

    <section data-help="qms-registers" class="registers wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Registers') }}</h2>
      <p class="wq-muted mb-3">{{ t('The records the standard asks for that are not nonconformances or documents. The checks read them.') }}</p>
      <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <RouterLink v-for="g in regs" :key="g.name" :to="`/system/registers/${g.name}`"
                    class="rounded-4 border border-outline-gray-2 p-3 hover:bg-surface-gray-1">
          <p class="text-base font-medium text-ink-gray-9">{{ g.label }}</p>
          <p class="text-sm text-ink-gray-5">{{ t('{n} entries', { n: (g.counts.open || 0) + (g.counts.signed || 0) }) }}<template v-if="g.signed && g.counts.open"> · {{ t('{n} to approve', { n: g.counts.open }) }}</template></p>
        </RouterLink>
      </div>
    </section>

    <section v-for="p in v.processes" v-show="p.controls.some(shown)" :key="p.id" data-help="qms-process" class="process wq-panel mb-4 p-5">
      <h2 class="wq-h2">{{ p.label }}</h2>
      <article v-for="c in sorted(p.controls).filter(shown)" :key="c.id" class="control border-t border-outline-gray-1 py-3 first:border-t-0">
        <div class="flex flex-wrap items-start gap-2">
          <Badge v-if="c.result" v-bind="S[c.result.status]" :label="t(S[c.result.status].label)" class="mt-0.5" />
          <div class="min-w-0 flex-1">
            <p class="text-base text-ink-gray-9">{{ c.summary }}</p>
            <p class="text-sm text-ink-gray-5">{{ v.name }} {{ c.clauses.join(', ') }}<template v-if="c.hint"> · {{ t('evidence: {hint}', { hint: c.hint }) }}</template></p>
            <p v-if="c.register" class="text-sm"><RouterLink :to="`/system/registers/${c.register}`" class="wq-link">{{ t('Open the register') }}</RouterLink></p>
            <p v-if="c.our_rule && ruleOn(c)" class="text-sm text-ink-gray-6">{{ t('Checked by the WenQuest Ops rule: {rule} (can be switched off in the settings below)', { rule: c.our_rule }) }}</p>
            <p v-else-if="c.our_rule" class="text-sm text-ink-gray-6">{{ t('Our rule is switched off: link the document that shows how you meet this.') }}</p>
            <p v-if="c.result" class="mt-1 text-sm text-ink-gray-7">{{ c.result.detail }}</p>
            <ul v-if="c.result?.problems.length" class="mt-1 flex flex-col gap-0.5 text-sm">
              <li v-for="x in c.result.problems" :key="`${x.kind}${x.id}${x.why}`">
                <RouterLink v-if="to(x, c)" :to="to(x, c)" class="wq-link">{{ x.label }}</RouterLink><span v-else>{{ x.label }}</span>
                <span class="text-ink-gray-6"> — {{ x.why }}</span></li>
              <li v-if="c.result.problem_count > c.result.problems.length" class="text-ink-gray-5">{{ t('and {n} more', { n: c.result.problem_count - c.result.problems.length }) }}</li>
            </ul>
            <p v-if="c.result?.evidence.length && c.result.status === 'met' && c.rule !== 'linked_document'" class="mt-1 text-sm text-ink-gray-6">{{ t('Records:') }}
              <template v-for="(x, i) in c.result.evidence" :key="x.id"><RouterLink :to="to(x, c)" class="wq-link">{{ x.label }}</RouterLink>{{ i < c.result.evidence.length - 1 ? ', ' : '' }}</template>
              <span v-if="c.result.evidence_count > c.result.evidence.length"> {{ t('and {n} more', { n: c.result.evidence_count - c.result.evidence.length }) }}</span></p>
          </div>
          <Button v-if="can && latest && (LINKED.includes(ruleOf(c)) || c.may_exclude)" size="sm" variant="ghost"
                  :label="open === c.id ? t('Close') : t('verb::Change')" @click="toggle(c)" />
        </div>
        <div v-if="open === c.id" class="mt-3 flex flex-col gap-3 rounded-4 bg-surface-gray-1 p-4 text-sm">
          <div v-if="LINKED.includes(ruleOf(c))">
            <p class="mb-1 text-ink-gray-7">{{ t('Documents linked as evidence:') }}</p>
            <ul class="mb-2"><li v-for="d in v.evidence[c.id] || []" :key="d.id">
              <RouterLink :to="`/documents/${d.id}`" class="wq-link">{{ d.name }}</RouterLink> <span class="text-ink-gray-5">{{ t('{status}, by {email}', { status: t(d.status.replace('_', ' ')), email: d.email }) }}</span>
              <Button size="sm" variant="ghost" :label="t('Remove')" @click="link(c, d.id, false)" /></li>
              <li v-if="!(v.evidence[c.id] || []).length" class="text-ink-gray-5">{{ t('None yet.') }}</li></ul>
            <div v-if="canDocs" class="flex flex-wrap items-end gap-2">
              <label class="wq-field">{{ t('Document') }}<select v-model="form.doc" class="wq-select max-w-md">
                <option value="" disabled>{{ t('Choose a document') }}</option>
                <option v-for="d in docs" :key="d.id" :value="d.id">{{ docName(d) }} ({{ t(d.status.replace('_', ' ')) }})</option></select></label>
              <Button :label="t('Link')" :disabled="!form.doc" @click="link(c, form.doc, true)" />
            </div>
          </div>
          <div v-if="c.may_exclude">
            <p class="mb-1 text-ink-gray-7">{{ v.applicability[c.id] ? t('Now: {state} ({reason})', { state: v.applicability[c.id].applies ? t('applies') : t('does not apply'), reason: v.applicability[c.id].reason }) : t('Say whether this applies to your company. Signed, with the reason.') }}</p>
            <div class="flex flex-wrap items-end gap-2">
              <label class="wq-field">{{ t('Reason') }}<input v-model="form.reason" class="wq-input w-80" :placeholder="t('e.g. we distribute; we do not design products')"></label>
              <label class="wq-field">{{ t('Your password') }}<input v-model="form.password" type="password" class="wq-input w-44" autocomplete="current-password"></label>
              <Button :label="t('Does not apply (sign)')" :disabled="!form.reason || !form.password" @click="declare(c, false)" />
              <Button :label="t('Applies (sign)')" :disabled="!form.reason || !form.password" @click="declare(c, true)" />
            </div>
          </div>
        </div>
      </article>
    </section>

    <section v-if="latest" data-help="qms-settings" class="settings wq-panel mb-4 p-5">
      <h2 class="wq-h2">{{ t('Settings') }}</h2>
      <p class="wq-muted mb-3">{{ t('Your company\'s values. The rules marked as ours are one way to show a requirement is met; switch them off and link your own procedure instead. Changes are recorded and the system is checked again.') }}</p>
      <div class="flex flex-col gap-2 text-sm">
        <div v-for="(spec, key) in v.setting_specs" :key="key" class="flex flex-wrap items-center gap-3">
          <span class="min-w-96 text-ink-gray-8">{{ spec.label }}</span>
          <template v-if="typeof spec.value === 'boolean'">
            <label class="inline-flex items-center gap-1.5"><input type="checkbox" class="form-checkbox" :checked="v.settings[key]" :disabled="!can"
              @change="saveSetting(key, $event.target.checked)">{{ v.settings[key] ? t('on') : t('off') }}</label>
          </template>
          <template v-else>
            <input type="number" class="wq-input w-24" :min="spec.min" :max="spec.max" :value="v.settings[key]" :disabled="!can"
                   @change="saveSetting(key, Number($event.target.value))">
          </template>
          <span v-if="v.settings[key] !== spec.value" class="text-ink-gray-5">{{ t('default {value}', { value: spec.value === true ? t('on') : spec.value === false ? t('off') : spec.value }) }}</span>
        </div>
      </div>
    </section>

    <section data-help="qms-history" class="wq-panel p-5">
      <h2 class="wq-h2">{{ t('Earlier checks') }}</h2>
      <div class="mb-3 flex flex-wrap items-end gap-2 text-sm">
        <label class="wq-field">{{ t('Show the check of a day') }}<input v-model="pickDay" type="date" class="wq-input w-44"></label>
        <Button :label="t('Show')" :disabled="!pickDay" @click="router.push(`/system?day=${pickDay}`)" />
      </div>
      <table class="wq-table text-sm"><thead><tr><th>{{ t('Day') }}</th><th>{{ t('Why') }}</th><th>{{ t('Met') }}</th><th>{{ t('Not met') }}</th><th>{{ t('Unknown') }}</th><th>{{ t('Does not apply') }}</th></tr></thead>
        <tbody><tr v-for="h in v.history.slice(0, 30)" :key="h.id" class="cursor-pointer" @click="router.push(`/system?evaluation=${h.id}`)">
          <td><RouterLink :to="`/system?evaluation=${h.id}`" class="wq-link">{{ h.day }}</RouterLink> <span class="text-ink-gray-5">{{ ago(h.at) }}</span></td>
          <td>{{ t(h.trigger) }}<span v-if="h.email" class="text-ink-gray-5"> {{ t('by {email}', { email: h.email }) }}</span></td>
          <td>{{ h.counts.met }}</td><td>{{ h.counts.not_met }}</td><td>{{ h.counts.unknown }}</td><td>{{ h.counts.not_applicable }}</td></tr></tbody></table>
    </section>
  </template>
</template>
