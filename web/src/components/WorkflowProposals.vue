<script setup>
// Suggestions from the company's procedures (ADR-0015, 15c): choose procedures of the library, the model reads them
// next to this workflow and proposes changes, each quoting a procedure; earlier proposals are listed.
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import { api } from '../api'
import { ago } from '../format'

const props = defineProps({ kind: String })
const router = useRouter()
const d = ref(null)
const chosen = ref([])
const busy = ref(false)
const error = ref('')
const MAX = 8

onMounted(async () => {
  try {
    d.value = await api(`/api/quality/workflows/${props.kind}/proposals`)
    chosen.value = d.value.procedures.filter((p) => p.suggested).slice(0, MAX).map((p) => p.id)
  } catch (e) { error.value = e.message }
})
const name = (p) => [p.number, p.title].filter(Boolean).join(' ') || p.original_name
const tooMany = computed(() => chosen.value.length > MAX)
async function ask() {
  busy.value = true; error.value = ''
  try {
    const p = await api(`/api/quality/workflows/${props.kind}/proposals`, { method: 'POST', body: { document_ids: chosen.value } })
    router.push(`/quality/workflows/proposals/${p.id}`)
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
</script>

<template>
  <div v-if="d" class="proposals mt-5 border-t border-outline-gray-1 pt-4">
    <h3 class="mb-1 text-sm font-semibold text-ink-gray-8">Suggestions from your procedures</h3>
    <p class="wq-muted mb-3 max-w-3xl">The AI reads the procedures you choose and suggests changes to this workflow. Every suggestion quotes the
      procedure; WenQuest Ops checks that the quote is really there and that the change keeps the rules that cannot be switched off.
      You accept or reject each one; accepted ones go into a draft that someone else enables.</p>
    <template v-if="d.can_propose">
      <p v-if="!d.procedures.length" class="wq-muted">There are no confirmed procedures in the document library yet. Import and confirm them under Documents first.</p>
      <template v-else>
        <div class="mb-3 flex max-h-56 flex-col gap-1 overflow-y-auto text-sm">
          <label v-for="p in d.procedures" :key="p.id" class="inline-flex items-center gap-2">
            <input v-model="chosen" type="checkbox" class="form-checkbox" :value="p.id">
            <span class="text-ink-gray-8">{{ name(p) }}</span>
            <span class="text-ink-gray-5">{{ p.revision ? `rev ${p.revision} · ` : '' }}{{ p.status.replace('_', ' ') }}{{ p.suggested ? ' · about these records' : '' }}</span>
          </label>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <Button variant="solid" icon-left="lucide-sparkles" :loading="busy" :disabled="!chosen.length || tooMany"
                  :label="busy ? 'Reading…' : `Read ${chosen.length} and suggest changes`" @click="ask" />
          <span v-if="tooMany" class="text-sm text-ink-amber-7">Choose at most {{ MAX }} at a time.</span>
        </div>
      </template>
    </template>
    <p v-else-if="!d.ai" class="wq-muted">This needs the company's model key (see Help, AI assistant). The workflow can still be changed by hand.</p>
    <p v-if="error" class="wq-error mt-2">{{ error }}</p>
    <ul v-if="d.proposals.length" class="mt-3 flex flex-col gap-1 text-sm">
      <li v-for="p in d.proposals" :key="p.id">
        <RouterLink :to="`/quality/workflows/proposals/${p.id}`" class="wq-link">Suggestions {{ ago(p.created_at) }}</RouterLink>
        <span class="text-ink-gray-5"> by {{ p.created_by }} from {{ p.documents.map((x) => x.name).join(', ') }} ·
          {{ p.changes }} suggested, {{ p.accepted }} accepted, {{ p.open }} to decide</span>
      </li>
    </ul>
  </div>
</template>
