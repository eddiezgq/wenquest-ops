<script setup>
// One inspection plan (ADR-0017, 17b): its AQL and characteristics while a draft; enabled with a password and then
// frozen; a change is a new version.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { ago } from '../format'
import { t } from '../i18n'

const route = useRoute()
const router = useRouter()
const p = ref(null)
const error = ref('')
const done = ref('')
const busy = ref(false)
const aql = ref('')
const chars = ref([])
const note = ref('')
const password = ref('')
const draft = computed(() => p.value?.status === 'draft')

function fill(v) {
  p.value = v
  aql.value = String(v.aql)
  note.value = v.note || ''
  chars.value = v.characteristics.map((c) => ({ ...c, lsl: c.lsl ?? '', usl: c.usl ?? '' }))
}
async function load() {
  error.value = ''
  try { fill(await api(`/api/iqc/plans/${route.params.id}`)) } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })
async function call(path, method, body, message) {
  error.value = ''; done.value = ''; busy.value = true
  try {
    const v = await api(path, { method, body })
    if (v.id !== p.value.id) router.push(`/quality/iqc/plans/${v.id}`)
    fill(v); done.value = message; password.value = ''
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
const num = (v) => (v === '' || v === null ? null : Number(v))
const save = () => call(`/api/iqc/plans/${p.value.id}`, 'PUT', { aql: Number(aql.value), note: note.value,
  characteristics: chars.value.map((c) => ({ ...c, lsl: c.kind === 'measured' ? num(c.lsl) : null, usl: c.kind === 'measured' ? num(c.usl) : null, unit: c.kind === 'measured' ? c.unit : '' })) }, t('Saved.'))
const enable = () => call(`/api/iqc/plans/${p.value.id}/enable`, 'POST', { password: password.value, seen: p.value.updated_at }, t('Enabled: lots of this item are now inspected to this plan.'))
const discard = () => call(`/api/iqc/plans/${p.value.id}/discard`, 'POST', {}, t('Discarded.'))
const newVersion = () => call(`/api/iqc/plans/${p.value.id}/new-version`, 'POST', {}, t('A new draft version: change it, then have it enabled.'))
const add = () => chars.value.push({ name: '', kind: 'measured', lsl: '', usl: '', unit: '', method: '' })
const limits = (c) => c.kind === 'attribute' ? t('pass / fail') : [c.lsl !== null && c.lsl !== '' ? `≥ ${c.lsl}` : '', c.usl !== null && c.usl !== '' ? `≤ ${c.usl}` : ''].filter(Boolean).join(' ' + t('and') + ' ') + (c.unit ? ` ${c.unit}` : '')
</script>

<template>
  <PageTop :crumbs="[{ label: t('Incoming inspection'), to: '/quality/iqc?tab=plans' }]">
    <template #title>{{ p ? t('Plan for {item}, version {v}', { item: p.item_code, v: p.version }) : t('Plan') }}</template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="p">
    <section data-help="iqc-plan" class="wq-panel mb-5 p-5">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <Badge :theme="p.status === 'enabled' ? 'green' : draft ? 'amber' : 'gray'" :label="t(p.status)" />
        <span class="text-sm text-ink-gray-5">{{ t('drafted by {who} {when}', { who: p.created_by, when: ago(p.created_at) }) }}<template v-if="p.enabled_by"> · {{ t('enabled by {who} {when}', { who: p.enabled_by, when: ago(p.enabled_at) }) }}
          · {{ t('fingerprint {fp}', { fp: p.fingerprint.slice(0, 12) + '…' }) }}</template></span>
      </div>
      <template v-if="draft && p.can_edit">
        <div class="mb-3 flex flex-wrap items-end gap-3">
          <label class="wq-field">AQL<input v-model="aql" class="wq-input w-24" inputmode="decimal"></label>
          <label class="wq-field grow">{{ t('Note') }}<input v-model="note" class="wq-input"></label>
        </div>
        <div class="overflow-x-auto"><table class="chars wq-table text-sm">
          <thead><tr><th>{{ t('Characteristic') }}</th><th>{{ t('Kind') }}</th><th>{{ t('Lower limit') }}</th><th>{{ t('Upper limit') }}</th><th>{{ t('Unit') }}</th><th>{{ t('Method') }}</th><th /></tr></thead>
          <tbody><tr v-for="(c, i) in chars" :key="i">
            <td><input v-model="c.name" class="wq-input w-40"></td>
            <td><select v-model="c.kind" class="wq-select"><option value="measured">{{ t('measured') }}</option><option value="attribute">{{ t('pass / fail') }}</option></select></td>
            <td><input v-model="c.lsl" :disabled="c.kind !== 'measured'" class="wq-input w-24" inputmode="decimal"></td>
            <td><input v-model="c.usl" :disabled="c.kind !== 'measured'" class="wq-input w-24" inputmode="decimal"></td>
            <td><input v-model="c.unit" :disabled="c.kind !== 'measured'" class="wq-input w-20"></td>
            <td><input v-model="c.method" class="wq-input w-48"></td>
            <td><Button size="sm" variant="ghost" :label="t('Remove')" @click="chars.splice(i, 1)" /></td></tr></tbody></table></div>
        <div class="mt-3 flex flex-wrap gap-2">
          <Button :label="t('Add a characteristic')" icon-left="lucide-plus" @click="add" />
          <Button variant="solid" :label="t('Save')" :loading="busy" @click="save" />
          <Button :label="t('Discard the draft')" @click="discard" />
        </div>
        <div v-if="p.can_configure" data-help="iqc-plan-enable" class="mt-5 flex flex-wrap items-end gap-2 border-t border-outline-gray-1 pt-4">
          <p class="wq-muted w-full">{{ t('Save first. Enabling freezes the plan and retires the version in use.') }}<template v-if="p.settings.plan_by_other"> {{ t('Someone other than {who} enables it.', { who: p.created_by }) }}</template></p>
          <label class="wq-field">{{ t('Your password') }}<input v-model="password" type="password" class="wq-input w-48" autocomplete="current-password"></label>
          <Button variant="solid" :label="t('Enable (sign)')" :disabled="!password" :loading="busy" @click="enable" />
        </div>
      </template>
      <template v-else>
        <p class="mb-2 text-base">AQL {{ p.aql }}<template v-if="p.note"> · {{ p.note }}</template></p>
        <table class="wq-table text-sm"><thead><tr><th>{{ t('Characteristic') }}</th><th>{{ t('Limits') }}</th><th>{{ t('Method') }}</th></tr></thead>
          <tbody><tr v-for="c in p.characteristics" :key="c.name"><td>{{ c.name }}</td><td>{{ limits(c) }}</td><td>{{ c.method }}</td></tr></tbody></table>
        <Button v-if="p.can_edit && p.status !== 'discarded' && !p.versions.some((v) => v.status === 'draft')" class="mt-3" :label="t('Make a new version')" @click="newVersion" />
      </template>
    </section>
    <section class="wq-panel p-5 text-sm">
      <h2 class="wq-h2">{{ t('Versions and history') }}</h2>
      <ul class="mb-3"><li v-for="v in p.versions" :key="v.id"><RouterLink :to="`/quality/iqc/plans/${v.id}`" class="wq-link">{{ t('version {n}', { n: v.version }) }}</RouterLink> {{ t(v.status) }}</li></ul>
      <ul><li v-for="(x, i) in p.history" :key="i" class="text-ink-gray-7">{{ ago(x.at) }} · {{ x.email }} · {{ x.action }} {{ x.note }}</li>
        <li v-for="(s, i) in p.signatures" :key="`s${i}`" class="text-ink-gray-7">{{ ago(s.at) }} · {{ t('signed by {name} ({email}): {meaning}', { name: s.name, email: s.email, meaning: s.meaning }) }}</li></ul>
    </section>
  </template>
</template>
