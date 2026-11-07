<script setup>
// Design change on a product change (ADR-0026, 26d): the parts it changes, how it takes effect, the impact analysis
// code makes, and an AI draft of the impact note that a person edits into the assessment.
import { computed, inject, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { api } from '../api'
import { t } from '../i18n'
import { stl } from '../plm'

const props = defineProps({ change: { type: Object, required: true } })
const emit = defineEmits(['note', 'changed'])
const ws = inject('workspace')
const on = computed(() => ws.value?.modules?.includes('plm') && ws.value?.user.permissions.includes('plm:view') && props.change.kind === 'product')
const v = ref(null)
const error = ref('')
const add = ref({ code: '', scope: 'part', note: '' })
const eff = ref({ mode: '', on_date: '', from_serial: '', note: '' })
const found = ref([])
const busy = ref(false)
const scopeL = (s) => ({ part: t('scope::part'), bom: t('scope::bom'), both: t('scope::both') })[s] || s
const modeL = (m) => ({ now: t('effect::now'), use_up: t('effect::use_up'), date: t('effect::date'), serial: t('effect::serial') })[m] || m
const unknown = (x) => x === null || x === undefined

function set(d) {
  v.value = d
  if (d.effect) eff.value = { mode: d.effect.mode, on_date: d.effect.on_date || '', from_serial: d.effect.from_serial || '', note: d.effect.note || '' }
}
async function load() {
  if (!on.value) return
  try { set(await api(`/api/plm/changes/${props.change.id}`)) } catch (e) { error.value = e.message }
}
watch(() => [props.change.id, props.change.status, on.value], load, { immediate: true })
async function act(action, body) {
  error.value = ''; busy.value = true
  try { set(await api(`/api/plm/changes/${props.change.id}/${action}`, { method: 'POST', body })); emit('changed') } catch (e) { error.value = e.message } finally { busy.value = false }
}
let timer = null
function find() {
  clearTimeout(timer)
  timer = setTimeout(async () => { try { found.value = (await api(`/api/plm/parts?status=released&q=${encodeURIComponent(add.value.code.trim())}`)).parts.slice(0, 30) } catch { /* suggestions only */ } }, 250)
}
async function draft() {
  error.value = ''; busy.value = true
  try { const r = await api(`/api/plm/changes/${props.change.id}/draft-note`, { method: 'POST', body: {} }); emit('note', r) } catch (e) { error.value = e.message } finally { busy.value = false }
}
</script>

<template>
  <section v-if="on && v" data-help="change-plm" class="wq-panel mb-5 p-5">
    <h2 class="wq-h2">{{ t('Design change (PLM)') }}</h2>
    <p v-if="error" class="wq-error mb-3">{{ error }}</p>
    <h3 class="mb-2 text-base font-medium">{{ t('Parts it changes') }}</h3>
    <p v-if="!v.items.length" class="wq-muted">{{ t('None.') }}</p>
    <table v-else class="wq-table mb-3 text-sm"><thead><tr><th>{{ t('Part') }}</th><th>{{ t('What changes') }}</th><th>{{ t('plm::From') }}</th><th>{{ t('New revision') }}</th><th /></tr></thead>
      <tbody><tr v-for="i in v.items" :key="i.id">
        <td><RouterLink :to="`/plm/parts/${i.part_id}`" class="wq-link">{{ i.item_code }}</RouterLink> {{ i.name }}</td>
        <td>{{ scopeL(i.scope) }}</td>
        <td><span v-if="i.from_part">{{ t('rev {revision}', { revision: i.from_part }) }}</span><span v-if="i.from_bom"> {{ t('BOM revision {revision}', { revision: i.from_bom }) }}</span></td>
        <td>
          <span v-if="i.new_part">{{ t('rev {revision}', { revision: i.new_part.revision }) }} ({{ stl(i.new_part.status) }}) </span>
          <RouterLink v-if="i.new_bom" :to="`/plm/boms/${i.new_bom.id}`" class="wq-link">{{ t('BOM revision {revision}', { revision: i.new_bom.revision }) }}</RouterLink><span v-if="i.new_bom"> ({{ stl(i.new_bom.status) }})</span>
          <RouterLink v-if="change.status === 'approved' && (!i.new_part && i.scope !== 'bom' || !i.new_bom && i.scope !== 'part')" :to="`/plm/parts/${i.part_id}?change=${change.id}`" class="wq-link">{{ t('Start it') }}</RouterLink>
        </td>
        <td><button v-if="v.editable && v.can_edit" class="text-ink-red-7" @click="act('remove', { part_id: i.part_id })">{{ t('Remove') }}</button></td></tr></tbody></table>
    <form v-if="v.editable && v.can_edit" class="mb-4 flex flex-wrap items-end gap-2" @submit.prevent="act('add', add); add.code = ''">
      <datalist id="plm-ecn-parts"><option v-for="p in found" :key="p.id" :value="p.code">{{ p.name }}</option></datalist>
      <label class="wq-field">{{ t('Part') }}<input v-model="add.code" list="plm-ecn-parts" class="wq-input w-40" @input="find"></label>
      <label class="wq-field">{{ t('What changes') }}<select v-model="add.scope" class="wq-select w-36"><option v-for="s in v.scopes" :key="s" :value="s">{{ scopeL(s) }}</option></select></label>
      <label class="wq-field grow">{{ t('Note') }}<input v-model="add.note" class="wq-input"></label>
      <Button type="submit" :label="t('Add')" :disabled="!add.code.trim() || busy" />
    </form>

    <h3 class="mb-2 text-base font-medium">{{ t('How it takes effect') }}</h3>
    <form class="mb-4 flex flex-wrap items-end gap-2" @submit.prevent="act('effect', eff)">
      <select v-model="eff.mode" class="wq-select w-48" :disabled="!v.editable || !v.can_edit"><option value="" disabled>{{ t('Choose…') }}</option><option v-for="m in v.modes" :key="m" :value="m">{{ modeL(m) }}</option></select>
      <input v-if="eff.mode === 'date'" v-model="eff.on_date" type="date" class="wq-input w-40" :disabled="!v.editable || !v.can_edit">
      <input v-if="eff.mode === 'serial'" v-model="eff.from_serial" class="wq-input w-40" :placeholder="t('First serial number')" :disabled="!v.editable || !v.can_edit">
      <input v-model="eff.note" class="wq-input grow" :placeholder="t('Note')" :disabled="!v.editable || !v.can_edit">
      <Button v-if="v.editable && v.can_edit" type="submit" :label="t('Save')" :disabled="!eff.mode || busy" />
    </form>

    <div class="mb-2 flex flex-wrap items-center gap-2">
      <h3 class="text-base font-medium">{{ t('Impact analysis') }}</h3>
      <span v-if="v.impact" class="text-sm" :class="v.impact.current ? 'text-ink-gray-5' : 'text-ink-amber-7'">
        {{ v.impact.current ? t('made {at} by {who}', { at: new Date(v.impact.made_at).toLocaleString(), who: v.impact.made_by }) : t('the parts changed since: analyse again') }}</span>
      <Button v-if="v.editable && v.can_edit" size="sm" :label="t('Analyse the impact')" :disabled="!v.items.length || busy" @click="act('analyse', {})" />
      <Button v-if="v.editable && v.can_edit && v.can_ai && v.impact?.current" size="sm" icon-left="lucide-sparkles" :label="t('Draft the impact note')" :disabled="busy" @click="draft" />
    </div>
    <table v-if="v.impact" class="wq-table text-sm"><thead><tr><th>{{ t('Part') }}</th><th>{{ t('Used in') }}</th><th>{{ t('Stock') }}</th><th>{{ t('Open purchase orders') }}</th><th>{{ t('Open work orders') }}</th><th>{{ t('Open sales orders of the machines') }}</th></tr></thead>
      <tbody><tr v-for="p in v.impact.data.parts" :key="p.code">
        <td>{{ p.code }} {{ p.name }}</td>
        <td><span v-for="a in p.used_in" :key="a.id" class="me-2">{{ a.code }}<b v-if="a.top"> ★</b></span><span v-if="!p.used_in.length">–</span></td>
        <td>{{ unknown(p.stock) ? t('unknown') : p.stock }}</td>
        <td v-for="k in ['purchase_orders', 'work_orders', 'sales_orders']" :key="k">
          <span v-if="unknown(p[k])" class="text-ink-amber-7">{{ t('unknown') }}</span>
          <span v-else-if="!p[k].length">–</span>
          <span v-for="o in p[k] || []" :key="o.name" class="me-2">{{ o.name }} ({{ o.open }})</span></td></tr></tbody></table>
    <p v-if="v.impact" class="mt-2 text-sm text-ink-gray-5">{{ t('★ a finished machine. Unknown: there is no data yet (not synced from ERPNext, or ERPNext did not answer).') }}</p>
  </section>
</template>
