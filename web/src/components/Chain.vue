<script setup>
// Root causes (upstream) and impact (downstream), one step per row, each with the reason and its numbers.
import { computed } from 'vue'
import { objectPath } from '../api'

const props = defineProps({ explain: Object })
const title = computed(() => Object.fromEntries(props.explain.nodes.map((n) => [`${n.type}|${n.key}`, n.title])))
const name = (ref) => title.value[`${ref[0]}|${ref[1]}`] || ref[1]
</script>

<template>
  <div class="chain">
    <section>
      <h3>Why <span class="muted small">(causes, upstream)</span></h3>
      <p v-if="!explain.causes.length" class="muted">No cause found in the synced data.</p>
      <ol>
        <li v-for="(s, i) in explain.causes" :key="'c' + i" :style="{ marginLeft: `${(s.depth - 1) * 1.4}rem` }">
          <RouterLink :to="objectPath(...s.from)">{{ name(s.from) }}</RouterLink>
          <span class="rel">{{ s.relation }}</span>
          <RouterLink v-if="s.to" :to="objectPath(...s.to)">{{ name(s.to) }}</RouterLink>
          <div class="why">{{ s.why }}</div>
        </li>
      </ol>
    </section>
    <section>
      <h3>What it affects <span class="muted small">(impact, downstream)</span></h3>
      <p v-if="!explain.impact.length" class="muted">Nothing downstream found.</p>
      <ol>
        <li v-for="(s, i) in explain.impact" :key="'i' + i" :style="{ marginLeft: `${(s.depth - 1) * 1.4}rem` }">
          <RouterLink :to="objectPath(...s.from)">{{ name(s.from) }}</RouterLink>
          <span class="rel">{{ s.relation }}</span>
          <RouterLink v-if="s.to" :to="objectPath(...s.to)">{{ name(s.to) }}</RouterLink>
          <div class="why">{{ s.why }}</div>
        </li>
      </ol>
    </section>
  </div>
</template>
