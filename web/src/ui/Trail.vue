<script setup>
// Signatures or history of a quality record: who, what, when; nothing here can be changed (ADR-0010).
import { ago } from '../format'
import { t } from '../i18n'

defineProps({ items: Array, kind: { type: String, default: 'history' } })
</script>

<template>
  <p v-if="!items.length" class="wq-muted">{{ t('None yet.') }}</p>
  <ol v-else class="wq-panel divide-y divide-outline-gray-1">
    <li v-for="(x, i) in items" :key="i" class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-4 py-2.5 text-sm">
      <template v-if="kind === 'signatures'">
        <span class="lucide-pen-line size-3.5 self-center text-ink-gray-5" />
        <span class="font-medium text-ink-gray-9">{{ x.meaning }}</span>
        <span class="text-ink-gray-7">{{ x.name }} ({{ x.email }})</span>
        <span class="ms-auto text-ink-gray-5">{{ ago(x.at) }}</span>
      </template>
      <template v-else>
        <span class="w-44 shrink-0 text-ink-gray-5">{{ ago(x.at) }}</span>
        <span class="font-medium text-ink-gray-8">{{ x.action }}</span>
        <span class="text-ink-gray-7">{{ x.email }}</span>
        <span class="text-ink-gray-5">{{ x.note }}</span>
      </template>
    </li>
  </ol>
</template>
