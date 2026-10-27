<script setup>
// The app frame (ADR-0013): Frappe's desktop shell with a sidebar like ERPNext's. Each page puts its own header
// (ui/PageTop.vue).
import { computed, onMounted, provide, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  Avatar, DesktopShell, FrappeUIProvider, Sidebar, SidebarHeader,
  SidebarItem, SidebarLabel,
} from 'frappe-ui'
import SidebarToggle from './components/SidebarToggle.vue'
import { api } from './api'
import { setCurrency } from './format'
import { lang, setLang, t, useCompanyLanguage } from './i18n'
import Tour from './components/Tour.vue'
import ChatPanel from './components/ChatPanel.vue'

const route = useRoute()
const ws = ref(null)
const error = ref('')
const touring = ref(false)
const tourSteps = ref(null)
const tourName = ref('')
provide('workspace', ws)
// no steps: the guided tour; a help topic passes its own (ADR-0019)
const startTour = (steps = null, name = '') => { tourSteps.value = steps; tourName.value = name; touring.value = false; setTimeout(() => { touring.value = true }) }
provide('startTour', startTour)
// the AI chat panel on every page (ADR-0021); the Assistant page opens a past conversation in it
const chatOpen = ref(false)
const chat = ref(null)
provide('openChat', (id) => chat.value?.openChat(id))
// the help videos are recorded by driving the same tours (ADR-0019 item 7, .github/scripts/help_tours.py)
window.wqoTour = startTour
const TOUR_KEY = 'wqo-tour-done'
function tourDone() {
  touring.value = false
  if (tourSteps.value) return
  try { localStorage.setItem(TOUR_KEY, '1') } catch { /* the tour just shows again next time */ }
}

onMounted(async () => {
  try {
    ws.value = await api('/api/workspace')
    setCurrency(ws.value.currency)
    useCompanyLanguage(ws.value.language)
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
  { label: t('My account'), icon: 'lucide-user', route: '/account' },
  { label: t('Help'), icon: 'lucide-circle-help', route: '/help' },
  { label: t('Take the guided tour'), icon: 'lucide-map', onClick: () => startTour() },
  { label: lang.value === 'zh' ? 'English' : '中文', icon: 'lucide-languages', onClick: () => setLang(lang.value === 'zh' ? 'en' : 'zh') },
  { label: t('Sign out'), icon: 'lucide-log-out', onClick: signOut },
])
</script>

<template>
  <FrappeUIProvider>
    <div v-if="error && !ws" class="p-8 text-base text-ink-red-7">{{ error }}</div>
    <RouterView v-if="ws && route.meta.bare" />
    <DesktopShell v-else-if="ws">
      <template #sidebar>
        <Sidebar class="bg-surface-sidebar border-e border-outline-gray-1">
          <SidebarHeader :title="ws.company" :subtitle="ws.demo ? t('Fictional demo') : 'WenQuest Ops'" :menu-items="menu" />
          <div class="flex-1 overflow-y-auto">
            <SidebarItem :label="t('Dashboard')" icon="lucide-layout-dashboard" route="/" :active="route.path === '/'" />
            <SidebarItem :label="t('Assistant')" icon="lucide-sparkles" route="/assistant" />
            <SidebarItem :label="t('Anomalies')" icon="lucide-triangle-alert" route="/anomalies" />
            <SidebarItem :label="t('Drafts')" icon="lucide-file-pen-line" route="/drafts" />
            <SidebarItem :label="t('Scan')" icon="lucide-scan-line" route="/scan" />
            <SidebarLabel divider>{{ t('Records') }}</SidebarLabel>
            <SidebarItem v-if="can('quality:view')" :label="t('Quality')" icon="lucide-shield-check" route="/quality" />
            <SidebarItem v-if="can('quality:view')" :label="t('Complaints')" icon="lucide-message-square-warning" route="/quality/complaints" />
            <SidebarItem v-if="can('quality:view')" :label="t('Quality tools')" icon="lucide-chart-column" route="/quality/tools" />
            <SidebarItem v-if="can('quality:view')" :label="t('Process flow')" icon="lucide-workflow" route="/quality/flow" />
            <SidebarItem v-if="can('quality:view')" :label="t('Process FMEA')" icon="lucide-list-tree" route="/quality/fmea" />
            <SidebarItem v-if="can('quality:view')" :label="t('Incoming inspection')" icon="lucide-scan-search" route="/quality/iqc" />
            <SidebarItem v-if="can('quality:view')" :label="t('Approved suppliers')" icon="lucide-badge-check" route="/quality/suppliers" />
            <SidebarItem v-if="can('quality:view')" :label="t('From machines')" icon="lucide-inbox" route="/quality/inbox" />
            <SidebarItem v-if="can('quality:view')" :label="t('Measuring equipment')" icon="lucide-ruler" route="/quality/gauges" />
            <SidebarItem v-if="can('quality:view')" :label="t('Changes')" icon="lucide-git-pull-request-arrow" route="/quality/changes" />
            <SidebarItem v-if="can('quality:view')" :label="t('Risk')" icon="lucide-triangle-alert" route="/quality/risk" />
            <SidebarItem v-if="can('quality:view')" :label="t('Production')" icon="lucide-factory" route="/quality/production" />
            <SidebarItem v-if="can('quality:view')" :label="t('Trace and recalls')" icon="lucide-route" route="/quality/recalls" />
            <SidebarItem v-if="can('quality:view')" :label="t('Management reviews')" icon="lucide-presentation" route="/quality/reviews" />
            <SidebarItem v-if="can('quality:view')" :label="t('Quality system')" icon="lucide-list-checks" route="/system" />
            <SidebarItem v-if="can('documents:view')" :label="t('Documents')" icon="lucide-folder-open" route="/documents" />
            <SidebarItem :label="t('My reading')" icon="lucide-book-open-check" route="/documents/control" />
            <SidebarItem :label="t('Objects')" icon="lucide-boxes" route="/objects" />
            <SidebarLabel divider>{{ t('Workspace') }}</SidebarLabel>
            <SidebarItem v-if="can('users:view')" :label="t('People')" icon="lucide-users" route="/people" />
            <SidebarItem v-if="can('integrations:manage')" :label="t('Machines and systems')" icon="lucide-cable" route="/integrations" />
            <SidebarItem :label="t('Help')" icon="lucide-circle-help" route="/help" />
            <SidebarItem v-if="ws.erp_url" label="ERPNext" icon="lucide-external-link" :href="ws.erp_url + '/login'"
                         target="_blank" rel="noopener" />
          </div>
          <SidebarItem :label="ws.user.name" route="/account" :title="t('My account')">
            <template #prefix><Avatar :label="ws.user.name" size="sm" /></template>
          </SidebarItem>
          <div class="flex items-center justify-between">
            <SidebarToggle />
            <span class="px-2 text-xs text-ink-gray-4">v{{ ws.version }}</span>
          </div>
        </Sidebar>
      </template>

      <main class="page">
        <RouterView />
      </main>
      <Tour v-if="touring" :permissions="ws.user.permissions" :steps="tourSteps" :name="tourName" @done="tourDone" />
      <ChatPanel v-if="can('ai:use')" ref="chat" v-model:open="chatOpen" />
    </DesktopShell>
  </FrappeUIProvider>
</template>
