<script setup>
// Ask the assistant (ADR-0008). It reads with your permissions and can only prepare drafts.
import { onMounted, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { ago } from '../format'
import Answer from '../components/Answer.vue'

const status = ref(null)
const question = ref('')
const busy = ref(false)
const runs = ref([])
const error = ref('')
const EXAMPLES = ['Which orders are late, and why?', 'What is short for open orders?',
  'How are our suppliers doing on time?', 'What needs my attention today?']

async function load() { runs.value = await api('/api/ai/runs?limit=20') }
onMounted(async () => {
  try { status.value = await api('/api/ai/status'); await load() } catch (e) { error.value = e.message }
})
async function ask(q) {
  if (q) question.value = q
  if (!question.value.trim()) return
  busy.value = true
  error.value = ''
  try {
    await api('/api/ai/ask', { method: 'POST', body: { question: question.value } })
    question.value = ''
    await load()
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function rate(r, useful) {
  await api(`/api/ai/runs/${r.id}/feedback`, { method: 'POST', body: { useful } })
  r.feedback = useful ? 1 : -1
}
</script>

<template>
  <PageTop title="Assistant">
    <Badge v-if="status" :theme="status.engine === 'model' ? 'violet' : 'gray'" variant="outline"
           :label="status.engine === 'model' ? status.model : 'Built-in rules'" />
  </PageTop>
  <p v-if="status" class="wq-muted mb-4">
    {{ status.engine === 'model' ? `Using ${status.model}.` : 'No AI model key is set, so built-in rules answer common questions.' }}
    The assistant sees what your role sees, cites what it used, and can only prepare drafts for someone to confirm.
  </p>
  <form class="search flex gap-2" @submit.prevent="ask()">
    <input v-model="question" class="wq-input flex-1" placeholder="Ask about orders, stock, suppliers or quality" :disabled="busy">
    <Button type="submit" variant="solid" :loading="busy" :label="busy ? 'Thinking…' : 'Ask'" icon-left="lucide-sparkles" />
  </form>
  <div class="mt-3 flex flex-wrap gap-2">
    <Button v-for="e in EXAMPLES" :key="e" size="sm" variant="outline" :label="e" @click="ask(e)" />
  </div>
  <p v-if="error" class="wq-error mt-4">{{ error }}</p>
  <article v-for="r in runs" :key="r.id" class="turn wq-panel mt-4 p-5">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <p class="text-base font-semibold text-ink-gray-9">{{ r.question }}</p>
      <span class="wq-muted">{{ ago(r.created_at) }} · {{ r.engine }}</span>
    </div>
    <Answer class="mt-2" :text="r.answer" :unverified="r.unverified" />
    <p v-if="r.drafts.length" class="mt-3 text-sm text-ink-gray-7">Prepared {{ r.drafts.length }} draft(s):
      <RouterLink to="/drafts" class="wq-link">review and confirm</RouterLink></p>
    <details v-if="r.tool_calls.length" class="mt-3 text-sm text-ink-gray-6">
      <summary class="cursor-pointer select-none">How it found this ({{ r.tool_calls.length }} steps)</summary>
      <ol class="mt-2 list-decimal space-y-1 ps-5">
        <li v-for="(t, i) in r.tool_calls" :key="i"><code class="rounded-3 bg-surface-gray-2 px-1">{{ t.tool }}</code>
          <span class="text-ink-gray-5"> {{ JSON.stringify(t.args) }}</span>
          <span :class="t.ok ? 'text-ink-gray-5' : 'text-ink-red-7'"> — {{ t.summary }}</span></li></ol>
    </details>
    <div v-if="r.kind === 'ask'" class="mt-3 flex items-center gap-1 text-sm text-ink-gray-5">Useful?
      <Button size="sm" variant="ghost" icon="lucide-thumbs-up" label="Yes" :disabled="r.feedback === 1" @click="rate(r, true)" />
      <Button size="sm" variant="ghost" icon="lucide-thumbs-down" label="No" :disabled="r.feedback === -1" @click="rate(r, false)" />
      <span v-if="r.feedback">thanks</span></div>
  </article>
</template>
