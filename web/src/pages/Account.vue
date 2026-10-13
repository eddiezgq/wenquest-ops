<script setup>
// My account (ADR-0005 item 6): your roles and permissions, and your own password.
import { inject, ref } from 'vue'
import { api } from '../api'

const ws = inject('workspace')
const f = ref({ current: '', password: '', again: '' })
const error = ref('')
async function change() {
  error.value = ''
  if (f.value.password !== f.value.again) { error.value = 'The two new passwords are not the same.'; return }
  try {
    await api('/api/users/password', { method: 'POST', body: { current: f.value.current, password: f.value.password } })
    location.href = '/login?next=/account'          // all sessions end: sign in with the new password
  } catch (e) { error.value = e.message }
}
</script>

<template>
  <h1>My account</h1>
  <table class="props" v-if="ws">
    <tr><th>Name</th><td>{{ ws.user.name }}</td></tr>
    <tr><th>Email</th><td>{{ ws.user.email }}</td></tr>
    <tr><th>Roles</th><td>{{ ws.user.roles.join(', ') }}</td></tr>
    <tr><th>Department</th><td>{{ ws.user.department || '—' }}</td></tr>
    <tr><th>You may</th><td><ul class="list small"><li v-for="p in ws.may" :key="p">{{ p }}</li></ul></td></tr>
  </table>
  <p class="muted small">Roles come from the company manifest; ask the owner to change them.</p>

  <h2>{{ ws?.user.has_password ? 'Change your password' : 'Set a password' }}</h2>
  <p class="muted small">You sign quality records with this password<template v-if="!ws?.user.has_password">, also when you sign in with Microsoft or Google</template>.
    At least 10 characters with letters and digits. Afterwards you sign in again everywhere.</p>
  <form class="card form" style="max-width:28rem" @submit.prevent="change">
    <input v-if="ws?.user.has_password" v-model="f.current" type="password" placeholder="Current password" autocomplete="current-password" required>
    <input v-model="f.password" type="password" placeholder="New password" autocomplete="new-password" required>
    <input v-model="f.again" type="password" placeholder="New password again" autocomplete="new-password" required>
    <button>Save password</button>
    <p v-if="error" class="err">{{ error }}</p>
  </form>
</template>
