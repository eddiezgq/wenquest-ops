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
import HelpHome from './pages/HelpHome.vue'
import HelpTopic from './pages/HelpTopic.vue'
import HelpChecklist from './pages/HelpChecklist.vue'
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
import Production from './pages/Production.vue'
import ProductionTemplate from './pages/ProductionTemplate.vue'
import ProductionRecord from './pages/ProductionRecord.vue'
import Trace from './pages/Trace.vue'
import Recalls from './pages/Recalls.vue'
import RecallPage from './pages/RecallPage.vue'
import Reviews from './pages/Reviews.vue'
import Scan from './pages/Scan.vue'
import Integrations from './pages/Integrations.vue'
import MachineInbox from './pages/MachineInbox.vue'
import DeviceIds from './pages/DeviceIds.vue'
import ReviewPage from './pages/ReviewPage.vue'
import ChangePage from './pages/ChangePage.vue'
import Gauges from './pages/Gauges.vue'
import GaugePage from './pages/GaugePage.vue'
import Complaints from './pages/Complaints.vue'
import QualityTools from './pages/QualityTools.vue'
import ComplaintPage from './pages/ComplaintPage.vue'
import DocControlPage from './pages/DocControlPage.vue'
import IqcPlan from './pages/IqcPlan.vue'
import IqcInspection from './pages/IqcInspection.vue'
import '@fontsource/barlow-condensed/500.css'
import '@fontsource/barlow-condensed/600.css'
import './style.css'
import Wall from './pages/Wall.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard, meta: { title: 'Dashboard' } },
    { path: '/wall', component: Wall, meta: { title: 'Big screen', bare: true } },
    { path: '/objects', component: Objects, meta: { title: 'Objects' } },
    { path: '/o/:type/:key(.*)', component: ObjectPage, meta: { title: 'Object' } },
    { path: '/anomalies', component: Anomalies, meta: { title: 'Anomalies' } },
    { path: '/anomalies/:id', component: AnomalyPage, meta: { title: 'Anomaly' } },
    { path: '/drafts', component: Drafts, meta: { title: 'Drafts' } },
    { path: '/assistant', component: Assistant, meta: { title: 'Assistant' } },
    { path: '/quality', component: Quality, meta: { title: 'Quality' } },
    { path: '/quality/tools', component: QualityTools, meta: { title: 'Quality tools' } },
    { path: '/quality/complaints', component: Complaints, meta: { title: 'Complaints' } },
    { path: '/quality/complaints/:id', component: ComplaintPage, meta: { title: 'Complaint' } },
    { path: '/quality/gauges', component: Gauges, meta: { title: 'Measuring equipment' } },
    { path: '/quality/gauges/:id', component: GaugePage, meta: { title: 'Equipment' } },
    { path: '/quality/changes', component: Changes, meta: { title: 'Changes' } },
    { path: '/quality/changes/:id', component: ChangePage, meta: { title: 'Change' } },
    { path: '/quality/risk', component: Risk, meta: { title: 'Risk management' } },
    { path: '/quality/risk/:id', component: RiskFilePage, meta: { title: 'Risk file' } },
    { path: '/quality/production', component: Production, meta: { title: 'Production records' } },
    { path: '/quality/production/templates/:id', component: ProductionTemplate, meta: { title: 'Production template' } },
    { path: '/quality/production/:id', component: ProductionRecord, meta: { title: 'Production record' } },
    { path: '/quality/trace', component: Trace, meta: { title: 'Trace' } },
    { path: '/quality/recalls', component: Recalls, meta: { title: 'Recalls' } },
    { path: '/quality/recalls/:id', component: RecallPage, meta: { title: 'Recall' } },
    { path: '/scan', component: Scan, meta: { title: 'Scan' } },
    { path: '/integrations', component: Integrations, meta: { title: 'Machines and systems' } },
    { path: '/quality/inbox', component: MachineInbox, meta: { title: 'From machines' } },
    { path: '/quality/udi', component: DeviceIds, meta: { title: 'Device identifiers' } },
    { path: '/quality/reviews', component: Reviews, meta: { title: 'Management reviews' } },
    { path: '/quality/reviews/:id', component: ReviewPage, meta: { title: 'Management review' } },
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
    { path: '/help', component: HelpHome, meta: { title: 'Help' } },
    { path: '/help/checklist', component: HelpChecklist, meta: { title: 'Test checklist' } },
    { path: '/help/quality', redirect: '/help/nonconformances' },   // pages of the help before ADR-0019
    { path: '/help/faq', redirect: '/help/questions' },
    { path: '/help/:topic', component: HelpTopic, meta: { title: 'Help' } },
    { path: '/account', component: Account, meta: { title: 'My account' } },
    { path: '/people', component: People, meta: { title: 'People' } },
    { path: '/documents', component: Documents, meta: { title: 'Documents' } },
    { path: '/documents/control', component: DocControlPage, meta: { title: 'Reading and review' } },
    { path: '/documents/ledger/:id', component: LedgerPage, meta: { title: 'Import a ledger' } },
    { path: '/documents/:id', component: DocumentPage, meta: { title: 'Document' } },
  ],
  scrollBehavior: (to) => (to.hash ? false : { top: 0 }),   // a help topic scrolls to its own anchors
})
router.afterEach((to) => { document.title = `${to.meta.title} · WenQuest Ops` })

createApp(App).use(router).mount('#app')
