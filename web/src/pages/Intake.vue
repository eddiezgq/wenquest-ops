<script setup>
// Design data inbox (ADR-0026, 26e): batches from FreeCAD, STEP and Excel waiting to be matched and written.
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, apiForm } from '../api'
import { t } from '../i18n'

const router = useRouter()
const v = ref(null)
const status = ref('pending')
const error = ref('')
const kind = ref('excel')
const file = ref(null)
const busy = ref(false)
const SRC = () => ({ freecad: 'FreeCAD', step: 'STEP', excel: 'Excel' })
async function load() { error.value = ''; try { v.value = await api(`/api/plm/intake?status=${status.value}`) } catch (e) { error.value = e.message } }
watch(status, load, { immediate: true })
async function upload() {
  error.value = ''; busy.value = true
  const form = new FormData(); form.append('kind', kind.value); form.append('file', file.value)
  try { const r = await apiForm('/api/plm/intake/upload', form); router.push(`/plm/intake/${r.id}`) } catch (e) { error.value = e.message } finally { busy.value = false }
}
const stl = (s) => ({ pending: t('intake::pending'), written: t('intake::written'), rejected: t('intake::rejected') })[s] || s
</script>

<template>
  <PageTop :crumbs="[{ label: t('Parts'), to: '/plm/parts' }]"><template #title>{{ t('Design data') }}</template></PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <section v-if="v?.can_edit" data-help="plm-intake-upload" class="wq-panel mb-5 p-5">
    <h2 class="wq-h2">{{ t('Upload a STEP file or an Excel BOM') }}</h2>
    <form class="flex flex-wrap items-end gap-2" @submit.prevent="upload">
      <select v-model="kind" class="wq-select w-36"><option value="excel">Excel (.xlsx)</option><option value="step">STEP (.stp, .step)</option></select>
      <input type="file" class="text-sm" :accept="kind === 'step' ? '.stp,.step' : '.xlsx'" @change="file = $event.target.files[0]">
      <Button type="submit" variant="solid" :label="t('Upload')" :disabled="!file || busy" />
    </form>
    <p class="mt-2 text-sm text-ink-gray-5">{{ t('Excel: a header row with 父件编码, 子件编码, 数量 (flat), or 层级, 编码, 数量 (levels); 名称, 单位, 自制/外购, 类别 if you have them. STEP: the assembly and part names are read, not the geometry. FreeCAD sends with the WenQuest PLM add-on.') }}</p>
  </section>
  <section v-if="v" data-help="plm-intake" class="wq-panel p-5">
    <div class="mb-3 flex gap-2"><button v-for="s in ['pending', 'written', 'rejected']" :key="s" class="rounded px-3 py-1 text-sm" :class="status === s ? 'bg-surface-gray-3 font-medium' : 'text-ink-gray-6'" @click="status = s">{{ stl(s) }}</button></div>
    <p v-if="!v.batches.length" class="wq-muted">{{ t('None.') }}</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>#</th><th>{{ t('From') }}</th><th>{{ t('Sent by') }}</th><th>{{ t('File') }}</th><th>{{ t('Parts') }}</th><th>{{ t('Received') }}</th><th>{{ t('Status') }}</th></tr></thead>
      <tbody><tr v-for="b in v.batches" :key="b.id"><td><RouterLink :to="`/plm/intake/${b.id}`" class="wq-link">{{ b.id }}</RouterLink></td>
        <td>{{ SRC()[b.source] }}</td><td>{{ b.sent_by }}</td><td>{{ b.file_name || '–' }}</td><td>{{ b.n }}</td><td>{{ new Date(b.created_at).toLocaleString() }}</td>
        <td><Badge :theme="b.status === 'written' ? 'green' : b.status === 'rejected' ? 'red' : 'orange'" :label="stl(b.status)" /></td></tr></tbody></table>
  </section>
</template>
