<script setup>
// One help topic (ADR-0019 item 2): what it is, a short video, a checklist to try it with "Take me there" and
// "Show me", what WenQuest Ops stops (each tied to an automated test) and questions.
import { computed, inject, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import HelpNav from '../components/HelpNav.vue'
import { bySlug, headings, inline, render, visible } from '../help'
import { count, done, error, load, tick } from '../help/progress'

const route = useRoute()
const router = useRouter()
const ws = inject('workspace')
const startTour = inject('startTour')
const topic = computed(() => bySlug[route.params.topic])
const allowed = computed(() => topic.value && visible(ws.value?.user?.permissions).includes(topic.value))
const html = computed(() => topic.value ? render(topic.value.body) : '')
const toc = computed(() => {
  if (!topic.value) return []
  const t = topic.value
  return [{ text: 'What it is', id: 'what-it-is' }, ...headings(t.body), ...(t.video ? [{ text: 'Watch', id: 'watch' }] : []),
    ...(t.try.length ? [{ text: 'Try it', id: 'try-it' }] : []),
    ...(t.blocks.length ? [{ text: 'What WenQuest Ops stops', id: 'what-it-stops' }] : []),
    ...(t.questions.length ? [{ text: 'Questions', id: 'questions' }] : [])]
})
load()
watch(() => [route.hash, topic.value], async () => {
  await nextTick()
  if (route.hash) document.querySelector(route.hash)?.scrollIntoView({ block: 'start' })
}, { immediate: true })
function click(e) {
  if (e.target.dataset?.tour) { e.preventDefault(); startTour() }
}
function show(item) {
  startTour(item.tour.map((s, k) => ({ ...s, path: s.path ?? (k === 0 && item.to ? item.to : undefined) })), topic.value.title)
}
</script>

<template>
  <PageTop :crumbs="[{ label: 'Help', to: '/help' }]">
    <template #title>{{ topic?.title || 'Not found' }}</template>
  </PageTop>
  <div class="grid gap-8 lg:grid-cols-[14rem_minmax(0,1fr)] xl:grid-cols-[14rem_minmax(0,1fr)_12rem]">
    <HelpNav :current="topic?.slug" />
    <article v-if="!topic || !allowed" class="max-w-3xl">
      <p class="text-base text-ink-gray-7">{{ topic ? 'Your role does not see this part of WenQuest Ops.' : 'There is no help page here.' }}
        <RouterLink to="/help" class="wq-link">Go to Help home</RouterLink>.</p>
    </article>
    <article v-else class="topic max-w-3xl">
      <p class="lede">{{ topic.summary }}</p>

      <section v-if="topic.video" id="watch" class="mb-8">
        <video :src="`${topic.video}#t=4`" controls muted playsinline preload="metadata" class="w-full rounded-5 border border-outline-gray-2" />
      </section>

      <h2 id="what-it-is" class="sec">What it is</h2>
      <div class="prose prose-sm max-w-none text-ink-gray-8 prose-headings:text-ink-gray-9 prose-a:text-ink-gray-9 prose-img:rounded-5 prose-img:border prose-img:border-outline-gray-2"
           v-html="html" @click="click"></div>

      <section v-if="topic.try.length" id="try-it" class="mt-10">
        <div class="flex items-baseline justify-between gap-3">
          <h2 class="sec">Try it</h2>
          <span class="text-sm tabular-nums text-ink-gray-5">{{ count(topic) }} of {{ topic.try.length }} done</span>
        </div>
        <p class="mb-4 text-sm text-ink-gray-6">On the demo company, in this order. Tick each step when it worked as described.</p>
        <p v-if="error" class="wq-error mb-3">{{ error }}</p>
        <ol class="track">
          <li v-for="(x, i) in topic.try" :key="x.key" class="step" :class="{ ok: done[x.key] }">
            <span class="dot" aria-hidden="true">{{ done[x.key] ? '✓' : i + 1 }}</span>
            <div class="min-w-0 grow">
              <p class="text-base text-ink-gray-9" v-html="inline(x.text)"></p>
              <p v-if="x.expect" class="mt-1 text-sm text-ink-gray-6">You should see: <span v-html="inline(x.expect)"></span></p>
              <div class="mt-2 flex flex-wrap items-center gap-2">
                <Button v-if="x.to" size="sm" icon-left="lucide-arrow-up-right" label="Take me there" @click="router.push(x.to)" />
                <Button v-if="x.tour?.length" size="sm" icon-left="lucide-mouse-pointer-click" label="Show me" @click="show(x)" />
                <label class="ms-auto flex cursor-pointer items-center gap-2 text-sm text-ink-gray-7">
                  <input type="checkbox" class="form-checkbox" :checked="!!done[x.key]" @change="tick(x.key, $event.target.checked)">Done</label>
              </div>
            </div>
          </li>
        </ol>
      </section>

      <section v-if="topic.blocks.length" id="what-it-stops" class="mt-10">
        <h2 class="sec">What WenQuest Ops stops</h2>
        <p class="mb-3 text-sm text-ink-gray-6">Try these too: the system refuses and says why. Each one is checked by an automated test on every change.</p>
        <ul class="space-y-2">
          <li v-for="b in topic.blocks" :key="b.text" class="flex gap-3 rounded-4 border border-outline-gray-2 px-4 py-3">
            <span class="lucide-octagon-x mt-0.5 size-4 shrink-0 text-ink-red-5" aria-hidden="true" />
            <span class="text-base text-ink-gray-8" v-html="inline(b.text)"></span>
          </li>
        </ul>
      </section>

      <section v-if="topic.questions.length" id="questions" class="mt-10">
        <h2 class="sec">Questions</h2>
        <details v-for="x in topic.questions" :key="x.q" class="border-b border-outline-gray-2 py-3">
          <summary class="cursor-pointer text-base font-medium text-ink-gray-9">{{ x.q }}</summary>
          <p class="mt-2 text-base text-ink-gray-7" v-html="inline(x.a)"></p>
        </details>
      </section>
    </article>
    <aside v-if="topic && allowed && toc.length > 2" class="toc no-print hidden xl:block">
      <p class="mb-2 text-sm font-semibold text-ink-gray-5">On this page</p>
      <a v-for="h in toc" :key="h.id" :href="`#${h.id}`" class="block py-1 text-sm text-ink-gray-6 hover:text-ink-gray-9">{{ h.text }}</a>
    </aside>
  </div>
</template>

<style scoped>
.lede { @apply mb-8 text-xl leading-8 text-ink-gray-7; }
.sec { @apply mb-3 scroll-mt-20 text-xl font-semibold text-ink-gray-9; }
.topic :deep(h2) { scroll-margin-top: 5rem; }
.toc { position: sticky; top: 5rem; align-self: start; }
.track { position: relative; }
.track::before { content: ''; position: absolute; left: 0.9rem; top: 1rem; bottom: 1rem; width: 2px; background: var(--outline-gray-2); }
.step { @apply relative flex gap-4 pb-6; }
.dot { @apply relative z-10 flex size-[1.8rem] shrink-0 items-center justify-center rounded-full border-2 border-outline-gray-3 bg-surface-base text-sm font-semibold tabular-nums text-ink-gray-7; }
.step.ok .dot { border-color: var(--ink-green-5); background: var(--ink-green-5); color: var(--ink-white, #fff); }
@media (prefers-reduced-motion: no-preference) { .dot { transition: background-color .2s, border-color .2s; } }
</style>
