// Реалістичніша 3D-людина для роликів: пропорції 1:7,5, об'ємна голова, борода, окуляри, одяг із фактурою, руки з пальцями.
// Інтерфейс сумісний із першою версією: fig.set(pose,x,y,z), fig.root, fig.J, fig.phone(on), fig.tint(c).
import * as THREE from 'three';
import { RoundedBoxGeometry } from './node_modules/three/examples/jsm/geometries/RoundedBoxGeometry.js';

export const ENV = { t: 0, mouth: 0, envI: 0.55 };
const lerp = (a, b, u) => a + (b - a) * u;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const sstep = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

// ---------------------------------------------------------------- текстури
function canvasTex(w, h, draw, rep = [1, 1], srgb = false) {
  const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rep[0], rep[1]);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}
function rnd(seed) { let s = seed >>> 0; return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296; }

const knitBump = canvasTex(128, 128, (g, w, h) => {
  g.fillStyle = '#808080'; g.fillRect(0, 0, w, h);
  for (let x = 0; x < w; x += 8) { const gr = g.createLinearGradient(x, 0, x + 8, 0); gr.addColorStop(0, '#303030'); gr.addColorStop(0.5, '#f0f0f0'); gr.addColorStop(1, '#303030'); g.fillStyle = gr; g.fillRect(x, 0, 8, h); }
  for (let y = 0; y < h; y += 8) { g.fillStyle = 'rgba(0,0,0,.22)'; g.fillRect(0, y, w, 2); }
}, [9, 5]);
const cottonBump = canvasTex(128, 128, (g, w, h) => {
  const r = rnd(7); g.fillStyle = '#808080'; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 2600; i++) { const v = 90 + r() * 90; g.fillStyle = `rgb(${v},${v},${v})`; g.fillRect(r() * w, r() * h, 2, 2); }
}, [14, 14]);
const irisTex = canvasTex(128, 128, (g, w, h) => {
  g.fillStyle = '#f2eee8'; g.fillRect(0, 0, w, h);
  const gr = g.createRadialGradient(64, 64, 6, 64, 64, 60); gr.addColorStop(0, '#0b0907'); gr.addColorStop(0.28, '#0b0907'); gr.addColorStop(0.32, '#6b4a2a'); gr.addColorStop(0.7, '#8a6238'); gr.addColorStop(0.92, '#3b2a1a'); gr.addColorStop(1, '#241a10');
  g.fillStyle = gr; g.beginPath(); g.arc(64, 64, 60, 0, Math.PI * 2); g.fill();
}, [1, 1], true);
irisTex.wrapS = irisTex.wrapT = THREE.ClampToEdgeWrapping;

// ---------------------------------------------------------------- матеріали
const mats = [];
function MM(o, phys = false) { const m = phys ? new THREE.MeshPhysicalMaterial(o) : new THREE.MeshStandardMaterial(o); m.envMapIntensity = ENV.envI; mats.push(m); return m; }
function makeMats() {
  return {
    skinV: MM({ color: 0xffffff, roughness: 0.5, vertexColors: true, sheen: 0.6, sheenRoughness: 0.45, sheenColor: new THREE.Color(0xff8f7a), clearcoat: 0.06, clearcoatRoughness: 0.5 }, true),
    skin: MM({ color: 0xe1b49a, roughness: 0.52, sheen: 0.6, sheenRoughness: 0.45, sheenColor: new THREE.Color(0xff8f7a) }, true),
    cardi: MM({ color: 0xc9a47a, roughness: 0.96, bumpMap: knitBump, bumpScale: 1.6, sheen: 0.5, sheenRoughness: 0.9, sheenColor: new THREE.Color(0xf0dcc0), side: THREE.DoubleSide }, true),
    tee: MM({ color: 0xf4f3ef, roughness: 0.9, bumpMap: cottonBump, bumpScale: 0.6 }),
    pants: MM({ color: 0xe0dbd0, roughness: 0.88, bumpMap: cottonBump, bumpScale: 0.8 }),
    shoe: MM({ color: 0xf5f4f1, roughness: 0.5 }),
    sole: MM({ color: 0xdedad0, roughness: 0.7 }),
    shoeAcc: MM({ color: 0x8c8f96, roughness: 0.6 }),
    lip: MM({ color: 0xc08f80, roughness: 0.5 }),
    dark: MM({ color: 0x1a0f0c, roughness: 0.9 }),
    brow: MM({ color: 0x40362f, roughness: 0.9 }),
    frame: MM({ color: 0x2b211d, roughness: 0.28, metalness: 0.15 }),
    lens: MM({ color: 0xcfe2ff, roughness: 0.04, transparent: true, opacity: 0.11, depthWrite: false }),
    sclera: MM({ color: 0xf2eee8, roughness: 0.22 }),
    iris: MM({ map: irisTex, roughness: 0.2 }),
    lid: MM({ color: 0xdcae94, roughness: 0.55 }),
    steel: MM({ color: 0xc8ccd2, roughness: 0.25, metalness: 0.85 }),
    strap: MM({ color: 0x2a2a2e, roughness: 0.6 }),
    beard: null,
  };
}

// ---------------------------------------------------------------- допоміжна геометрія
function profileGeo(pts, seg = 28, phiStart = 0, phiLen = Math.PI * 2, n = 22) {
  const curve = new THREE.CatmullRomCurve3(pts.map(([r, y]) => new THREE.Vector3(r, y, 0)), false, 'catmullrom', 0.5);
  const sp = curve.getPoints(n).map(v => new THREE.Vector2(Math.max(0.0005, v.x), v.y));
  return new THREE.LatheGeometry(sp, seg, phiStart, phiLen);
}
// тулуб-оболонка з вирізом спереду (кардиган), gap(y) — півширина вирізу, рад
function openShell(pts, kz, gap, seg = 40, n = 26) {
  const curve = new THREE.CatmullRomCurve3(pts.map(([r, y]) => new THREE.Vector3(r, y, 0)), false, 'catmullrom', 0.5);
  const sp = curve.getPoints(n);
  const pos = [], idx = [], edge = [[], []];
  sp.forEach((p, j) => {
    const g = gap(p.y);
    for (let i = 0; i <= seg; i++) {
      const phi = g + (i / seg) * (Math.PI * 2 - 2 * g);
      pos.push(p.x * Math.sin(phi), p.y, kz * p.x * Math.cos(phi));
    }
    edge[0].push(new THREE.Vector3(p.x * Math.sin(g), p.y, kz * p.x * Math.cos(g)));
    edge[1].push(new THREE.Vector3(-p.x * Math.sin(g), p.y, kz * p.x * Math.cos(g)));
  });
  for (let j = 0; j < sp.length - 1; j++) for (let i = 0; i < seg; i++) {
    const a = j * (seg + 1) + i, b = a + 1, c = a + seg + 1, d = c + 1;
    idx.push(a, c, b, b, c, d);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  const uv = []; sp.forEach((p, j) => { for (let i = 0; i <= seg; i++) uv.push(i / seg, j / (sp.length - 1)); });
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx); geo.computeVertexNormals();
  return { geo, edge };
}
function capsuleLimb(len, r0, r1, mat, bulge = 0.0) { // конічний відрізок, що росте вниз від y=0
  const pts = [[0.001, 0.004], [r0 * 0.7, 0.002], [r0, -0.01]];
  const k = 6;
  for (let i = 1; i < k; i++) { const u = i / k; pts.push([lerp(r0, r1, u) + bulge * Math.sin(u * Math.PI), -0.01 - u * (len - 0.02)]); }
  pts.push([r1, -len + 0.01], [r1 * 0.75, -len + 0.003], [0.001, -len]);
  const m = new THREE.Mesh(profileGeo(pts, 20, 0, Math.PI * 2, 18), mat); return m;
}

// ---------------------------------------------------------------- голова
function buildHead(M, withFace) {
  const SX = 0.0775, SY = 0.115, SZ = 0.099;
  const geo = withFace ? new THREE.SphereGeometry(1, 72, 52) : new THREE.SphereGeometry(1, 40, 28);
  const pos = geo.attributes.position, n = pos.count;
  const eyesAt = [[-0.034, 0.008], [0.034, 0.008]];
  const col = new Float32Array(n * 3), mask = new Float32Array(n);
  const base = new THREE.Color(0xe6bba2);
  for (let i = 0; i < n; i++) {
    const a = pos.getX(i), b = pos.getY(i), c = pos.getZ(i);
    let x = a * SX, y = b * SY, z = c * SZ;
    const t = Math.max(0, -b);
    x *= 1 - 0.13 * Math.pow(t, 1.5);
    if (c > 0) z *= 1 + 0.05 * Math.pow(t, 1.5);
    if (b < -0.55) y *= 0.97;
    if (b > 0.35 && c > 0) z *= 1 - 0.07 * (b - 0.35) / 0.65;
    x *= 1 - 0.03 * Math.max(0, b - 0.5);
    x *= 1 + 0.04 * Math.exp(-Math.pow((b + 0.18) / 0.2, 2)) * Math.max(0, c);
    z += 0.0055 * Math.exp(-Math.pow((y - 0.04) / 0.012, 2)) * sstep(0.2, 0.7, c) * sstep(0.06, 0.02, Math.abs(x)) * 0 + 0.0055 * Math.exp(-Math.pow((y - 0.040) / 0.011, 2)) * sstep(0.3, 0.8, c) * sstep(0.075, 0.03, Math.abs(x));
    let ao = 1;
    if (withFace) for (const [ex, ey] of eyesAt) {
      const d = Math.hypot(x - ex, y - ey);
      if (c > 0.3 && d < 0.021) { const k = 1 - (d / 0.021) ** 2; z -= 0.0022 * k; ao *= 1 - 0.22 * k; }
    }
    pos.setXYZ(i, x, y, z);
    ao *= 1 - 0.18 * sstep(-0.55, -1, b);
    // колір шкіри + рум'янець
    const cheek = Math.exp(-(Math.pow((Math.abs(x) - 0.042) / 0.022, 2) + Math.pow((y + 0.015) / 0.03, 2))) * Math.max(0, c);
    let m = 0;
    if (withFace) {
      const upper = lerp(-0.026, -0.004, sstep(0.02, 0.07, Math.abs(x)));
      m = sstep(upper + 0.012, upper - 0.012, y) * sstep(-0.05, -0.012, z);
      const side = sstep(0.058, 0.068, Math.abs(x)) * sstep(0.034, 0.012, y) * sstep(-0.034, -0.01, z) * sstep(0.07, 0.02, z - 0.0) ;
      m = Math.max(m, side * 0.9);
      m *= sstep(-0.07, -0.02, z + (y < -0.08 ? 0.03 : 0));
      const lx = Math.abs(x) / 0.027, ly = (y + 0.064) / 0.0125;
      const lipD = Math.hypot(lx, ly); m *= sstep(0.95, 1.5, lipD) * (z > 0.03 ? 1 : 1);
      m *= 0.92;
    }
    mask[i] = m;
    const r = base.r * ao * (1 + 0.1 * cheek) , g2 = base.g * ao * (1 - 0.05 * cheek), bl = base.b * ao * (1 - 0.06 * cheek);
    const dm = m * 0.55;
    col[i * 3] = r * (1 - 0.40 * dm); col[i * 3 + 1] = g2 * (1 - 0.34 * dm); col[i * 3 + 2] = bl * (1 - 0.26 * dm);
  }
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  geo.computeVertexNormals();
  const head = new THREE.Mesh(geo, M.skinV);
  const group = new THREE.Group(); group.add(head);
  // поверхня: z за (x,y)
  const P = geo.attributes.position;
  const surf = (x, y) => { let zb = -9; for (let i = 0; i < P.count; i++) { const dx = P.getX(i) - x, dy = P.getY(i) - y; if (dx * dx + dy * dy < 2.5e-5 && P.getZ(i) > zb) zb = P.getZ(i); } return zb; };
  const out = { group, head, surf, jaw: null, mouth: null, lids: [], pupils: [] };
  if (!withFace) return out;
  // ---- борода: оболонка з відсіканням за маскою
  const nrm = geo.attributes.normal, idx = geo.index.array;
  const keep = [];
  for (let i = 0; i < idx.length; i += 3) if (mask[idx[i]] > 0.03 || mask[idx[i + 1]] > 0.03 || mask[idx[i + 2]] > 0.03) keep.push(idx[i], idx[i + 1], idx[i + 2]);
  const bgeo = new THREE.BufferGeometry();
  const bp = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { bp[i * 3] = P.getX(i) + nrm.getX(i) * 0.0032; bp[i * 3 + 1] = P.getY(i) + nrm.getY(i) * 0.0032; bp[i * 3 + 2] = P.getZ(i) + nrm.getZ(i) * 0.0032; }
  bgeo.setAttribute('position', new THREE.BufferAttribute(bp, 3)); bgeo.setAttribute('normal', nrm.clone()); bgeo.setAttribute('aMask', new THREE.BufferAttribute(mask, 1));
  bgeo.setIndex(keep);
  const bm = MM({ color: 0x5a4a3f, roughness: 0.92 });
  bm.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nattribute float aMask; varying float vMask; varying vec3 vP;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvMask = aMask; vP = position;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying float vMask; varying vec3 vP;\nfloat h31(vec3 p){ return fract(sin(dot(p, vec3(127.1,311.7,74.7)))*43758.5453); }')
      .replace('#include <clipping_planes_fragment>', '#include <clipping_planes_fragment>\nvec3 cellP = floor(vP*1500.0); float hn = h31(cellP); if (hn > vMask*0.80) discard;')
      .replace('#include <color_fragment>', '#include <color_fragment>\ndiffuseColor.rgb *= 0.85 + 0.7*h31(cellP+3.7); diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.70,0.68,0.66), step(0.84, h31(cellP+9.1))*0.85);');
  };
  const beard = new THREE.Mesh(bgeo, bm); group.add(beard); out.beard = beard;
  // ---- ніс
  const zN = surf(0, -0.018);
  const nose = new THREE.Group(); nose.position.set(0, 0, zN - 0.002);
  const bridge = new THREE.Mesh(new THREE.CapsuleGeometry(0.0062, 0.036, 6, 12), M.skin); bridge.position.set(0, 0.006, 0.006); bridge.rotation.x = -0.2; bridge.scale.set(1, 1, 1.05); nose.add(bridge);
  const tip = new THREE.Mesh(new THREE.SphereGeometry(0.0108, 18, 14), M.skin); tip.position.set(0, -0.0225, 0.0155); tip.scale.set(1.0, 0.88, 1.0); nose.add(tip);
  for (const s of [-1, 1]) { const al = new THREE.Mesh(new THREE.SphereGeometry(0.0082, 14, 12), M.skin); al.position.set(s * 0.0105, -0.0265, 0.0075); al.scale.set(0.9, 0.95, 0.95); nose.add(al);
    const nh = new THREE.Mesh(new THREE.SphereGeometry(0.0034, 8, 6), M.dark); nh.position.set(s * 0.0062, -0.0318, 0.0128); nh.scale.set(0.8, 0.5, 1); nose.add(nh); }
  group.add(nose);
  // ---- губи й рот
  const zL = surf(0, -0.064);
  const mouth = new THREE.Group(); mouth.position.set(0, -0.064, zL - 0.004); group.add(mouth);
  const cav = new THREE.Mesh(new THREE.CircleGeometry(0.0125, 20), M.dark); cav.position.z = 0.0066; cav.scale.set(1, 0.05, 1); mouth.add(cav);
  const up = new THREE.Mesh(new THREE.CapsuleGeometry(0.0046, 0.027, 4, 12), M.lip); up.rotation.z = Math.PI / 2; up.position.set(0, 0.0035, 0.0058); up.scale.set(1, 0.85, 0.9); mouth.add(up);
  const lo = new THREE.Mesh(new THREE.CapsuleGeometry(0.0052, 0.024, 4, 12), M.lip); lo.rotation.z = Math.PI / 2; lo.position.set(0, -0.0052, 0.0054); lo.scale.set(1, 0.95, 0.9); mouth.add(lo);
  out.mouth = { group: mouth, cav, up, lo };
  // ---- очі (плоскі «міндалі» на поверхні: на відстані читаються краще за об'ємні кульки)
  for (const s of [-1, 1]) {
    const ex = s * 0.034, ey = 0.008; const zE = surf(ex, ey);
    const eye = new THREE.Group(); eye.position.set(ex, ey, zE + 0.0006); group.add(eye);
    const scl = new THREE.Mesh(new THREE.CircleGeometry(0.0108, 24), M.sclera); scl.scale.set(1.2, 0.46, 1); eye.add(scl);
    const iris = new THREE.Mesh(new THREE.CircleGeometry(0.0052, 24), M.iris); iris.position.set(0, -0.0004, 0.0004); eye.add(iris); out.pupils.push(iris);
    const hi = new THREE.Mesh(new THREE.CircleGeometry(0.0009, 8), new THREE.MeshBasicMaterial({ color: 0xffffff })); hi.position.set(0.0016, 0.0016, 0.0009); eye.add(hi);
    const upLid = new THREE.Mesh(new THREE.TorusGeometry(0.0104, 0.0007, 6, 20, Math.PI), M.dark); upLid.position.set(0, -0.0006, 0.0008); upLid.scale.set(1.2, 0.5, 1); eye.add(upLid);
    const lid = new THREE.Mesh(new THREE.CircleGeometry(0.0132, 20), M.lid); lid.position.set(0, 0.0, 0.0012); lid.scale.set(1.2, 0.001, 1); lid.visible = false; eye.add(lid); out.lids.push(lid);
    const bz = surf(ex, 0.039) + 0.0012;
    const curve = new THREE.CatmullRomCurve3([new THREE.Vector3(s * 0.011, 0.033, bz), new THREE.Vector3(s * 0.028, 0.0405, bz + 0.002), new THREE.Vector3(s * 0.046, 0.0415, bz - 0.001), new THREE.Vector3(s * 0.060, 0.0345, bz - 0.009)]);
    const brow = new THREE.Mesh(new THREE.TubeGeometry(curve, 16, 0.0034, 6, false), M.brow); brow.scale.z = 0.7; group.add(brow);
    const ear = new THREE.Mesh(new THREE.SphereGeometry(0.029, 16, 12), M.skin); ear.position.set(s * 0.0775, -0.006, -0.004); ear.scale.set(0.34, 1, 0.68); group.add(ear);
    const ei = new THREE.Mesh(new THREE.SphereGeometry(0.018, 12, 10), M.lid); ei.position.set(s * 0.0795, -0.006, -0.002); ei.scale.set(0.2, 0.9, 0.55); group.add(ei);
  }
  // ---- окуляри
  const zG = surf(0, 0.008) + 0.0135;
  const rr = (w, h, r) => { const s = new THREE.Shape(); const x = -w / 2, y = -h / 2; s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r); s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h); s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r); s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y); return s; };
  const frameShape = rr(0.056, 0.040, 0.014); const pts = frameShape.getPoints(8).map(p => new THREE.Vector3(p.x, p.y, 0));
  const loop = new THREE.CatmullRomCurve3(pts, true, 'catmullrom', 0.1);
  for (const s of [-1, 1]) {
    const fr = new THREE.Mesh(new THREE.TubeGeometry(loop, 48, 0.0023, 8, true), M.frame); fr.position.set(s * 0.0345, 0.008, zG); group.add(fr);
    const ln = new THREE.Mesh(new THREE.ShapeGeometry(frameShape, 6), M.lens); ln.position.set(s * 0.0345, 0.008, zG - 0.0002); ln.renderOrder = 5; group.add(ln);
    const tmp = new THREE.CatmullRomCurve3([new THREE.Vector3(s * 0.0645, 0.014, zG - 0.001), new THREE.Vector3(s * 0.0715, 0.013, zG - 0.03), new THREE.Vector3(s * 0.0805, 0.010, zG - 0.082), new THREE.Vector3(s * 0.0835, 0.002, zG - 0.108)]);
    const arm = new THREE.Mesh(new THREE.TubeGeometry(tmp, 16, 0.0019, 6, false), M.frame); group.add(arm);
  }
  const br = new THREE.CatmullRomCurve3([new THREE.Vector3(-0.0045, 0.0185, zG + 0.0004), new THREE.Vector3(0, 0.0215, zG + 0.0016), new THREE.Vector3(0.0045, 0.0185, zG + 0.0004)]);
  group.add(new THREE.Mesh(new THREE.TubeGeometry(br, 8, 0.0021, 6, false), M.frame));
  return out;
}

// ---------------------------------------------------------------- руки
const HAND_STATES = [[0.35, 0.30, 0.38, 0.46, 0.55], [0.05, 0.04, 0.05, 0.06, 0.08], [0.55, 0.0, 1.25, 1.3, 1.3], [0.95, 1.0, 1.0, 1.0, 1.0]];
function handCurls(h) { h = clamp(h, 0, 3); const i = Math.floor(h), f = h - i; const a = HAND_STATES[i], b = HAND_STATES[Math.min(3, i + 1)]; return a.map((v, k) => lerp(v, b[k], f)); }
function buildHand(side, skin, human) {
  const g = new THREE.Group();
  const palm = new THREE.Mesh(new RoundedBoxGeometry(0.03, 0.092, 0.082, 3, 0.011), skin); palm.position.set(0, -0.044, 0); g.add(palm);
  const fingers = [];
  const L = [[0.040, 0.026, 0.022], [0.044, 0.028, 0.023], [0.041, 0.027, 0.022], [0.032, 0.021, 0.019]]; // вказівний, середній, безіменний, мізинець
  const zs = [0.030, 0.011, -0.009, -0.027]; const rs = [0.0086, 0.0088, 0.0082, 0.0072];
  const rad = human ? 1 : 1.0;
  for (let f = 0; f < 4; f++) {
    const j1 = new THREE.Group(); j1.position.set(0, -0.092, zs[f]); g.add(j1);
    const s1 = new THREE.Mesh(new THREE.CapsuleGeometry(rs[f] * rad, L[f][0] - 2 * rs[f], 4, 8), skin); s1.position.y = -L[f][0] / 2; j1.add(s1);
    const j2 = new THREE.Group(); j2.position.y = -L[f][0]; j1.add(j2);
    const s2 = new THREE.Mesh(new THREE.CapsuleGeometry(rs[f] * 0.95, L[f][1] - 2 * rs[f] * 0.95, 4, 8), skin); s2.position.y = -L[f][1] / 2; j2.add(s2);
    const j3 = new THREE.Group(); j3.position.y = -L[f][1]; j2.add(j3);
    const s3 = new THREE.Mesh(new THREE.CapsuleGeometry(rs[f] * 0.88, Math.max(0.001, L[f][2] - 2 * rs[f] * 0.88), 4, 8), skin); s3.position.y = -L[f][2] / 2; j3.add(s3);
    fingers.push([j1, j2, j3]);
  }
  const t1 = new THREE.Group(); t1.position.set(0, -0.026, 0.038); t1.rotation.x = -0.75; g.add(t1);
  const ts1 = new THREE.Mesh(new THREE.CapsuleGeometry(0.0098, 0.02, 4, 8), skin); ts1.position.y = -0.016; t1.add(ts1);
  const t2 = new THREE.Group(); t2.position.y = -0.032; t1.add(t2);
  const ts2 = new THREE.Mesh(new THREE.CapsuleGeometry(0.0088, 0.02, 4, 8), skin); ts2.position.y = -0.014; t2.add(ts2);
  const s = -side;
  const api = { group: g, set(h) { const c = handCurls(h);
    for (let f = 0; f < 4; f++) { const k = c[f + 1]; fingers[f][0].rotation.z = s * k * 0.95; fingers[f][1].rotation.z = s * k * 1.15; fingers[f][2].rotation.z = s * k * 0.7; }
    t1.rotation.z = s * c[0] * 0.55; t2.rotation.z = s * c[0] * 0.8; } };
  api.set(0);
  return api;
}

// ---------------------------------------------------------------- пози
export const POSE0 = { hipY: 0.97, lean: 0, hx: 0, hy: 0, hz: 0, ry: 0,
  aAx: 0.04, aAz: 0.10, aAe: 0.14, bAx: 0.04, bAz: 0.10, bAe: 0.14,
  aHx: 0, aKx: 0, bHx: 0, bKx: 0, aHd: 0, bHd: 0, talk: 1, eyes: 1 };
export const P = (o) => ({ ...POSE0, ...o });
export const POSES = {
  stand: P({}),
  shrug: P({ aAz: 0.62, aAe: 1.05, bAz: 0.62, bAe: 1.05, hz: 0.1, aHd: 1, bHd: 1 }),
  point: P({ aAx: 1.45, aAz: 0.05, aAe: 0.08, lean: 0.04, aHd: 2, bHd: 0 }),
  sit: P({ hipY: 0.5, aHx: 1.5, bHx: 1.5, aKx: 1.5, bKx: 1.5, aAx: 0.45, aAe: 1.0, bAx: 0.45, bAe: 1.0, lean: 0.05 }),
  sleep: P({ hipY: 0.5, aHx: 1.5, bHx: 1.5, aKx: 1.5, bKx: 1.5, aAx: 0.6, aAe: 1.4, bAx: 0.6, bAe: 1.4, lean: 0.38, hx: 0.62, talk: 0, eyes: 0 }),
  waitSit: P({ hipY: 0.5, aHx: 1.5, bHx: 1.5, aKx: 1.5, bKx: 1.5, aAx: 0.4, aAe: 1.5, bAx: 0.4, bAe: 1.5, lean: 0.25, hx: 0.45 }),
  hips: P({ aAz: 0.5, aAe: 1.45, bAz: 0.5, bAe: 1.45, aAx: -0.2, bAx: -0.2 }),
  phone: P({ aAx: 1.0, aAe: 1.5, bAx: 0.3, bAe: 0.2, hx: 0.3, aHd: 3 }),
  hold: P({ aAx: 1.1, aAe: 0.9, bAx: 1.1, bAe: 0.9, aAz: 0.1, bAz: 0.1, aHd: 3, bHd: 3 }),
  no: P({ aAz: 0.55, aAe: 0.3, bAz: 0.55, bAe: 0.3, aHd: 1, bHd: 1 }),
  up: P({ aAz: 2.7, aAe: 0.15, bAz: 2.7, bAe: 0.15, aAx: 0, bAx: 0, aHd: 1, bHd: 1 }),
  wave: P({ aAz: 2.4, aAe: 0.5, bAz: 0.15, bAe: 0.1, hz: 0.08, aHd: 1 }),
  look: P({ hy: 0.6 }),
  explain: P({ aAx: 0.8, aAz: 0.35, aAe: 1.0, bAx: 0.5, bAz: 0.2, bAe: 0.9, aHd: 1, bHd: 1 }),
};
export function mix(a, b, u) { const o = {}; for (const k in POSE0) o[k] = lerp(a[k] ?? POSE0[k], b[k] ?? POSE0[k], u); return o; }
export function walkPose(ph, base = POSES.stand, amp = 1) {
  const s = Math.sin(ph), c = Math.cos(ph);
  return { ...base, hipY: 0.97 - 0.014 * Math.abs(c), aHx: 0.5 * s * amp, bHx: -0.5 * s * amp,
    aKx: 0.62 * Math.max(0, -s) * amp, bKx: 0.62 * Math.max(0, s) * amp,
    aAx: 0.42 * -s * amp, bAx: 0.42 * s * amp, aAe: 0.3, bAe: 0.3, lean: 0.045 };
}

// ---------------------------------------------------------------- фігура
let uid = 0;
export function makeHuman(world, kind = 'vadim', tint = null, scale = 1) {
  const v = kind === 'vadim';
  const id = ++uid, seed = id * 1.713;
  const M = makeMats();
  const mc = tint ?? (kind === 'red' ? 0xb53a3f : kind === 'gray' ? 0x9b9ba3 : 0xf2f2f2);
  const man = MM({ color: mc, roughness: 0.55, metalness: 0.0, emissive: 0x141414 }, true);
  const root = new THREE.Group(); const J = {};
  const torso = new THREE.Group(); root.add(torso); J.torso = torso;
  const cloth = v ? M.cardi : man, under = v ? M.tee : man, legm = v ? M.pants : man, skin = v ? M.skin : man;
  let chestGroup = new THREE.Group(); torso.add(chestGroup);
  // ---- тулуб
  const prof = [[0.176, -0.10], [0.168, -0.04], [0.156, 0.07], [0.172, 0.20], [0.188, 0.32], [0.190, 0.41], [0.150, 0.485], [0.088, 0.525], [0.060, 0.545]];
  const KZ = 0.60;
  if (v) {
    const inner = new THREE.Mesh(profileGeo(prof.map(([r, y]) => [r * 0.965, y]), 36, 0, Math.PI * 2, 24), under); inner.scale.z = KZ; chestGroup.add(inner);
    const sh = openShell(prof, KZ, (y) => lerp(0.30, 0.62, sstep(-0.1, 0.45, y)));
    const shell = new THREE.Mesh(sh.geo, cloth); chestGroup.add(shell);
    for (const e of sh.edge) { const c = new THREE.CatmullRomCurve3(e.map(p => p.clone().multiplyScalar(1.0)).filter((p, i) => p.y < 0.50)); const band = new THREE.Mesh(new THREE.TubeGeometry(c, 30, 0.011, 8, false), cloth); band.scale.set(1, 1, 1); chestGroup.add(band); }
    const col = new THREE.TorusGeometry(0.074, 0.019, 10, 32, Math.PI * 2 * 0.78); col.rotateZ(Math.PI / 2 - (Math.PI * 2 + Math.PI * 2 * 0.78) / 2); col.rotateX(Math.PI / 2);
    const collar = new THREE.Mesh(col, cloth); collar.position.y = 0.52; collar.scale.set(1, 1, 1.0); chestGroup.add(collar);
    const crew = new THREE.Mesh(new THREE.TorusGeometry(0.058, 0.011, 8, 28), under); crew.rotation.x = Math.PI / 2; crew.position.y = 0.545; crew.scale.set(1, 1.0, 1); chestGroup.add(crew);
    for (let i = 0; i < 3; i++) { const b = new THREE.Mesh(new THREE.CylinderGeometry(0.011, 0.011, 0.005, 14), M.cardi); b.rotation.x = Math.PI / 2; b.position.set(0, 0.0 + i * 0.075, 0.106); b.visible = false; chestGroup.add(b); }
  } else {
    const body = new THREE.Mesh(profileGeo(prof.map(([r, y]) => [r * 0.9, y]), 28, 0, Math.PI * 2, 20), man); body.scale.z = 0.66; chestGroup.add(body);
  }
  // ---- таз і ноги
  const pel = new THREE.Mesh(profileGeo([[0.150, 0.075], [0.168, 0.0], [0.16, -0.08], [0.12, -0.14], [0.001, -0.15]], 28, 0, Math.PI * 2, 14), legm); pel.scale.z = 0.7; root.add(pel);
  function leg(side) {
    const hp = new THREE.Group(); hp.position.set(side * 0.092, -0.03, 0); root.add(hp);
    const th = capsuleLimb(0.46, v ? 0.088 : 0.07, v ? 0.062 : 0.052, legm, 0.004); hp.add(th);
    const kn = new THREE.Group(); kn.position.y = -0.46; hp.add(kn);
    const sh = capsuleLimb(0.43, v ? 0.060 : 0.05, v ? 0.044 : 0.04, legm, 0.0); kn.add(sh);
    if (v) { const cuff = new THREE.Mesh(new THREE.CylinderGeometry(0.047, 0.049, 0.02, 20), legm); cuff.position.y = -0.4; kn.add(cuff);
      const foot = new THREE.Group(); foot.position.set(0, -0.455, 0.045); kn.add(foot);
      const up = new THREE.Mesh(new RoundedBoxGeometry(0.095, 0.058, 0.27, 4, 0.026), M.shoe); up.position.set(0, 0.026, 0.015); foot.add(up);
      const so = new THREE.Mesh(new RoundedBoxGeometry(0.1, 0.022, 0.285, 3, 0.011), M.sole); so.position.set(0, -0.012, 0.016); foot.add(so);
      const st = new THREE.Mesh(new RoundedBoxGeometry(0.098, 0.014, 0.08, 2, 0.006), M.shoeAcc); st.position.set(0, 0.03, -0.045); foot.add(st);
    } else {
      const foot = new THREE.Mesh(new RoundedBoxGeometry(0.075, 0.055, 0.2, 3, 0.022), man); foot.position.set(0, -0.435, 0.05); kn.add(foot);
    }
    return { hp, kn };
  }
  const lA = leg(1), lB = leg(-1); J.lA = lA; J.lB = lB;
  // ---- шия і голова
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.052, 0.064, 0.12, 20), skin); neck.position.y = 0.575; torso.add(neck);
  const H = buildHead(M, v);
  const head = new THREE.Group(); head.position.y = 0.622; torso.add(head); J.head = head;
  H.group.position.set(0, 0.105, 0.012); head.add(H.group);
  if (!v) { H.group.scale.set(0.93, 0.98, 0.93); }
  // ---- руки
  function arm(side) {
    const sh = new THREE.Group(); sh.position.set(side * 0.198, 0.455, 0); torso.add(sh);
    const ball = new THREE.Mesh(new THREE.SphereGeometry(v ? 0.058 : 0.05, 16, 12), cloth); ball.scale.set(1, 1.1, 1.05); sh.add(ball);
    const up = capsuleLimb(0.30, v ? 0.060 : 0.05, v ? 0.049 : 0.042, cloth, 0.003); sh.add(up);
    const el = new THREE.Group(); el.position.y = -0.30; sh.add(el);
    const elb = new THREE.Mesh(new THREE.SphereGeometry(v ? 0.05 : 0.043, 14, 10), cloth); el.add(elb);
    const fo = capsuleLimb(0.27, v ? 0.049 : 0.042, v ? 0.036 : 0.032, cloth, 0.0); el.add(fo);
    let hand = null;
    if (v) {
      const cuffW = new THREE.Mesh(new THREE.CylinderGeometry(0.0375, 0.0375, 0.014, 18), M.tee); cuffW.position.y = -0.272; el.add(cuffW);
      hand = buildHand(side, M.skin, true); hand.group.position.set(0, -0.285, 0); hand.group.scale.setScalar(1.0); el.add(hand.group);
      if (side < 0) { const w = new THREE.Mesh(new THREE.CylinderGeometry(0.0395, 0.0395, 0.03, 20), M.steel); w.position.y = -0.255; el.add(w);
        const fc = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.006, 20), M.dark); fc.position.set(0.0, -0.255, 0); fc.rotation.z = Math.PI / 2; fc.visible = false; el.add(fc);
        const st = new THREE.Mesh(new THREE.CylinderGeometry(0.0405, 0.0405, 0.012, 20), M.strap); st.position.y = -0.236; el.add(st); }
    } else {
      const hnd = new THREE.Mesh(new THREE.SphereGeometry(0.04, 14, 10), man); hnd.position.y = -0.3; hnd.scale.set(0.7, 1.25, 0.95); el.add(hnd);
    }
    if (side > 0) { const ph = new THREE.Mesh(new RoundedBoxGeometry(0.075, 0.155, 0.012, 2, 0.006), MM({ color: 0x15151a, roughness: 0.3 })); ph.position.set(-0.004, -0.325, 0.045); ph.rotation.x = 0.1; ph.visible = false;
      const sc = new THREE.Mesh(new THREE.PlaneGeometry(0.066, 0.138), MM({ color: 0x7ad0ff, emissive: 0x7ad0ff, emissiveIntensity: 1.3 })); sc.position.z = 0.0065; ph.add(sc); el.add(ph); J.phone = ph; }
    return { sh, el, hand };
  }
  const aA = arm(1), aB = arm(-1); J.aA = aA; J.aB = aB;
  root.scale.setScalar(scale);
  root.traverse(o => { if (o.isMesh) { o.castShadow = true; } });
  // ---- бічні ефекти: дихання, кліпання, рот
  const breathers = [chestGroup];
  const fig = {
    root, scale, J, kind, id,
    set(p, x, y, z) {
      const T = ENV.t + seed * 3.7;
      const br = Math.sin(T * 1.55) * 0.5 + 0.5;
      chestGroup.scale.set(1 + 0.006 * br, 1 + 0.004 * br, 1 + 0.014 * br);
      const sway = (Math.sin(T * 0.7) * 0.012 + Math.sin(T * 1.13 + 1.3) * 0.008);
      torso.rotation.set(p.lean + 0.006 * br, sway * 0.6, sway * 0.5);
      head.rotation.set(p.hx + Math.sin(T * 0.9) * 0.012 - 0.012 * br, p.hy + Math.sin(T * 0.6 + 2) * 0.03, p.hz + Math.sin(T * 0.8) * 0.01);
      aA.sh.rotation.set(-p.aAx, 0, p.aAz); aA.el.rotation.x = -p.aAe;
      aB.sh.rotation.set(-p.bAx, 0, -p.bAz); aB.el.rotation.x = -p.bAe;
      if (aA.hand) { aA.hand.set(p.aHd); aB.hand.set(p.bHd); }
      lA.hp.rotation.x = -p.aHx; lA.kn.rotation.x = p.aKx;
      lB.hp.rotation.x = -p.bHx; lB.kn.rotation.x = p.bKx;
      root.rotation.y = p.ry;
      root.position.set(x, y + p.hipY * scale - 0.0 + (1 - 0) * 0.0, z);
      if (v) {
        // кліпання
        const k = (T % 3.9); const bl = (k > 3.62 && k < 3.8) ? Math.sin((k - 3.62) / 0.18 * Math.PI) : 0;
        const closed = Math.max(bl, 1 - p.eyes);
        H.lids.forEach(l => { l.visible = closed > 0.02; l.scale.y = Math.max(0.001, closed * 0.5); });
        // рот
        const m = clamp(ENV.mouth, 0, 1) * p.talk;
        const mo = H.mouth; mo.cav.scale.y = 0.05 + m * 0.9; mo.lo.position.y = -0.0052 - m * 0.0075; mo.up.position.y = 0.0035 + m * 0.0012;
        H.head.rotation.x = 0;
      }
    },
    tint(c) { man.color.set(c); },
    phone(on) { if (J.phone) J.phone.visible = on; },
  };
  world.add(root);
  return fig;
}
