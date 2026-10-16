<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { SEV, STATUS } from '../ui/themes'
import { api, objectPath } from '../api'
import { ago } from '../format'
import Chain from '../components/Chain.vue'

const route = useRoute()
const a = ref(null)
const note = ref('')
const error = ref('')
const NEXT = { open: ['ack', 'doing', 'closed'], ack: ['doing', 'closed'], doing: ['ack', 'closed'] }
const LABEL = { ack: 'Acknowledge', doing: 'Working on it', closed: 'Close' }

async function load() {
  try { a.value = await api(`/api/anomalies/${route.params.id}`) } catch (e) { error.value = e.message }
}
async function setStatus(s) {
  error.value = ''
  try {
    await api(`/api/anomalies/${a.value.id}/status`, { method: 'POST', body: { status: s, note: note.value } })
    note.value = ''
    await load()
  } catch (e) {
    error.value = e.message
  }
}
watch(() => route.params.id, load, { immediate: true })
</script>

<template>
  <PageTop :title="a ? a.title : 'Anomaly'" :crumbs="[{ label: 'Anomalies', to: '/anomalies' }]">
    <template v-if="a">
      <Badge :theme="SEV[a.severity]" :label="a.severity" size="lg" class="capitalize" />
      <Badge :theme="STATUS[a.status] || 'gray'" :label="a.status" variant="outline" size="lg" />
    </template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <template v-if="a">
    <section class="wq-panel p-5">
      <p class="wq-muted">{{ a.rule_name }}</p>
      <p class="mt-1 text-p-base text-ink-gray-9">{{ a.detail }}</p>
      <div data-help="anomaly-hint" class="mt-4 flex gap-3 rounded-4 bg-surface-gray-1 p-3">
        <span class="lucide-lightbulb mt-0.5 size-4 shrink-0 text-ink-amber-6" />
        <p class="text-p-sm text-ink-gray-8"><b>Suggested:</b> {{ a.hint }}
          <span class="text-ink-gray-5">(usually handled by: {{ a.owner?.replace('_', ' ') }})</span></p>
      </div>
      <p class="mt-4 text-sm text-ink-gray-6">About
        <RouterLink :to="objectPath(...a.subject)" class="wq-link">{{ a.subject[1] }}</RouterLink>
        <template v-for="r in a.related" :key="r.join()"> · <RouterLink :to="objectPath(...r)" class="wq-link">{{ r[1] }}</RouterLink></template></p>
      <div v-if="NEXT[a.status]" data-help="anomaly-status" class="mt-4 flex flex-wrap items-center gap-2">
        <input v-model="note" class="wq-input max-w-md flex-1" placeholder="Note (optional)">
        <Button v-for="s in NEXT[a.status]" :key="s" :label="LABEL[s]" :variant="s === 'closed' ? 'solid' : 'subtle'"
                @click="setStatus(s)" />
      </div>
      <p v-else class="mt-4 wq-muted">Status: {{ a.status }} {{ a.ended_at ? 'on ' + ago(a.ended_at) : '' }}</p>
    </section>

    <h2 data-help="anomaly-causes" class="wq-h2 mt-8">Causes and impact</h2>
    <Chain :explain="a.explain" />

    <h2 class="wq-h2 mt-8">Log</h2>
    <ol data-help="anomaly-log" class="wq-panel divide-y divide-outline-gray-1">
      <li v-for="(l, i) in a.log" :key="i" class="flex flex-wrap gap-x-3 px-4 py-2.5 text-sm">
        <span class="text-ink-gray-5">{{ ago(l.at) }}</span>
        <span class="font-medium text-ink-gray-8">{{ l.action }}</span>
        <span class="text-ink-gray-7">{{ l.email || 'WenQuest Ops' }}</span>
        <span class="text-ink-gray-5">{{ l.note }}</span></li>
    </ol>
  </template>
</template>
