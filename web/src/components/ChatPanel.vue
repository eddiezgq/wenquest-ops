<script setup>
// The AI chat panel (ADR-0021): on every page, a conversation with the assistant that knows the page and the record
// on it. Same rules as the Assistant page (ADR-0008): it reads with your role, cites, and only prepares drafts.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import { api } from '../api'
import { t } from '../i18n'
import Answer from './Answer.vue'

const props = defineProps({ open: Boolean })
const emit = defineEmits(['update:open'])
const route = useRoute()
const KEY = 'wqo-chat-id'
const chat = ref(null)
const chats = ref([])
const status = ref(null)
const question = ref('')
const busy = ref(false)
const error = ref('')
const showList = ref(false)
const scroller = ref(null)
const input = ref(null)

// the record a page shows: its kind (as the assistant's get_record tool names it) and id
const PAGES = [
  [/^\/quality\/ncr\/(\d+)$/, 'ncr', 'nonconformance report'], [/^\/quality\/capa\/(\d+)$/, 'capa', 'corrective action'],
  [/^\/quality\/complaints\/(\d+)$/, 'complaint', 'complaint'], [/^\/quality\/changes\/(\d+)$/, 'change', 'change'],
  [/^\/quality\/risk\/(\d+)$/, 'risk_file', 'risk file'], [/^\/quality\/production\/(\d+)$/, 'production', 'production lot'],
  [/^\/quality\/recalls\/(\d+)$/, 'recall', 'recall'], [/^\/quality\/reviews\/(\d+)$/, 'review', 'management review'],
  [/^\/quality\/iqc\/(\d+)$/, 'iqc', 'incoming inspection'], [/^\/quality\/gauges\/(\d+)$/, 'gauge', 'gauge'],
  [/^\/documents\/(\d+)$/, 'document', 'document'],
]
const record = computed(() => {
  for (const [re, kind, label] of PAGES) {
    const m = route.path.match(re)
    if (m) return { kind, id: Number(m[1]), label }
  }
  return null
})
const SUGGEST = {
  ncr: ['Summarize this report', 'What is the next step, and who does it?', 'Draft a root cause statement for this report'],
  capa: ['Summarize this corrective action', 'Which of its actions are late?'],
  complaint: ['Summarize this complaint', 'What is still needed to close it?'],
  production: ['Summarize this lot', 'Which incoming lots went into it?'],
  recall: ['Summarize this recall', 'Who has not confirmed yet?'],
  review: ['Summarize the inputs of this review', 'What actions did it decide?'],
  iqc: ['Summarize this inspection'], gauge: ['When is this gauge due, and what did it measure?'],
  risk_file: ['Summarize the hazards in this file'], change: ['Summarize this change'], document: ['Summarize this document'],
}
const GENERAL = ['Which orders are late, and why?', 'What needs my attention today?', 'How are our suppliers doing on time?']
const suggestions = computed(() => (record.value ? SUGGEST[record.value.kind] || ['Summarize this'] : GENERAL))

function page() {
  const title = document.querySelector('main h1')?.textContent?.trim() || document.title
  return { path: route.path, title, ...(record.value ? { record: { kind: record.value.kind, id: record.value.id } } : {}) }
}
function remember(id) { try { localStorage.setItem(KEY, String(id)) } catch { /* only this tab remembers */ } }
async function scroll() { await nextTick(); scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: 'smooth' }) }

async function load(id) {
  error.value = ''
  try { chat.value = await api(`/api/ai/chats/${id}`); remember(id); showList.value = false; scroll() } catch { chat.value = null }
}
async function fresh() {
  error.value = ''
  try { chat.value = await api('/api/ai/chats', { method: 'POST' }); remember(chat.value.id); showList.value = false } catch (e) { error.value = e.message }
  nextTick(() => input.value?.focus())
}
async function list() { showList.value = !showList.value; if (showList.value) chats.value = await api('/api/ai/chats') }
async function ask(q) {
  const text = (q ?? question.value).trim()
  if (!text || busy.value) return
  if (!chat.value) await fresh()
  if (!chat.value) return
  busy.value = true
  error.value = ''
  question.value = ''
  chat.value.turns.push({ id: `pending-${Date.now()}`, question: text, pending: true })
  scroll()
  try {
    await api(`/api/ai/chats/${chat.value.id}/ask`, { method: 'POST', body: { question: text, page: page() } })
    await load(chat.value.id)
  } catch (e) {
    error.value = e.message
    chat.value.turns = chat.value.turns.filter((x) => !x.pending)
    question.value = text
  } finally { busy.value = false; nextTick(() => input.value?.focus()) }
}
function key(e) { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask() } }
function close() { emit('update:open', false) }
function shortcut(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') { e.preventDefault(); emit('update:open', !props.open) }
  if (e.key === 'Escape' && props.open) close()
}
// the Assistant page opens a past conversation here
function openChat(id) { emit('update:open', true); load(id) }
defineExpose({ openChat })

watch(() => props.open, async (o) => {
  if (!o) return
  if (!status.value) api('/api/ai/status').then((s) => { status.value = s }).catch(() => {})
  if (!chat.value) {
    let id = null
    try { id = localStorage.getItem(KEY) } catch { /* none */ }
    if (id) await load(id)
  }
  nextTick(() => input.value?.focus())
})
onMounted(() => window.addEventListener('keydown', shortcut))
onBeforeUnmount(() => window.removeEventListener('keydown', shortcut))
</script>

<template>
  <button v-if="!open" data-help="chat-open" class="chat-fab no-print" :aria-label="t('Ask the AI assistant (Ctrl+J)')" :title="t('Ask the AI assistant (Ctrl+J)')" @click="emit('update:open', true)">
    <span class="lucide-sparkles size-4" aria-hidden="true" /><span>{{ t('Ask AI') }}</span>
  </button>
  <Transition name="chat">
    <aside v-if="open" class="chat no-print" role="dialog" :aria-label="t('AI assistant')">
      <header class="flex items-center gap-2 border-b border-outline-gray-2 px-4 py-3">
        <span class="lucide-sparkles size-4 text-ink-gray-7" aria-hidden="true" />
        <h2 class="grow text-base font-semibold text-ink-gray-9">{{ t('Assistant') }}</h2>
        <Button size="sm" variant="ghost" icon="lucide-history" :aria-label="t('Earlier conversations')" :title="t('Earlier conversations')" @click="list" />
        <Button size="sm" variant="ghost" icon="lucide-square-pen" :aria-label="t('New conversation')" :title="t('New conversation')" @click="fresh" />
        <Button size="sm" variant="ghost" icon="lucide-x" :aria-label="t('Close')" :title="t('Close (Esc)')" @click="close" />
      </header>
      <div v-if="showList" class="border-b border-outline-gray-2 bg-surface-gray-1 px-2 py-2">
        <p v-if="!chats.length" class="px-2 py-1 text-sm text-ink-gray-5">{{ t('No earlier conversations.') }}</p>
        <button v-for="h in chats" :key="h.id" class="block w-full truncate rounded-3 px-2 py-1.5 text-left text-sm text-ink-gray-8 hover:bg-surface-gray-3"
                @click="load(h.id)">{{ h.title || t('New conversation') }}<span class="ms-2 text-ink-gray-4">{{ h.turns }}</span></button>
      </div>
      <div ref="scroller" class="grow overflow-y-auto px-4 py-4">
        <p v-if="status && status.engine !== 'model'" class="mb-3 rounded-4 bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-6">
          {{ t('No AI model key is set, so built-in rules answer common questions. Whoever runs the system can add one.') }}</p>
        <div v-if="!chat?.turns?.length" class="text-sm text-ink-gray-6">
          <p class="mb-3">{{ record ? t('Ask about this {label}, or anything else you may see.', { label: t(record.label) }) : t('Ask about orders, stock, suppliers or quality.') }}
            {{ t('Answers cite your records; anything to write becomes a draft for someone to confirm.') }}</p>
          <div class="flex flex-col items-start gap-2">
            <Button v-for="s in suggestions" :key="s" size="sm" variant="outline" :label="t(s)" @click="ask(s)" />
          </div>
        </div>
        <div v-for="turn in chat?.turns || []" :key="turn.id" class="mb-5">
          <p class="ms-auto mb-2 w-fit max-w-[85%] rounded-5 bg-surface-gray-3 px-3 py-2 text-base text-ink-gray-9">{{ turn.question }}</p>
          <p v-if="turn.pending" class="thinking text-sm text-ink-gray-5">{{ t('Looking at your records…') }}</p>
          <template v-else>
            <Answer :text="turn.answer" :unverified="turn.unverified" />
            <p v-if="turn.drafts?.length" class="mt-1 text-sm"><RouterLink to="/drafts" class="wq-link">{{ t('{n} draft(s) waiting for confirmation', { n: turn.drafts.length }) }}</RouterLink></p>
          </template>
        </div>
        <p v-if="error" class="wq-error">{{ error }}</p>
      </div>
      <form class="border-t border-outline-gray-2 p-3" @submit.prevent="ask()">
        <p v-if="record" class="mb-2 text-xs text-ink-gray-5">{{ t('Looking at this {label}', { label: t(record.label) }) }}</p>
        <div class="flex items-end gap-2">
          <textarea ref="input" v-model="question" rows="2" class="wq-input grow resize-none" :placeholder="t('Ask a question (Enter to send)')" :aria-label="t('Your question')" :disabled="busy" @keydown="key" />
          <Button type="submit" variant="solid" icon="lucide-arrow-up" :aria-label="t('Send')" :loading="busy" :disabled="!question.trim()" />
        </div>
      </form>
    </aside>
  </Transition>
</template>

<style scoped>
.chat-fab { position: fixed; right: 20px; bottom: 20px; z-index: 40; display: flex; align-items: center; gap: 6px;
  padding: 10px 16px; border-radius: 999px; background: var(--ink-gray-9); color: var(--surface-white, #fff);
  font-size: 14px; font-weight: 500; box-shadow: 0 6px 20px rgb(0 0 0 / .18); }
.chat-fab:hover { background: var(--ink-gray-8); }
.chat-fab:focus-visible { outline: 2px solid var(--ink-gray-6); outline-offset: 3px; }
.chat { position: fixed; top: 0; right: 0; bottom: 0; z-index: 45; width: min(440px, 100vw); display: flex;
  flex-direction: column; background: var(--surface-white, #fff); border-left: 1px solid var(--outline-gray-2);
  box-shadow: -12px 0 32px rgb(0 0 0 / .08); }
.chat-enter-active, .chat-leave-active { transition: transform .22s ease, opacity .22s ease; }
.chat-enter-from, .chat-leave-to { transform: translateX(24px); opacity: 0; }
@media (prefers-reduced-motion: reduce) { .chat-enter-active, .chat-leave-active { transition: none; } }
.thinking { animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: .45; } }
@media print { .no-print { display: none !important; } }
</style>
