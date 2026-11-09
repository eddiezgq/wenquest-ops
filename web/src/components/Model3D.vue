<script setup>
// A 3D view of STEP models in the browser (round 124, 27a): each item is one placed use of a part, {url, m, code,
// name} with m the 4x4 matrix (row by row) from the server. The STEP files are read here with OpenCascade compiled
// to WebAssembly (occt-import-js), loaded only when a 3D view opens; the server does no CAD work.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { t } from '../i18n'
import { geometries, lights, shade } from '../plm3d/step3d'

const props = defineProps({ items: { type: Array, default: () => [] }, height: { type: Number, default: 420 } })
const box = ref(null)
const status = ref('')
const picked = ref(null)
let stop = () => {}

async function draw() {
  stop()
  if (!box.value || !props.items.length) return
  status.value = t('Reading the models…')
  const THREE = await import('three')
  const { OrbitControls } = await import('three/examples/jsm/controls/OrbitControls.js')
  const geoms = new Map()
  let bad = 0
  for (const url of new Set(props.items.map((x) => x.url))) {
    try { geoms.set(url, await geometries(THREE, url)) } catch (e) { if (e.message === 'occt') { status.value = t('The 3D reader did not load.'); return } bad += 1 }
  }
  const scene = new THREE.Scene()
  scene.background = new THREE.Color(getComputedStyle(document.body).getPropertyValue('--wq-3d-bg').trim() || '#f4f5f7')
  lights(THREE, scene)
  const all = new THREE.Group()
  const mats = new Map()
  for (const it of props.items) {
    const gs = geoms.get(it.url)
    if (!gs) continue
    if (!mats.has(it.code)) mats.set(it.code, new THREE.MeshStandardMaterial({ color: shade(it.code), metalness: 0.35, roughness: 0.55 }))
    const g = new THREE.Group()
    for (const geo of gs) { const mesh = new THREE.Mesh(geo, mats.get(it.code)); mesh.userData = it; g.add(mesh) }
    g.matrixAutoUpdate = false
    g.matrix.set(...it.m)
    all.add(g)
  }
  all.rotation.x = -Math.PI / 2                     // CAD's z up as the screen's up
  scene.add(all)
  all.updateMatrixWorld(true)
  const w = box.value.clientWidth, h = props.height
  const camera = new THREE.PerspectiveCamera(35, w / h, 0.1, 1e6)
  const bb = new THREE.Box3().setFromObject(all)
  const size = bb.getSize(new THREE.Vector3()).length() || 100
  const mid = bb.getCenter(new THREE.Vector3())
  camera.position.copy(mid).add(new THREE.Vector3(size * 0.8, size * 0.55, size * 1.0))
  camera.near = size / 1000; camera.far = size * 20; camera.updateProjectionMatrix()
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); renderer.setSize(w, h)
  box.value.innerHTML = ''; box.value.appendChild(renderer.domElement)
  const controls = new OrbitControls(camera, renderer.domElement); controls.target.copy(mid); controls.update()
  const ray = new THREE.Raycaster(), at = new THREE.Vector2()
  const onClick = (e) => {
    const r = renderer.domElement.getBoundingClientRect()
    at.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
    ray.setFromCamera(at, camera)
    const hit = ray.intersectObject(all, true)[0]
    picked.value = hit ? hit.object.userData : null
  }
  renderer.domElement.addEventListener('click', onClick)
  let frame = 0
  const loop = () => { controls.update(); renderer.render(scene, camera); frame = requestAnimationFrame(loop) }
  loop()
  status.value = bad ? t('{n} model files could not be read.', { n: bad }) : ''
  stop = () => {
    cancelAnimationFrame(frame); renderer.domElement.removeEventListener('click', onClick)
    controls.dispose(); renderer.dispose(); mats.forEach((m) => m.dispose())
    stop = () => {}
  }
}

onMounted(draw)
watch(() => props.items, draw)
onBeforeUnmount(() => stop())
</script>

<template>
  <div data-help="plm-3d">
    <div ref="box" class="w-full overflow-hidden rounded-4 border border-outline-gray-2" :style="{ height: `${height}px` }" />
    <p class="mt-2 text-sm text-ink-gray-5">
      <span v-if="status">{{ status }}</span>
      <span v-else-if="picked"><b>{{ picked.code }}</b> {{ picked.name }}</span>
      <span v-else>{{ t('Drag to turn, scroll to zoom, click a part to name it.') }}</span>
    </p>
  </div>
</template>
