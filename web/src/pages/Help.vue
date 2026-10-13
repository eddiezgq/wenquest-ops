<script setup>
// English help (ADR-0012): Markdown pages bundled with the web app, and a way to restart the guided tour.
import { computed, inject } from 'vue'
import { useRoute } from 'vue-router'
import MarkdownIt from 'markdown-it'

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
  <div class="help">
    <nav class="help-nav">
      <RouterLink v-for="p in list" :key="p.slug" :to="`/help/${p.slug}`" :class="{ on: p.slug === page.slug }">{{ p.title }}</RouterLink>
      <a href="#" @click.prevent="tour()">Take the guided tour</a>
    </nav>
    <article class="card prose" v-html="html" @click="click"></article>
  </div>
</template>
