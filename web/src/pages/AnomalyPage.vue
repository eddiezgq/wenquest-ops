<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, objectPath } from '../api'
import { ago } from '../format'
import Chain from '../components/Chain.vue'

const route = useRoute()
const a = ref(null)
const note = ref('')
const error = ref('')
const NEXT = { open: ['ack', 'doing', 'closed'], ack: ['doing', 'closed'], doing: ['ack', 'closed'] }
const LABEL = { ack: 'Acknowledge', doing: 'Working on it', closed: 'Close' }

async function load() {
  try { a.value = await api(`/api/anomalies/${route.params.id}`) } catch (e) { error.value = e.message }
}
async function setStatus(s) {
  error.value = ''
  try {
    await api(`/api/anomalies/${a.value.id}/status`, { method: 'POST', body: { status: s, note: note.value } })
    note.value = ''
    await load()
  } catch (e) {
    error.value = e.message
  }
}
watch(() => route.params.id, load, { immediate: true })
</script>

<template>
  <p v-if="error" class="err">{{ error }}</p>
  <template v-if="a">
    <p class="muted small"><RouterLink to="/anomalies">Anomalies</RouterLink> · {{ a.rule_name }}</p>
    <h1><span class="sev" :class="a.severity">{{ a.severity }}</span> {{ a.title }}</h1>
    <p>{{ a.detail }}</p>
    <p><b>Suggested:</b> {{ a.hint }} <span class="muted">(usually handled by: {{ a.owner?.replace('_', ' ') }})</span></p>
    <p>About <RouterLink :to="objectPath(...a.subject)">{{ a.subject[1] }}</RouterLink>
      <template v-for="r in a.related" :key="r.join()"> · <RouterLink :to="objectPath(...r)">{{ r[1] }}</RouterLink></template></p>
    <div class="actions" v-if="NEXT[a.status]">
      <input v-model="note" placeholder="Note (optional)">
      <button v-for="s in NEXT[a.status]" :key="s" @click="setStatus(s)">{{ LABEL[s] }}</button>
    </div>
    <p v-else class="muted">Status: {{ a.status }} {{ a.ended_at ? 'on ' + ago(a.ended_at) : '' }}</p>
    <h2>Causes and impact</h2>
    <Chain :explain="a.explain" />
    <h2>Log</h2>
    <ul class="list small">
      <li v-for="(l, i) in a.log" :key="i">{{ ago(l.at) }} — <b>{{ l.action }}</b> {{ l.email || 'WenQuest Ops' }}
        <span class="muted">{{ l.note }}</span></li>
    </ul>
  </template>
</template>
