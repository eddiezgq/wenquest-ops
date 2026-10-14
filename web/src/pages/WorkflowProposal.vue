<script setup>
// Changes the AI suggested from the company's procedures (ADR-0015, 15c): each with its quote and what code found;
// a person accepts (into the draft) or rejects each one.
import { computed, inject, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { ago } from '../format'

const ws = inject('workspace')
const route = useRoute()
const p = ref(null)
const error = ref('')
const done = ref('')
const notes = ref({})
const KIND = { ncr: 'Nonconformance report', capa: 'Corrective action' }
const canDecide = computed(() => p.value?.can_decide)
const open = computed(() => (p.value?.items || []).filter((i) => i.acceptable).length)

async function load() {
  error.value = ''
  try { p.value = await api(`/api/quality/workflows/proposals/${route.params.id}`) } catch (e) { error.value = e.message }
}
watch(() => route.params.id, load, { immediate: true })

async function decide(it, how) {
  error.value = ''; done.value = ''
  const body = how === 'accept' ? { note: notes.value[it.id] || '' } : { reason: notes.value[it.id] || '' }
  try {
    p.value = await api(`/api/quality/workflows/proposal-items/${it.id}/${how}`, { method: 'POST', body })
    done.value = how === 'accept'
      ? `Added to draft version ${p.value.draft?.version}. Someone who did not change the draft enables it.`
      : 'Rejected.'
  } catch (e) { error.value = e.message }
}
function state(it) {
  if (it.decision !== 'open') return { theme: it.decision === 'accepted' ? 'green' : 'gray', label: it.decision }
  if (it.already) return { theme: 'gray', label: 'already so' }
  if (!it.acceptable) return { theme: 'red', label: 'cannot be accepted' }
  return { theme: 'blue', label: 'to decide' }
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality', to: '/quality?tab=workflows' }]">
    <template #title>{{ p ? `Suggested changes · ${KIND[p.kind]} workflow` : 'Suggested changes' }}</template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}
    <RouterLink v-if="p?.draft" :to="`/quality/workflows/${p.draft.id}`" class="wq-link ms-1">Open the draft</RouterLink></p>

  <template v-if="p">
    <section class="wq-panel mb-5 p-5">
      <p class="mb-2 text-base text-ink-gray-8">{{ p.summary }}</p>
      <p class="wq-muted">Suggested by the AI {{ ago(p.created_at) }} for {{ p.created_by }}, compared with version {{ p.base }}<template v-if="p.enabled !== p.base">
          (version {{ p.enabled }} is in use now; each change is checked again when accepted)</template>.
        Read: <span v-for="(d, i) in p.documents" :key="d.id"><RouterLink :to="`/documents/${d.id}`" class="wq-link">{{ d.name }}</RouterLink>
          <span v-if="d.revision" class="text-ink-gray-5"> rev {{ d.revision }}</span><span v-if="d.cut" class="text-ink-amber-7"> (only the start: it is long)</span>{{ i < p.documents.length - 1 ? ', ' : '' }}</span></p>
      <p class="mt-2 text-sm text-ink-gray-7">{{ p.items.length }} suggested · {{ open }} can be accepted
        <template v-if="p.draft"> · draft <RouterLink :to="`/quality/workflows/${p.draft.id}`" class="wq-link">version {{ p.draft.version }}</RouterLink></template></p>
    </section>

    <article v-for="it in p.items" :key="it.id" class="suggestion wq-panel mb-4 p-5">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <span class="text-sm text-ink-gray-5">{{ it.seq }}.</span>
        <h2 class="text-base font-semibold text-ink-gray-9">{{ it.text }}</h2>
        <Badge v-bind="state(it)" />
      </div>
      <ul v-if="it.lines.length" class="mb-2 list-disc ps-5 text-sm text-ink-gray-7"><li v-for="l in it.lines" :key="l">{{ l }}</li></ul>
      <blockquote class="mb-2 border-s-2 ps-3 text-sm italic text-ink-gray-8"
                  :class="it.verified ? 'border-outline-green-3' : 'border-outline-red-3'">“{{ it.quote }}”</blockquote>
      <p v-if="it.verified" class="mb-1 flex items-center gap-1.5 text-sm text-ink-green-7"><span class="lucide-check size-4" />Found in
        <RouterLink :to="`/documents/${it.document.id}`" class="wq-link">{{ it.document.name }}</RouterLink></p>
      <p v-if="it.why" class="mb-1 text-sm text-ink-gray-6">Why: {{ it.why }}</p>
      <ul v-if="it.problems.length" class="mb-1 list-disc ps-5 text-sm text-ink-red-7"><li v-for="x in it.problems" :key="x">{{ x }}</li></ul>
      <p v-if="it.already && it.decision === 'open'" class="text-sm text-ink-gray-6">The workflow already does this.</p>
      <p v-if="it.decision !== 'open'" class="text-sm text-ink-gray-6">{{ it.decision === 'accepted' ? 'Accepted' : 'Rejected' }} by {{ it.decided_by }}
        {{ ago(it.decided_at) }}<span v-if="it.decision_note">: {{ it.decision_note }}</span></p>
      <div v-if="canDecide && it.decision === 'open' && !it.already" class="mt-3 flex flex-wrap items-center gap-2">
        <input v-model="notes[it.id]" class="wq-input w-72" :placeholder="it.acceptable ? 'Note (optional)' : 'Why rejected (optional)'">
        <Button v-if="it.acceptable" variant="solid" icon-left="lucide-check" label="Accept into the draft" @click="decide(it, 'accept')" />
        <Button icon-left="lucide-x" label="Reject" @click="decide(it, 'reject')" />
      </div>
    </article>

    <section v-if="p.cannot.length" class="wq-panel p-5">
      <h2 class="wq-h2">What the procedures ask that the workflow cannot do</h2>
      <p class="wq-muted mb-3">For a person to handle another way, or to change in the procedure.</p>
      <div v-for="(c, i) in p.cannot" :key="i" class="mb-3">
        <blockquote class="mb-1 border-s-2 border-outline-gray-3 ps-3 text-sm italic text-ink-gray-8">“{{ c.quote }}”</blockquote>
        <p class="text-sm text-ink-gray-6"><span v-if="c.document">{{ c.document.name }}<span v-if="!c.verified" class="text-ink-red-7"> (quote not found)</span> · </span>{{ c.why }}</p>
      </div>
    </section>
  </template>
</template>
