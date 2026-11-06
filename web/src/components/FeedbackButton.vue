<script setup>
// "Report a problem" (ADR-0025 25d): a sentence from the person, plus the page and the last few errors the browser
// saw; the hub keeps it and emails all reports once a day to whoever runs the pilot.
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button, Dialog } from 'frappe-ui'
import { api } from '../api'
import { t } from '../i18n'

const recent = []
window.addEventListener('error', (e) => { recent.push(String(e.message || e)); recent.splice(0, recent.length - 10) })
window.addEventListener('unhandledrejection', (e) => {
  recent.push(String(e.reason?.message || e.reason)); recent.splice(0, recent.length - 10)
})

const route = useRoute()
const open = ref(false)
const text = ref('')
const done = ref('')
const error = ref('')
async function send() {
  error.value = ''
  try {
    await api('/api/feedback', { method: 'POST', body: { text: text.value, page: route.fullPath, errors: recent } })
    text.value = ''
    done.value = t('Thank you - it has been sent. We read every report.')
  } catch (e) { error.value = e.message }
}
</script>

<template>
  <button type="button" class="wq-feedback" data-help="feedback" @click="open = true; done = ''">{{ t('Report a problem') }}</button>
  <Dialog v-model="open" :options="{ title: t('Report a problem') }">
    <template #body-content>
      <p class="mb-2 text-sm text-ink-gray-6">{{ t('What did you do, and what went wrong? The page you are on is sent with it.') }}</p>
      <textarea v-model="text" class="wq-input h-28 w-full" maxlength="4000" />
      <p v-if="done" class="mt-2 text-sm text-ink-green-7">{{ done }}</p>
      <p v-if="error" class="mt-2 text-sm text-ink-red-7">{{ error }}</p>
    </template>
    <template #actions>
      <Button variant="solid" :label="t('Send')" :disabled="!text.trim()" @click="send" />
    </template>
  </Dialog>
</template>

<style scoped>
.wq-feedback { position: fixed; right: 16px; bottom: 16px; z-index: 40; font-size: 13px; padding: 6px 12px;
  border-radius: 999px; border: 1px solid var(--outline-gray-2, #ddd); background: var(--surface-white, #fff);
  color: var(--ink-gray-7, #333); box-shadow: 0 2px 8px rgba(0,0,0,.08); }
</style>
