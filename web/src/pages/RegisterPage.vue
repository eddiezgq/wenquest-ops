<script setup>
// One quality register (ADR-0016, 16b): its entries, a form built from the register's fields, approval with a
// password for signed registers, voiding with a reason. The fields come from the process pack.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { ago } from '../format'
import { t } from '../i18n'

const route = useRoute()
const r = ref(null)
const error = ref('')
const done = ref('')
const form = ref({})
const editing = ref(null)          // entry id being changed, or null for a new one
const showVoid = ref(false)
const password = ref('')
const reason = ref('')
const signing = ref(null)
const voiding = ref(null)
const busy = ref(false)
const fields = computed(() => Object.entries(r.value?.spec.fields || {}))
const columns = computed(() => fields.value.filter(([, f]) => f.type !== 'longtext').slice(0, 6))
const longs = computed(() => fields.value.filter(([, f]) => f.type === 'longtext'))
const shown = computed(() => (r.value?.entries || []).filter((e) => showVoid.value || e.status !== 'void'))
const STATUS = { open: { theme: 'gray', label: 'recorded' }, signed: { theme: 'green', label: 'approved' }, void: { theme: 'red', label: 'void' } }

function blank() { form.value = Object.fromEntries(fields.value.map(([k]) => [k, ''])); editing.value = null }
async function load() {
  error.value = ''
  try { r.value = await api(`/api/registers/${route.params.name}`); blank() } catch (e) { error.value = e.message }
  if (route.hash) setTimeout(() => document.querySelector(route.hash)?.scrollIntoView({ block: 'center' }), 100)
}
watch(() => route.params.name, load, { immediate: true })

async function call(path, method, body, message) {
  error.value = ''; done.value = ''; busy.value = true
  try { r.value = await api(path, { method, body }); done.value = message; blank(); signing.value = voiding.value = null; password.value = reason.value = '' }
  catch (e) { error.value = e.message } finally { busy.value = false }
}
function values() { return Object.fromEntries(Object.entries(form.value).map(([k, v]) => [k, v === '' ? null : v])) }
const save = () => editing.value
  ? call(`/api/register-entries/${editing.value}`, 'PUT', { values: values() }, t('Entry changed.'))
  : call(`/api/registers/${route.params.name}`, 'POST', { values: values() }, t('Entry recorded.'))
function edit(e) {
  form.value = Object.fromEntries(fields.value.map(([k, f]) => [k, e.values[k] === undefined ? '' : f.type === 'yesno' ? (e.values[k] ? 'yes' : 'no') : e.values[k]]))
  editing.value = e.id
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
const sign = (e) => call(`/api/register-entries/${e.id}/sign`, 'POST', { password: password.value }, t('Approved and locked.'))
const doVoid = (e) => call(`/api/register-entries/${e.id}/void`, 'POST', { reason: reason.value, password: password.value }, t('Entry void.'))
const show = (f, v) => (v === undefined || v === null ? '' : f.type === 'yesno' ? (v ? t('yes') : t('no'))
  : f.type === 'choice' ? t(`choice::${v}`) : String(v))
</script>

<template>
  <PageTop :crumbs="[{ label: t('Quality system'), to: '/system' }]">
    <template #title>{{ r?.spec.label || t('Register') }}</template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <template v-if="r">
    <section v-if="r.can_edit" data-help="register-form" class="entry-form wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ editing ? t('Change entry #{id}', { id: editing }) : t('Record an entry') }}</h2>
      <p v-if="r.spec.sign" class="wq-muted mb-3">{{ t('Entries are approved with a password ("{sign}") and then locked; a wrong one is voided with a reason.', { sign: r.spec.sign }) }}</p>
      <form class="grid gap-3 md:grid-cols-3" @submit.prevent="save">
        <label v-for="[k, f] in fields" :key="k" class="wq-field" :class="f.type === 'longtext' ? 'md:col-span-3' : ''">
          <span>{{ f.label }}<span v-if="f.required" class="text-ink-red-6"> *</span></span>
          <textarea v-if="f.type === 'longtext'" v-model="form[k]" rows="2" class="wq-input" />
          <select v-else-if="f.type === 'choice'" v-model="form[k]" class="wq-select"><option value="" />
            <option v-for="c in f.choices" :key="c" :value="c">{{ t(`choice::${c}`) }}</option></select>
          <select v-else-if="f.type === 'yesno'" v-model="form[k]" class="wq-select"><option value="" /><option value="yes">{{ t('yes') }}</option><option value="no">{{ t('no') }}</option></select>
          <input v-else v-model="form[k]" :type="f.type === 'date' ? 'date' : f.type === 'number' ? 'number' : 'text'" class="wq-input">
        </label>
        <div class="flex items-end gap-2 md:col-span-3">
          <Button type="submit" variant="solid" :loading="busy" :label="editing ? t('Save changes') : t('Record')" />
          <Button v-if="editing" :label="t('Cancel')" @click="blank" />
        </div>
      </form>
      <p class="wq-muted mt-3">{{ t('An old spreadsheet of these? Upload it under Documents, open it and choose to import it as "Register: {label}".', { label: r.spec.label }) }}</p>
    </section>

    <section data-help="register-entries" class="wq-panel p-5">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <h2 class="wq-h2 m-0">{{ t('Entries') }}</h2>
        <label class="inline-flex items-center gap-1.5 text-sm text-ink-gray-6"><input v-model="showVoid" type="checkbox" class="form-checkbox">{{ t('Show void entries') }}</label>
      </div>
      <p v-if="!shown.length" class="wq-muted">{{ t('Nothing recorded yet.') }}</p>
      <div v-else class="overflow-x-auto">
        <table class="wq-table text-sm">
          <thead><tr><th>#</th><th v-for="[k, f] in columns" :key="k">{{ f.label }}</th><th>{{ t('Status') }}</th><th /></tr></thead>
          <tbody>
            <template v-for="e in shown" :key="e.id">
              <tr :id="`e${e.id}`" :class="[e.status === 'void' ? 'text-ink-gray-4 line-through' : '', route.hash === `#e${e.id}` ? 'bg-surface-amber-1' : '']">
                <td>{{ e.id }}</td>
                <td v-for="[k, f] in columns" :key="k">{{ show(f, e.values[k]) }}</td>
                <td><Badge v-bind="{ ...STATUS[e.status], label: t(STATUS[e.status].label) }" />
                  <span v-if="e.source_doc" class="ms-1 text-ink-gray-5" :title="t('row {n}', { n: e.source_row })">{{ t('imported') }}</span>
                  <span v-if="e.signed_by" class="block text-ink-gray-5">{{ e.signed_by }} {{ ago(e.signed_at) }}</span></td>
                <td class="whitespace-nowrap">
                  <template v-if="r.can_edit && e.status !== 'void'">
                    <Button v-if="e.status === 'open'" size="sm" variant="ghost" :label="t('verb::Change')" @click="edit(e)" />
                    <Button v-if="e.status === 'open' && r.spec.sign" size="sm" variant="ghost" :label="t('Approve')" @click="signing = signing === e.id ? null : e.id; voiding = null" />
                    <Button size="sm" variant="ghost" :label="t('Void')" @click="voiding = voiding === e.id ? null : e.id; signing = null" />
                  </template>
                </td>
              </tr>
              <tr v-if="longs.some(([k]) => e.values[k]) || e.void_reason">
                <td />
                <td :colspan="columns.length + 2" class="text-ink-gray-6">
                  <template v-for="[k, f] in longs" :key="k"><span v-if="e.values[k]" class="me-4"><b>{{ f.label }}:</b> {{ e.values[k] }}</span></template>
                  <span v-if="e.void_reason" class="text-ink-red-7">{{ t('Void: {reason}', { reason: e.void_reason }) }}</span></td>
              </tr>
              <tr v-if="signing === e.id || voiding === e.id">
                <td />
                <td :colspan="columns.length + 2">
                  <div v-if="signing === e.id" class="flex flex-wrap items-end gap-2">
                    <label class="wq-field">{{ t('Your password to approve') }}<input v-model="password" type="password" class="wq-input w-56" autocomplete="current-password"></label>
                    <Button variant="solid" :label="t('Approve (sign)')" :disabled="!password" @click="sign(e)" />
                  </div>
                  <div v-else class="flex flex-wrap items-end gap-2">
                    <label class="wq-field">{{ t('Why is it void?') }}<input v-model="reason" class="wq-input w-96"></label>
                    <label v-if="e.status === 'signed'" class="wq-field">{{ t('Your password (it was approved)') }}<input v-model="password" type="password" class="wq-input w-48" autocomplete="current-password"></label>
                    <Button :label="t('Void the entry')" :disabled="!reason.trim() || (e.status === 'signed' && !password)" @click="doVoid(e)" />
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>
  </template>
</template>
