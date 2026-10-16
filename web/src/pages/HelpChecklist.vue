<script setup>
// The test checklist (ADR-0019 item 4): every "Try it" step of every topic you see, with your ticks; printable and
// exported as CSV.
import { computed, inject } from 'vue'
import { useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import HelpNav from '../components/HelpNav.vue'
import { grouped, inline, visible } from '../help'
import { count, done, error, load, tick } from '../help/progress'

const ws = inject('workspace')
const router = useRouter()
const list = computed(() => visible(ws.value?.user?.permissions).filter((t) => t.try.length))
const groups = computed(() => grouped(list.value))
const items = computed(() => list.value.reduce((n, t) => n + t.try.length, 0))
const ticked = computed(() => list.value.reduce((n, t) => n + count(t), 0))
load()
const plain = (s) => String(s || '').replace(/[*_`]/g, '')
function csv() {
  const q = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`
  const rows = [['Group', 'Topic', 'Step', 'What to do', 'Done', 'When']]
  for (const t of list.value) t.try.forEach((x, i) => rows.push([t.group, t.title, i + 1, plain(x.text), done.value[x.key] ? 'yes' : 'no', done.value[x.key] || '']))
  const url = URL.createObjectURL(new Blob([rows.map((r) => r.map(q).join(',')).join('\r\n')], { type: 'text/csv' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: 'wenquest-ops-test-checklist.csv' })
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function print() { window.print() }
</script>

<template>
  <PageTop :crumbs="[{ label: 'Help', to: '/help' }]">
    <template #title>Test checklist</template>
    <Button icon-left="lucide-download" label="Export CSV" class="no-print" @click="csv" />
    <Button icon-left="lucide-printer" label="Print" class="no-print" @click="print" />
  </PageTop>
  <div class="grid gap-8 lg:grid-cols-[14rem_minmax(0,1fr)]">
    <HelpNav current="checklist" />
    <div class="max-w-4xl">
      <p class="mb-2 max-w-2xl text-base text-ink-gray-7">Work through WenQuest Ops on the demo company. Each step is
        on its topic page with a video and "Show me"; tick it here or there. Your ticks are kept for you, on any
        computer.</p>
      <p class="mb-6 text-base font-medium tabular-nums text-ink-gray-9">{{ ticked }} of {{ items }} done</p>
      <p v-if="error" class="wq-error mb-4">{{ error }}</p>
      <section v-for="g in groups" :key="g.name" class="mb-8">
        <h2 class="mb-3 text-lg font-semibold text-ink-gray-9">{{ g.name }}</h2>
        <div v-for="t in g.topics" :key="t.slug" class="mb-5 break-inside-avoid">
          <h3 class="mb-1 flex items-baseline justify-between gap-3 border-b border-outline-gray-2 pb-1">
            <RouterLink :to="`/help/${t.slug}#try-it`" class="text-base font-semibold text-ink-gray-9 hover:underline">{{ t.title }}</RouterLink>
            <span class="text-sm tabular-nums text-ink-gray-5">{{ count(t) }}/{{ t.try.length }}</span>
          </h3>
          <ol>
            <li v-for="(x, i) in t.try" :key="x.key" class="flex items-start gap-3 py-1.5">
              <input :id="x.key" type="checkbox" class="form-checkbox mt-1" :checked="!!done[x.key]" @change="tick(x.key, $event.target.checked)">
              <label :for="x.key" class="grow cursor-pointer text-base" :class="done[x.key] ? 'text-ink-gray-5' : 'text-ink-gray-8'">
                <span class="tabular-nums text-ink-gray-5">{{ i + 1 }}.</span> <span v-html="inline(x.text)"></span></label>
              <Button v-if="x.to" size="sm" variant="ghost" icon-left="lucide-arrow-up-right" label="Go" class="no-print" @click="router.push(x.to)" />
            </li>
          </ol>
        </div>
      </section>
    </div>
  </div>
</template>

<style>
@media print {
  .no-print, aside, .help-nav { display: none !important; }
}
</style>
