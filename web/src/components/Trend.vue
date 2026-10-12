<script setup>
// Weekly values as small bars; weeks without data are drawn as a gap and labelled "unknown".
import { computed } from 'vue'
import { fmt } from '../format'

const props = defineProps({ points: Array, unit: String, label: String })
const max = computed(() => Math.max(1, ...props.points.map((p) => p.value ?? 0)))
</script>

<template>
  <figure class="trend">
    <figcaption>{{ label }} by week</figcaption>
    <div class="bars">
      <div v-for="p in points" :key="p.week_ending" class="bar"
           :title="`Week ending ${p.week_ending}: ${fmt(p.value, unit)}`">
        <span v-if="p.value !== null" :style="{ height: `${Math.max(3, (p.value / max) * 100)}%` }"></span>
        <i v-else>–</i>
      </div>
    </div>
    <div class="axis"><span>{{ points[0]?.week_ending }}</span><span>{{ points.at(-1)?.week_ending }}</span></div>
  </figure>
</template>
