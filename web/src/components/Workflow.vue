<script setup>
// One quality workflow, read-only (ADR-0015, 15a): its states in order and every step with who may do it, what it
// needs, whether it is signed and who may not do it.
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { ago } from '../format'

const props = defineProps({ data: Object })
const wf = computed(() => props.data.workflow)
// states in the order a record meets them (breadth first from the first state)
const order = computed(() => {
  const out = [wf.value.initial]
  for (let i = 0; i < out.length; i++) {
    for (const s of Object.values(wf.value.steps)) {
      if (!s.from.includes(out[i])) continue
      for (const t of [s.to, s.to_when_approval_needed]) if (t && !out.includes(t)) out.push(t)
    }
  }
  const all = [...out, ...Object.keys(wf.value.states).filter((s) => !out.includes(s))]
  return [...all.filter((s) => !wf.value.states[s].final), ...all.filter((s) => wf.value.states[s].final)]
})
const stateLabel = (s) => wf.value.states[s]?.label || s
</script>

<template>
  <section class="wq-panel mb-6 p-5">
    <div class="mb-1 flex flex-wrap items-center gap-2">
      <h2 class="text-base font-semibold text-ink-gray-9">{{ wf.label }}</h2>
      <Badge theme="green" :label="`version ${data.enabled.version} in use`" />
      <span class="text-sm text-ink-gray-5">{{ data.enabled.note }} · enabled by {{ data.enabled.enabled_by }} {{ ago(data.enabled.enabled_at) }}
        · numbers {{ wf.numbering.prefix }}-{{ '0'.repeat(wf.numbering.digits - 1) }}1</span>
    </div>
    <p class="wq-muted mb-4">Fingerprint {{ data.enabled.fingerprint.slice(0, 12) }}… Records keep the version they started under.</p>

    <ol class="states mb-5 flex flex-wrap items-center gap-2">
      <template v-for="(s, i) in order" :key="s">
        <li class="rounded-3 border px-3 py-1.5 text-sm"
            :class="wf.states[s].final ? 'border-outline-gray-2 bg-surface-gray-2 text-ink-gray-7' : 'border-outline-gray-3 bg-surface-base text-ink-gray-9'">
          {{ stateLabel(s) }}<span v-if="data.counts[s]" class="ms-1.5 text-ink-gray-5">{{ data.counts[s] }}</span></li>
        <span v-if="i < order.length - 1" class="size-4 text-ink-gray-4" :class="wf.states[order[i + 1]].final && !wf.states[s].final ? 'lucide-dot' : 'lucide-chevron-right'" />
      </template>
    </ol>

    <div class="overflow-x-auto">
      <table class="wq-table text-sm">
        <thead><tr><th>Step</th><th>From</th><th>To</th><th>Needs</th><th>Signed</th><th>Not by</th><th>Who</th></tr></thead>
        <tbody><tr v-for="s in wf.steps" :key="s.name">
          <td class="whitespace-nowrap font-medium text-ink-gray-9">{{ s.label }}</td>
          <td>{{ s.from.map(stateLabel).join(', ') }}</td>
          <td class="whitespace-nowrap">{{ s.to ? stateLabel(s.to) : '(stays)' }}<span v-if="s.to_when_approval_needed" class="block text-ink-gray-5">or {{ stateLabel(s.to_when_approval_needed) }} when the disposition needs approval</span></td>
          <td>{{ s.needs.join(', ') || (s.reason ? 'a reason' : '—') }}</td>
          <td><span v-if="s.sign" class="inline-flex items-center gap-1"><span class="lucide-pen-line size-3.5" />{{ s.sign }}</span><span v-else class="text-ink-gray-4">—</span></td>
          <td>{{ s.not_by_text.join(', ') || '—' }}</td>
          <td class="min-w-36 text-ink-gray-6" :title="s.permission_text">{{ s.who.map((r) => r.replace('_', ' ')).join(', ') }}</td>
        </tr></tbody>
      </table>
    </div>
    <ul v-if="wf.rules" class="mt-4 list-disc ps-5 text-sm text-ink-gray-7">
      <li v-if="wf.rules.capa_closed_before_close?.length">{{ wf.rules.capa_closed_before_close.join(' and ') }} reports close only after a linked corrective action is closed</li>
      <li v-if="wf.rules.eight_d_before_close?.length">{{ wf.rules.eight_d_before_close.join(' and ') }} reports close only after their 8D is complete</li>
      <li v-if="wf.rules.one_open_capa_per_ncr">one open corrective action per nonconformance report</li>
    </ul>
  </section>
</template>
