<script setup>
import { ref, watch } from 'vue'
import { Badge } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { SEV, STATUS } from '../ui/themes'
import { api, objectPath } from '../api'
import { ago } from '../format'
import { t } from '../i18n'

const status = ref('active')
const rows = ref([])
const error = ref('')
async function load() {
  try { rows.value = await api(`/api/anomalies?status=${status.value}`) } catch (e) { error.value = e.message }
}
watch(status, load, { immediate: true })
</script>

<template>
  <PageTop :title="t('Anomalies')">
    <select v-model="status" data-help="anomalies-show" class="wq-select" :aria-label="t('Show')">
      <option value="active">{{ t('Active') }}</option><option value="resolved">{{ t('Resolved') }}</option>
      <option value="closed">{{ t('Closed') }}</option><option value="all">{{ t('All') }}</option></select>
  </PageTop>
  <p v-if="error" class="wq-error">{{ error }}</p>
  <p v-if="!rows.length" class="wq-muted">{{ t('None.') }}</p>
  <div v-else data-help="anomalies-list" class="wq-panel overflow-x-auto">
    <table class="wq-table">
      <thead><tr><th class="w-24">{{ t('Severity') }}</th><th>{{ t('What') }}</th><th>{{ t('Rule') }}</th><th>{{ t('About') }}</th><th>{{ t('Status') }}</th><th>{{ t('Since') }}</th></tr></thead>
      <tbody>
        <tr v-for="a in rows" :key="a.id">
          <td><Badge :theme="SEV[a.severity]" :label="t(a.severity)" class="capitalize" /></td>
          <td><RouterLink :to="`/anomalies/${a.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ a.title }}</RouterLink>
            <div class="mt-0.5 text-sm text-ink-gray-5">{{ a.detail }}</div></td>
          <td class="text-sm text-ink-gray-6">{{ a.rule_name }}</td>
          <td class="text-sm"><RouterLink :to="objectPath(...a.subject)" class="wq-link">{{ a.subject[1] }}</RouterLink></td>
          <td><Badge :theme="STATUS[a.status] || 'gray'" :label="t(a.status)" variant="outline" /></td>
          <td class="whitespace-nowrap text-sm text-ink-gray-5">{{ ago(a.first_seen) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
