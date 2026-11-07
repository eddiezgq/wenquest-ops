<script setup>
// Model configuration of a base machine (ADR-0026, 26c): option groups, what each option does to the base BOM,
// rules between options, generating a model (an item coded base code + option codes, its BOM a draft to release),
// and the models whose BOM no longer matches the configuration.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import { api } from '../api'
import { t } from '../i18n'
import { stl } from '../plm'

const props = defineProps({ partId: { type: Number, required: true } })
const router = useRouter()
const v = ref(null)
const cfg = ref({ groups: [], rules: [] })
const saved = ref('')
const error = ref('')
const done = ref('')
const pick = ref({})
const editing = ref(false)
const dirty = computed(() => JSON.stringify(cfg.value) !== saved.value)
const options = computed(() => cfg.value.groups.flatMap((g) => g.options.map((o) => ({ key: `${g.code}/${o.code}`, label: `${g.name}: ${o.name} (${g.code}/${o.code})` }))))
const actL = (a) => ({ add: t('config::add'), remove: t('config::remove'), replace: t('config::replace') })[a] || a
const ruleL = (k) => ({ requires: t('rule::requires'), excludes: t('rule::excludes') })[k] || k

function set(d) {
  v.value = d
  cfg.value = JSON.parse(JSON.stringify(d.config))
  saved.value = JSON.stringify(cfg.value)
  pick.value = Object.fromEntries(d.config.groups.map((g) => [g.code, g.options.some((o) => o.code === pick.value[g.code]) ? pick.value[g.code] : g.options[0]?.code]))
}
async function load() { error.value = ''; try { set(await api(`/api/plm/parts/${props.partId}/config`)) } catch (e) { error.value = e.message } }
watch(() => props.partId, load, { immediate: true })
async function save() {
  error.value = ''; done.value = ''
  try { set(await api(`/api/plm/parts/${props.partId}/config`, { method: 'PUT', body: { ...cfg.value, version: v.value.version } })); done.value = t('Saved.') } catch (e) { error.value = e.message }
}
async function generate() {
  error.value = ''; done.value = ''
  try {
    const r = await api(`/api/plm/parts/${props.partId}/models`, { method: 'POST', body: { choice: pick.value, version: v.value.version } })
    if (r.existing) { done.value = t('This choice was made before: opening that model.'); router.push(`/plm/parts/${r.model}`) } else router.push(`/plm/boms/${r.bom}`)
  } catch (e) { error.value = e.message }
}
const addGroup = () => cfg.value.groups.push({ code: '', name: '', options: [{ code: '', name: '', edits: [] }] })
const addOption = (g) => g.options.push({ code: '', name: '', edits: [] })
const addEdit = (o) => o.edits.push({ action: 'add', code: '', with: null, qty: 1 })
const addRule = () => cfg.value.rules.push({ kind: 'requires', a: '', b: '' })
</script>

<template>
  <section v-if="v" data-help="plm-config" class="wq-panel mb-5 p-5">
    <h2 class="wq-h2">{{ t('Model configuration') }}</h2>
    <p v-if="error" class="wq-error mb-3">{{ error }}</p>
    <p v-if="done" class="mb-3 text-sm text-ink-green-7">{{ done }}</p>
    <p v-if="!v.base_bom" class="mb-3 text-sm text-ink-amber-7">{{ t('Release the BOM of this machine first: models start from it.') }}</p>
    <p v-else class="mb-3 text-sm text-ink-gray-6">{{ t('Models start from BOM revision {revision}.', { revision: v.base_bom.revision }) }}</p>

    <template v-if="cfg.groups.length && v.base_bom">
      <h3 class="mb-2 text-base font-medium">{{ t('Generate a model') }}</h3>
      <div class="mb-4 flex flex-wrap items-end gap-2">
        <label v-for="g in cfg.groups" :key="g.code" class="wq-field">{{ g.name }}
          <select v-model="pick[g.code]" class="wq-select w-40"><option v-for="o in g.options" :key="o.code" :value="o.code">{{ o.name }} ({{ o.code }})</option></select></label>
        <Button v-if="v.can_edit" variant="solid" :label="t('Generate')" :disabled="dirty" @click="generate" />
      </div>
    </template>

    <h3 class="mb-2 text-base font-medium">{{ t('Models') }}</h3>
    <p v-if="!v.models.length" class="wq-muted mb-4">{{ t('None.') }}</p>
    <table v-else class="wq-table mb-4 text-sm"><thead><tr><th>{{ t('plm::Code') }}</th><th>{{ t('Name') }}</th><th v-for="g in cfg.groups" :key="g.code">{{ g.code }}</th><th>BOM</th><th>{{ t('Matches the configuration') }}</th></tr></thead>
      <tbody><tr v-for="m in v.models" :key="m.id">
        <td><RouterLink :to="`/plm/parts/${m.part_id}`" class="wq-link">{{ m.code }}</RouterLink></td><td>{{ m.name }}</td>
        <td v-for="g in cfg.groups" :key="g.code">{{ m.choice[g.code] || '–' }}</td>
        <td><RouterLink v-if="m.bom" :to="`/plm/boms/${m.bom.id}`" class="wq-link">{{ m.bom.revision }}</RouterLink> <span v-if="m.bom">({{ stl(m.bom.status) }})</span></td>
        <td><Badge v-if="m.differs && !m.differs.length" theme="green" :label="t('yes')" />
          <span v-else-if="m.differs" class="text-ink-amber-7">{{ m.differs.map((d) => `${d.code} ${d.old || '–'} → ${d.new || '–'}`).join('; ') }} · <RouterLink to="/quality/changes" class="wq-link">{{ t('change it under a design change') }}</RouterLink></span>
          <span v-else class="text-ink-red-7">{{ m.problem }}</span></td></tr></tbody></table>

    <details :open="editing || !cfg.groups.length" @toggle="editing = $event.target.open"><summary class="cursor-pointer text-base font-medium">{{ t('Option groups and rules') }}</summary>
      <div v-for="(g, gi) in cfg.groups" :key="gi" class="mt-3 rounded border border-outline-gray-2 p-3">
        <div class="mb-2 flex flex-wrap items-end gap-2">
          <label class="wq-field">{{ t('Group') }}<input v-model="g.name" class="wq-input w-40" :disabled="!v.can_edit"></label>
          <label class="wq-field">{{ t('plm::Code') }}<input v-model="g.code" class="wq-input w-20" :disabled="!v.can_edit"></label>
          <button v-if="v.can_edit" class="text-sm text-ink-red-7" @click="cfg.groups.splice(gi, 1)">{{ t('Remove') }}</button>
        </div>
        <div v-for="(o, oi) in g.options" :key="oi" class="mb-2 ms-4 border-s border-outline-gray-2 ps-3">
          <div class="flex flex-wrap items-end gap-2">
            <label class="wq-field">{{ t('Option') }}<input v-model="o.name" class="wq-input w-40" :disabled="!v.can_edit"></label>
            <label class="wq-field">{{ t('plm::Code') }}<input v-model="o.code" class="wq-input w-20" :disabled="!v.can_edit"></label>
            <button v-if="v.can_edit" class="text-sm text-ink-red-7" @click="g.options.splice(oi, 1)">{{ t('Remove') }}</button>
            <button v-if="v.can_edit" class="text-sm wq-link" @click="addEdit(o)">{{ t('+ change to the BOM') }}</button>
          </div>
          <div v-for="(e, ei) in o.edits" :key="ei" class="mt-1 flex flex-wrap items-center gap-2 text-sm">
            <select v-model="e.action" class="wq-select w-28" :disabled="!v.can_edit"><option v-for="a in ['add', 'remove', 'replace']" :key="a" :value="a">{{ actL(a) }}</option></select>
            <input v-model="e.code" class="wq-input w-36" :placeholder="t('Part code')" :disabled="!v.can_edit">
            <template v-if="e.action === 'replace'">→ <input v-model="e.with" class="wq-input w-36" :placeholder="t('New part code')" :disabled="!v.can_edit"></template>
            <input v-if="e.action !== 'remove'" v-model="e.qty" class="wq-input w-20" :placeholder="e.action === 'replace' ? t('same qty') : t('Quantity')" :disabled="!v.can_edit">
            <button v-if="v.can_edit" class="text-ink-red-7" @click="o.edits.splice(ei, 1)">×</button>
          </div>
        </div>
        <button v-if="v.can_edit" class="ms-4 text-sm wq-link" @click="addOption(g)">{{ t('+ option') }}</button>
      </div>
      <button v-if="v.can_edit" class="mt-3 text-sm wq-link" @click="addGroup">{{ t('+ option group') }}</button>
      <h3 class="mt-4 mb-2 text-base font-medium">{{ t('Rules') }}</h3>
      <div v-for="(r, ri) in cfg.rules" :key="ri" class="mb-1 flex flex-wrap items-center gap-2 text-sm">
        <select v-model="r.a" class="wq-select w-64" :disabled="!v.can_edit"><option v-for="o in options" :key="o.key" :value="o.key">{{ o.label }}</option></select>
        <select v-model="r.kind" class="wq-select w-32" :disabled="!v.can_edit"><option value="requires">{{ ruleL('requires') }}</option><option value="excludes">{{ ruleL('excludes') }}</option></select>
        <select v-model="r.b" class="wq-select w-64" :disabled="!v.can_edit"><option v-for="o in options" :key="o.key" :value="o.key">{{ o.label }}</option></select>
        <button v-if="v.can_edit" class="text-ink-red-7" @click="cfg.rules.splice(ri, 1)">×</button>
      </div>
      <button v-if="v.can_edit" class="text-sm wq-link" @click="addRule">{{ t('+ rule') }}</button>
      <div v-if="v.can_edit" class="mt-3 flex gap-2"><Button variant="solid" :label="t('Save')" :disabled="!dirty" @click="save" />
        <span v-if="dirty" class="text-sm text-ink-amber-7">{{ t('Save the configuration before generating a model.') }}</span></div>
    </details>
  </section>
</template>
