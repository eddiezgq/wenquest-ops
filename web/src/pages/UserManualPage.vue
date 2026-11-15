<script setup>
// The instruction manual of a machine (33d, ADR-0031): eight fixed chapters, Chinese and English with pictures. The
// AI drafts a chapter, a person edits and confirms it; only confirmed chapters go into an edition (print and screen
// PDFs). Editing a confirmed chapter makes it a draft again.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, apiForm } from '../api'
import { t } from '../i18n'

const route = useRoute()
const v = ref(null)
const error = ref('')
const done = ref('')
const busy = ref('')
const edit = ref({})            // chapter key -> {body_zh, body_en, figures} as being edited
const pid = () => Number(route.params.id)
const when = (x) => x?.slice(0, 16).replace('T', ' ') || '–'
const explodeOf = computed(() => Object.fromEntries((v.value?.explodes || []).map((e) => [e.code, e])))
const ST = { none: 'gray', draft: 'amber', confirmed: 'green' }
const stl = (s) => ({ none: t('not written'), draft: t('draft'), confirmed: t('confirmed') }[s] || s)

function take(d) {
  v.value = d
  edit.value = Object.fromEntries(d.chapters.map((c) => [c.key, { body_zh: c.body_zh, body_en: c.body_en, figures: (c.figures || []).map((f) => ({ ...f })) }]))
}
async function load() { error.value = ''; try { take(await api(`/api/plm/user-manual/${pid()}`)) } catch (e) { error.value = e.message } }
watch(() => route.params.id, load, { immediate: true })

async function act(key, what, fn) {
  busy.value = `${key}:${what}`; error.value = ''; done.value = ''
  try { take(await fn()) } catch (e) { error.value = e.message } finally { busy.value = '' }
}
const save = (c) => act(c.key, 'save', () => api(`/api/plm/user-manual/${pid()}/chapters/${c.key}`, { method: 'PUT', body: edit.value[c.key] }))
const confirm = (c) => act(c.key, 'confirm', async () => {
  await api(`/api/plm/user-manual/${pid()}/chapters/${c.key}`, { method: 'PUT', body: edit.value[c.key] })
  return api(`/api/plm/user-manual/${pid()}/chapters/${c.key}/confirm`, { method: 'POST', body: {} })
})
const draft = (c) => act(c.key, 'draft', () => api(`/api/plm/user-manual/${pid()}/chapters/${c.key}/draft`, { method: 'POST', body: {} }))
const generate = () => act('', 'generate', async () => {
  const r = await api(`/api/plm/user-manual/${pid()}/editions`, { method: 'POST', body: {} })
  done.value = t('Edition {n} made.', { n: r.editions[0].edition })
  return r
})
const changed = (c) => { const e = edit.value[c.key]; return e && (e.body_zh !== c.body_zh || e.body_en !== c.body_en || JSON.stringify(e.figures) !== JSON.stringify(c.figures || [])) }

function addExplode(c, code) { if (code) edit.value[c.key].figures.push({ kind: 'explode', code, caption: explodeOf.value[code]?.name || '' }) }
async function upload(c, ev) {
  const f = ev.target.files[0]
  if (!f) return
  const form = new FormData(); form.append('file', f, f.name)
  try {
    const fig = await apiForm(`/api/plm/user-manual/${pid()}/pictures`, form)
    edit.value[c.key].figures.push(fig)
    await save(c)
  } catch (e) { error.value = e.message } finally { ev.target.value = '' }
}
const thumb = (f) => (f.kind === 'upload' ? `/api/plm/user-manual/${pid()}/pictures/${f.sha}`
  : explodeOf.value[f.code] ? `/api/plm/explode/${explodeOf.value[f.code].bom}/snapshot` : '')
</script>

<template>
  <PageTop :crumbs="[{ label: t('Parts'), to: '/plm/parts' }, ...(v ? [{ label: v.part.code, to: `/plm/parts/${v.part.id}` }] : [])]">
    <template #title>{{ t('Instruction manual') }}</template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="v">
    <section data-help="plm-user-manual" class="wq-panel mb-5 p-5">
      <p class="text-sm text-ink-gray-6">{{ v.part.name }} · {{ t('{n} of 8 chapters confirmed. Only confirmed chapters go into an edition.', { n: v.confirmed }) }}</p>
      <Button v-if="v.can_edit" class="mt-3" variant="solid" :loading="busy === ':generate'" :disabled="!v.confirmed" :label="t('Make a new edition')" @click="generate" />
      <table v-if="v.editions.length" class="wq-table mt-4 text-sm"><thead><tr><th>{{ t('manual::Edition') }}</th><th>{{ t('Chapters') }}</th><th>{{ t('Made by') }}</th><th>{{ t('Made at') }}</th><th /></tr></thead>
        <tbody><tr v-for="e in v.editions" :key="e.id"><td>{{ t('Edition {n}', { n: e.edition }) }}</td><td>{{ e.chapters }}</td><td>{{ e.created_by }}</td><td>{{ when(e.created_at) }}</td>
          <td><a :href="`/api/plm/user-manual/editions/${e.id}/pdf`" target="_blank" class="wq-link">{{ t('PDF (screen)') }}</a>
            <a :href="`/api/plm/user-manual/editions/${e.id}/pdf?kind=print`" target="_blank" class="wq-link ms-3">{{ t('PDF (print)') }}</a></td></tr></tbody></table>
    </section>

    <section v-for="(c, n) in v.chapters" :key="c.key" :data-help="n === 0 ? 'plm-user-manual-chapter' : undefined" class="wq-panel mb-5 p-5">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <h2 class="wq-h2 mb-0">{{ n + 1 }}. {{ c.title_zh }} <span class="text-base font-normal text-ink-gray-5">{{ c.title_en }}</span></h2>
        <Badge :theme="ST[c.state]" :label="stl(c.state)" />
        <span v-if="c.drafted_by" class="text-sm text-ink-gray-5">{{ t('Written by {who}', { who: c.drafted_by }) }}<span v-if="c.confirmed_by"> · {{ t('Confirmed by {who}', { who: c.confirmed_by }) }}</span></span>
      </div>
      <div class="grid gap-3 lg:grid-cols-2">
        <label class="text-sm">中文<textarea v-model="edit[c.key].body_zh" rows="9" class="wq-input mt-1 w-full" :disabled="!v.can_edit" /></label>
        <label class="text-sm">English<textarea v-model="edit[c.key].body_en" rows="9" class="wq-input mt-1 w-full" :disabled="!v.can_edit" /></label>
      </div>
      <div class="mt-3 flex flex-wrap gap-3">
        <figure v-for="(f, i) in edit[c.key].figures" :key="i" class="w-48 text-xs">
          <img v-if="thumb(f)" :src="thumb(f)" class="h-32 w-full rounded-3 border border-outline-gray-2 bg-white object-contain" alt="">
          <input v-model="f.caption" class="wq-input mt-1 h-7 w-full text-xs" :placeholder="t('Caption')" :disabled="!v.can_edit">
          <button v-if="v.can_edit" class="mt-1 text-ink-red-7" @click="edit[c.key].figures.splice(i, 1)">{{ t('Remove') }}</button>
        </figure>
      </div>
      <div v-if="v.can_edit" class="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <select class="wq-select w-64" @change="addExplode(c, $event.target.value); $event.target.value = ''">
          <option value="">{{ t('Add an exploded view…') }}</option>
          <option v-for="e in v.explodes" :key="e.code" :value="e.code">{{ e.code }} {{ e.name }}</option>
        </select>
        <label>{{ t('or a picture of your own') }} <input type="file" accept="image/png,image/jpeg" class="text-sm" @change="upload(c, $event)"></label>
      </div>
      <div v-if="v.can_edit" class="mt-4 flex flex-wrap gap-2">
        <Button :label="t('AI drafts this chapter')" :loading="busy === `${c.key}:draft`" @click="draft(c)" />
        <Button :label="t('Save')" :disabled="!changed(c)" :loading="busy === `${c.key}:save`" @click="save(c)" />
        <Button variant="solid" :label="t('Confirm')" :disabled="c.state === 'confirmed' && !changed(c)" :loading="busy === `${c.key}:confirm`" @click="confirm(c)" />
      </div>
    </section>
  </template>
</template>
