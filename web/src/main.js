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
import Account from './pages/Account.vue'
import People from './pages/People.vue'
import Documents from './pages/Documents.vue'
import DocumentPage from './pages/DocumentPage.vue'
import LedgerPage from './pages/LedgerPage.vue'
import WorkflowEditor from './pages/WorkflowEditor.vue'
import WorkflowProposal from './pages/WorkflowProposal.vue'
import QualitySystem from './pages/QualitySystem.vue'
import RegisterPage from './pages/RegisterPage.vue'
import QualityGaps from './pages/QualityGaps.vue'
import AuditChecklist from './pages/AuditChecklist.vue'
import QualitySetup from './pages/QualitySetup.vue'
import IqcHome from './pages/IqcHome.vue'
import AslPage from './pages/AslPage.vue'
import Changes from './pages/Changes.vue'
import Risk from './pages/Risk.vue'
import RiskFilePage from './pages/RiskFilePage.vue'
import ChangePage from './pages/ChangePage.vue'
import Gauges from './pages/Gauges.vue'
import GaugePage from './pages/GaugePage.vue'
import Complaints from './pages/Complaints.vue'
import ComplaintPage from './pages/ComplaintPage.vue'
import DocControlPage from './pages/DocControlPage.vue'
import IqcPlan from './pages/IqcPlan.vue'
import IqcInspection from './pages/IqcInspection.vue'
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
    { path: '/quality/complaints', component: Complaints, meta: { title: 'Complaints' } },
    { path: '/quality/complaints/:id', component: ComplaintPage, meta: { title: 'Complaint' } },
    { path: '/quality/gauges', component: Gauges, meta: { title: 'Measuring equipment' } },
    { path: '/quality/gauges/:id', component: GaugePage, meta: { title: 'Equipment' } },
    { path: '/quality/changes', component: Changes, meta: { title: 'Changes' } },
    { path: '/quality/changes/:id', component: ChangePage, meta: { title: 'Change' } },
    { path: '/quality/risk', component: Risk, meta: { title: 'Risk management' } },
    { path: '/quality/risk/:id', component: RiskFilePage, meta: { title: 'Risk file' } },
    { path: '/quality/suppliers', component: AslPage, meta: { title: 'Approved suppliers' } },
    { path: '/quality/iqc', component: IqcHome, meta: { title: 'Incoming inspection' } },
    { path: '/quality/iqc/plans/:id', component: IqcPlan, meta: { title: 'Inspection plan' } },
    { path: '/quality/iqc/:id', component: IqcInspection, meta: { title: 'Incoming inspection' } },
    { path: '/quality/ncr/:id', component: NcrPage, meta: { title: 'Nonconformance' } },
    { path: '/quality/capa/:id', component: CapaPage, meta: { title: 'Corrective action' } },
    { path: '/quality/workflows/proposals/:id', component: WorkflowProposal, meta: { title: 'Suggested changes' } },
    { path: '/quality/workflows/:id', component: WorkflowEditor, meta: { title: 'Workflow' } },
    { path: '/system', component: QualitySystem, meta: { title: 'Quality system' } },
    { path: '/system/registers/:name', component: RegisterPage, meta: { title: 'Register' } },
    { path: '/system/gaps', component: QualityGaps, meta: { title: 'Gap report' } },
    { path: '/system/audit', component: AuditChecklist, meta: { title: 'Audit checklist' } },
    { path: '/system/setup', component: QualitySetup, meta: { title: 'Set up' } },
    { path: '/help/:topic?', component: Help, meta: { title: 'Help' } },
    { path: '/account', component: Account, meta: { title: 'My account' } },
    { path: '/people', component: People, meta: { title: 'People' } },
    { path: '/documents', component: Documents, meta: { title: 'Documents' } },
    { path: '/documents/control', component: DocControlPage, meta: { title: 'Reading and review' } },
    { path: '/documents/ledger/:id', component: LedgerPage, meta: { title: 'Import a ledger' } },
    { path: '/documents/:id', component: DocumentPage, meta: { title: 'Document' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
router.afterEach((to) => { document.title = `${to.meta.title} · WenQuest Ops` })

createApp(App).use(router).mount('#app')
