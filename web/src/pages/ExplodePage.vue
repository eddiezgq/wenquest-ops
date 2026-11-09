<script setup>
// The exploded view of one assembly, a page of the parts manual (round 124, 27b): the parts directly under it
// pulled apart in 3D (a sub-assembly moves as one block: it has a page of its own) or an uploaded drawing; numbered
// balloons on the picture, one per drawn line; the table with the English names. A layout, not design data.
import { computed, onBeforeUnmount, ref, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api, apiForm } from '../api'
import { t } from '../i18n'
import { fileUrl, geometries, lights, shade } from '../plm3d/step3d'

const route = useRoute()
const v = ref(null)
const error = ref('')
const done = ref('')
const busy = ref(false)
const kind = ref('model')
const factor = ref(0.6)
const moves = ref({})          // part id -> [dx, dy, dz] mm, on top of the automatic pull
const drawn = ref({})          // part id -> drawn or not (default: not for fasteners)
const balloons = ref([])       // {part_id, x, y} as fractions of the picture
const anchors = ref({})        // part id -> {x, y} where the part is on the picture now
const selected = ref(null)     // a line's part id
const imageUrl = ref('')
const imageFile = ref(null)
const status = ref('')
const stage = ref(null)
const W = 960, H = 640
const bid = () => Number(route.params.id)

const lines = computed(() => v.value?.lines || [])
const no = computed(() => Object.fromEntries(lines.value.map((l) => [l.part_id, l.no])))
const isDrawn = (l) => (l.part_id in drawn.value ? drawn.value[l.part_id] : l.drawn)
const groups = computed(() => new Set((v.value?.scene.items || []).map((x) => x.line)))

let three = null              // {THREE, renderer, scene, camera, controls, root, blocks, size, mid, frame}
function teardown() {
  if (!three) return
  cancelAnimationFrame(three.frame); three.controls.dispose(); three.renderer.dispose(); three = null
}
onBeforeUnmount(teardown)

async function load() {
  error.value = ''; done.value = ''
  try {
    const d = await api(`/api/plm/explode/${bid()}`)
    v.value = d
    const p = d.page
    kind.value = p.kind || (d.scene.items.length ? 'model' : 'image')
    factor.value = p.layout?.factor ?? 0.6
    moves.value = Object.fromEntries(Object.entries(p.layout?.moves || {}).map(([k, m]) => [Number(k), m]))
    drawn.value = Object.fromEntries(Object.entries(p.layout?.drawn || {}).map(([k, x]) => [Number(k), x]))
    balloons.value = (p.balloons || []).map((b) => ({ ...b }))
    imageUrl.value = p.image_sha ? `/api/plm/explode/${bid()}/image?${p.image_sha.slice(0, 8)}` : ''
    await nextTick()
    await draw(p.layout?.camera)
  } catch (e) { error.value = e.message }
}
watch(() => route.params.id, () => { teardown(); load() }, { immediate: true })

// ---- 3D
async function draw(camera) {
  teardown()
  if (kind.value !== 'model' || !stage.value || !v.value?.scene.items.length) return
  status.value = t('Reading the models…')
  const THREE = await import('three')
  const { OrbitControls } = await import('three/examples/jsm/controls/OrbitControls.js')
  const scene = new THREE.Scene()
  scene.background = new THREE.Color('#ffffff')
  lights(THREE, scene)
  const root = new THREE.Group(); root.rotation.x = -Math.PI / 2; scene.add(root)
  const blocks = new Map()      // line part id -> {group, center (assembly frame)}
  let bad = 0
  for (const it of v.value.scene.items) {
    let gs
    try { gs = await geometries(THREE, fileUrl(it)) } catch (e) { if (e.message === 'occt') { status.value = t('The 3D reader did not load.'); return } bad += 1; continue }
    const key = `${it.line}:${it.use || 0}`      // each use of a line moves on its own; a sub-assembly as one block
    if (!blocks.has(key)) { const g = new THREE.Group(); g.userData.line = it.line; root.add(g); blocks.set(key, { group: g, line: it.line, use: it.use || 0 }) }
    const holder = new THREE.Group(); holder.matrixAutoUpdate = false; holder.matrix.set(...it.m)
    const mat = new THREE.MeshStandardMaterial({ color: shade(String(it.line)), metalness: 0.3, roughness: 0.55 })
    for (const geo of gs) { const mesh = new THREE.Mesh(geo, mat); mesh.userData.line = it.line; holder.add(mesh) }
    blocks.get(key).group.add(holder)
  }
  root.updateMatrixWorld(true)
  const inv = new THREE.Matrix4().copy(root.matrixWorld).invert()
  const all = new THREE.Box3()
  for (const b of blocks.values()) {
    const bb = new THREE.Box3().setFromObject(b.group)
    all.union(bb)
    b.center = bb.getCenter(new THREE.Vector3()).applyMatrix4(inv)         // in the assembly's frame
  }
  const mid = all.getCenter(new THREE.Vector3()).applyMatrix4(inv)
  const size = all.getSize(new THREE.Vector3()).length() || 100
  const cam = new THREE.PerspectiveCamera(30, W / H, size / 1000, size * 40)
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true })
  renderer.setPixelRatio(1); renderer.setSize(W, H)
  renderer.domElement.style.width = '100%'; renderer.domElement.style.height = 'auto'
  stage.value.querySelector('.canvas').replaceChildren(renderer.domElement)
  const controls = new OrbitControls(cam, renderer.domElement)
  const wmid = all.getCenter(new THREE.Vector3())
  if (camera?.position) {
    cam.position.set(...camera.position); controls.target.set(...(camera.target || wmid.toArray()))
    if (camera.up) cam.up.set(...camera.up)
  } else {
    cam.position.copy(wmid).add(new THREE.Vector3(size * 1.1, size * 0.75, size * 1.4)); controls.target.copy(wmid)
  }
  controls.update()
  three = { THREE, renderer, scene, camera: cam, controls, root, blocks, size, mid, frame: 0 }
  if (!camera?.position) { place(); fit() }
  renderer.domElement.addEventListener('click', pick)
  const loop = () => { place(); controls.update(); renderer.render(scene, cam); project(); three.frame = requestAnimationFrame(loop) }
  loop()
  status.value = bad ? t('{n} model files could not be read.', { n: bad }) : ''
}

function place() {             // each block pulled out from the middle, plus its own moves
  const { THREE, blocks, size, mid } = three
  for (const b of blocks.values()) {
    const line = b.line
    const dir = new THREE.Vector3().subVectors(b.center, mid)
    if (dir.length() < size * 1e-3) dir.set(0, 0, 1)
    dir.normalize().multiplyScalar(factor.value * size * 0.5)
    const m = moves.value[line] || [0, 0, 0]
    b.group.position.set(dir.x + m[0], dir.y + m[1], dir.z + m[2])
    const l = lines.value.find((x) => x.part_id === line)
    b.group.visible = l ? isDrawn(l) : true
  }
}

function fit() {               // the drawn parts, pulled apart, filling the picture; the direction of view kept
  if (!three) return
  const { THREE, blocks, camera, controls, root } = three
  root.updateMatrixWorld(true)
  const bb = new THREE.Box3()
  for (const b of blocks.values()) if (b.group.visible) bb.union(new THREE.Box3().setFromObject(b.group))
  if (bb.isEmpty()) return
  const c = bb.getCenter(new THREE.Vector3()), r = bb.getSize(new THREE.Vector3()).length() / 2
  const dir = new THREE.Vector3().subVectors(camera.position, controls.target).normalize()
  const dist = r / Math.sin((camera.fov * Math.PI) / 360) * 1.15
  controls.target.copy(c); camera.position.copy(c).addScaledVector(dir, dist)
  camera.near = dist / 100; camera.far = dist * 20; camera.updateProjectionMatrix(); controls.update()
}

function project() {           // where each drawn block is on the picture now (fractions)
  const { THREE, blocks, camera, root } = three
  const out = {}
  for (const b of blocks.values()) {
    const line = b.line
    if (!b.group.visible || (line in out && b.use > 0)) continue          // the balloon points at the first use
    const p = b.center.clone().add(b.group.position).applyMatrix4(root.matrixWorld).project(camera)
    out[line] = { x: (p.x + 1) / 2, y: (1 - p.y) / 2 }
  }
  anchors.value = out
}

function pick(e) {
  const { THREE, renderer, camera, root } = three
  const r = renderer.domElement.getBoundingClientRect()
  const at = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
  const ray = new THREE.Raycaster(); ray.setFromCamera(at, camera)
  const hit = ray.intersectObject(root, true).find((h) => h.object.visible)
  selected.value = hit ? hit.object.userData.line : null
}

function nudge(axis, sign) {
  if (!selected.value || !three) return
  const m = [...(moves.value[selected.value] || [0, 0, 0])]
  m[axis] += sign * three.size * 0.05
  moves.value = { ...moves.value, [selected.value]: m }
}

// ---- balloons
function autoBalloons() {
  const have = new Set(balloons.value.map((b) => b.part_id))
  const add = []
  for (const l of lines.value) {
    if (!isDrawn(l) || have.has(l.part_id)) continue
    const a = kind.value === 'model' ? anchors.value[l.part_id] : null
    if (!a) continue
    const dx = a.x - 0.5, dy = a.y - 0.5, n = Math.hypot(dx, dy) || 1
    add.push({ part_id: l.part_id, x: Math.min(0.96, Math.max(0.04, a.x + (dx / n) * 0.1)), y: Math.min(0.94, Math.max(0.06, a.y + (dy / n) * 0.1)) })
  }
  balloons.value = [...balloons.value, ...add]
}
const anchorOf = (b) => (kind.value === 'model' ? anchors.value[b.part_id] : (b.ax != null ? { x: b.ax, y: b.ay } : null))
let drag = null
function down(b, e) { drag = b; e.target.setPointerCapture(e.pointerId) }
function move(e) {
  if (!drag) return
  const r = stage.value.querySelector('.overlay').getBoundingClientRect()
  drag.x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)); drag.y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))
}
function up() { drag = null }
function clickImage(e) {        // drawing: put the selected line's balloon where the part is, a little to the side
  if (kind.value !== 'image' || !selected.value || drag) return
  const r = e.currentTarget.getBoundingClientRect()
  const ax = (e.clientX - r.left) / r.width, ay = (e.clientY - r.top) / r.height
  balloons.value = [...balloons.value.filter((b) => b.part_id !== selected.value),
    { part_id: selected.value, ax, ay, x: Math.min(0.96, ax + 0.06), y: Math.max(0.04, ay - 0.06) }]
}
const removeBalloon = (pid) => { balloons.value = balloons.value.filter((b) => b.part_id !== pid) }

function pickImage(e) {
  const f = e.target.files[0]
  if (!f) return
  imageFile.value = f; imageUrl.value = URL.createObjectURL(f); kind.value = 'image'; teardown()
}

// ---- save: the settings and the picture with its balloons
async function picture() {
  const c = document.createElement('canvas'); c.width = W; c.height = H
  const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, W, H)
  if (kind.value === 'model' && three) {
    three.renderer.render(three.scene, three.camera); g.drawImage(three.renderer.domElement, 0, 0, W, H)
  } else if (imageUrl.value) {
    const img = await new Promise((ok, no2) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no2; i.src = imageUrl.value })
    const s = Math.min(W / img.width, H / img.height)
    g.drawImage(img, (W - img.width * s) / 2, (H - img.height * s) / 2, img.width * s, img.height * s)
  }
  g.strokeStyle = '#333'; g.lineWidth = 1; g.font = 'bold 15px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'
  for (const b of balloons.value) {
    const a = anchorOf(b)
    if (a) { g.beginPath(); g.moveTo(b.x * W, b.y * H); g.lineTo(a.x * W, a.y * H); g.stroke(); g.beginPath(); g.arc(a.x * W, a.y * H, 2.5, 0, 7); g.fillStyle = '#333'; g.fill() }
    g.beginPath(); g.arc(b.x * W, b.y * H, 14, 0, 7); g.fillStyle = '#fff'; g.fill(); g.stroke()
    g.fillStyle = '#111'; g.fillText(String(no.value[b.part_id] ?? '?'), b.x * W, b.y * H + 1)
  }
  return new Promise((ok) => c.toBlob(ok, 'image/png'))
}
async function save() {
  busy.value = true; error.value = ''; done.value = ''
  try {
    const cam = three ? { position: three.camera.position.toArray(), target: three.controls.target.toArray(), up: three.camera.up.toArray() } : undefined
    const data = { kind: kind.value, layout: { camera: cam, factor: factor.value, moves: moves.value, drawn: drawn.value },
      balloons: balloons.value.map((b) => ({ ...b, ...(kind.value === 'model' && anchors.value[b.part_id] ? { ax: anchors.value[b.part_id].x, ay: anchors.value[b.part_id].y } : {}) })) }
    const form = new FormData()
    form.append('data', JSON.stringify(data))
    form.append('snapshot', await picture(), 'explode.png')
    if (imageFile.value) form.append('image', imageFile.value, imageFile.value.name)
    v.value = { ...(await apiForm(`/api/plm/explode/${bid()}`, form)) }
    imageFile.value = null
    done.value = t('Saved.')
  } catch (e) { error.value = e.message } finally { busy.value = false }
}

// ---- English names
async function nameEn(l, confirm) {
  try {
    const r = await api(`/api/plm/parts/${l.part_id}/name-en`, { method: 'PUT', body: { name_en: l.name_en, confirm } })
    l.name_en = r.name_en; l.name_en_state = r.name_en_state
  } catch (e) { error.value = e.message }
}
async function draftNames() {
  busy.value = true; error.value = ''; done.value = ''
  try {
    const r = await api(`/api/plm/explode/${bid()}/names`, { method: 'POST', body: {} })
    done.value = t('{n} English names drafted: read and confirm them.', { n: r.drafted })
    v.value = { ...v.value, lines: (await api(`/api/plm/explode/${bid()}`)).lines }
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
const NAME_ST = { none: 'gray', draft: 'amber', confirmed: 'green' }
const nameStl = (s) => ({ none: t('none'), draft: t('AI draft'), confirmed: t('confirmed') }[s] || s)
// switching between the 3D picture and a drawing: balloons of the other kind point at nothing there
watch(kind, (k) => {
  balloons.value = balloons.value.filter((b) => (k === 'image') === (b.ax != null && !(b.part_id in anchors.value)))
  if (k === 'model') nextTick(() => draw()); else teardown()
})
</script>

<template>
  <PageTop :crumbs="[{ label: t('Parts'), to: '/plm/parts' }, ...(v ? [{ label: v.part.code, to: `/plm/parts/${v.part.id}` }, { label: `BOM ${v.bom.revision}`, to: `/plm/boms/${v.bom.id}` }] : [])]">
    <template #title>{{ v ? t('Exploded view of {code}', { code: v.part.code }) : t('Exploded view') }}</template>
  </PageTop>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <template v-if="v">
    <p class="mb-3 text-sm text-ink-gray-6">{{ v.part.name }} · BOM {{ v.bom.revision }}
      <span v-if="v.page.from_revision"> · {{ t('Started from the layout of revision {r}', { r: v.page.from_revision }) }}</span>
      <span v-if="v.page.saved_at"> · {{ t('Saved by {who}', { who: v.page.saved_by }) }}</span></p>
    <div class="grid gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section data-help="plm-explode-picture" class="wq-panel p-4">
        <div class="mb-3 flex flex-wrap items-center gap-2 text-sm">
          <select v-model="kind" class="wq-select w-40" :disabled="!v.can_edit"><option value="model" :disabled="!v.scene.items.length">{{ t('From the 3D models') }}</option><option value="image">{{ t('From a drawing') }}</option></select>
          <template v-if="kind === 'model'">
            <label class="flex items-center gap-2">{{ t('Pull apart') }} <input v-model.number="factor" type="range" min="0" max="3" step="0.05" class="w-32"></label>
            <span v-if="selected" class="ms-2">{{ t('Move no. {n}', { n: no[selected] }) }}:
              <button v-for="[ax, lab] in [[0, 'X'], [1, 'Y'], [2, 'Z']]" :key="lab" class="ms-1 wq-link" @click="nudge(ax, -1)">−{{ lab }}</button>
              <button v-for="[ax, lab] in [[0, 'X'], [1, 'Y'], [2, 'Z']]" :key="'p' + lab" class="ms-1 wq-link" @click="nudge(ax, 1)">+{{ lab }}</button></span>
          </template>
          <label v-else-if="v.can_edit" class="text-sm">{{ t('Drawing (PNG or JPG)') }} <input type="file" accept="image/png,image/jpeg" class="text-sm" @change="pickImage"></label>
        </div>
        <div ref="stage" class="relative w-full select-none overflow-hidden rounded-4 border border-outline-gray-2" :style="{ aspectRatio: `${W} / ${H}` }" @pointermove="move" @pointerup="up">
          <div v-show="kind === 'model'" class="canvas absolute inset-0" />
          <img v-if="kind === 'image' && imageUrl" :src="imageUrl" class="absolute inset-0 h-full w-full object-contain" alt="" @click="clickImage">
          <p v-if="kind === 'image' && !imageUrl" class="absolute inset-0 flex items-center justify-center text-ink-gray-5">{{ t('Upload the drawing of this assembly.') }}</p>
          <svg class="overlay pointer-events-none absolute inset-0 h-full w-full" :viewBox="`0 0 ${W} ${H}`">
            <g v-for="b in balloons" :key="b.part_id">
              <line v-if="anchorOf(b)" :x1="b.x * W" :y1="b.y * H" :x2="anchorOf(b).x * W" :y2="anchorOf(b).y * H" stroke="#333" stroke-width="1" />
              <circle :cx="b.x * W" :cy="b.y * H" r="14" fill="#fff" :stroke="selected === b.part_id ? '#d97706' : '#333'" stroke-width="1.5" class="pointer-events-auto cursor-move" @pointerdown="down(b, $event)" />
              <text :x="b.x * W" :y="b.y * H + 5" text-anchor="middle" font-size="15" font-weight="700" class="pointer-events-none">{{ no[b.part_id] }}</text>
            </g>
          </svg>
        </div>
        <p class="mt-2 text-sm text-ink-gray-5">{{ status || (kind === 'model' ? t('Drag to turn, scroll to zoom; click a part to move it; drag a balloon to place it.') : t('Choose a line in the table, then click the part on the drawing to put its balloon.')) }}</p>
        <div v-if="v.can_edit" class="mt-3 flex flex-wrap gap-2">
          <Button v-if="kind === 'model'" :label="t('Fit to the picture')" @click="fit" />
          <Button v-if="kind === 'model'" :label="t('Place balloons')" @click="autoBalloons" />
          <Button :label="t('Clear balloons')" @click="balloons = []" />
          <Button variant="solid" :label="t('Save')" :loading="busy" @click="save" />
          <a v-if="v.page.snapshot_sha" :href="`/api/plm/explode/${v.bom.id}/snapshot?${v.page.snapshot_sha.slice(0, 8)}`" target="_blank" class="wq-link self-center text-sm">{{ t('Picture as saved') }}</a>
        </div>
        <p v-if="!v.scene.items.length" class="mt-2 text-sm text-ink-gray-6">{{ t('No part here has a 3D model and a place in the assembly: use a drawing.') }}</p>
      </section>

      <section data-help="plm-explode-table" class="wq-panel p-4">
        <div class="mb-2 flex items-center justify-between gap-2">
          <h2 class="wq-h2 mb-0">{{ t('Parts on this page') }}</h2>
          <Button v-if="v.can_edit" size="sm" :label="t('AI drafts English names')" :loading="busy" @click="draftNames" />
        </div>
        <table class="wq-table text-sm"><thead><tr><th>{{ t('No.') }}</th><th>{{ t('plm::Code') }}</th><th>{{ t('Name') }}</th><th>{{ t('Qty') }}</th><th>{{ t('Drawn') }}</th></tr></thead>
          <tbody><tr v-for="l in lines" :key="l.part_id" :class="selected === l.part_id ? 'bg-surface-amber-1' : ''" @click.capture="selected = l.part_id">
            <td>{{ l.no }}<button v-if="balloons.some((b) => b.part_id === l.part_id) && v.can_edit" class="ms-1 text-ink-gray-5" :title="t('Remove the balloon')" @click.stop="removeBalloon(l.part_id)">×</button></td>
            <td class="whitespace-nowrap">{{ l.code }}</td>
            <td>{{ l.name }}
              <div class="mt-1 flex items-center gap-1">
                <input v-model="l.name_en" class="wq-input h-7 min-w-0 flex-1 text-sm" :placeholder="t('English name')" :disabled="!v.can_edit" @change="nameEn(l, false)" @click.stop>
                <Badge :theme="NAME_ST[l.name_en_state]" :label="nameStl(l.name_en_state)" />
                <button v-if="v.can_edit && l.name_en && l.name_en_state !== 'confirmed'" class="wq-link text-xs" @click.stop="nameEn(l, true)">{{ t('Confirm') }}</button>
              </div>
              <RouterLink v-if="l.page" :to="`/plm/boms/${l.page}/explode`" class="wq-link text-xs" @click.stop>{{ t('Its own page') }}</RouterLink></td>
            <td>{{ l.qty }} {{ l.uom }}</td>
            <td><input type="checkbox" :checked="isDrawn(l)" :disabled="!v.can_edit || kind !== 'model' || !groups.has(l.part_id)" @click.stop @change="drawn = { ...drawn, [l.part_id]: $event.target.checked }"></td>
          </tr></tbody></table>
      </section>
    </div>
  </template>
</template>
