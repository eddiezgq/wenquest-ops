<script setup>
// The app frame (ADR-0013): Frappe's desktop shell with a sidebar like ERPNext's. Each page puts its own header
// (ui/PageTop.vue).
import { computed, onMounted, provide, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  Avatar, DesktopShell, FrappeUIProvider, Sidebar, SidebarCollapseToggle, SidebarHeader,
  SidebarItem, SidebarLabel,
} from 'frappe-ui'
import { api } from './api'
import { setCurrency } from './format'
import Tour from './components/Tour.vue'

const route = useRoute()
const ws = ref(null)
const error = ref('')
const touring = ref(false)
provide('workspace', ws)
const startTour = () => { touring.value = true }
provide('startTour', startTour)
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

const can = (p) => ws.value?.user.permissions.includes(p)
const menu = computed(() => [
  { label: 'My account', icon: 'lucide-user', route: '/account' },
  { label: 'Help', icon: 'lucide-circle-help', route: '/help' },
  { label: 'Take the guided tour', icon: 'lucide-map', onClick: startTour },
  { label: 'Sign out', icon: 'lucide-log-out', onClick: signOut },
])
</script>

<template>
  <FrappeUIProvider>
    <div v-if="error && !ws" class="p-8 text-base text-ink-red-7">{{ error }}</div>
    <DesktopShell v-if="ws">
      <template #sidebar>
        <Sidebar class="bg-surface-sidebar border-e border-outline-gray-1">
          <SidebarHeader :title="ws.company" :subtitle="ws.demo ? 'Fictional demo' : 'WenQuest Ops'" :menu-items="menu" />
          <div class="flex-1 overflow-y-auto">
            <SidebarItem label="Dashboard" icon="lucide-layout-dashboard" route="/" :active="route.path === '/'" />
            <SidebarItem label="Assistant" icon="lucide-sparkles" route="/assistant" />
            <SidebarItem label="Anomalies" icon="lucide-triangle-alert" route="/anomalies" />
            <SidebarItem label="Drafts" icon="lucide-file-pen-line" route="/drafts" />
            <SidebarLabel divider>Records</SidebarLabel>
            <SidebarItem v-if="can('quality:view')" label="Quality" icon="lucide-shield-check" route="/quality" />
            <SidebarItem v-if="can('quality:view')" label="Complaints" icon="lucide-message-square-warning" route="/quality/complaints" />
            <SidebarItem v-if="can('quality:view')" label="Incoming inspection" icon="lucide-scan-search" route="/quality/iqc" />
            <SidebarItem v-if="can('quality:view')" label="Approved suppliers" icon="lucide-badge-check" route="/quality/suppliers" />
            <SidebarItem v-if="can('quality:view')" label="Quality system" icon="lucide-list-checks" route="/system" />
            <SidebarItem v-if="can('documents:view')" label="Documents" icon="lucide-folder-open" route="/documents" />
            <SidebarItem label="My reading" icon="lucide-book-open-check" route="/documents/control" />
            <SidebarItem label="Objects" icon="lucide-boxes" route="/objects" />
            <SidebarLabel divider>Workspace</SidebarLabel>
            <SidebarItem v-if="can('users:view')" label="People" icon="lucide-users" route="/people" />
            <SidebarItem label="Help" icon="lucide-circle-help" route="/help" />
            <SidebarItem v-if="ws.erp_url" label="ERPNext" icon="lucide-external-link" :href="ws.erp_url + '/login'"
                         target="_blank" rel="noopener" />
          </div>
          <SidebarItem :label="ws.user.name" route="/account" title="My account">
            <template #prefix><Avatar :label="ws.user.name" size="sm" /></template>
          </SidebarItem>
          <div class="flex items-center justify-between">
            <SidebarCollapseToggle />
            <span class="px-2 text-xs text-ink-gray-4">v{{ ws.version }}</span>
          </div>
        </Sidebar>
      </template>

      <main class="page">
        <RouterView />
      </main>
      <Tour v-if="touring" :permissions="ws.user.permissions" @done="tourDone" />
    </DesktopShell>
  </FrappeUIProvider>
</template>
