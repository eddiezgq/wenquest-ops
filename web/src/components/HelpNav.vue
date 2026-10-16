<script setup>
// The help center's left column (ADR-0019 item 3): search, then the topics by group, with how many "Try it"
// items you have ticked.
import { computed, inject, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { grouped, search, visible } from '../help'
import { count } from '../help/progress'

const props = defineProps({ current: { type: String, default: '' } })
const ws = inject('workspace')
const router = useRouter()
const list = computed(() => visible(ws.value?.user?.permissions))
const groups = computed(() => grouped(list.value))
const q = ref('')
const hits = computed(() => search(q.value, list.value))
const pick = ref(0)
const open = ref(false)   // the topic list on a phone
watch(() => props.current, () => { open.value = false })
watch(q, () => { pick.value = 0 })
function go(h) { q.value = ''; router.push(`/help/${h.topic.slug}${h.hash}`) }
function key(e) {
  if (e.key === 'ArrowDown') { pick.value = Math.min(pick.value + 1, hits.value.length - 1); e.preventDefault() }
  if (e.key === 'ArrowUp') { pick.value = Math.max(pick.value - 1, 0); e.preventDefault() }
  if (e.key === 'Enter' && hits.value[pick.value]) go(hits.value[pick.value])
  if (e.key === 'Escape') q.value = ''
}
</script>

<template>
  <nav class="help-nav no-print" aria-label="Help topics">
    <div class="relative mb-4">
      <input v-model="q" type="search" class="wq-input" placeholder="Search the help" aria-label="Search the help" @keydown="key">
      <ol v-if="q.trim()" class="hits absolute left-0 top-full w-[min(26rem,calc(100vw-2rem))] z-20 mt-1 max-h-[70vh] overflow-auto rounded-4 border border-outline-gray-2 bg-surface-base p-1 shadow-lg">
        <li v-if="!hits.length" class="px-3 py-2 text-sm text-ink-gray-5">Nothing found. Try fewer or other words.</li>
        <li v-for="(h, i) in hits" :key="h.topic.slug">
          <button class="w-full rounded-3 px-3 py-2 text-left" :class="i === pick ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'" @click="go(h)" @mouseenter="pick = i">
            <span class="block text-sm font-medium text-ink-gray-9">{{ h.topic.title }}</span>
            <span class="block text-xs leading-5 text-ink-gray-6">{{ h.snippet }}</span>
          </button>
        </li>
      </ol>
    </div>
    <div class="lg:hidden">
      <button class="item w-full" :aria-expanded="open" @click="open = !open">
        <span>All help topics</span><span :class="open ? 'lucide-chevron-up' : 'lucide-chevron-down'" class="size-4" aria-hidden="true" />
      </button>
    </div>
    <div :class="open ? 'block' : 'hidden lg:block'">
    <RouterLink to="/help" class="item" :class="{ on: props.current === 'home' }">Help home</RouterLink>
    <RouterLink to="/help/checklist" class="item" :class="{ on: props.current === 'checklist' }">Test checklist</RouterLink>
    <section v-for="g in groups" :key="g.name" class="mt-4">
      <h2 class="px-2.5 pb-1 text-sm font-semibold text-ink-gray-5">{{ g.name }}</h2>
      <RouterLink v-for="t in g.topics" :key="t.slug" :to="`/help/${t.slug}`" class="item" :class="{ on: t.slug === props.current }">
        <span class="truncate">{{ t.title }}</span>
        <span v-if="t.try.length" class="tally" :class="{ full: count(t) === t.try.length }">{{ count(t) }}/{{ t.try.length }}</span>
      </RouterLink>
    </section>
    </div>
  </nav>
</template>

<style scoped>
.item { @apply flex items-center justify-between gap-2 rounded-4 px-2.5 py-1.5 text-base text-ink-gray-6; }
.item:hover { @apply bg-surface-gray-2; }
.item.on { @apply bg-surface-gray-3 font-medium text-ink-gray-9; }
.tally { @apply shrink-0 text-xs tabular-nums text-ink-gray-4; }
.tally.full { @apply text-ink-green-6; }
</style>
