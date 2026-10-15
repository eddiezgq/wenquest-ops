<script setup>
// The internal audit checklist (ADR-0016, 16c): for a process, what to ask, what the records show and a sample of
// them. The auditor records the audit in the internal audits register.
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, objectPath } from '../api'
import { ago } from '../format'
import { standard } from '../standard'

const route = useRoute()
const router = useRouter()
const cl = ref(null)
const error = ref('')
const print = () => window.print()
const process = ref(route.query.process || '')
const S = { met: { theme: 'green', label: 'met' }, not_met: { theme: 'red', label: 'not met' },
  unknown: { theme: 'gray', label: 'unknown' }, not_applicable: { theme: 'blue', label: 'does not apply' } }

async function load() {
  error.value = ''
  try { cl.value = await api(`/api/qms/${standard.value}/checklist${process.value ? `?process=${process.value}` : ''}`) } catch (e) { error.value = e.message }
}
watch(process, (p) => { router.replace({ query: p ? { process: p } : {} }); load() }, { immediate: true })
function to(p, item) {
  if (p.kind === 'ncr') return `/quality/ncr/${p.id}`
  if (p.kind === 'capa') return `/quality/capa/${p.id}`
  if (p.kind === 'document') return `/documents/${p.id}`
  if (p.kind === 'inspection') return objectPath('QualityInspection', p.id)
  if (p.kind === 'supplier') return objectPath('Supplier', p.id)
  if (p.kind === 'asl') return `/quality/suppliers#a${p.id}`
  if (p.kind === 'reading') return '/documents/control'
  if (p.kind === 'entry') return `/system/registers/${item.register}#e${p.id}`
  return null
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Quality system', to: '/system' }]">
    <template #title>Internal audit checklist{{ cl ? ` · ${cl.name}` : '' }}</template>
    <Button icon-left="lucide-printer" label="Print" @click="print" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <template v-if="cl">
    <div class="mb-4 flex flex-wrap items-end gap-3">
      <label class="wq-field">Process<select v-model="process" class="wq-select"><option value="">All processes</option>
        <option v-for="p in cl.processes_all" :key="p.id" :value="p.id">{{ p.label }}</option></select></label>
      <span class="pb-2 text-sm text-ink-gray-5">{{ cl.edition_label }}, from the check of {{ ago(cl.evaluation?.at) }}</span>
      <RouterLink to="/system/registers/audits" class="wq-link pb-2 text-sm">Record the audit in the internal audits register</RouterLink>
    </div>
    <section v-for="p in cl.processes" :key="p.id" class="checklist wq-panel mb-4 p-5">
      <h2 class="wq-h2">{{ p.label }}</h2>
      <ol class="flex flex-col gap-3">
        <li v-for="(it, i) in p.items" :key="it.id" class="border-t border-outline-gray-1 pt-3 first:border-t-0 first:pt-0">
          <div class="flex flex-wrap items-start gap-2">
            <span class="text-sm text-ink-gray-5">{{ i + 1 }}.</span>
            <div class="min-w-0 flex-1">
              <p class="text-base text-ink-gray-9">{{ it.question }} <span class="text-sm text-ink-gray-5">({{ cl.name }} {{ it.clauses.join(', ') }})</span></p>
              <p class="mt-1 text-sm text-ink-gray-7"><Badge v-if="it.status" v-bind="S[it.status]" class="me-1" />{{ it.detail }}</p>
              <p v-if="it.sample.length" class="mt-1 text-sm text-ink-gray-6">Sample to look at:
                <template v-for="(x, j) in it.sample" :key="j"><RouterLink v-if="to(x, it)" :to="to(x, it)" class="wq-link">{{ x.label }}</RouterLink><span v-else>{{ x.label }}</span>{{ j < it.sample.length - 1 ? ', ' : '' }}</template></p>
              <ul v-if="it.gaps.length" class="mt-1 text-sm text-ink-red-7"><li v-for="(x, j) in it.gaps" :key="j">{{ x.label }} — {{ x.why }}</li></ul>
              <p class="mt-2 text-sm text-ink-gray-4">Auditor's notes: ____________________________________________</p>
            </div>
          </div>
        </li>
      </ol>
    </section>
  </template>
</template>
