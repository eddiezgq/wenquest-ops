<script setup>
// Scan (ADR-0020, 20b): a device label, a lot or a GS1 web address, with the camera of a phone or tablet or with a
// scanner that types into the box. Shows what the code holds and the records it may be.
import { nextTick, onBeforeUnmount, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, objectPath } from '../api'
import { t } from '../i18n'

const code = ref('')
const out = ref(null)
const error = ref('')
const camera = ref(false)
const video = ref(null)
const box = ref(null)
let controls = null
const NAMES = { di: 'Device identifier', lot: 'Lot', serial: 'Serial number', production_date: 'Production date',
  expiry_date: 'Expiry date', lic: 'Labeler code', pcn: 'Product number', unit: 'Unit of measure', quantity: 'Quantity' }

async function look(text) {
  error.value = ''; out.value = null
  const v = (text ?? code.value).replace(/^\s+|[\r\n]+$/g, '')   // a HIBC check character can be a space
  if (!v) return
  try { out.value = await api('/api/udi/scan', { method: 'POST', body: { code: v } }) } catch (e) { error.value = e.message }
}
async function start() {
  error.value = ''
  try {
    const { BrowserMultiFormatReader } = await import('@zxing/browser')   // only loaded when the camera is used
    camera.value = true
    await nextTick()
    controls = await new BrowserMultiFormatReader().decodeFromVideoDevice(undefined, video.value, (res) => {
      if (res) { code.value = res.getText(); stop(); look() }
    })
  } catch (e) { camera.value = false; error.value = t('The camera cannot be used here ({reason}). Type or scan the code into the box.', { reason: e.name || e.message }) }
}
// a scanner sends the GS separator of GS1 codes as Ctrl+]; a text box would drop it, so it is written as <GS>
function gs(e) { if (e.ctrlKey && (e.key === ']' || e.code === 'BracketRight')) { e.preventDefault(); const el = e.target; const at = el.selectionStart ?? code.value.length; code.value = code.value.slice(0, at) + '<GS>' + code.value.slice(el.selectionEnd ?? at); nextTick(() => el.setSelectionRange(at + 4, at + 4)) } }
function stop() { controls?.stop(); controls = null; camera.value = false; nextTick(() => box.value?.focus()) }
onBeforeUnmount(stop)
</script>

<template>
  <PageTop :title="t('Scan')">
    <Button v-if="!camera" variant="solid" icon-left="lucide-camera" :label="t('Use the camera')" @click="start" />
    <Button v-else icon-left="lucide-camera-off" :label="t('Stop the camera')" @click="stop" />
  </PageTop>
  <div class="max-w-3xl">
    <p class="mb-4 text-base text-ink-gray-7">{{ t('Scan a device label (GS1, HIBC or ISBT 128), or a GS1 web address. A barcode scanner types into the box below; on a phone or tablet, use the camera.') }}</p>
    <video v-show="camera" ref="video" class="mb-4 w-full max-w-md rounded-5 border border-outline-gray-2" muted playsinline />
    <form data-help="scan-box" class="flex gap-2" @submit.prevent="look()">
      <input ref="box" v-model="code" class="wq-input grow font-mono" :placeholder="t('Scan or type the code')" autofocus :aria-label="t('The scanned code')" @keydown="gs">
      <Button type="submit" :label="t('Read')" />
    </form>
    <p v-if="error" class="wq-error mt-4">{{ error }}</p>
    <section v-if="out" data-help="scan-result" class="wq-panel mt-5 p-5">
      <div class="mb-3 flex items-center gap-2"><h2 class="wq-h2 m-0">{{ t('What the code holds') }}</h2>
        <Badge :label="out.read.form || out.read.agency" /></div>
      <dl class="grid grid-cols-[12rem_1fr] gap-y-1 text-base">
        <template v-for="(label, k) in NAMES" :key="k"><template v-if="out.read[k]">
          <dt class="text-ink-gray-6">{{ t(label) }}</dt><dd class="font-mono text-ink-gray-9">{{ out.read[k] }}</dd></template></template>
      </dl>
      <p v-if="out.read.agency === 'iccbba'" class="mt-2 text-sm text-ink-gray-6">{{ t('An ISBT 128 code: recognised, its fields are not read yet.') }}</p>
      <h3 class="mb-1 mt-4 text-base font-semibold text-ink-gray-9">{{ t('In WenQuest Ops') }}</h3>
      <p v-if="out.found.item_code">{{ t('Item') }} <RouterLink :to="objectPath('Item', out.found.item_code)" class="wq-link">{{ out.found.item_code }}</RouterLink></p>
      <p v-else-if="out.read.di" class="text-ink-gray-6">{{ t('No item has this device identifier (Device identifiers).') }}</p>
      <p v-for="p in out.found.production" :key="'p' + p.id">{{ t('Production lot') }} <RouterLink :to="`/quality/production/${p.id}`" class="wq-link">{{ p.name }}</RouterLink>
        ({{ t('{item} lot {lot}, {status}', { item: p.item_code, lot: p.lot_no, status: t(p.status.replace('_', ' ')) }) }}) ·
        <RouterLink :to="`/quality/trace?record=${p.id}`" class="wq-link">{{ t('trace it') }}</RouterLink></p>
      <p v-for="p in out.found.incoming" :key="'i' + p.id">{{ t('Incoming lot') }} <RouterLink :to="`/quality/iqc/${p.id}`" class="wq-link">{{ p.name }}</RouterLink>
        ({{ t('{item} lot {lot}, {status}', { item: p.item_code, lot: p.lot_no, status: t(p.status.replace('_', ' ')) }) }}) ·
        <RouterLink :to="`/quality/trace?incoming=${p.id}`" class="wq-link">{{ t('trace it') }}</RouterLink></p>
      <p v-if="!out.found.item_code && (out.found.production.length || out.found.incoming.length)" class="text-sm text-ink-gray-6">
        {{ t('The item of this code is not known here: these lots only have the same number, so check the item.') }}</p>
      <p v-if="(out.read.lot || out.read.serial) && !out.found.production.length && !out.found.incoming.length" class="text-ink-gray-6">
        {{ t('No production or incoming lot with this number.') }}</p>
    </section>
  </div>
</template>
