<script setup>
// A measurement file into an incoming inspection (ADR-0020, 20c): a CSV export of a coordinate measuring machine or
// a 3D scanner's report, or a Q-DAS file. Previewed first, nothing written; then signed with your password.
import { computed, ref } from 'vue'
import { Button } from 'frappe-ui'
import { apiForm } from '../api'

const props = defineProps({ inspectionId: { type: Number, required: true }, gauges: { type: Array, default: () => [] },
  imports: { type: Array, default: () => [] }, beforeImport: { type: Function, default: async () => true } })
const emit = defineEmits(['imported'])
const file = ref(null)
const p = ref(null)
const choice = ref({})            // feature -> characteristic ('' leaves it out)
const first = ref('')
const gauge = ref('')
const password = ref('')
const error = ref('')
const busy = ref('')
const picker = ref(null)
const url = computed(() => `/api/iqc/inspections/${props.inspectionId}/measurements`)

function form(extra = {}) {
  const f = new FormData()
  f.append('file', file.value)
  if (p.value) f.append('mapping', JSON.stringify(Object.fromEntries(p.value.features.map((x) => [x.name, choice.value[x.name] ?? '']))))
  if (first.value) f.append('first_sample', String(first.value))
  if (gauge.value) f.append('gauge_id', gauge.value)
  for (const [k, x] of Object.entries(extra)) if (x !== '' && x !== null) f.append(k, x)
  return f
}
const send = (path, body) => apiForm(path, body)
async function preview(fresh = false) {
  error.value = ''; busy.value = 'preview'
  if (fresh) { p.value = null; choice.value = {}; first.value = '' }
  try {
    if (!(await props.beforeImport())) { error.value = 'Fix the readings above first, then preview again.'; return }   // saved first, so the preview counts them
    p.value = await send(`${url.value}/preview`, form())
    choice.value = Object.fromEntries(p.value.features.map((x) => [x.name, p.value.mapping[x.name] || '']))
    first.value = p.value.first_sample
  } catch (e) { error.value = e.message } finally { busy.value = '' }
}
function pick(e) { file.value = e.target.files[0] || null; p.value = null; if (file.value) preview(true) }
async function save() {
  error.value = ''; busy.value = 'import'
  const pw = password.value; password.value = ''
  try {
    if (!(await props.beforeImport())) return
    const r = await send(url.value, form({ password: pw, seen: p.value.print }))
    p.value = null; file.value = null
    if (picker.value) picker.value.value = ''
    emit('imported', `${r.readings} readings imported from ${r.file_name}.`)
  } catch (e) { error.value = e.message } finally { busy.value = '' }
}
</script>

<template>
  <section data-help="iqc-import" class="wq-panel mb-5 p-5">
    <h2 class="wq-h2">Measurement file</h2>
    <p class="wq-muted mb-3 max-w-3xl">A CSV export of a coordinate measuring machine, a 3D scanner or gauge software, or a Q-DAS file
      (.dfq). Its features go to the plan's characteristics with the same name, or as you choose; its parts go to the samples in order.
      The plan's limits decide.</p>
    <div class="flex flex-wrap items-center gap-3">
      <input ref="picker" type="file" accept=".csv,.txt,.tsv,.dfq,.dfd,.dfx" class="text-sm" aria-label="The measurement file" @change="pick">
      <Button v-if="file" size="sm" label="Preview again" :loading="busy === 'preview'" @click="preview()" />
    </div>
    <p v-if="error" class="wq-error mt-3">{{ error }}</p>
    <template v-if="p">
      <p v-if="p.already" class="mt-3 rounded-3 bg-surface-amber-2 px-3 py-2 text-sm text-ink-amber-8">This file was imported into
        {{ p.inspection }} before, by {{ p.already.by }}.</p>
      <p class="mt-3 text-sm text-ink-gray-7">{{ p.format === 'dfq' ? 'Q-DAS file' : `CSV, ${p.shape === 'long' ? 'one row per feature' : 'one row per part'}` }}:
        {{ p.parts.length }} part(s), {{ p.features.length }} feature(s)<template v-if="p.part_no">, part number {{ p.part_no }}</template>.</p>
      <table data-help="iqc-import-match" class="wq-table mt-2 text-sm"><thead><tr><th>In the file</th><th>Limits in the file</th><th>Characteristic of the plan</th></tr></thead>
        <tbody><tr v-for="f in p.features" :key="f.name"><td class="font-mono">{{ f.name }}</td>
          <td>{{ [f.lsl != null ? `≥ ${f.lsl}` : '', f.usl != null ? `≤ ${f.usl}` : ''].filter(Boolean).join(', ') || '–' }}</td>
          <td><select :value="choice[f.name]" class="wq-select" @change="choice[f.name] = $event.target.value; preview()"><option value="">leave out</option>
            <option v-for="c in p.characteristics" :key="c" :value="c">{{ c }}</option></select></td></tr></tbody></table>
      <div class="mt-3 flex flex-wrap items-end gap-3">
        <label class="wq-field">Parts go to samples from<input :value="first" type="number" min="1" :max="p.n" class="wq-input w-24" @change="first = Number($event.target.value) || ''; preview()"></label>
        <label class="wq-field">Measured with<select :value="gauge" class="wq-select w-56" @change="gauge = $event.target.value; preview()"><option value="">(not named)</option>
          <option v-for="g in gauges" :key="g.id" :value="String(g.id)">{{ g.code }} · {{ g.name }}</option></select></label>
      </div>
      <p class="mt-3 text-sm text-ink-gray-8"><b>{{ p.readings.length }}</b> readings on samples {{ p.samples[0] }} to {{ p.samples.at(-1) }}<template
        v-if="p.replaces.length">, replacing {{ p.replaces.length }} entered before</template>.<template v-if="p.unmapped_characteristics.length">
        Not in the file: {{ p.unmapped_characteristics.join(', ') }}.</template></p>
      <p class="mt-1 text-sm text-ink-gray-6">Parts to samples: {{ p.parts.map((x, i) => `${x} → ${p.samples[i]}`).join(', ') }}</p>
      <ul v-if="p.blocks.length || p.problems.length || p.notes.length" class="mt-2 list-disc ps-5 text-sm text-ink-gray-7">
        <li v-for="x in p.blocks" :key="x" class="font-medium text-ink-red-7">{{ x }}</li>
        <li v-for="x in p.problems" :key="x" class="text-ink-red-7">{{ x }}</li><li v-for="x in p.notes" :key="x">{{ x }}</li></ul>
      <div class="mt-3 flex flex-wrap items-end gap-2">
        <label class="wq-field">Your password to sign<input v-model="password" type="password" class="wq-input w-48" autocomplete="current-password"></label>
        <Button variant="solid" :label="`Import ${p.readings.length} readings (sign)`" :disabled="!password || !p.readings.length || !!p.already || p.blocks.length > 0"
                :loading="busy === 'import'" @click="save" />
      </div>
    </template>
    <ul v-if="imports.length" class="mt-4 text-sm text-ink-gray-7">
      <li v-for="m in imports" :key="m.id"><a :href="`/api/measurements/${m.id}/file`" class="wq-link">{{ m.file_name }}</a>:
        {{ m.readings }} readings by {{ m.imported_by }}<template v-if="m.gauge_code"> with {{ m.gauge_code }}</template>, {{ m.imported_at.slice(0, 16).replace('T', ' ') }}</li></ul>
  </section>
</template>
