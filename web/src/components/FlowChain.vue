<script setup>
// The chain from purchase order to payment (ADR-0018): each step with what is there now and what is stuck. Goods move
// along the line from left to right; a step with something stuck pulses. What customers send back (complaints,
// recalls) returns over the top. Motion is left out when the person asks for reduced motion.
import { computed, onMounted, ref } from 'vue'
import { fmt, fmtShort } from '../format'
import { t } from '../i18n'

const props = defineProps({ steps: { type: Array, required: true }, returns: { type: Array, default: () => [] },
  big: { type: Boolean, default: false } })
const still = ref(false)
onMounted(() => { still.value = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches })
const n = computed(() => Math.max(props.steps.length, 1))
const x = (i) => ((i + 0.5) / n.value) * 100
const dots = computed(() => Array.from({ length: Math.max(3, n.value + 1) }, (_, i) => i))
const one = (note) => note.replace(/^items /, 'item ').replace(/(\d+) days/, '$1 days')
// the note under a step, in the person's language ("waiting over 2 days" has its own pattern so the number can move)
function note(s) {
  const text = s.stuck === 1 ? one(s.stuck_note) : s.stuck_note
  const m = /^(waiting|open|started) over (\d+) days( ago)?$/.exec(text)
  if (m) return t(`${m[1]} over {n} days${m[3] || ''}`, { n: m[2] })
  return t(text)
}
const shown = (s) => s.count === null || s.count === undefined ? '—' : s.unit === 'currency' ? fmtShort(s.count) : fmt(s.count)
</script>

<template>
  <div class="chain-scroll"><div class="chain relative" :class="big ? 'chain-big' : ''">
    <div v-if="returns.length" class="returns mb-1 flex justify-end gap-4 pe-2 text-sm">
      <RouterLink v-for="r in returns" :key="r.key" :to="r.link" class="ret" :class="r.count ? 'ret-on' : ''">
        <span class="lucide-undo-2 size-3.5" />{{ t(r.label) }} <b>{{ r.count }}</b></RouterLink>
    </div>
    <div class="relative">
      <div class="track pointer-events-none absolute inset-x-0" aria-hidden="true">
        <span class="rail" />
        <template v-if="!still">
          <i v-for="d in dots" :key="d" class="unit" :style="{ animationDuration: `${n * 1.6}s`, animationDelay: `${-d * (n * 1.6) / dots.length}s` }" />
        </template>
      </div>
      <ol class="relative grid" :style="{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }">
        <li v-for="(s, i) in steps" :key="s.key" class="step flex flex-col items-center text-center">
          <RouterLink :to="s.link || '/'" class="group flex flex-col items-center" :title="s.stuck ? `${s.stuck} ${note(s)}` : ''">
            <span class="count">{{ shown(s) }}</span>
            <span class="node" :class="s.stuck ? 'node-stuck' : ''"><i v-if="s.stuck && !still" class="pulse" /></span>
            <span class="label">{{ t(s.label) }}</span>
            <span v-if="s.stuck" class="stuck">{{ s.stuck }} {{ note(s) }}</span>
            <span v-else class="stuck-none">&nbsp;</span>
          </RouterLink>
          <span class="sr-only">{{ i < steps.length - 1 ? t('then') : '' }}</span>
        </li>
      </ol>
    </div>
  </div></div>
</template>

<style scoped>
.chain { --rail: #c9d3dc; --unit: #1f7a8c; --node: #1f7a8c; --stuck: #d1453b; --ink: #1b2733; --muted: #66727e; }
.chain-big { --rail: #2c4a62; --unit: #5ccfd6; --node: #5ccfd6; --stuck: #ff6b5e; --ink: #eef3f6; --muted: #9db2c3; }
.track { top: 49px; height: 0; }
.chain-big .track { top: 98px; }
.rail { position: absolute; left: 0; right: 0; top: -1.5px; height: 3px; background: var(--rail); border-radius: 2px; }
.chain-big .rail { top: -2.5px; height: 5px; }
.unit { position: absolute; top: -4px; left: 0; width: 8px; height: 8px; border-radius: 50%; background: var(--unit); opacity: .9;
  animation-name: travel; animation-timing-function: linear; animation-iteration-count: infinite; }
.chain-big .unit { top: -6px; width: 12px; height: 12px; box-shadow: 0 0 10px var(--unit); }
@keyframes travel { from { left: -1% } to { left: 100% } }
.count { font-family: 'Barlow Condensed', 'Inter', sans-serif; font-weight: 600; font-size: 1.75rem; line-height: 1; color: var(--ink);
  font-variant-numeric: tabular-nums; height: 2.1rem; }
.chain-big .count { font-size: 3.6rem; height: 4.4rem; }
.node { position: relative; display: block; width: 16px; height: 16px; margin: 8px 0 8px; border-radius: 50%; background: var(--node);
  box-shadow: 0 0 0 4px #fff; transition: transform .2s; }
.chain-big .node { width: 24px; height: 24px; margin: 12px 0; box-shadow: 0 0 0 6px #10263a; }
.group:hover .node, .group:focus-visible .node { transform: scale(1.25); }
.node-stuck { background: var(--stuck); }
.pulse { position: absolute; inset: 0; border-radius: 50%; border: 2px solid var(--stuck); animation: pulse 1.8s ease-out infinite; }
@keyframes pulse { from { transform: scale(1); opacity: .9 } to { transform: scale(2.6); opacity: 0 } }
.label { font-size: .8125rem; font-weight: 600; color: var(--ink); line-height: 1.2; }
.chain-big .label { font-size: 1.35rem; }
.stuck { margin-top: 2px; font-size: .75rem; color: var(--stuck); line-height: 1.2; }
.chain-big .stuck { font-size: 1.05rem; }
.stuck-none { font-size: .75rem; }
.ret { display: inline-flex; align-items: center; gap: .3rem; color: var(--muted); }
.ret b { font-weight: 600; color: var(--ink); }
.ret-on, .ret-on b { color: var(--stuck); }
.chain-big .returns { font-size: 1.2rem; }
a:focus-visible { outline: 2px solid var(--unit); outline-offset: 4px; border-radius: 6px; }
.chain-scroll { overflow-x: auto; }
@media (max-width: 760px) { .chain { min-width: 720px; } }
</style>
