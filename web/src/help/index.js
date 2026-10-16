// The help center's pages (ADR-0019): one Markdown file per topic in ./topics, with a YAML head (title, group,
// order, summary, needs, video, try, blocks, questions). Bundled with the app; searched here, without AI.
import { parse } from 'yaml'
import MarkdownIt from 'markdown-it'

export const GROUPS = ['Start here', 'Daily work', 'Quality', 'Regulated modules', 'Documents', 'Quality system', 'Help']

const raw = import.meta.glob('./topics/*.md', { query: '?raw', import: 'default', eager: true })
// screenshots and videos recorded by CI on the demo company (ADR-0012 item 7, ADR-0019 item 7)
const images = import.meta.glob('./img/*.webp', { query: '?url', import: 'default', eager: true })
const videos = import.meta.glob('./media/*.webm', { query: '?url', import: 'default', eager: true })

function split(path, text) {
  const m = text.match(/^---\n([\s\S]*?)\n---\n/)
  const meta = m ? parse(m[1]) : {}
  const slug = path.split('/').pop().replace('.md', '')
  return {
    slug, title: meta.title || slug, group: meta.group || 'Help', order: meta.order ?? 99, summary: meta.summary || '',
    needs: meta.needs || null, video: meta.video ? videos[`./media/${meta.video}.webm`] || null : null,
    try: (meta.try || []).map((x) => ({ ...x, key: `${slug}/${x.id}` })), blocks: meta.blocks || [],
    questions: meta.questions || [], body: m ? text.slice(m[0].length) : text,
  }
}

export const topics = Object.entries(raw).map(([p, t]) => split(p, t))
  .sort((a, b) => GROUPS.indexOf(a.group) - GROUPS.indexOf(b.group) || a.order - b.order)
export const bySlug = Object.fromEntries(topics.map((t) => [t.slug, t]))

export function visible(permissions = []) {
  return topics.filter((t) => !t.needs || permissions.includes(t.needs))
}

export function grouped(list) {
  return GROUPS.map((g) => ({ name: g, topics: list.filter((t) => t.group === g) })).filter((g) => g.topics.length)
}

// ---------------------------------------------------------------- rendering

const md = new MarkdownIt({ html: false, linkify: true })
const image = md.renderer.rules.image
md.renderer.rules.image = (tokens, i, opts, env, self) => {
  const t = tokens[i]
  const url = images[`./${t.attrGet('src')}`]
  if (url) t.attrSet('src', url)
  t.attrSet('loading', 'lazy')
  return image(tokens, i, opts, env, self)
}
export const anchor = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
md.renderer.rules.heading_open = (tokens, i, opts, env, self) => {
  if (tokens[i].tag === 'h2') tokens[i].attrSet('id', anchor(tokens[i + 1].content))
  return self.renderToken(tokens, i, opts)
}

export function render(text) {
  return md.render(text).replace('href="#tour"', 'href="#" data-tour="1"')
}
export const headings = (text) => [...text.matchAll(/^## (.+)$/gm)].map((m) => ({ text: m[1], id: anchor(m[1]) }))
export const inline = (text) => md.renderInline(text || '')

// ---------------------------------------------------------------- search

const plain = (s) => (s || '').replace(/!\[[^\]]*\]\([^)]*\)/g, '').replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
  .replace(/[*_`#>|]/g, '').replace(/\s+/g, ' ')
const words = (s) => (s.toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => w.length > 1)
const index = topics.map((t) => ({
  t, title: t.title.toLowerCase(), summary: t.summary.toLowerCase(),
  heads: headings(t.body).map((h) => h.text.toLowerCase()).join(' '),
  text: plain([t.body, ...t.try.map((x) => x.text), ...t.blocks.map((x) => x.text),
    ...t.questions.map((x) => `${x.q} ${x.a}`)].join(' ')),
}))

export function search(query, list) {
  const q = words(query)
  if (!q.length) return []
  const allowed = new Set(list.map((t) => t.slug))
  const out = []
  for (const x of index) {
    if (!allowed.has(x.t.slug)) continue
    const low = x.text.toLowerCase()
    let score = 0
    for (const w of q) {
      const n = low.split(w).length - 1
      if (!n && !x.title.includes(w) && !x.summary.includes(w)) { score = 0; break }   // every word must appear
      score += (x.title.includes(w) ? 8 : 0) + (x.summary.includes(w) ? 4 : 0) + (x.heads.includes(w) ? 3 : 0) + Math.min(n, 5)
    }
    if (!score) continue
    const at = low.indexOf(q[0])
    const snippet = at < 0 ? x.t.summary : (at > 60 ? '…' : '') + x.text.slice(Math.max(0, at - 60), at + 140).trim() + '…'
    const head = headings(x.t.body).find((h) => h.text.toLowerCase().includes(q[0]))
    out.push({ topic: x.t, score, snippet, hash: head ? `#${head.id}` : '' })
  }
  return out.sort((a, b) => b.score - a.score).slice(0, 12)
}
