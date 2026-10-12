<script setup>
import { onMounted, provide, ref } from 'vue'
import { api } from './api'
import { setCurrency } from './format'

const ws = ref(null)
const error = ref('')
provide('workspace', ws)

onMounted(async () => {
  try {
    ws.value = await api('/api/workspace')
    setCurrency(ws.value.currency)
  } catch (e) {
    error.value = e.message
  }
})

async function signOut() {
  await fetch('/api/logout', { method: 'POST' })
  location.href = '/login'
}
</script>

<template>
  <header class="top" v-if="ws">
    <div class="brand">
      <strong>{{ ws.company }}</strong>
      <span v-if="ws.demo" class="tag">fictional demo</span>
    </div>
    <nav>
      <RouterLink to="/" exact-active-class="on">Dashboard</RouterLink>
      <RouterLink to="/anomalies" active-class="on">Anomalies</RouterLink>
      <RouterLink to="/objects" active-class="on">Objects</RouterLink>
      <a v-if="ws.erp_url" :href="ws.erp_url + '/login'" target="_blank" rel="noopener">ERPNext ↗</a>
    </nav>
    <div class="me">
      <span>{{ ws.user.name }}</span>
      <button class="link" @click="signOut">Sign out</button>
    </div>
  </header>
  <main>
    <p v-if="error" class="err">{{ error }}</p>
    <RouterView v-if="ws" />
  </main>
  <footer v-if="ws" class="muted">WenQuest Ops {{ ws.version }}</footer>
</template>
