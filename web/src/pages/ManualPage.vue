<script setup>
// One edition of a parts manual, inside the company (round 124, 27c): the pages as frozen, each with its picture and
// table, and a way to the exploded view where the 3D can be turned (the links for dealers never show 3D).
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { t } from '../i18n'

const route = useRoute()
const m = ref(null)
const error = ref('')
const CH = { added: 'Added', removed: 'Removed', quantity: 'Quantity changed', 'new page': 'New page', 'page removed': 'Page removed' }
async function load() { error.value = ''; try { m.value = await api(`/api/plm/manuals/${route.params.id}`) } catch (e) { error.value = e.message } }
watch(() => route.params.id, load, { immediate: true })
</script>

<template>
  <PageTop :crumbs="m ? [{ label: t('Parts'), to: '/plm/parts' }, { label: m.item_code, to: `/plm/parts/${m.part_id}` }] : [{ label: t('Parts'), to: '/plm/parts' }]">
    <template #title>{{ m ? `${t('Parts manual')} · ${m.item_code} · ${t('Edition {n}', { n: m.edition })}` : t('Parts manual') }}</template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <template v-if="m">
    <p class="mb-4 text-sm">{{ m.name }} · {{ m.created_by }} {{ m.created_at?.slice(0, 16).replace('T', ' ') }} ·
      <a :href="`/api/plm/manuals/${m.id}/pdf`" target="_blank" class="wq-link">PDF</a></p>
    <section v-if="m.changes.length" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ t('Changes from the previous edition') }}</h2>
      <table class="wq-table text-sm"><thead><tr><th>{{ t('Assembly') }}</th><th>{{ t('Part') }}</th><th>{{ t('Change') }}</th><th>{{ t('Was') }}</th><th>{{ t('Now') }}</th></tr></thead>
        <tbody><tr v-for="(c, i) in m.changes" :key="i"><td>{{ c.page }}</td><td>{{ c.code || '–' }} {{ c.name || '' }}</td><td>{{ t(CH[c.change] || c.change) }}</td><td>{{ c.old ?? '–' }}</td><td>{{ c.new ?? '–' }}</td></tr></tbody></table>
    </section>
    <section v-for="(p, i) in m.pages" :id="`s${i + 1}`" :key="p.bom" class="wq-panel mb-5 p-5">
      <h2 class="wq-h2">{{ i + 1 }}. {{ p.code }} {{ p.name }} <span class="text-ink-gray-5">{{ p.name_en }}</span>
        <span class="ms-2 text-sm font-normal">BOM {{ p.revision }} · <RouterLink :to="`/plm/boms/${p.bom}/explode`" class="wq-link">{{ t('Exploded view and 3D') }}</RouterLink></span></h2>
      <img v-if="p.picture" :src="`/api/plm/manuals/${m.id}/picture/${i + 1}`" :alt="p.code" class="mb-3 w-full max-w-4xl rounded-2 border border-outline-gray-2 bg-white">
      <p v-else class="wq-muted mb-3">{{ t('No exploded view on this page.') }}</p>
      <table class="wq-table text-sm"><thead><tr><th>{{ t('No.') }}</th><th>{{ t('Part number') }}</th><th>{{ t('Name') }}</th><th>{{ t('English name') }}</th><th>{{ t('Quantity') }}</th><th>{{ t('Note') }}</th></tr></thead>
        <tbody><tr v-for="x in p.lines" :key="x.no"><td>{{ x.no }}</td><td>{{ x.code }}</td><td>{{ x.name }}</td>
          <td>{{ x.name_en }}<span v-if="!x.name_en" class="text-ink-amber-7">{{ t('to be confirmed') }}</span></td><td>{{ x.qty }} {{ x.uom }}</td>
          <td><a v-if="x.page" :href="`#s${x.page}`" class="wq-link">{{ t('See section {n}', { n: x.page }) }}</a><template v-else>{{ x.note }}</template></td></tr></tbody></table>
    </section>
  </template>
</template>
