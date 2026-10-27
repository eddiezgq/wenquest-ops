<script setup>
// Setting the quality system up (ADR-0016, 16d): a short questionnaire, changes the AI proposes from your own
// procedures (each quoting them, accepted one by one), and procedures written from the workflow in use.
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { ago } from '../format'
import { standard } from '../standard'
import { t } from '../i18n'

const router = useRouter()
const v = ref(null)
const error = ref('')
const done = ref('')
const busy = ref('')
const form = ref({})
const password = ref('')
const chosen = ref([])
const prop = ref(null)
const pw = ref({})

async function load() {
  try {
    v.value = await api(`/api/qms/${standard.value}/setup`)
    form.value = { ...v.value.answers }
    if (v.value.proposals.length && !prop.value) prop.value = await api(`/api/qms-setup/${v.value.proposals[0].id}`)
  } catch (e) { error.value = e.message }
}
load()
async function run(key, fn, message) {
  error.value = ''; done.value = ''; busy.value = key
  try { await fn(); done.value = message } catch (e) { error.value = e.message } finally { busy.value = '' }
}
const save = () => run('save', async () => {
  const answers = Object.fromEntries(Object.entries(form.value).filter(([, x]) => x !== '' && x !== undefined))
  v.value = await api(`/api/qms/${standard.value}/setup/answers`, { method: 'POST', body: { answers } })
}, t('Answers saved.'))
const apply = () => run('apply', async () => {
  v.value = await api(`/api/qms/${standard.value}/setup/apply`, { method: 'POST', body: { password: password.value } })
  password.value = ''
}, t('Declared and signed.'))
const ask = () => run('ask', async () => {
  prop.value = await api(`/api/qms/${standard.value}/setup/proposals`, { method: 'POST', body: { document_ids: chosen.value } })
  v.value = await api(`/api/qms/${standard.value}/setup`)
}, t('Suggestions ready below.'))
const open = (id) => run('open', async () => { prop.value = await api(`/api/qms-setup/${id}`) }, '')
const decide = (it, how) => run(`i${it.id}`, async () => {
  prop.value = await api(`/api/qms-setup-items/${it.id}/${how}`, { method: 'POST', body: { password: pw.value[it.id] || '' } })
  v.value = await api(`/api/qms/${standard.value}/setup`)
}, how === 'accept' ? t('Done: the change is made.') : t('Rejected.'))
const write = (kind) => run(`w${kind}`, async () => {
  const d = await api(`/api/qms-procedures/${kind}`, { method: 'POST' })
  router.push(`/documents/${d.document_id}`)
}, '')
const toApply = computed(() => (v.value?.proposed || []).filter((p) => !p.same))
const label = (d) => [d.number, d.title].filter(Boolean).join(' ') || d.original_name
</script>

<template>
  <PageTop :crumbs="[{ label: t('Quality system'), to: '/system' }]">
    <template #title>{{ v ? t('Set up for {name}', { name: v.name }) : t('Set up') }}</template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>

  <template v-if="v">
    <p v-if="!v.adopted" class="wq-panel mb-4 p-4 text-base">{{ t('Adopt the standard on the') }} <RouterLink to="/system" class="wq-link">{{ t('Quality system') }}</RouterLink> {{ t('page first.') }}</p>

    <section data-help="setup-questions" class="questions wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('1. About the company') }}</h2>
      <p class="wq-muted mb-3">{{ t('The answers say which requirements may not apply. Nothing changes until you declare it with your password.') }}</p>
      <div class="grid gap-3 md:grid-cols-2">
        <label v-for="(q, k) in v.questions" :key="k" class="wq-field">{{ q.label }}
          <select v-if="q.type === 'yesno'" v-model="form[k]" class="wq-select" :disabled="!v.can_configure">
            <option :value="undefined" /><option :value="true">{{ t('yes') }}</option><option :value="false">{{ t('no') }}</option></select>
          <input v-else-if="q.type === 'number'" v-model.number="form[k]" type="number" min="1" class="wq-input" :disabled="!v.can_configure">
          <input v-else v-model="form[k]" class="wq-input" :disabled="!v.can_configure">
        </label>
      </div>
      <div v-if="v.can_configure" class="mt-3"><Button :label="t('Save the answers')" :loading="busy === 'save'" @click="save" /></div>
      <div v-if="v.proposed.length" data-help="setup-declare" class="mt-4">
        <p class="mb-1 text-sm font-medium text-ink-gray-8">{{ t('What the answers say') }}</p>
        <ul class="mb-3 text-sm"><li v-for="p in v.proposed" :key="p.control">
          <Badge :theme="p.applies ? 'green' : 'blue'" :label="p.applies ? t('applies') : t('does not apply')" /> {{ p.control.replace('_', ' ') }}: {{ p.reason }}
          <span v-if="p.same" class="text-ink-gray-5">{{ ' ' + t('(already declared)') }}</span></li></ul>
        <div v-if="v.can_configure && toApply.length" class="flex flex-wrap items-end gap-2">
          <label class="wq-field">{{ t('Your password to declare {n}', { n: toApply.length }) }}<input v-model="password" type="password" class="wq-input w-48" autocomplete="current-password"></label>
          <Button variant="solid" :label="t('Declare (sign)')" :disabled="!password" :loading="busy === 'apply'" @click="apply" />
        </div>
      </div>
    </section>

    <section data-help="setup-procedures" class="suggestions wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('2. From your own procedures') }}</h2>
      <p class="wq-muted mb-3">{{ t('The AI reads the procedures you choose and suggests settings, what does not apply and which procedure shows a requirement. Each suggestion quotes the procedure; WenQuest Ops checks the quote. You accept or reject each one. Workflow changes are suggested on the Quality → Workflows page.') }}</p>
      <template v-if="v.can_propose">
        <p v-if="!v.procedures.length" class="wq-muted">{{ t('No procedures in effect in the document library yet.') }}</p>
        <div v-else class="mb-3 flex max-h-48 flex-col gap-1 overflow-y-auto text-sm">
          <label v-for="d in v.procedures" :key="d.id" class="inline-flex items-center gap-2"><input v-model="chosen" type="checkbox" class="form-checkbox" :value="d.id">{{ label(d) }}</label>
        </div>
        <Button v-if="v.procedures.length" variant="solid" icon-left="lucide-sparkles" :disabled="!chosen.length || chosen.length > 8"
                :loading="busy === 'ask'" :label="t('Read {n} and suggest', { n: chosen.length })" @click="ask" />
      </template>
      <p v-else-if="!v.ai" class="wq-muted">{{ t("This needs the company's model key. Everything can be set by hand on the Quality system page.") }}</p>
      <ul v-if="v.proposals.length" class="mt-3 text-sm"><li v-for="p in v.proposals" :key="p.id">
        <a href="#" class="wq-link" @click.prevent="open(p.id)">{{ t('Suggestions {when}', { when: ago(p.created_at) }) }}</a>
        <span class="text-ink-gray-5">{{ ' ' + t('by {who}: {changes} suggested, {accepted} accepted', { who: p.created_by, changes: p.changes, accepted: p.accepted }) }}</span></li></ul>
      <div v-if="prop" class="mt-4 flex flex-col gap-3">
        <p class="text-sm text-ink-gray-7">{{ prop.summary }}</p>
        <article v-for="it in prop.items" :key="it.id" class="item rounded-4 border border-outline-gray-2 p-3 text-sm">
          <p class="font-medium text-ink-gray-9">{{ it.text }}
            <Badge v-if="it.decision !== 'open'" :theme="it.decision === 'accepted' ? 'green' : 'gray'" :label="t(it.decision)" />
            <Badge v-else-if="it.already" theme="gray" :label="t('already so')" />
            <Badge v-else-if="!it.acceptable" theme="red" :label="t('cannot be accepted')" /></p>
          <blockquote class="my-1 border-s-2 ps-3 italic text-ink-gray-8" :class="it.verified ? 'border-outline-green-3' : 'border-outline-red-3'">“{{ it.quote }}”</blockquote>
          <p v-if="it.verified" class="text-ink-green-7">{{ t('Found in {name}', { name: it.document?.name }) }}</p>
          <ul v-if="it.problems.length" class="list-disc ps-5 text-ink-red-7"><li v-for="x in it.problems" :key="x">{{ x }}</li></ul>
          <div v-if="prop.can_decide !== false && v.can_configure && it.decision === 'open' && !it.already" class="mt-2 flex flex-wrap items-end gap-2">
            <input v-if="it.acceptable && it.change.kind === 'applies'" v-model="pw[it.id]" type="password" class="wq-input w-44" :placeholder="t('Your password')">
            <Button v-if="it.acceptable" size="sm" variant="solid" :label="t('Accept')" :loading="busy === `i${it.id}`" @click="decide(it, 'accept')" />
            <Button size="sm" :label="t('Reject')" @click="decide(it, 'reject')" />
          </div>
        </article>
      </div>
    </section>

    <section data-help="setup-written" class="written wq-panel p-5">
      <h2 class="wq-h2">{{ t('3. Procedures written from the workflow') }}</h2>
      <p class="wq-muted mb-3">{{ t('WenQuest Ops writes the procedure from the workflow in use, so the procedure says what the system does. It goes into Documents to review and is in effect once someone else approves it. Write it again after the workflow changes.') }}</p>
      <div v-if="v.can_write" class="mb-3 flex flex-wrap gap-2">
        <Button :label="t('Write the nonconformance procedure')" :loading="busy === 'wncr'" @click="write('ncr')" />
        <Button :label="t('Write the corrective action procedure')" :loading="busy === 'wcapa'" @click="write('capa')" />
      </div>
      <ul v-if="v.generated.length" class="text-sm"><li v-for="d in v.generated" :key="d.id">
        <RouterLink :to="`/documents/${d.id}`" class="wq-link">{{ d.title }}</RouterLink>
        <span class="text-ink-gray-5">{{ ' ' + t('from the {source}, {status}', { source: d.generated_from, status: t(d.status.replace('_', ' ')) }) }}</span>
        <Badge v-if="!d.current" theme="amber" :label="t('the workflow changed since: write it again')" /></li></ul>
    </section>
  </template>
</template>
