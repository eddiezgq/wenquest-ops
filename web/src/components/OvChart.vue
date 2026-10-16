<script setup>
// A chart of the company overview (ADR-0018), drawn with Apache ECharts. ECharts is loaded only where a chart is
// shown. A new option animates from the old values to the new ones, so a refresh shows what moved.
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

const props = defineProps({ option: { type: Object, required: true }, height: { type: String, default: '160px' } })
const el = ref(null)
const chart = shallowRef(null)
let ro = null

async function lib() {
  const [core, charts, comps, renderers] = await Promise.all([
    import('echarts/core'), import('echarts/charts'), import('echarts/components'), import('echarts/renderers')])
  core.use([charts.LineChart, charts.BarChart, comps.GridComponent, comps.TooltipComponent, comps.MarkLineComponent,
    renderers.CanvasRenderer])
  return core
}

onMounted(async () => {
  const core = await lib()
  if (!el.value) return
  chart.value = core.init(el.value, null, { renderer: 'canvas' })
  chart.value.setOption(props.option)
  ro = new ResizeObserver(() => chart.value?.resize())
  ro.observe(el.value)
})
// a new option object only when the data changed (the parents build them in computed values)
watch(() => props.option, (o) => chart.value?.setOption(o, { notMerge: false }))
onBeforeUnmount(() => { ro?.disconnect(); chart.value?.dispose() })
</script>

<template>
  <div ref="el" :style="{ height }" class="w-full" role="img" :aria-label="option.aria || 'chart'" />
</template>
