<script setup>
// Machines and other systems (ADR-0020, 20d): each has its own access token, limited to what it may do and revocable.
// The token is shown once; WenQuest Ops keeps only a hash of it. Every call is logged.
import { ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'

const v = ref(null)
const error = ref('')
const f = ref({ name: '', scopes: [] })
const fresh = ref(null)
const copied = ref(false)
const open = ref(null)
const calls = ref([])
const note = ref('')
async function load() { try { v.value = await api('/api/integrations/tokens') } catch (e) { error.value = e.message } }
load()
async function create() {
  error.value = ''; copied.value = false
  try {
    fresh.value = await api('/api/integrations/tokens', { method: 'POST', body: f.value })
    f.value = { name: '', scopes: [] }
    await load()
  } catch (e) { error.value = e.message }
}
async function copy() { try { await navigator.clipboard.writeText(fresh.value.token); copied.value = true } catch { copied.value = false } }
async function show(t) {
  open.value = open.value === t.id ? null : t.id; note.value = ''
  calls.value = open.value ? await api(`/api/integrations/tokens/${t.id}/calls`) : []
}
async function revoke(t) {
  error.value = ''
  try { await api(`/api/integrations/tokens/${t.id}/revoke`, { method: 'POST', body: { note: note.value } }); open.value = null; await load() } catch (e) { error.value = e.message }
}
const when = (s) => (s ? s.slice(0, 16).replace('T', ' ') : '–')
</script>

<template>
  <PageTop title="Machines and systems" />
  <p class="mb-4 max-w-3xl text-base text-ink-gray-7">An MES, a test bench or a gauge station sends measurements and step results, and
    reads events, with its own access token. What it sends waits under <RouterLink to="/quality/inbox" class="wq-link">From machines</RouterLink>
    until someone accepts it. See the <RouterLink to="/help/machines-and-mes" class="wq-link">help</RouterLink> for the calls.</p>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <section v-if="fresh" data-help="token-once" class="mb-5 rounded-5 border border-outline-amber-3 bg-surface-amber-1 p-5">
    <h2 class="wq-h2">Token for {{ fresh.name }}</h2>
    <p class="mb-2 text-sm text-ink-gray-8">Copy it into the machine's settings now. It is not shown again; if it is lost, revoke it and make a new one.</p>
    <div class="flex flex-wrap items-center gap-2"><code class="break-all rounded-3 bg-surface-white px-3 py-2 font-mono text-sm">{{ fresh.token }}</code>
      <Button size="sm" :label="copied ? 'Copied' : 'Copy'" icon-left="lucide-copy" @click="copy" />
      <Button size="sm" variant="ghost" label="Done" @click="fresh = null" /></div>
  </section>
  <form v-if="v" data-help="token-new" class="wq-panel mb-5 flex flex-wrap items-end gap-4 p-5" @submit.prevent="create">
    <label class="wq-field">Machine or system<input v-model="f.name" class="wq-input w-64" placeholder="Line 1 MES" maxlength="100"></label>
    <fieldset class="flex flex-col gap-1 text-sm text-ink-gray-8"><legend class="mb-1 text-sm text-ink-gray-6">It may</legend>
      <label v-for="(text, k) in v.scopes" :key="k" class="flex items-center gap-2"><input v-model="f.scopes" type="checkbox" :value="k">{{ text }}</label></fieldset>
    <Button type="submit" variant="solid" label="Make a token" :disabled="!f.name.trim() || !f.scopes.length" />
  </form>
  <section v-if="v" data-help="token-list" class="wq-panel p-5">
    <p v-if="!v.tokens.length" class="wq-muted">No machine or system has a token yet.</p>
    <table v-else class="wq-table text-sm"><thead><tr><th>Name</th><th>May</th><th>Token</th><th>Made</th><th>Last call</th><th>Calls</th><th /></tr></thead>
      <tbody><template v-for="t in v.tokens" :key="t.id"><tr :class="t.active ? '' : 'text-ink-gray-5'">
        <td class="font-medium">{{ t.name }} <Badge v-if="!t.active" label="revoked" /></td>
        <td>{{ t.scopes.join(', ') }}</td><td class="font-mono">{{ t.prefix }}…</td>
        <td>{{ when(t.created_at) }} by {{ t.created_by }}</td><td>{{ when(t.last_used_at) }}</td><td>{{ t.calls }}</td>
        <td><Button size="sm" variant="ghost" :label="open === t.id ? 'Close' : 'Calls'" @click="show(t)" /></td></tr>
        <tr v-if="open === t.id"><td colspan="7" class="bg-surface-gray-1">
          <p v-if="!t.active" class="text-sm">Revoked {{ when(t.revoked_at) }} by {{ t.revoked_by }}<template v-if="t.revoke_note">: {{ t.revoke_note }}</template></p>
          <div v-else class="mb-2 flex flex-wrap items-end gap-2"><label class="wq-field">Why revoke<input v-model="note" class="wq-input w-72"></label>
            <Button size="sm" theme="red" label="Revoke" @click="revoke(t)" /></div>
          <p v-if="!calls.length" class="text-sm text-ink-gray-5">No calls yet.</p>
          <p v-for="(c, i) in calls" :key="i" class="font-mono text-xs">{{ when(c.at) }} {{ c.method }} {{ c.path }} → {{ c.status }}</p></td></tr>
      </template></tbody></table>
  </section>
</template>
