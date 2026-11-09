<script setup>
// The parts manual of an assembly (round 124, 27c): what stops making it, the editions (each frozen when made, with
// its PDF), and read-only links for dealers: the address shown once when made, revocable, views counted.
import { ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { api } from '../api'
import { t } from '../i18n'

const props = defineProps({ partId: { type: Number, required: true } })
const v = ref(null)
const error = ref('')
const busy = ref(false)
const label = ref('')
const made = ref('')
const when = (x) => x?.slice(0, 16).replace('T', ' ') || '–'

async function load() { error.value = ''; try { v.value = await api(`/api/plm/manuals/part/${props.partId}`) } catch (e) { error.value = e.message } }
watch(() => props.partId, load, { immediate: true })
async function generate() {
  error.value = ''; busy.value = true
  try { v.value = await api(`/api/plm/manuals/part/${props.partId}`, { method: 'POST', body: {} }) } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function addLink() {
  error.value = ''; made.value = ''
  try {
    const r = await api(`/api/plm/manuals/part/${props.partId}/links`, { method: 'POST', body: { label: label.value } })
    made.value = `${location.origin}/m/${r.token}`; label.value = ''
    await load()
  } catch (e) { error.value = e.message }
}
async function revoke(id) {
  error.value = ''
  try { v.value = { ...v.value, ...(await api(`/api/plm/manual-links/${id}/revoke`, { method: 'POST', body: {} })) } } catch (e) { error.value = e.message }
}
</script>

<template>
  <section data-help="plm-manual" class="wq-panel mb-5 p-5">
    <h2 class="wq-h2">{{ t('Parts manual') }}</h2>
    <p v-if="error" class="wq-error mb-3">{{ error }}</p>
    <template v-if="v">
      <div class="text-sm">
        <p v-if="v.readiness.not_released.length" class="text-ink-red-7">{{ t('Not released yet, so no manual:') }}
          <span v-for="x in v.readiness.not_released" :key="x.code" class="me-2">
            <RouterLink v-if="x.bom" :to="`/plm/boms/${x.bom}`" class="wq-link">{{ x.code }}</RouterLink><template v-else>{{ x.code }}</template> {{ x.name }}</span></p>
        <p v-else>{{ t('{n} sections: this assembly, then each assembly below it.', { n: v.readiness.boms.length }) }}</p>
        <p v-if="v.readiness.no_picture.length" class="text-ink-amber-7">{{ t('No exploded view yet (the table only):') }}
          <span v-for="x in v.readiness.no_picture" :key="x.bom" class="me-2"><RouterLink :to="`/plm/boms/${x.bom}/explode`" class="wq-link">{{ x.code }}</RouterLink> {{ x.name }}</span></p>
        <p v-if="v.readiness.names_open" class="text-ink-amber-7">{{ t('{n} English names not confirmed: those parts show the Chinese name, marked “to be confirmed”.', { n: v.readiness.names_open }) }}</p>
      </div>
      <Button v-if="v.can_edit" class="mt-3" variant="solid" :loading="busy" :disabled="!v.readiness.ok" :label="t('Make a new edition')" @click="generate" />

      <h3 class="mt-5 mb-2 text-base font-medium">{{ t('Editions') }}</h3>
      <p v-if="!v.editions.length" class="wq-muted">{{ t('None.') }}</p>
      <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('manual::Edition') }}</th><th>{{ t('Sections') }}</th><th>{{ t('manual::Changes') }}</th><th>{{ t('Made by') }}</th><th>{{ t('Made at') }}</th><th /></tr></thead>
        <tbody><tr v-for="e in v.editions" :key="e.id"><td><RouterLink :to="`/plm/manuals/${e.id}`" class="wq-link">{{ t('Edition {n}', { n: e.edition }) }}</RouterLink></td>
          <td>{{ e.pages }}</td><td>{{ e.edition === 1 ? '–' : e.changes }}</td><td>{{ e.created_by }}</td><td>{{ when(e.created_at) }}</td>
          <td><a :href="`/api/plm/manuals/${e.id}/pdf`" target="_blank" class="wq-link">PDF</a></td></tr></tbody></table>

      <h3 class="mt-5 mb-2 text-base font-medium">{{ t('Links for dealers') }}</h3>
      <p class="mb-2 text-sm text-ink-gray-6">{{ t('Anyone with the address sees the newest edition: pictures, tables and the PDF, never the 3D models. No sign-in.') }}</p>
      <p v-if="made" class="mb-2 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-sm text-ink-green-7">{{ t('The address, shown only now: copy it.') }}
        <input :value="made" readonly class="wq-input mt-1 w-full font-mono" @focus="$event.target.select()"></p>
      <table v-if="v.links.length" class="wq-table mb-2 text-sm"><thead><tr><th>{{ t('manual::For') }}</th><th>{{ t('Made by') }}</th><th>{{ t('Views') }}</th><th>{{ t('Last opened') }}</th><th /></tr></thead>
        <tbody><tr v-for="l in v.links" :key="l.id"><td>{{ l.label || '–' }}</td><td>{{ l.created_by }} {{ when(l.created_at) }}</td><td>{{ l.views }}</td><td>{{ when(l.last_view_at) }}</td>
          <td><span v-if="l.revoked_at" class="text-ink-gray-5">{{ t('Revoked {when}', { when: when(l.revoked_at) }) }}</span>
            <button v-else-if="v.can_release" class="text-ink-red-7" @click="revoke(l.id)">{{ t('manual::Revoke') }}</button></td></tr></tbody></table>
      <form v-if="v.can_release && v.editions.length" class="flex flex-wrap items-end gap-2" @submit.prevent="addLink">
        <input v-model="label" class="wq-input w-64" :placeholder="t('Who it is for, e.g. a dealer')">
        <Button type="submit" :label="t('Make a link')" />
      </form>
    </template>
  </section>
</template>
