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
  ],
  scrollBehavior: () => ({ top: 0 }),
})
router.afterEach((to) => { document.title = `${to.meta.title} · WenQuest Ops` })

createApp(App).use(router).mount('#app')
