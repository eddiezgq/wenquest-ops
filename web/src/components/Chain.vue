<script setup>
// Root causes (upstream) and impact (downstream), one step per row, each with the reason and its numbers.
import { computed } from 'vue'
import { objectPath } from '../api'

const props = defineProps({ explain: Object })
const title = computed(() => Object.fromEntries(props.explain.nodes.map((n) => [`${n.type}|${n.key}`, n.title])))
const name = (ref) => title.value[`${ref[0]}|${ref[1]}`] || ref[1]
const SIDES = [
  { key: 'causes', title: 'Why', sub: 'causes, upstream', none: 'No cause found in the synced data.', icon: 'lucide-arrow-up-left' },
  { key: 'impact', title: 'What it affects', sub: 'impact, downstream', none: 'Nothing downstream found.', icon: 'lucide-arrow-down-right' },
]
</script>

<template>
  <div class="chain grid gap-6 lg:grid-cols-2">
    <section v-for="side in SIDES" :key="side.key">
      <h3 class="mb-2 flex items-center gap-2 text-sm font-medium text-ink-gray-6">
        <span :class="side.icon" class="size-4" />{{ side.title }} <span class="text-ink-gray-4">({{ side.sub }})</span></h3>
      <p v-if="!explain[side.key].length" class="wq-muted">{{ side.none }}</p>
      <ol class="space-y-2">
        <li v-for="(s, i) in explain[side.key]" :key="side.key + i" class="relative"
            :style="{ marginLeft: `${(s.depth - 1) * 1.5}rem` }">
          <span v-if="s.depth > 1" class="absolute -left-4 top-3 text-ink-gray-4">↳</span>
          <div class="wq-panel px-3 py-2.5">
            <div class="text-base">
              <RouterLink :to="objectPath(...s.from)" class="font-medium text-ink-gray-9 hover:underline">{{ name(s.from) }}</RouterLink>
              <span class="mx-1.5 text-sm text-ink-gray-5">{{ s.relation }}</span>
              <RouterLink v-if="s.to" :to="objectPath(...s.to)" class="font-medium text-ink-gray-9 hover:underline">{{ name(s.to) }}</RouterLink>
            </div>
            <p class="mt-1 text-sm text-ink-gray-6">{{ s.why }}</p>
          </div>
        </li>
      </ol>
    </section>
  </div>
</template>
