<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, objectPath } from '../api'
import { t } from '../i18n'

const route = useRoute()
const router = useRouter()
const schema = ref([])
const q = ref(route.query.q || '')
const type = ref(route.query.type || '')
const results = ref([])
const listing = ref(null)
const error = ref('')

async function run() {
  error.value = ''
  router.replace({ query: { ...(q.value && { q: q.value }), ...(type.value && { type: type.value }) } })
  try {
    if (q.value) {
      listing.value = null
      results.value = await api(`/api/ont/search?limit=100&q=${encodeURIComponent(q.value)}&type=${type.value}`)
    } else if (type.value) {
      results.value = []
      listing.value = await api(`/api/ont/objects/${type.value}?limit=200`)
    } else {
      results.value = []
      listing.value = null
    }
  } catch (e) {
    error.value = e.message
  }
}
onMounted(async () => {
  schema.value = await api('/api/ont/schema')
  run()
})
watch(type, run)
const label = (ty) => schema.value.flatMap((d) => d.types).find((x) => x.name === ty)?.label || ty
</script>

<template>
  <PageTop :title="t('Objects')" />
  <form class="search mb-5 flex flex-wrap gap-2" @submit.prevent="run">
    <input v-model="q" class="wq-input min-w-[16rem] flex-1" :placeholder="t('Search by name, number or item code')" autofocus>
    <select v-model="type" class="wq-select" :aria-label="t('Type')">
      <option value="">{{ t('All types') }}</option>
      <optgroup v-for="d in schema" :key="d.domain" :label="d.label">
        <option v-for="ty in d.types" :key="ty.name" :value="ty.name" :disabled="ty.maturity !== 'have'">
          {{ ty.label }}{{ ty.maturity !== 'have' ? ' ' + t('(not synced yet)') : '' }}</option>
      </optgroup>
    </select>
    <Button type="submit" variant="solid" :label="t('Search')" icon-left="lucide-search" />
  </form>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <ul v-if="results.length" class="wq-panel divide-y divide-outline-gray-1">
    <li v-for="o in results" :key="o.type + o.key" class="flex items-center gap-3 px-4 py-2.5">
      <Badge :label="label(o.type)" class="shrink-0" />
      <RouterLink :to="objectPath(o.type, o.key)" class="text-base text-ink-gray-8 hover:underline">{{ o.title }}</RouterLink>
    </li>
  </ul>
  <p v-else-if="q" class="wq-muted">{{ t('Nothing found.') }}</p>
  <template v-if="listing">
    <p class="wq-muted mb-2">{{ t('{n} {type} objects', { n: listing.total, type: label(type) }) }}<span v-if="listing.total > 200">{{ t('; first 200') }}</span></p>
    <ul class="wq-panel divide-y divide-outline-gray-1">
      <li v-for="o in listing.objects" :key="o.key" class="px-4 py-2.5">
        <RouterLink :to="objectPath(o.type, o.key)" class="text-base text-ink-gray-8 hover:underline">{{ o.title }}</RouterLink></li>
    </ul>
  </template>
  <section v-if="!q && !type" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
    <article v-for="d in schema" :key="d.domain" class="wq-panel p-4">
      <h3 class="mb-2 text-base font-semibold text-ink-gray-9">{{ d.label }}</h3>
      <ul class="space-y-1.5 text-sm">
        <li v-for="ty in d.types" :key="ty.name" class="flex items-baseline justify-between gap-2">
          <a v-if="ty.maturity === 'have'" href="#" class="text-ink-gray-8 hover:underline" @click.prevent="type = ty.name">{{ ty.label }}</a>
          <span v-else class="text-ink-gray-4">{{ ty.label }} — {{ ty.maturity_label }}</span>
          <span class="shrink-0 text-xs text-ink-gray-4">{{ ty.source }}</span>
        </li>
      </ul>
    </article>
  </section>
</template>
