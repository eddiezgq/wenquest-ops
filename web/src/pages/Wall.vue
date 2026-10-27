<script setup>
// The big screen (ADR-0018): the company overview in large type for a TV in the office or on the shop floor. It
// moves through five scenes on its own and refreshes after each ERPNext sync. In visitor mode (the company's setting,
// on unless the owner turns it off) it shows no amounts of money and no names: shares, counts and curves only.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { fmt, setCurrency } from '../format'
import { t, locale } from '../i18n'
import { LIGHT, optionFor } from '../ui/ovcharts'
import FlowChain from '../components/FlowChain.vue'
import OvChart from '../components/OvChart.vue'

const router = useRouter()
const v = ref(null)
const error = ref('')
const scene = ref(0)
const paused = ref(false)
const now = ref(new Date())
const updated = ref(null)
const SCENES = [
  { title: 'The business today', panels: [] },
  { title: 'Sales and money', panels: ['sales', 'finance'] },
  { title: 'Delivering and stock', panels: ['delivery', 'inventory'] },
  { title: 'Buying and making', panels: ['purchasing', 'production'] },
  { title: 'Quality', panels: ['quality'] },
]
const SECONDS = 20
const COLOR_WORD = { green: 'On target', amber: 'Watch', red: 'Act now', unknown: 'Not enough data' }
let t1 = null; let t2 = null; let t3 = null

async function load() {
  try {
    if (!v.value) setCurrency((await api('/api/workspace')).currency)
    v.value = await api('/api/overview/wall')
    updated.value = new Date()
    error.value = ''
  } catch (e) { error.value = e.message }
}
const scenes = computed(() => SCENES.filter((s, i) => i === 0 || s.panels.some((k) => v.value?.panels.some((p) => p.key === k))))
const current = computed(() => scenes.value[scene.value % Math.max(scenes.value.length, 1)])
const shownPanels = computed(() => (v.value?.panels || []).filter((p) => current.value?.panels.includes(p.key)))
const next = (d = 1) => { scene.value = (scene.value + d + scenes.value.length) % scenes.value.length }
function key(e) {
  if (e.key === 'ArrowRight') next(1)
  else if (e.key === 'ArrowLeft') next(-1)
  else if (e.key === ' ') { paused.value = !paused.value; e.preventDefault() }
  else if (e.key === 'Escape') leave()
  else if (e.key === 'f') document.documentElement.requestFullscreen?.()
}
function leave() { if (document.fullscreenElement) document.exitFullscreen?.(); router.push('/') }
onMounted(() => {
  load()
  t1 = setInterval(load, 60_000)
  t2 = setInterval(() => { if (!paused.value) next(1) }, SECONDS * 1000)
  t3 = setInterval(() => { now.value = new Date() }, 30_000)
  window.addEventListener('keydown', key)
})
onBeforeUnmount(() => { clearInterval(t1); clearInterval(t2); clearInterval(t3); window.removeEventListener('keydown', key) })

const value = (x) => (x.hidden ? '' : x.value === null || x.value === undefined ? '—'
  : fmt(x.value, ['items', 'orders', 'lots', 'open', 'reports'].includes(x.unit) ? '' : x.unit))
const figs = (p) => p.figures.filter((f) => !f.hidden)
const scaled = computed(() => v.value?.visitor_mode)
const chartOf = computed(() => Object.fromEntries((v.value?.panels || []).map((p) => {
  const s = Object.values(p.series)[0]
  if (!s) return [p.key, null]
  const sc = scaled.value && s.unit === 'currency'
  return [p.key, { label: s.label, scaled: sc, option: optionFor(s, { dark: true, big: true, scaled: sc }) }]
})))

</script>

<template>
  <div class="wall" @dblclick="paused = !paused">
    <header class="top">
      <div>
        <p class="company">{{ v?.company || 'WenQuest Ops' }}</p>
        <h1 class="scene-title">{{ current ? t(current.title) : '' }}</h1>
      </div>
      <div class="meta">
        <p class="clock">{{ now.toLocaleDateString(locale(), { weekday: 'long', month: 'long', day: 'numeric' }) }}
          · {{ now.toLocaleTimeString(locale(), { hour: 'numeric', minute: '2-digit' }) }}</p>
        <nav class="pips" :aria-label="t('Scenes')">
          <button v-for="(s, i) in scenes" :key="s.title" :class="i === scene % scenes.length ? 'on' : ''" :aria-label="t(s.title)" @click="scene = i" />
        </nav>
        <button class="exit" @click="leave">{{ t('Leave the big screen') }}</button>
      </div>
    </header>

    <p v-if="error" class="err">{{ t('Not updated since {when}: {error}. Sign in again on this screen if the session ended.', { when: updated ? updated.toLocaleTimeString(locale(), { hour: 'numeric', minute: '2-digit' }) : t('the page opened'), error }) }}</p>

    <main v-if="v" :key="scene" class="stage">
      <template v-if="!current.panels.length">
        <section class="chain-wrap"><FlowChain :steps="v.chain" :returns="v.returns" big /></section>
        <section class="lights" :style="{ gridTemplateColumns: `repeat(${v.panels.length}, minmax(0, 1fr))` }">
          <div v-for="p in v.panels" :key="p.key" class="light" :style="{ '--c': LIGHT[p.light.color] }">
            <span class="lamp" />
            <p class="l-label">{{ t(p.label) }}</p>
            <p class="l-value">{{ value(p.light) }}</p>
            <p class="l-word">{{ t(COLOR_WORD[p.light.color]) }}</p>
          </div>
        </section>
      </template>
      <section v-else class="duo" :class="shownPanels.length === 1 ? 'solo' : ''">
        <article v-for="p in shownPanels" :key="p.key" class="wpanel" :style="{ '--c': LIGHT[p.light.color] }">
          <h2 class="p-title"><span class="lamp sm" />{{ t(p.label) }}<span class="p-what">{{ t(p.light.what) }}</span></h2>
          <div class="figs">
            <div v-for="f in figs(p).slice(0, 5)" :key="f.label" class="fig"><p class="f-value">{{ value(f) }}</p><p class="f-label">{{ t(f.label) }}</p></div>
          </div>
          <template v-if="chartOf[p.key]">
            <p class="s-label">{{ t(chartOf[p.key].label) }}<span v-if="chartOf[p.key].scaled"> {{ t('(shape only)') }}</span></p>
            <OvChart :key="`${p.key}-${chartOf[p.key].scaled}`" :option="chartOf[p.key].option" height="34vh" />
          </template>
          <div v-for="r in p.lists?.iso || []" :key="r.standard" class="iso">
            <p class="s-label">{{ t('{standard}: {met} control points met, {not_met} not met, {unknown} unknown', { standard: r.standard.toUpperCase().replace('ISO', 'ISO '), met: r.met, not_met: r.not_met, unknown: r.unknown }) }}</p>
            <div class="iso-bar"><i :style="{ flex: r.met, background: LIGHT.green }" /><i :style="{ flex: r.not_met, background: LIGHT.red }" /><i :style="{ flex: r.unknown, background: LIGHT.unknown }" /></div>
          </div>
        </article>
      </section>
    </main>
    <footer class="foot">
      <span>{{ paused ? t('Paused: space to go on') : t('Next scene in {s} s · arrow keys to move, space to pause, F for full screen', { s: SECONDS }) }}</span>
      <span v-if="v?.visitor_mode">{{ t('Visitor mode: no amounts or names shown') }}</span>
    </footer>
  </div>
</template>

<style scoped>
.wall { --bg: #0f2233; --panel: #15304a; --ink: #eef3f6; --muted: #9db2c3; --line: #24435e;
  min-height: 100vh; background: radial-gradient(1200px 600px at 15% -10%, #1b3f5e 0%, transparent 60%), var(--bg); color: var(--ink);
  display: flex; flex-direction: column; padding: 2.2vh 3vw; font-family: 'Inter', sans-serif; }
.top { display: flex; justify-content: space-between; align-items: flex-end; gap: 2rem; }
.company { color: var(--muted); font-size: 1.1rem; }
.scene-title { font-family: 'Barlow Condensed', sans-serif; font-weight: 600; font-size: clamp(2.2rem, 4.2vw, 4.6rem); line-height: 1; letter-spacing: .01em; }
.meta { display: flex; flex-direction: column; align-items: flex-end; gap: .6rem; }
.clock { color: var(--muted); font-size: 1.15rem; }
.pips { display: flex; gap: .5rem; }
.pips button { width: 34px; height: 6px; border-radius: 3px; background: var(--line); }
.pips button.on { background: #5ccfd6; }
.exit { color: var(--muted); font-size: .9rem; text-decoration: underline; text-underline-offset: 3px; }
.exit:focus-visible, .pips button:focus-visible { outline: 2px solid #5ccfd6; outline-offset: 3px; }
.err { margin-top: 1rem; color: #ff6b5e; }
.stage { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: 5vh; animation: enter .7s ease-out; }
@keyframes enter { from { opacity: 0; transform: translateY(12px) } to { opacity: 1; transform: none } }
.chain-wrap { background: color-mix(in srgb, var(--panel) 70%, transparent); border: 1px solid var(--line); border-radius: 18px; padding: 2.5vh 1.5vw 1.5vh; }
.lights { display: grid; gap: 1.2vw; }
.light { position: relative; background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 1.6vh 1.1vw 1.4vh; overflow: hidden; }
.light::after { content: ''; position: absolute; inset: auto 0 0 0; height: 5px; background: var(--c); }
.lamp { display: inline-block; width: 18px; height: 18px; border-radius: 50%; background: var(--c); box-shadow: 0 0 18px var(--c); }
.lamp.sm { width: 14px; height: 14px; margin-right: .7rem; }
.l-label { margin-top: .6rem; font-size: 1.25rem; color: var(--muted); }
.l-value { font-family: 'Barlow Condensed', sans-serif; font-weight: 600; font-size: clamp(2.4rem, 4.4vw, 5rem); line-height: 1.05; font-variant-numeric: tabular-nums; }
.l-word { font-size: 1.05rem; color: var(--c); font-weight: 600; }
.duo { display: grid; grid-template-columns: 1fr 1fr; gap: 2vw; }
.duo.solo { grid-template-columns: 1fr; }
.wpanel { background: var(--panel); border: 1px solid var(--line); border-top: 5px solid var(--c); border-radius: 18px; padding: 2.4vh 1.8vw; }
.p-title { display: flex; align-items: center; flex-wrap: wrap; font-family: 'Barlow Condensed', sans-serif; font-weight: 600; font-size: 2.4rem; }
.p-what { margin-left: auto; font-family: 'Inter', sans-serif; font-weight: 400; font-size: 1rem; color: var(--muted); }
.figs { display: flex; flex-wrap: wrap; gap: 1.2vh 3vw; margin: 2vh 0 2.4vh; }
.f-value { font-family: 'Barlow Condensed', sans-serif; font-weight: 600; font-size: clamp(2rem, 3.4vw, 3.8rem); line-height: 1; font-variant-numeric: tabular-nums; }
.f-label { color: var(--muted); font-size: 1.05rem; margin-top: .3rem; }
.s-label { color: var(--muted); font-size: 1rem; }
.iso { margin-top: 2vh; }
.iso-bar { display: flex; height: 16px; margin-top: .6rem; border-radius: 8px; overflow: hidden; background: var(--line); }
.iso-bar i { display: block; }
.foot { display: flex; justify-content: space-between; color: var(--muted); font-size: .95rem; padding-top: 1.5vh; }
@media (prefers-reduced-motion: reduce) { .stage { animation: none; } }
@media (max-width: 900px) { .duo { grid-template-columns: 1fr; } .lights { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; } }
</style>
