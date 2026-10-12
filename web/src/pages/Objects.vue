<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, objectPath } from '../api'

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
const label = (t) => schema.value.flatMap((d) => d.types).find((x) => x.name === t)?.label || t
</script>

<template>
  <h1>Objects</h1>
  <form class="search" @submit.prevent="run">
    <input v-model="q" placeholder="Search by name, number or item code" autofocus>
    <select v-model="type">
      <option value="">All types</option>
      <optgroup v-for="d in schema" :key="d.domain" :label="d.label">
        <option v-for="t in d.types" :key="t.name" :value="t.name" :disabled="t.maturity !== 'have'">
          {{ t.label }}{{ t.maturity !== 'have' ? ' (not synced yet)' : '' }}</option>
      </optgroup>
    </select>
    <button>Search</button>
  </form>
  <p v-if="error" class="err">{{ error }}</p>
  <ul v-if="results.length" class="list">
    <li v-for="o in results" :key="o.type + o.key">
      <span class="tag">{{ label(o.type) }}</span> <RouterLink :to="objectPath(o.type, o.key)">{{ o.title }}</RouterLink>
    </li>
  </ul>
  <p v-else-if="q" class="muted">Nothing found.</p>
  <template v-if="listing">
    <p class="muted">{{ listing.total }} {{ label(type) }} objects<span v-if="listing.total > 200">; first 200</span></p>
    <ul class="list">
      <li v-for="o in listing.objects" :key="o.key"><RouterLink :to="objectPath(o.type, o.key)">{{ o.title }}</RouterLink></li>
    </ul>
  </template>
  <section v-if="!q && !type" class="map">
    <article v-for="d in schema" :key="d.domain" class="card">
      <h3>{{ d.label }}</h3>
      <ul class="list small">
        <li v-for="t in d.types" :key="t.name">
          <a href="#" v-if="t.maturity === 'have'" @click.prevent="type = t.name">{{ t.label }}</a>
          <span v-else class="muted">{{ t.label }} — {{ t.maturity_label }}</span>
          <span class="muted"> · {{ t.source }}</span>
        </li>
      </ul>
    </article>
  </section>
</template>
