<script setup>
// Management reviews (ADR-0017, 17j): the inputs counted from every module, the meeting, the decisions, the chair's
// signature.
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { t } from '../i18n'

const router = useRouter()
const v = ref(null)
const error = ref('')
const show = ref(false)
const now = new Date()
const y = now.getFullYear()
const local = `${y}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
const f = ref({ title: t('Management review {year}', { year: y }), period_start: `${y}-01-01`, period_end: local })
const ST = { draft: 'gray', frozen: 'blue', closed: 'green', cancelled: 'gray' }
const STATUS = { draft: 'draft', frozen: 'inputs collected', closed: 'signed', cancelled: 'cancelled' }
async function load() { try { v.value = await api('/api/reviews') } catch (e) { error.value = e.message } }
load()
async function create() {
  error.value = ''
  try { const r = await api('/api/reviews', { method: 'POST', body: f.value }); router.push(`/quality/reviews/${r.id}`) } catch (e) { error.value = e.message }
}
</script>

<template>
  <PageTop :crumbs="[{ label: t('Quality system'), to: '/system' }]">
    <template #title>{{ t('Management reviews') }}</template>
    <Button v-if="v?.can_configure" data-help="new-review" variant="solid" icon-left="lucide-plus" :label="t('New review')" @click="show = !show" />
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <form v-if="show" data-help="review-period" class="new wq-panel mb-5 flex flex-wrap items-end gap-3 p-5" @submit.prevent="create">
    <label class="wq-field grow">{{ t('Title') }}<input v-model="f.title" class="wq-input"></label>
    <label class="wq-field">{{ t('From') }}<input v-model="f.period_start" type="date" class="wq-input"></label>
    <label class="wq-field">{{ t('To') }}<input v-model="f.period_end" type="date" class="wq-input"></label>
    <Button type="submit" variant="solid" :label="t('Start')" :disabled="!f.title.trim()" />
  </form>
  <section v-if="v" data-help="reviews-list" class="wq-panel p-5">
    <p class="wq-muted mb-3 max-w-3xl">{{ t('Top management reviews the quality system at planned intervals. WenQuest Ops counts the inputs from your records for the period; the meeting writes its assessment, conclusion and actions, and the chair signs.') }}</p>
    <p v-if="!v.reviews.length" class="wq-muted">{{ t('None yet.') }}</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>{{ t('Number') }}</th><th>{{ t('Title') }}</th><th>{{ t('Period') }}</th><th>{{ t('Meeting') }}</th><th>{{ t('Chair') }}</th><th>{{ t('Status') }}</th></tr></thead>
      <tbody><tr v-for="r in v.reviews" :key="r.id">
        <td><RouterLink :to="`/quality/reviews/${r.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ r.name }}</RouterLink></td>
        <td>{{ r.title }}</td><td>{{ t('{from} to {to}', { from: r.period_start, to: r.period_end }) }}</td><td>{{ r.meeting_on }}</td><td>{{ r.chair }}</td>
        <td><Badge :theme="ST[r.status]" :label="t(STATUS[r.status])" /></td></tr></tbody></table>
  </section>
</template>
