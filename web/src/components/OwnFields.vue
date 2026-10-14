<script setup>
// A company's own fields and extra signed approvals on a nonconformance report or corrective action (ADR-0015, 15b).
import { ref, watch } from 'vue'
import { Badge, Button } from 'frappe-ui'
import { api } from '../api'
import { ago } from '../format'

const props = defineProps({ record: Object, kind: String, canEdit: Boolean })
const emit = defineEmits(['changed'])
const vals = ref({})
const pw = ref({})
const error = ref('')
const locked = () => ['closed', 'cancelled'].includes(props.record.status)
watch(() => props.record, (r) => { vals.value = { ...(r.custom || {}) } }, { immediate: true })

async function post(path, body) {
  error.value = ''
  try { emit('changed', await api(`/api/quality/${props.kind}s/${props.record.id}/${path}`, { method: 'POST', body })); pw.value = {} }
  catch (e) { error.value = e.message }
}
const save = () => post('update', { custom: Object.fromEntries(Object.keys(props.record.fields).map((k) => [k, vals.value[k] ?? ''])) })
</script>

<template>
  <section v-if="Object.keys(record.fields).length || record.approvals.length" class="own wq-panel mt-5 p-5">
    <p v-if="error" class="wq-error mb-3">{{ error }}</p>
    <template v-if="Object.keys(record.fields).length">
      <h2 class="wq-h2">Your fields</h2>
      <form class="grid gap-3 sm:grid-cols-2" @submit.prevent="save">
        <label v-for="(f, k) in record.fields" :key="k" class="wq-field">{{ f.label }}<span v-if="f.required_at?.length" class="text-ink-gray-4">needed before {{ f.required_at.join(', ').replaceAll('_', ' ') }}</span>
          <select v-if="f.type === 'choice'" v-model="vals[k]" class="wq-select" :disabled="!canEdit || locked()"><option value="">—</option><option v-for="c in f.choices" :key="c">{{ c }}</option></select>
          <input v-else v-model="vals[k]" class="wq-input" :disabled="!canEdit || locked()"
                 :type="f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : f.type === 'person' ? 'email' : 'text'" step="any"></label>
        <div v-if="canEdit && !locked()" class="sm:col-span-2"><Button type="submit" icon-left="lucide-save" label="Save fields" /></div>
      </form>
    </template>
    <template v-if="record.approvals.length">
      <h2 class="wq-h2" :class="{ 'mt-5': Object.keys(record.fields).length }">Approvals</h2>
      <ul class="flex flex-col gap-2">
        <li v-for="a in record.approvals" :key="a.name" class="flex flex-wrap items-center gap-2 text-base">
          <span class="font-medium text-ink-gray-9">{{ a.label }}</span>
          <span class="text-sm text-ink-gray-5">before {{ a.before_label.toLowerCase() }}, by {{ a.roles.join(' or ') }}</span>
          <Badge v-if="a.given_by" theme="green" :label="`given by ${a.given_by}, ${ago(a.given_at)}`" />
          <template v-else-if="a.now">
            <input v-model="pw[a.name]" class="wq-input max-w-48" type="password" placeholder="Your password to sign" autocomplete="current-password">
            <Button variant="solid" icon-left="lucide-pen-line" label="Approve (sign)" @click="post(`approvals/${a.name}`, { password: pw[a.name] || '' })" />
          </template>
          <Badge v-else theme="gray" label="not yet" />
        </li>
      </ul>
    </template>
  </section>
</template>
