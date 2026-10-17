<script setup>
// The label of a released lot (ADR-0020, 20b): the device identifier from Device identifiers, the lot and the
// production date from the record, an expiry date if you give one. Printed from the screen or sent to a Zebra
// printer as ZPL; every print is kept.
import { ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { api } from '../api'

const props = defineProps({ recordId: { type: Number, required: true } })
const v = ref(null)
const error = ref('')
const expiry = ref('')
const copies = ref(1)
const svg = ref('')
const done = ref('')

async function draw() {
  svg.value = ''
  if (!v.value?.label) return
  const { toSVG } = await import('bwip-js')     // only loaded on the label page
  const l = v.value.label
  svg.value = toSVG(l.agency === 'gs1' ? { bcid: 'gs1datamatrix', text: l.text, scale: 3 }
    : { bcid: 'datamatrix', text: l.data, scale: 3 })
}
async function load() {
  error.value = ''
  try {
    v.value = await api(`/api/production/${props.recordId}/label${expiry.value ? `?expiry=${expiry.value}` : ''}`)
    await draw()
  } catch (e) { error.value = e.message; v.value = null }
}
watch(() => [props.recordId, expiry.value], load, { immediate: true })

async function printIt() {
  error.value = ''; done.value = ''
  try {
    const out = await api(`/api/production/${props.recordId}/label`, { method: 'POST', body: { format: 'screen', copies: copies.value, expiry: expiry.value || null } })
    v.value = { ...v.value, prints: out.prints }
    document.body.classList.add('printing-label')
    window.print()
    document.body.classList.remove('printing-label')
  } catch (e) { error.value = e.message }
}
async function zpl() {
  error.value = ''; done.value = ''
  try {
    const r = await fetch(`/api/production/${props.recordId}/label`, { method: 'POST', credentials: 'same-origin',
      headers: { 'content-type': 'application/json' }, body: JSON.stringify({ format: 'zpl', copies: copies.value, expiry: expiry.value || null }) })
    if (!r.ok) throw new Error((await r.json()).detail || 'the label could not be made')
    const url = URL.createObjectURL(await r.blob())
    Object.assign(document.createElement('a'), { href: url, download: `${v.value.label.record}-label.zpl` }).click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    done.value = 'ZPL file saved: send it to the Zebra printer.'
    await load()
  } catch (e) { error.value = e.message }
}
</script>

<template>
  <section data-help="production-label" class="label-panel wq-panel mb-5 p-5">
    <h2 class="wq-h2">Device label</h2>
    <p v-if="error" class="wq-error mb-3">{{ error }}</p>
    <div v-if="v?.label" class="flex flex-wrap items-start gap-6">
      <figure class="device-label flex items-center gap-4 rounded-4 border border-outline-gray-3 bg-white p-4">
        <div class="code" v-html="svg" />
        <figcaption class="text-sm leading-6 text-black">
          <div v-for="l in v.label.lines" :key="l" class="font-medium">{{ l }}</div>
          <div class="mt-1 font-mono text-xs">{{ v.label.text }}</div>
        </figcaption>
      </figure>
      <div class="no-print flex flex-col gap-3">
        <label class="wq-field">Expiry date (if the device has one)<input v-model="expiry" type="date" class="wq-input"></label>
        <label class="wq-field">Copies<input v-model.number="copies" type="number" min="1" max="500" class="wq-input w-28"></label>
        <div v-if="v.can_print" class="flex gap-2">
          <Button variant="solid" icon-left="lucide-printer" label="Print" @click="printIt" />
          <Button icon-left="lucide-download" label="ZPL for a Zebra printer" @click="zpl" />
        </div>
        <p v-if="done" class="text-sm text-ink-green-7">{{ done }}</p>
      </div>
    </div>
    <p v-if="v?.prints?.length" class="no-print mt-3 text-sm text-ink-gray-6">Printed {{ v.prints.length }} time(s); last by
      {{ v.prints.at(-1).printed_by }} ({{ v.prints.at(-1).format }}, {{ v.prints.at(-1).copies }} copies).</p>
  </section>
</template>

<style>
.device-label .code svg { width: 120px; height: 120px; }
@media print {
  body.printing-label * { visibility: hidden; }
  body.printing-label .device-label, body.printing-label .device-label * { visibility: visible; }
  body.printing-label .device-label { position: fixed; left: 0; top: 0; border: none; }
}
</style>
