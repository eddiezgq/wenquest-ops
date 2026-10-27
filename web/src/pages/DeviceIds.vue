<script setup>
// Device identifiers (ADR-0020, 20b): the identifier the company got from its issuing agency for each item it
// labels. WenQuest Ops checks the form and the check digit; it never makes one up.
import { computed, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, objectPath } from '../api'
import { t } from '../i18n'

const v = ref(null)
const error = ref('')
const done = ref('')
const f = ref({ item: '', agency: 'gs1', gtin: '', lic: '', pcn: '', unit: '0' })
const open = ref('')
const hist = ref([])
async function load() { try { v.value = await api('/api/udi/items') } catch (e) { error.value = e.message } }
load()
const free = computed(() => (v.value?.erp_items || []))
async function save() {
  error.value = ''; done.value = ''
  try {
    const { item, ...rest } = f.value
    await api(`/api/udi/items/${encodeURIComponent(item)}`, { method: 'PUT', body: rest })
    done.value = t('Saved for {item}.', { item })
    await load()
  } catch (e) { error.value = e.message }
}
async function show(code) { open.value = open.value === code ? '' : code; hist.value = open.value ? await api(`/api/udi/items/${encodeURIComponent(code)}/history`) : [] }
</script>

<template>
  <PageTop :crumbs="[{ label: t('Production'), to: '/quality/production' }]"><template #title>{{ t('Device identifiers') }}</template></PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <p class="mb-4 max-w-3xl text-base text-ink-gray-7">{{ t('The device identifier of each item you label, as your issuing agency gave it: a GTIN from GS1, or your HIBCC labeler code with the product number and unit. Labels for released lots add the lot and dates. WenQuest Ops checks the check digit; it never makes an identifier up.') }}</p>
  <form v-if="v?.can_edit" data-help="udi-form" class="wq-panel mb-5 flex flex-wrap items-end gap-3 p-5" @submit.prevent="save">
    <label class="wq-field">{{ t('Item') }}<select v-model="f.item" class="wq-select"><option value="" /><option v-for="i in free" :key="i">{{ i }}</option></select></label>
    <label class="wq-field">{{ t('Agency') }}<select v-model="f.agency" class="wq-select"><option value="gs1">GS1</option><option value="hibcc">HIBCC</option></select></label>
    <label v-if="f.agency === 'gs1'" class="wq-field">GTIN<input v-model="f.gtin" class="wq-input font-mono" :placeholder="t('8, 12, 13 or 14 digits')"></label>
    <template v-else>
      <label class="wq-field">{{ t('Labeler code (LIC)') }}<input v-model="f.lic" class="wq-input w-28 font-mono" maxlength="4"></label>
      <label class="wq-field">{{ t('Product number') }}<input v-model="f.pcn" class="wq-input font-mono" maxlength="18"></label>
      <label class="wq-field">{{ t('Unit') }}<input v-model="f.unit" class="wq-input w-16 font-mono" maxlength="1"></label>
    </template>
    <Button type="submit" variant="solid" :label="t('Save')" :disabled="!f.item" />
  </form>
  <section v-if="v" data-help="udi-list" class="wq-panel p-5">
    <p v-if="!v.items.length" class="wq-muted">{{ t('No item has a device identifier yet.') }}</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Item') }}</th><th>{{ t('Agency') }}</th><th>{{ t('Device identifier') }}</th><th>{{ t('Set by') }}</th><th /></tr></thead>
      <tbody><template v-for="i in v.items" :key="i.item_code"><tr>
        <td><RouterLink :to="objectPath('Item', i.item_code)" class="wq-link">{{ i.item_code }}</RouterLink></td>
        <td><Badge :label="i.agency === 'gs1' ? 'GS1' : 'HIBCC'" /></td><td class="font-mono">{{ i.di }}</td>
        <td>{{ i.set_by }}</td><td><Button size="sm" variant="ghost" :label="t('History')" @click="show(i.item_code)" /></td></tr>
        <tr v-if="open === i.item_code"><td colspan="5" class="bg-surface-gray-1"><p v-for="h in hist" :key="h.at" class="text-sm">{{ h.at.slice(0, 16).replace('T', ' ') }} {{ h.email }} {{ h.action }}: {{ h.note }}</p></td></tr>
      </template></tbody></table>
  </section>
</template>
