<script setup>
// Change control (ADR-0017, 17g): changes raised, assessed, approved by someone who did not raise, own, submit or
// edit them (signed), implemented and closed by someone other than the owner (signed).
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { t } from '../i18n'

const router = useRouter()
const v = ref(null)
const error = ref('')
const status = ref('open')
const show = ref(false)
const f = ref({ title: '', kind: 'process' })
const ST = { draft: 'gray', submitted: 'amber', approved: 'blue', implemented: 'violet', closed: 'green', cancelled: 'gray' }
async function load() { try { v.value = await api(`/api/changes?status=${status.value}`) } catch (e) { error.value = e.message } }
watch(status, load, { immediate: true })
async function create() {
  error.value = ''
  try { const r = await api('/api/changes', { method: 'POST', body: f.value }); router.push(`/quality/changes/${r.id}`) } catch (e) { error.value = e.message }
}
</script>

<template>
  <PageTop :crumbs="[{ label: t('Quality'), to: '/quality' }]">
    <template #title>{{ t('Changes') }}</template>
    <Button v-if="v?.can_edit" variant="solid" icon-left="lucide-plus" :label="t('Raise a change')" @click="show = !show" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <form v-if="show" class="new wq-panel mb-5 flex flex-wrap items-end gap-3 p-5" @submit.prevent="create">
    <label class="wq-field grow">{{ t('Title') }}<input v-model="f.title" class="wq-input"></label>
    <label class="wq-field">{{ t('Kind') }}<select v-model="f.kind" class="wq-select"><option v-for="k in v?.kinds" :key="k" :value="k">{{ t(k) }}</option></select></label>
    <Button type="submit" variant="solid" :label="t('Raise')" :disabled="!f.title.trim()" />
  </form>
  <section v-if="v" data-help="changes-list" class="wq-panel p-5">
    <div class="mb-3"><select v-model="status" class="wq-select w-40"><option value="open">{{ t('status::Open') }}</option><option value="closed">{{ t('Closed') }}</option><option value="cancelled">{{ t('Cancelled') }}</option><option value="all">{{ t('All') }}</option></select></div>
    <p v-if="!v.changes.length" class="wq-muted">{{ t('None.') }}</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Number') }}</th><th>{{ t('Title') }}</th><th>{{ t('Kind') }}</th><th>{{ t('Status') }}</th><th>{{ t('Owner') }}</th><th>{{ t('Target') }}</th><th>{{ t('Regulatory') }}</th></tr></thead>
      <tbody><tr v-for="c in v.changes" :key="c.id">
        <td><RouterLink :to="`/quality/changes/${c.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ c.name }}</RouterLink></td>
        <td>{{ c.title }}</td><td>{{ t(c.kind) }}</td><td><Badge :theme="ST[c.status]" :label="t(c.status)" /></td><td>{{ c.owner }}</td>
        <td :class="c.overdue ? 'text-ink-red-7' : ''">{{ c.overdue ? t('{date} (overdue)', { date: c.target_date || '–' }) : (c.target_date || '–') }}</td>
        <td><Badge v-if="c.q_regulatory === 'yes'" theme="amber" :label="t('yes')" /></td></tr></tbody></table>
  </section>
</template>
