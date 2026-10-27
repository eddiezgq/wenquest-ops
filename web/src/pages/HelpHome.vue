<script setup>
// Help home (ADR-0019 item 3): search, where to start for your role, every topic by group, and the test checklist.
import { computed, inject } from 'vue'
import { Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import HelpNav from '../components/HelpNav.vue'
import { bySlug, grouped, visible } from '../help'
import { count, load } from '../help/progress'
import { t } from '../i18n'

const ws = inject('workspace')
const startTour = inject('startTour')
const list = computed(() => visible(ws.value?.user?.permissions))
const groups = computed(() => grouped(list.value).filter((g) => g.name !== 'Start here'))
// a first path through the system, in order; topics your role does not see are left out
const PATH = ['getting-started', 'dashboard', 'nonconformances', 'incoming-inspection', 'documents', 'quality-system']
const path = computed(() => PATH.map((s) => bySlug[s]).filter((t) => t && list.value.includes(t)))
const items = computed(() => list.value.reduce((n, t) => n + t.try.length, 0))
const ticked = computed(() => list.value.reduce((n, t) => n + count(t), 0))
load()
</script>

<template>
  <PageTop :title="t('Help')">
    <Button icon-left="lucide-map" :label="t('Take the guided tour')" @click="startTour()" />
  </PageTop>
  <div class="grid gap-8 lg:grid-cols-[14rem_minmax(0,1fr)]">
    <HelpNav current="home" />
    <div class="max-w-4xl">
      <p class="mb-8 max-w-2xl text-xl leading-8 text-ink-gray-7">{{ t('How WenQuest Ops works, page by page. Every topic says what the page is for, lets you try it on the demo company step by step, and lists what the system will not let anyone do.') }}</p>

      <section class="mb-10">
        <h2 class="mb-3 text-base font-semibold text-ink-gray-9">{{ t('Start here') }}</h2>
        <ol class="path">
          <li v-for="(tp, i) in path" :key="tp.slug">
            <RouterLink :to="`/help/${tp.slug}`" class="block h-full rounded-5 border border-outline-gray-2 p-4 hover:border-outline-gray-4">
              <span class="text-sm tabular-nums text-ink-gray-5">{{ i + 1 }}</span>
              <span class="mt-1 block text-base font-semibold text-ink-gray-9">{{ tp.title }}</span>
              <span class="mt-1 block text-sm leading-5 text-ink-gray-6">{{ tp.summary }}</span>
            </RouterLink>
          </li>
        </ol>
      </section>

      <RouterLink v-if="items" to="/help/checklist" class="check mb-10 flex flex-wrap items-center gap-4 rounded-5 border border-outline-gray-2 p-4 hover:border-outline-gray-4">
        <span class="grow">
          <span class="block text-base font-semibold text-ink-gray-9">{{ t('Test checklist') }}</span>
          <span class="block text-sm text-ink-gray-6">{{ t('Every "Try it" step of every topic on one page, to work through, print or export.') }}</span>
        </span>
        <span class="flex items-center gap-3">
          <span class="bar"><span :style="{ width: `${(100 * ticked) / items}%` }" /></span>
          <span class="text-sm tabular-nums text-ink-gray-7">{{ t('{done} of {total}', { done: ticked, total: items }) }}</span>
        </span>
      </RouterLink>

      <div class="grid gap-x-10 gap-y-8 md:grid-cols-2">
        <section v-for="g in groups" :key="g.name">
          <h2 class="mb-2 text-base font-semibold text-ink-gray-9">{{ t(g.name) }}</h2>
          <ul>
            <li v-for="tp in g.topics" :key="tp.slug" class="border-t border-outline-gray-1 py-2.5">
              <RouterLink :to="`/help/${tp.slug}`" class="group block">
                <span class="flex items-baseline justify-between gap-3">
                  <span class="text-base font-medium text-ink-gray-9 group-hover:underline">{{ tp.title }}</span>
                  <span v-if="tp.try.length" class="shrink-0 text-xs tabular-nums text-ink-gray-4">{{ t('{done}/{total} tried', { done: count(tp), total: tp.try.length }) }}</span>
                </span>
                <span class="block text-sm text-ink-gray-6">{{ tp.summary }}</span>
              </RouterLink>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.path { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr)); }
.bar { @apply block h-2 w-40 overflow-hidden rounded-full bg-surface-gray-3; }
.bar > span { @apply block h-full rounded-full; background: var(--ink-green-5); }
</style>
