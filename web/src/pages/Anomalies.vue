<script setup>
import { ref, watch } from 'vue'
import { api, objectPath } from '../api'
import { ago } from '../format'

const status = ref('active')
const rows = ref([])
const error = ref('')
async function load() {
  try { rows.value = await api(`/api/anomalies?status=${status.value}`) } catch (e) { error.value = e.message }
}
watch(status, load, { immediate: true })
</script>

<template>
  <div class="head">
    <h1>Anomalies</h1>
    <label class="muted">Show <select v-model="status">
      <option value="active">Active</option><option value="resolved">Resolved</option>
      <option value="closed">Closed</option><option value="all">All</option></select></label>
  </div>
  <p v-if="error" class="err">{{ error }}</p>
  <p v-if="!rows.length" class="muted">None.</p>
  <table v-else class="grid">
    <thead><tr><th>Severity</th><th>What</th><th>Rule</th><th>About</th><th>Status</th><th>Since</th></tr></thead>
    <tbody>
      <tr v-for="a in rows" :key="a.id" :class="a.severity">
        <td><span class="sev">{{ a.severity }}</span></td>
        <td><RouterLink :to="`/anomalies/${a.id}`">{{ a.title }}</RouterLink><div class="muted small">{{ a.detail }}</div></td>
        <td class="small">{{ a.rule_name }}</td>
        <td class="small"><RouterLink :to="objectPath(...a.subject)">{{ a.subject[1] }}</RouterLink></td>
        <td>{{ a.status }}</td>
        <td class="small">{{ ago(a.first_seen) }}</td>
      </tr>
    </tbody>
  </table>
</template>
