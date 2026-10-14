<script setup>
// English help (ADR-0012): Markdown pages bundled with the web app, and a way to restart the guided tour.
import { computed, inject } from 'vue'
import { useRoute } from 'vue-router'
import MarkdownIt from 'markdown-it'
import { Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'

const pages = import.meta.glob('../help/*.md', { query: '?raw', import: 'default', eager: true })
// screenshots recorded by CI on the demo company (ADR-0012 item 7), referenced in the pages as img/<name>.webp
const images = import.meta.glob('../help/img/*.webp', { query: '?url', import: 'default', eager: true })
const md = new MarkdownIt({ html: false, linkify: true })
const image = md.renderer.rules.image
md.renderer.rules.image = (tokens, i, opts, env, self) => {
  const t = tokens[i]
  const url = images[`../help/${t.attrGet('src')}`]
  if (url) t.attrSet('src', url)
  t.attrSet('loading', 'lazy')
  return image(tokens, i, opts, env, self)
}
const list = Object.entries(pages).sort(([a], [b]) => a.localeCompare(b)).map(([path, text]) => ({
  slug: path.split('/').pop().replace(/^\d+-/, '').replace('.md', ''),
  title: text.split('\n')[0].replace(/^#\s*/, ''),
  text,
}))
const route = useRoute()
const page = computed(() => list.find((p) => p.slug === route.params.topic) || list[0])
const html = computed(() => md.render(page.value.text).replace('href="#tour"', 'href="#" data-tour="1"'))
const tour = inject('startTour')
function click(e) {
  if (e.target.dataset?.tour) { e.preventDefault(); tour() }
}
</script>

<template>
  <PageTop :title="page.title" :crumbs="[{ label: 'Help', to: '/help' }]">
    <Button icon-left="lucide-map" label="Take the guided tour" @click="tour()" />
  </PageTop>
  <div class="help grid gap-8 md:grid-cols-[13rem_1fr]">
    <nav class="help-nav flex flex-col gap-0.5">
      <RouterLink v-for="p in list" :key="p.slug" :to="`/help/${p.slug}`"
                  class="rounded-4 px-2.5 py-1.5 text-base"
                  :class="p.slug === page.slug ? 'bg-surface-gray-3 font-medium text-ink-gray-9' : 'text-ink-gray-6 hover:bg-surface-gray-2'">{{ p.title }}</RouterLink>
    </nav>
    <article class="prose prose-sm max-w-3xl [&>h1:first-child]:hidden text-ink-gray-8 prose-headings:text-ink-gray-9 prose-a:text-ink-gray-9 prose-img:rounded-5 prose-img:border prose-img:border-outline-gray-2"
             v-html="html" @click="click"></article>
  </div>
</template>
