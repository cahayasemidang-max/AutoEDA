(function () {
  'use strict';

  /* ═══════════════════════════════════════════════════════
     THREE.JS — 5 SCENE MANAGER
     ═══════════════════════════════════════════════════════ */

  const SCENE_NAMES = [
    'Bar Chart 3D',
    'Scatter Plot 3D',
    'Wave Chart 3D',
    'Heatmap Grid 3D',
    'Neural Network 3D',
  ];

  const SCENE_DURATION = 4500;
  const FADE_DURATION = 600;
  const isMobile = window.innerWidth < 768;
  const particleCount = isMobile ? 300 : 600;

  let renderer, camera, mainScene;
  let sceneGroup = new THREE.Group();
  let currentSceneIndex = 0;
  let sceneOpacity = 1;
  let transitionPhase = 'none';
  let sceneClock = new THREE.Clock();
  let sceneTimer = 0;
  let animFrameId = null;
  let sceneTime = 0;

  const CAMERA_POSITIONS = [
    { x: 0, y: 10, z: 22 },
    { x: 0, y: 5, z: 18 },
    { x: 0, y: 14, z: 20 },
    { x: 0, y: 18, z: 18 },
    { x: 0, y: 2, z: 20 },
  ];

  let cameraTarget = new THREE.Vector3(0, 10, 22);
  let cameraCurrent = new THREE.Vector3(0, 10, 22);

  /* ── Scene Data ── */
  let sceneData = {};

  function disposeObject(obj) {
    if (!obj) return;
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      if (Array.isArray(obj.material)) {
        obj.material.forEach(function (m) { m.dispose(); });
      } else {
        obj.material.dispose();
      }
    }
    if (obj.children) {
      while (obj.children.length > 0) {
        disposeObject(obj.children[0]);
        obj.remove(obj.children[0]);
      }
    }
  }

  function buildScene(index, time) {
    const group = new THREE.Group();
    group.name = 'scene-' + index;
    group.opacity = 0;

    switch (index) {
      case 0: buildBarChart(group, time); break;
      case 1: buildScatterPlot(group, time); break;
      case 2: buildWaveChart(group, time); break;
      case 3: buildHeatmap(group, time); break;
      case 4: buildNeuralNetwork(group, time); break;
    }

    return group;
  }

  /* ── Scene 1: Bar Chart 3D ── */
  function buildBarChart(group, time) {
    const rows = 5, cols = 6;
    const spacing = 1.8;
    const startX = -(cols - 1) * spacing * 0.5;
    const startZ = -(rows - 1) * spacing * 0.5;
    const bars = [];

    const pointLight = new THREE.PointLight(0x2563eb, 1, 30);
    pointLight.position.set(0, 12, 0);
    group.add(pointLight);

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const height = 1 + Math.random() * 7;
        const t = height / 8;
        const color = new THREE.Color().setHSL(0.58 + t * 0.12, 0.8, 0.3 + t * 0.4);
        const geo = new THREE.BoxGeometry(0.9, height, 0.9);
        const mat = new THREE.MeshPhongMaterial({
          color: color,
          emissive: color,
          emissiveIntensity: 0.08,
          shininess: 40,
        });
        const mesh = new THREE.Mesh(geo, mat);
        const x = startX + c * spacing;
        const z = startZ + r * spacing;
        mesh.position.set(x, height * 0.5 - 3, z);
        mesh.castShadow = true;
        group.add(mesh);

        const edges = new THREE.EdgesGeometry(geo);
        const edgeMat = new THREE.LineBasicMaterial({
          color: 0x3b82f6,
          transparent: true,
          opacity: 0.15,
        });
        const line = new THREE.LineSegments(edges, edgeMat);
        line.position.copy(mesh.position);
        group.add(line);

        bars.push({
          mesh: mesh,
          line: line,
          baseHeight: height,
          offset: Math.random() * Math.PI * 2,
          speed: 0.5 + Math.random() * 0.8,
          px: x,
          pz: z,
        });
      }
    }

    sceneData.bars = bars;
  }

  /* ── Scene 2: Scatter Plot 3D ── */
  function buildScatterPlot(group, time) {
    const clusterCenters = [
      { x: -4, y: 0, z: -3, color: 0xf472b6 },
      { x: 4, y: 0, z: -3, color: 0x60a5fa },
      { x: -4, y: 0, z: 3, color: 0x34d399 },
      { x: 4, y: 0, z: 3, color: 0xfbbf24 },
      { x: 0, y: 2, z: 0, color: 0xa78bfa },
    ];

    const positions = [];
    const colors = [];

    for (let i = 0; i < 800; i++) {
      const cluster = clusterCenters[Math.floor(Math.random() * clusterCenters.length)];
      const px = cluster.x + gaussRandom() * 1.2;
      const py = cluster.y + gaussRandom() * 1.2;
      const pz = cluster.z + gaussRandom() * 1.2;
      positions.push(px, py, pz);

      const col = new THREE.Color(cluster.color);
      colors.push(col.r, col.g, col.b);
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

    const mat = new THREE.PointsMaterial({
      size: 0.12,
      sizeAttenuation: true,
      vertexColors: true,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
    });

    const points = new THREE.Points(geo, mat);
    group.add(points);
    sceneData.scatterPoints = points;
    sceneData.scatterBasePos = positions.slice();

    /* Axis lines */
    const axisMat = new THREE.LineBasicMaterial({
      color: 0x3b82f6,
      transparent: true,
      opacity: 0.15,
    });
    for (let sign = -1; sign <= 1; sign += 2) {
      const pts = [
        new THREE.Vector3(-7 * sign, 0, 0),
        new THREE.Vector3(7 * sign, 0, 0),
      ];
      const g = new THREE.BufferGeometry().setFromPoints(pts);
      group.add(new THREE.Line(g, axisMat.clone()));
    }
  }

  function gaussRandom() {
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  /* ── Scene 3: Wave / Line Chart 3D ── */
  function buildWaveChart(group, time) {
    const size = 40;
    const geo = new THREE.PlaneGeometry(size, size, size, size);
    geo.rotateX(-Math.PI * 0.5);
    const pos = geo.attributes.position.array;

    sceneData.wavePositions = pos;
    sceneData.waveGeo = geo;

    const wireMat = new THREE.MeshPhongMaterial({
      color: 0x1d4ed8,
      wireframe: true,
      transparent: true,
      opacity: 0.5,
    });
    const wireMesh = new THREE.Mesh(geo, wireMat);
    wireMesh.position.y = -3;
    group.add(wireMesh);

    const solidMat = new THREE.MeshPhongMaterial({
      color: 0x1d4ed8,
      transparent: true,
      opacity: 0.15,
      side: THREE.DoubleSide,
    });
    const solidMesh = new THREE.Mesh(geo.clone(), solidMat);
    solidMesh.position.y = -3;
    group.add(solidMesh);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(0, 15, 10);
    group.add(dirLight);

    const ambLight = new THREE.AmbientLight(0x1a3a7a, 0.4);
    group.add(ambLight);

    /* Sweeping lines */
    const sweepGroup = new THREE.Group();
    const sweepMat = new THREE.LineBasicMaterial({
      color: 0x06b6d4,
      transparent: true,
      opacity: 0.3,
    });
    for (let i = 0; i < 5; i++) {
      const pts = [];
      for (let x = -size * 0.5; x <= size * 0.5; x += 0.5) {
        pts.push(new THREE.Vector3(x, 0, 0));
      }
      const g = new THREE.BufferGeometry().setFromPoints(pts);
      const line = new THREE.Line(g, sweepMat.clone());
      line.position.z = -size * 0.5 + (size / 6) * (i + 0.5);
      sweepGroup.add(line);
    }
    sweepGroup.position.y = 2;
    group.add(sweepGroup);
    sceneData.sweepGroup = sweepGroup;
  }

  /* ── Scene 4: Heatmap Grid 3D ── */
  function buildHeatmap(group, time) {
    const gridSize = 10;
    const spacing = 1.5;
    const startX = -(gridSize - 1) * spacing * 0.5;
    const startZ = -(gridSize - 1) * spacing * 0.5;
    const tiles = [];

    for (let r = 0; r < gridSize; r++) {
      for (let c = 0; c < gridSize; c++) {
        const val = Math.random();
        const geo = new THREE.BoxGeometry(1.2, 0.2, 1.2);
        const color = heatmapColor(val);
        const mat = new THREE.MeshPhongMaterial({
          color: color,
          emissive: color,
          emissiveIntensity: 0.15,
        });
        const mesh = new THREE.Mesh(geo, mat);
        const x = startX + c * spacing;
        const z = startZ + r * spacing;
        mesh.position.set(x, -3, z);
        group.add(mesh);

        tiles.push({
          mesh: mesh,
          currentVal: val,
          targetVal: Math.random(),
          speed: 0.3 + Math.random() * 0.5,
          time: Math.random() * 100,
        });
      }
    }

    sceneData.heatTiles = tiles;
  }

  function heatmapColor(val) {
    if (val < 0.25) return 0x1e3a8a;
    if (val < 0.5) return 0x2563eb;
    if (val < 0.75) return 0x06b6d4;
    return 0xf0abfc;
  }

  /* ── Scene 5: Neural Network 3D ── */
  function buildNeuralNetwork(group, time) {
    const layers = [5, 8, 8, 3];
    const layerSpacing = 3.5;
    const nodeRadius = 0.3;
    const allNodes = [];

    /* Build nodes per layer */
    layers.forEach(function (nodeCount, li) {
      const x = -((layers.length - 1) * layerSpacing) * 0.5 + li * layerSpacing;
      const ySpacing = 1.2;
      const startY = -(nodeCount - 1) * ySpacing * 0.5;
      const nodes = [];

      for (let ni = 0; ni < nodeCount; ni++) {
        const y = startY + ni * ySpacing;
        const z = 0;

        const sphereGeo = new THREE.SphereGeometry(nodeRadius, 16, 16);
        const sphereMat = new THREE.MeshPhongMaterial({
          color: 0x06b6d4,
          emissive: 0x06b6d4,
          emissiveIntensity: 0.2,
          transparent: true,
          opacity: 0.85,
        });
        const sphere = new THREE.Mesh(sphereGeo, sphereMat);
        sphere.position.set(x, y, z - 3);
        group.add(sphere);

        /* Glow sprite */
        const spriteMap = (function () {
          const canvas = document.createElement('canvas');
          canvas.width = 64;
          canvas.height = 64;
          const ctx = canvas.getContext('2d');
          const gradient = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
          gradient.addColorStop(0, 'rgba(6,182,212,0.4)');
          gradient.addColorStop(1, 'rgba(6,182,212,0)');
          ctx.fillStyle = gradient;
          ctx.fillRect(0, 0, 64, 64);
          return new THREE.CanvasTexture(canvas);
        })();

        const spriteMat2 = new THREE.SpriteMaterial({
          map: spriteMap,
          blending: THREE.AdditiveBlending,
          transparent: true,
          opacity: 0.5,
        });
        const sprite = new THREE.Sprite(spriteMat2);
        sprite.position.copy(sphere.position);
        sprite.scale.set(2.5, 2.5, 1);
        group.add(sprite);

        nodes.push({
          sphere: sphere,
          sprite: sprite,
          pulseOffset: Math.random() * Math.PI * 2,
        });
      }

      allNodes.push(nodes);

      /* Connections to previous layer */
      if (li > 0) {
        const prevNodes = allNodes[li - 1];
        const lineMat = new THREE.LineBasicMaterial({
          color: 0x3b82f6,
          transparent: true,
          opacity: 0.12,
        });

        prevNodes.forEach(function (prev) {
          nodes.forEach(function (node) {
            const pts = [
              prev.sphere.position.clone(),
              node.sphere.position.clone(),
            ];
            const g = new THREE.BufferGeometry().setFromPoints(pts);
            const line = new THREE.Line(g, lineMat.clone());
            group.add(line);
          });
        });
      }
    });

    sceneData.neuralNodes = allNodes;

    /* Signal particles */
    const signals = [];
    for (let i = 0; i < 12; i++) {
      const sigGeo = new THREE.SphereGeometry(0.08, 8, 8);
      const sigMat = new THREE.MeshBasicMaterial({
        color: 0xfbbf24,
        transparent: true,
        opacity: 0.9,
      });
      const sig = new THREE.Mesh(sigGeo, sigMat);
      sig.visible = false;
      group.add(sig);

      signals.push({
        mesh: sig,
        fromLayer: 0,
        fromNode: 0,
        toLayer: 0,
        toNode: 0,
        progress: Math.random(),
        speed: 0.2 + Math.random() * 0.3,
        delay: Math.random() * 3,
      });
    }
    sceneData.signals = signals;

    const camLight = new THREE.AmbientLight(0x1a3a7a, 0.5);
    group.add(camLight);
  }

  /* ── Scene Update Functions ── */

  function updateBarChart(time) {
    const bars = sceneData.bars;
    if (!bars) return;
    for (let i = 0; i < bars.length; i++) {
      const b = bars[i];
      const wave = Math.sin(time * b.speed + b.offset) * 0.5 + 0.5;
      const h = b.baseHeight * (0.4 + wave * 0.6);
      b.mesh.scale.y = h / b.baseHeight;
      b.mesh.position.y = h * 0.5 - 3;
      b.line.scale.y = h / b.baseHeight;
      b.line.position.y = h * 0.5 - 3;
    }
  }

  function updateScatterPlot(time) {
    const pts = sceneData.scatterPoints;
    if (!pts) return;
    const pos = pts.geometry.attributes.position.array;
    const base = sceneData.scatterBasePos;
    if (!base) return;

    for (let i = 0; i < pos.length; i += 3) {
      const idx = i / 3;
      const noise = Math.sin(time * 0.5 + idx * 0.1) * 0.08;
      pos[i] = base[i] + noise;
      pos[i + 1] = base[i + 1] + Math.sin(time * 0.7 + idx * 0.15) * 0.08;
      pos[i + 2] = base[i + 2] + Math.cos(time * 0.6 + idx * 0.12) * 0.08;
    }
    pts.geometry.attributes.position.needsUpdate = true;

    /* Rotate group */
    pts.rotation.x = Math.sin(time * 0.08) * 0.1;
    pts.rotation.y = time * 0.05;
  }

  function updateWaveChart(time) {
    const pos = sceneData.wavePositions;
    const geo = sceneData.waveGeo;
    if (!pos || !geo) return;

    for (let i = 0; i < pos.length; i += 3) {
      const x = pos[i];
      const y = pos[i + 2];
      const z = Math.sin(x * 0.5 + time * 1.2) * Math.cos(y * 0.5 + time * 0.8) * 2.5;
      pos[i + 1] = z;
    }
    geo.attributes.position.needsUpdate = true;
    geo.computeVertexNormals();

    const sweep = sceneData.sweepGroup;
    if (sweep) {
      const children = sweep.children;
      for (let i = 0; i < children.length; i++) {
        const line = children[i];
        const linePos = line.geometry.attributes.position.array;
        for (let j = 0; j < linePos.length; j += 3) {
          const x = linePos[j];
          const z = Math.sin(x * 0.5 + time * 1.2) * Math.cos(line.position.z * 0.5 + time * 0.8) * 2.5;
          linePos[j + 1] = z;
        }
        line.geometry.attributes.position.needsUpdate = true;
      }
      sweep.position.z = Math.sin(time * 0.15) * 2;
    }
  }

  function updateHeatmap(time) {
    const tiles = sceneData.heatTiles;
    if (!tiles) return;

    for (let i = 0; i < tiles.length; i++) {
      const t = tiles[i];
      t.time += 0.016;

      if (t.time > 1.5) {
        t.targetVal = Math.random();
        t.time = 0;
      }

      t.currentVal += (t.targetVal - t.currentVal) * 0.03;
      const val = t.currentVal;
      const color = new THREE.Color(heatmapColor(val));
      t.mesh.material.color.copy(color);
      t.mesh.material.emissive.copy(color);

      const scaleY = 0.2 + val * 0.6;
      t.mesh.scale.y = scaleY;
      t.mesh.position.y = -3 + scaleY * 0.1;
    }
  }

  function updateNeuralNetwork(time) {
    const nodes = sceneData.neuralNodes;
    if (!nodes) return;

    /* Node pulse */
    for (let li = 0; li < nodes.length; li++) {
      const layer = nodes[li];
      for (let ni = 0; ni < layer.length; ni++) {
        const n = layer[ni];
        const pulse = 0.95 + Math.sin(time * 1.5 + n.pulseOffset) * 0.05;
        n.sphere.scale.setScalar(pulse);
        n.sprite.scale.setScalar(2.5 * (0.9 + Math.sin(time * 1.5 + n.pulseOffset) * 0.1));
      }
    }

    /* Signals */
    const signals = sceneData.signals;
    if (!signals) return;

    for (let i = 0; i < signals.length; i++) {
      const sig = signals[i];
      sig.delay -= 0.016;
      if (sig.delay > 0) {
        sig.mesh.visible = false;
        continue;
      }

      sig.progress += sig.speed * 0.016;
      if (sig.progress > 1) {
        sig.progress = 0;
        sig.fromLayer = Math.floor(Math.random() * (nodes.length - 1));
        sig.fromNode = Math.floor(Math.random() * nodes[sig.fromLayer].length);
        sig.toLayer = sig.fromLayer + 1;
        sig.toNode = Math.floor(Math.random() * nodes[sig.toLayer].length);
        sig.speed = 0.2 + Math.random() * 0.3;
        sig.delay = 0.5 + Math.random() * 1.5;
      }

      const fromPos = nodes[sig.fromLayer][sig.fromNode].sphere.position;
      const toPos = nodes[sig.toLayer][sig.toNode].sphere.position;
      sig.mesh.position.lerpVectors(fromPos, toPos, sig.progress);
      sig.mesh.visible = true;
    }
  }

  /* ── Animation Loop ── */

  function animateScene() {
    const delta = sceneClock.getDelta();
    sceneTime += delta;
    sceneTimer += delta * 1000;

    /* Update current scene */
    switch (currentSceneIndex) {
      case 0: updateBarChart(sceneTime); break;
      case 1: updateScatterPlot(sceneTime); break;
      case 2: updateWaveChart(sceneTime); break;
      case 3: updateHeatmap(sceneTime); break;
      case 4: updateNeuralNetwork(sceneTime); break;
    }

    /* Update permanent particles */
    updateParticles(delta);

    /* Camera lerp */
    cameraCurrent.lerp(cameraTarget, 0.02);
    camera.position.copy(cameraCurrent);

    /* Handle transitions */
    if (transitionPhase === 'fadeOut') {
      sceneOpacity -= delta * (1000 / FADE_DURATION);
      if (sceneOpacity <= 0) {
        sceneOpacity = 0;
        doSceneSwap((currentSceneIndex + 1) % 5);
        transitionPhase = 'fadeIn';
      }
    } else if (transitionPhase === 'fadeIn') {
      sceneOpacity += delta * (1000 / FADE_DURATION);
      if (sceneOpacity >= 1) {
        sceneOpacity = 1;
        transitionPhase = 'none';
      }
    } else {
      if (sceneTimer >= SCENE_DURATION) {
        transitionPhase = 'fadeOut';
        sceneTimer = 0;
      }
    }

    sceneGroup.traverse(function (child) {
      if (child.isMesh || child.isPoints || child.isLine || child.isLineSegments) {
        child.material.transparent = true;
        child.material.opacity = sceneOpacity * (child.userData.baseOpacity || 1);
        child.material.needsUpdate = true;
      }
    });

    camera.lookAt(0, 0, 0);
    renderer.render(mainScene, camera);
    animFrameId = requestAnimationFrame(animateScene);
  }

  function doSceneSwap(newIndex) {
    disposeObject(sceneGroup);
    mainScene.remove(sceneGroup);

    sceneTimer = 0;
    currentSceneIndex = newIndex;
    sceneGroup = buildScene(currentSceneIndex, sceneTime);
    mainScene.add(sceneGroup);

    cameraTarget.set(
      CAMERA_POSITIONS[currentSceneIndex].x,
      CAMERA_POSITIONS[currentSceneIndex].y,
      CAMERA_POSITIONS[currentSceneIndex].z
    );

    updateSceneIndicator();
  }

  function jumpToScene(index) {
    if (index === currentSceneIndex && transitionPhase === 'none') return;
    if (index < 0 || index > 4) return;

    doSceneSwap(index);
    sceneOpacity = 0;
    transitionPhase = 'fadeIn';
  }

  function updateSceneIndicator() {
    document.querySelectorAll('.scene-dot').forEach(function (dot, i) {
      dot.classList.toggle('active', i === currentSceneIndex);
    });
    var nameEl = document.getElementById('scene-name');
    if (nameEl) nameEl.textContent = SCENE_NAMES[currentSceneIndex];
  }

  /* ── Permanent Objects ── */

  let particleSystem;
  let particleSpeeds = [];

  function buildPermanentObjects(scene) {
    /* Particles */
    const count = particleCount;
    const positions = new Float32Array(count * 3);
    particleSpeeds = [];

    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 50;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 25;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 30 - 5;
      particleSpeeds.push({
        x: (Math.random() - 0.5) * 0.005,
        y: 0.003 + Math.random() * 0.008,
        z: (Math.random() - 0.5) * 0.005,
      });
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const mat = new THREE.PointsMaterial({
      color: 0x88bbff,
      size: isMobile ? 0.04 : 0.05,
      transparent: true,
      opacity: 0.4,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });

    particleSystem = new THREE.Points(geo, mat);
    scene.add(particleSystem);

    /* Grid floor */
    const gridHelper = new THREE.GridHelper(40, 40, 0x2563eb, 0x1a3a6a);
    gridHelper.position.y = -3.2;
    gridHelper.material.opacity = 0.12;
    gridHelper.material.transparent = true;
    scene.add(gridHelper);

    const gridHelper2 = new THREE.GridHelper(40, 10, 0x3b82f6, 0x2563eb);
    gridHelper2.position.y = -3.15;
    gridHelper2.material.opacity = 0.06;
    gridHelper2.material.transparent = true;
    scene.add(gridHelper2);
  }

  function updateParticles(delta) {
    if (!particleSystem) return;
    const pos = particleSystem.geometry.attributes.position.array;
    const count = particleCount;

    for (let i = 0; i < count; i++) {
      pos[i * 3] += particleSpeeds[i].x;
      pos[i * 3 + 1] += particleSpeeds[i].y;
      pos[i * 3 + 2] += particleSpeeds[i].z;

      if (pos[i * 3 + 1] > 14) {
        pos[i * 3] = (Math.random() - 0.5) * 50;
        pos[i * 3 + 1] = -10;
        pos[i * 3 + 2] = (Math.random() - 0.5) * 30 - 5;
      }
    }
    particleSystem.geometry.attributes.position.needsUpdate = true;
  }

  /* ── Init Three.js ── */

  function initThreeScene() {
    const canvas = document.getElementById('three-canvas');
    if (!canvas) return;

    mainScene = new THREE.Scene();

    camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);

    renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      antialias: true,
      alpha: true,
    });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    /* Ambient light for all scenes */
    const ambient = new THREE.AmbientLight(0x1a2a4a, 0.6);
    mainScene.add(ambient);

    /* Build permanent objects */
    buildPermanentObjects(mainScene);

    /* Build initial scene */
    sceneGroup = buildScene(0, 0);
    mainScene.add(sceneGroup);
    sceneOpacity = 1;

    /* Set camera position based on initial scene */
    camera.position.set(0, 10, 22);
    cameraTarget.set(0, 10, 22);
    cameraCurrent.set(0, 10, 22);

    /* Start animation loop */
    sceneClock = new THREE.Clock();
    animateScene();

    /* ── Resize ── */
    window.addEventListener('resize', function () {
      const w = window.innerWidth;
      const h = window.innerHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });

    /* ── Visibility ── */
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        sceneClock.stop();
      } else {
        sceneClock = new THREE.Clock();
      }
    });
  }

  /* ═══════════════════════════════════════════════════════
     SCENE INDICATOR — UI
     ═══════════════════════════════════════════════════════ */

  function initSceneIndicator() {
    document.querySelectorAll('.scene-dot').forEach(function (dot) {
      dot.addEventListener('click', function () {
        const index = parseInt(this.getAttribute('data-index'), 10);
        jumpToScene(index);
      });
    });
  }

  /* ═══════════════════════════════════════════════════════
     NAVBAR — SCROLL EFFECT
     ═══════════════════════════════════════════════════════ */

  function initNavbar() {
    const navbar = document.getElementById('navbar');
    if (!navbar) return;

    let ticking = false;
    window.addEventListener('scroll', function () {
      if (!ticking) {
        window.requestAnimationFrame(function () {
          if (window.scrollY > 40) {
            navbar.classList.add('scrolled');
          } else {
            navbar.classList.remove('scrolled');
          }
          ticking = false;
        });
        ticking = true;
      }
    });
  }

  /* ═══════════════════════════════════════════════════════
     MOBILE HAMBURGER MENU
     ═══════════════════════════════════════════════════════ */

  function initMobileMenu() {
    const hamburger = document.getElementById('nav-hamburger');
    const navLinks = document.getElementById('nav-links');
    if (!hamburger || !navLinks) return;

    hamburger.addEventListener('click', function () {
      const isOpen = navLinks.classList.toggle('open');
      hamburger.classList.toggle('active', isOpen);
      document.body.style.overflow = isOpen ? 'hidden' : '';
    });

    navLinks.querySelectorAll('.nav-link').forEach(function (link) {
      link.addEventListener('click', function () {
        navLinks.classList.remove('open');
        hamburger.classList.remove('active');
        document.body.style.overflow = '';
      });
    });
  }

  /* ═══════════════════════════════════════════════════════
     INTERSECTION OBSERVER — REVEAL ANIMATIONS
     ═══════════════════════════════════════════════════════ */

  function initRevealAnimations() {
    const revealEls = document.querySelectorAll('.reveal');
    if (!revealEls.length) return;

    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              entry.target.classList.add('visible');
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
      );

      revealEls.forEach(function (el) {
        observer.observe(el);
      });
    } else {
      revealEls.forEach(function (el) {
        el.classList.add('visible');
      });
    }
  }

  /* ═══════════════════════════════════════════════════════
     SMOOTH SCROLL FOR ANCHOR LINKS
     ═══════════════════════════════════════════════════════ */

  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        const targetId = this.getAttribute('href');
        if (!targetId || targetId === '#') return;

        const target = document.querySelector(targetId);
        if (target) {
          e.preventDefault();
          const navH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--nav-h'), 10) || 72;
          const top = target.getBoundingClientRect().top + window.pageYOffset - navH - 16;
          window.scrollTo({ top: top, behavior: 'smooth' });
        }
      });
    });
  }

  /* ═══════════════════════════════════════════════════════
     INIT
     ═══════════════════════════════════════════════════════ */

  function init() {
    initThreeScene();
    initSceneIndicator();
    initNavbar();
    initMobileMenu();
    initRevealAnimations();
    initSmoothScroll();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
