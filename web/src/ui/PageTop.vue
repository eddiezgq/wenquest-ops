<script setup>
// The header row of every page (ADR-0013): breadcrumbs and title on the left, the page's actions on the right.
import { PageHeader } from 'frappe-ui'
import { t } from '../i18n'

defineProps({ title: String, crumbs: { type: Array, default: () => [] } })
</script>

<template>
  <PageHeader>
    <div class="flex min-w-0 items-center gap-1.5">
      <template v-for="c in crumbs" :key="c.label">
        <RouterLink :to="c.to" class="shrink-0 text-lg text-ink-gray-5 hover:text-ink-gray-8">{{ t(c.label) }}</RouterLink>
        <span class="text-lg text-ink-gray-4">/</span>
      </template>
      <h1 class="truncate text-lg font-semibold text-ink-gray-9"><slot name="title">{{ t(title) }}</slot></h1>
    </div>
    <div class="flex shrink-0 items-center gap-2"><slot /></div>
  </PageHeader>
</template>
