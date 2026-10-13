<script setup>
import { onMounted, provide, ref } from 'vue'
import { api } from './api'
import { setCurrency } from './format'
import Tour from './components/Tour.vue'

const ws = ref(null)
const error = ref('')
const touring = ref(false)
provide('workspace', ws)
provide('startTour', () => { touring.value = true })
const TOUR_KEY = 'wqo-tour-done'
function tourDone() {
  touring.value = false
  try { localStorage.setItem(TOUR_KEY, '1') } catch { /* the tour just shows again next time */ }
}

onMounted(async () => {
  try {
    ws.value = await api('/api/workspace')
    setCurrency(ws.value.currency)
    // the tour starts by itself only on the first visit to the dashboard
    try { touring.value = location.pathname === '/' && !localStorage.getItem(TOUR_KEY) } catch { touring.value = false }
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
      <RouterLink to="/assistant" active-class="on">Assistant</RouterLink>
      <RouterLink to="/anomalies" active-class="on">Anomalies</RouterLink>
      <RouterLink v-if="ws.user.permissions.includes('quality:view')" to="/quality" active-class="on">Quality</RouterLink>
      <RouterLink to="/objects" active-class="on">Objects</RouterLink>
      <RouterLink to="/drafts" active-class="on">Drafts</RouterLink>
      <RouterLink v-if="ws.user.permissions.includes('users:view')" to="/people" active-class="on">People</RouterLink>
      <RouterLink to="/help" active-class="on">Help</RouterLink>
      <a v-if="ws.erp_url" :href="ws.erp_url + '/login'" target="_blank" rel="noopener">ERPNext ↗</a>
    </nav>
    <div class="me">
      <RouterLink to="/account" title="My account">{{ ws.user.name }}</RouterLink>
      <button class="link" @click="signOut">Sign out</button>
    </div>
  </header>
  <main>
    <p v-if="error" class="err">{{ error }}</p>
    <RouterView v-if="ws" />
    <Tour v-if="ws && touring" :permissions="ws.user.permissions" @done="tourDone" />
  </main>
  <footer v-if="ws" class="muted">WenQuest Ops {{ ws.version }}</footer>
</template>
