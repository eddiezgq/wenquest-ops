// Reading STEP files in the browser (round 124): OpenCascade compiled to WebAssembly (occt-import-js), loaded on
// first use; the geometries of each file are kept for the page's life so a part used ten times is read once.
import occtJs from 'occt-import-js/dist/occt-import-js.js?url'
import occtWasm from 'occt-import-js/dist/occt-import-js.wasm?url'

let occtReady = null
export function occt() {
  if (!occtReady) {
    occtReady = new Promise((resolve, reject) => {
      const s = document.createElement('script')
      s.src = occtJs
      s.onload = () => window.occtimportjs({ locateFile: () => occtWasm }).then(resolve, reject)
      s.onerror = () => { occtReady = null; reject(new Error('occt')) }
      document.head.appendChild(s)
    })
  }
  return occtReady
}

const cache = new Map()       // url -> Promise<[BufferGeometry]>
export async function geometries(THREE, url) {
  if (!cache.has(url)) {
    cache.set(url, (async () => {
      const lib = await occt()
      const buf = new Uint8Array(await (await fetch(url, { credentials: 'same-origin' })).arrayBuffer())
      const res = lib.ReadStepFile(buf, null)
      if (!res.success) throw new Error('step')
      return res.meshes.map((m) => {
        const g = new THREE.BufferGeometry()
        g.setAttribute('position', new THREE.Float32BufferAttribute(m.attributes.position.array, 3))
        if (m.attributes.normal) g.setAttribute('normal', new THREE.Float32BufferAttribute(m.attributes.normal.array, 3))
        g.setIndex(Array.from(m.index.array))
        if (!m.attributes.normal) g.computeVertexNormals()
        return g
      })
    })().catch((e) => { cache.delete(url); throw e }))
  }
  return cache.get(url)
}

const shades = ['#8fa3b8', '#b8a48f', '#9fb88f', '#b88fa9', '#8fb5b8', '#b8b08f', '#a38fb8']
export function shade(code) { let h = 0; for (const ch of code || '') h = (h * 31 + ch.charCodeAt(0)) >>> 0; return shades[h % shades.length] }

export function lights(THREE, scene) {
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f99, 1.6))
  const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(1, 2, 3); scene.add(sun)
}

export const fileUrl = (x) => `/api/plm/parts/${x.part_id}/files/${x.file.id}`
