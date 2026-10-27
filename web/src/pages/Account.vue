<script setup>
// My account (ADR-0005 item 6): your roles and permissions, and your own password.
import { inject, ref } from 'vue'
import { Avatar, Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { t } from '../i18n'

const ws = inject('workspace')
const f = ref({ current: '', password: '', again: '' })
const error = ref('')
async function change() {
  error.value = ''
  if (f.value.password !== f.value.again) { error.value = t('The two new passwords are not the same.'); return }
  try {
    await api('/api/users/password', { method: 'POST', body: { current: f.value.current, password: f.value.password } })
    location.href = '/login?next=/account'          // all sessions end: sign in with the new password
  } catch (e) { error.value = e.message }
}
</script>

<template>
  <PageTop :title="t('My account')" />
  <div v-if="ws" class="grid max-w-5xl gap-6 lg:grid-cols-2">
    <section data-help="account-roles" class="wq-panel p-5">
      <div class="flex items-center gap-3"><Avatar :label="ws.user.name" size="2xl" />
        <div><div class="text-lg font-semibold text-ink-gray-9">{{ ws.user.name }}</div><div class="wq-muted">{{ ws.user.email }}</div></div></div>
      <dl class="wq-dl mt-5">
        <dt>{{ t('Roles') }}</dt><dd><Badge v-for="r in ws.user.roles" :key="r" :label="t(r.replace('_', ' '))" class="me-1 capitalize" /></dd>
        <dt>{{ t('Department') }}</dt><dd class="capitalize">{{ ws.user.department || '—' }}</dd>
      </dl>
      <h3 class="mt-5 text-sm font-medium text-ink-gray-5">{{ t('You may') }}</h3>
      <ul class="mt-2 space-y-1.5 text-sm text-ink-gray-8">
        <li v-for="p in ws.may" :key="p" class="flex gap-2"><span class="lucide-check mt-0.5 size-4 shrink-0 text-ink-green-6" />{{ p }}</li></ul>
      <p class="wq-muted mt-4">{{ t('Roles come from the company manifest; ask the owner to change them.') }}</p>
    </section>
    <section data-help="account-password" class="wq-panel h-fit p-5">
      <h2 class="text-base font-semibold text-ink-gray-9">{{ ws.user.has_password ? t('Change your password') : t('Set a password') }}</h2>
      <p class="wq-muted mt-1">{{ ws.user.has_password
        ? t('You sign quality records with this password. At least 10 characters with letters and digits. Afterwards you sign in again everywhere.')
        : t('You sign quality records with this password, also when you sign in with Microsoft or Google. At least 10 characters with letters and digits. Afterwards you sign in again everywhere.') }}</p>
      <form class="mt-4 grid gap-3" @submit.prevent="change">
        <input v-if="ws.user.has_password" v-model="f.current" class="wq-input" type="password" :placeholder="t('Current password')" autocomplete="current-password" required>
        <input v-model="f.password" class="wq-input" type="password" :placeholder="t('New password')" autocomplete="new-password" required>
        <input v-model="f.again" class="wq-input" type="password" :placeholder="t('New password again')" autocomplete="new-password" required>
        <div><Button type="submit" variant="solid" :label="t('Save password')" /></div>
        <p v-if="error" class="wq-error">{{ error }}</p>
      </form>
    </section>
  </div>
</template>
