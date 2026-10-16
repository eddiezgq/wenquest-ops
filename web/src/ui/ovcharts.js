// Chart options for the company overview (ADR-0018). One look for the workspace (light) and the big screen (dark).
import { fmt } from '../format'

export const LIGHT = { green: '#2f9e5b', amber: '#d9902a', red: '#d1453b', unknown: '#9aa3ae' }
const THEMES = {
  light: { line: '#1f7a8c', area: 'rgba(31,122,140,.14)', axis: '#8a96a1', grid: '#e7ecf0', text: '#1b2733', bar: '#1f7a8c' },
  dark: { line: '#5ccfd6', area: 'rgba(92,207,214,.18)', axis: '#7f98ab', grid: '#203b52', text: '#eef3f6', bar: '#5ccfd6' },
}
const COUNTS = new Set(['lots', 'reports', 'orders', 'items', 'open'])
const short = (iso) => (iso ? `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}` : '')
const axisFmt = (unit) => (v) => (unit === 'currency' ? compact(v) : unit === '%' ? `${v}%` : v)

export function compact(v) {
  if (v === null || v === undefined) return ''
  const a = Math.abs(v)
  return a >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : a >= 1e3 ? `${(v / 1e3).toFixed(a >= 1e4 ? 0 : 1)}k` : `${Math.round(v)}`
}

// A weekly curve. ``scaled``: the big screen in visitor mode, where the values are shares of the largest week.
export function curve(s, { dark = false, big = false, scaled = false } = {}) {
  const t = THEMES[dark ? 'dark' : 'light']
  const unit = scaled ? '' : s.unit
  const fs = big ? 16 : 11
  return {
    aria: s.label,
    animationDuration: 900, animationDurationUpdate: 700,
    grid: { left: big ? 64 : 44, right: big ? 28 : 18, top: 12, bottom: big ? 32 : 24 },
    tooltip: { trigger: 'axis', valueFormatter: (v) => (scaled ? `${v}% of the best week` : fmt(v, s.unit)) },
    xAxis: { type: 'category', boundaryGap: false, data: s.points.map((p) => short(p.week_ending)),
      axisLine: { lineStyle: { color: t.grid } }, axisTick: { show: false }, axisLabel: { color: t.axis, fontSize: fs } },
    yAxis: { type: 'value', splitNumber: 3, min: s.unit === '%' && !scaled ? (v) => Math.max(0, Math.floor(v.min / 10) * 10) : 0,
      max: scaled ? 100 : undefined, minInterval: COUNTS.has(s.unit) ? 1 : undefined,
      axisLabel: { show: !scaled, color: t.axis, fontSize: fs, formatter: axisFmt(unit) }, splitLine: { lineStyle: { color: t.grid } } },
    series: [{ type: 'line', smooth: 0.35, symbol: 'circle', symbolSize: big ? 9 : 6, showSymbol: true, connectNulls: false,
      data: s.points.map((p) => p.value), lineStyle: { width: big ? 4 : 2.5, color: t.line }, itemStyle: { color: t.line },
      areaStyle: { color: t.area } }],
  }
}

// Bars: receivables by days past due (later buckets in warmer colours).
export function aging(s, { dark = false, big = false, scaled = false } = {}) {
  const t = THEMES[dark ? 'dark' : 'light']
  const colors = [t.bar, LIGHT.amber, '#e0703a', LIGHT.red, '#9b2c2c']
  const fs = big ? 16 : 11
  return {
    aria: s.label, animationDuration: 900, animationDurationUpdate: 700,
    grid: { left: big ? 64 : 44, right: 12, top: 12, bottom: big ? 32 : 24 },
    tooltip: { trigger: 'axis', valueFormatter: (v) => (scaled ? `${v}%` : fmt(v, 'currency')) },
    xAxis: { type: 'category', data: s.points.map((p) => p.bucket), axisTick: { show: false },
      axisLine: { lineStyle: { color: t.grid } }, axisLabel: { color: t.axis, fontSize: fs } },
    yAxis: { type: 'value', splitNumber: 3, axisLabel: { color: t.axis, fontSize: fs, formatter: axisFmt(scaled ? '' : 'currency') },
      splitLine: { lineStyle: { color: t.grid } } },
    series: [{ type: 'bar', barWidth: '55%', data: s.points.map((p, i) => ({ value: p.value, itemStyle: { color: colors[i], borderRadius: [3, 3, 0, 0] } })) }],
  }
}

export const optionFor = (s, opts) => (s.kind === 'aging' ? aging(s, opts) : curve(s, opts))
