import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './pages/Dashboard.vue'
import Objects from './pages/Objects.vue'
import ObjectPage from './pages/ObjectPage.vue'
import Anomalies from './pages/Anomalies.vue'
import AnomalyPage from './pages/AnomalyPage.vue'
import Drafts from './pages/Drafts.vue'
import Assistant from './pages/Assistant.vue'
import Quality from './pages/Quality.vue'
import NcrPage from './pages/NcrPage.vue'
import CapaPage from './pages/CapaPage.vue'
import Help from './pages/Help.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard, meta: { title: 'Dashboard' } },
    { path: '/objects', component: Objects, meta: { title: 'Objects' } },
    { path: '/o/:type/:key(.*)', component: ObjectPage, meta: { title: 'Object' } },
    { path: '/anomalies', component: Anomalies, meta: { title: 'Anomalies' } },
    { path: '/anomalies/:id', component: AnomalyPage, meta: { title: 'Anomaly' } },
    { path: '/drafts', component: Drafts, meta: { title: 'Drafts' } },
    { path: '/assistant', component: Assistant, meta: { title: 'Assistant' } },
    { path: '/quality', component: Quality, meta: { title: 'Quality' } },
    { path: '/quality/ncr/:id', component: NcrPage, meta: { title: 'Nonconformance' } },
    { path: '/quality/capa/:id', component: CapaPage, meta: { title: 'Corrective action' } },
    { path: '/help/:topic?', component: Help, meta: { title: 'Help' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
router.afterEach((to) => { document.title = `${to.meta.title} · WenQuest Ops` })

createApp(App).use(router).mount('#app')
