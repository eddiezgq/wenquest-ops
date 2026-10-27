<!-- frappe-ui's SidebarCollapseToggle with its label in the interface language (ADR-0023) -->
<template>
  <SidebarItem :label="isCollapsed ? t('Expand') : t('Collapse')" @click="toggle">
    <template #prefix>
      <span class="lucide-panel-right-open size-4 text-ink-gray-6 transition-transform duration-300 ease-in-out"
            :class="{ 'rotate-180': isCollapsed }" />
    </template>
  </SidebarItem>
</template>

<script setup>
import { computed, inject } from 'vue'
import { SidebarItem, sidebarCollapsedKey, sidebarToggleKey } from 'frappe-ui'
import { t } from '../i18n'

const isCollapsed = inject(sidebarCollapsedKey, computed(() => false))
const toggle = inject(sidebarToggleKey, () => {})
</script>
