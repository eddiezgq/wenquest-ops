<script setup>
// Cause analyses on a nonconformance report, a CAPA or a complaint (ADR-0022, 22b): the ones made, and starting a
// fishbone or a 5 Why while the record can still take a root cause.
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import { api } from '../api'

const props = defineProps({ kind: String, id: [Number, String], status: String })
const router = useRouter()
const data = ref(null)
const error = ref('')
const method = ref('fishbone')
const THEME = { open: 'blue', concluded: 'green', cancelled: 'gray' }

async function load() {
  try { data.value = await api(`/api/quality/causes/for/${props.kind}/${props.id}`) } catch (e) { error.value = e.message }
}
watch(() => [props.id, props.status], load, { immediate: true })

async function start() {
  error.value = ''
  try {
    const a = await api('/api/quality/causes', { method: 'POST', body: { kind: props.kind, ref_id: Number(props.id), method: method.value } })
    router.push(`/quality/causes/${a.id}`)
  } catch (e) { error.value = e.message }
}
</script>

<template>
  <section v-if="data && (data.analyses.length || data.can_start)" data-help="cause-start" class="wq-panel mt-5 p-5">
    <h2 class="wq-h2">Cause analysis</h2>
    <p v-if="error" class="wq-error mb-3">{{ error }}</p>
    <ul v-if="data.analyses.length" class="mb-3 text-base">
      <li v-for="a in data.analyses" :key="a.id" class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 py-2">
        <RouterLink :to="`/quality/causes/${a.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ a.name }}</RouterLink>
        <span class="text-ink-gray-6">{{ data.methods[a.method] }}</span>
        <Badge :theme="THEME[a.status]" :label="a.status" />
        <span class="min-w-0 flex-1 truncate text-ink-gray-6">{{ a.conclusion || a.problem }}</span>
      </li>
    </ul>
    <div v-if="data.can_start" class="flex flex-wrap items-center gap-2">
      <select v-model="method" class="wq-select"><option v-for="(l, k) in data.methods" :key="k" :value="k">{{ l }}</option></select>
      <Button icon-left="lucide-git-fork" label="Start an analysis" @click="start" />
      <span class="text-sm text-ink-gray-5">The signed conclusion is added to this record's root cause.</span>
    </div>
  </section>
</template>
