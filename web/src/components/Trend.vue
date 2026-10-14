<script setup>
// Weekly values as small bars; weeks without data are drawn as a gap and labelled "unknown".
import { computed } from 'vue'
import { fmt } from '../format'

const props = defineProps({ points: Array, unit: String, label: String })
const max = computed(() => Math.max(1, ...props.points.map((p) => p.value ?? 0)))
const last = computed(() => props.points.at(-1)?.value ?? null)
</script>

<template>
  <figure class="m-0 rounded-lg border border-outline-gray-2 bg-surface-base p-4">
    <figcaption class="flex items-baseline justify-between gap-2">
      <span class="text-sm font-medium text-ink-gray-5">{{ label }} by week</span>
      <span class="text-sm text-ink-gray-8">{{ fmt(last, unit) }}</span>
    </figcaption>
    <div class="mt-3 flex h-20 items-end gap-1">
      <div v-for="p in points" :key="p.week_ending" class="flex h-full flex-1 items-end justify-center"
           :title="`Week ending ${p.week_ending}: ${fmt(p.value, unit)}`">
        <span v-if="p.value !== null" class="w-full rounded-t bg-blue-400 transition-colors hover:bg-blue-500"
              :style="{ height: `${Math.max(3, (p.value / max) * 100)}%` }" />
        <i v-else class="text-sm not-italic text-ink-gray-4">–</i>
      </div>
    </div>
    <div class="mt-1 flex justify-between text-xs text-ink-gray-4">
      <span>{{ points[0]?.week_ending }}</span><span>{{ points.at(-1)?.week_ending }}</span>
    </div>
  </figure>
</template>
