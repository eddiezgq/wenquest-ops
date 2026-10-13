<script setup>
// Ask the assistant (ADR-0008). It reads with your permissions and can only prepare drafts.
import { onMounted, ref } from 'vue'
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
  <h1>Assistant</h1>
  <p class="muted small" v-if="status">
    {{ status.engine === 'model' ? `Using ${status.model}.` : 'No AI model key is set, so built-in rules answer common questions.' }}
    The assistant sees what your role sees, cites what it used, and can only prepare drafts for someone to confirm.
  </p>
  <form class="search" @submit.prevent="ask()">
    <input v-model="question" placeholder="Ask about orders, stock, suppliers or quality" :disabled="busy">
    <button :disabled="busy">{{ busy ? 'Thinking…' : 'Ask' }}</button>
  </form>
  <p class="small"><a v-for="e in EXAMPLES" :key="e" href="#" class="chip" @click.prevent="ask(e)">{{ e }}</a></p>
  <p v-if="error" class="err">{{ error }}</p>
  <article v-for="r in runs" :key="r.id" class="card turn">
    <p class="q"><b>{{ r.question }}</b> <span class="muted small">{{ ago(r.created_at) }} · {{ r.engine }}</span></p>
    <Answer :text="r.answer" :unverified="r.unverified" />
    <p v-if="r.drafts.length" class="small">Prepared {{ r.drafts.length }} draft(s): <RouterLink to="/drafts">review and confirm</RouterLink></p>
    <details v-if="r.tool_calls.length" class="small"><summary>How it found this ({{ r.tool_calls.length }} steps)</summary>
      <ol><li v-for="(t, i) in r.tool_calls" :key="i"><code>{{ t.tool }}</code> {{ JSON.stringify(t.args) }}
        <span :class="t.ok ? 'muted' : 'err'"> — {{ t.summary }}</span></li></ol>
    </details>
    <p class="small muted" v-if="r.kind === 'ask'">Useful?
      <button class="link" :disabled="r.feedback === 1" @click="rate(r, true)">Yes</button> ·
      <button class="link" :disabled="r.feedback === -1" @click="rate(r, false)">No</button>
      <span v-if="r.feedback"> — thanks</span></p>
  </article>
</template>
