'use strict';

window.addEventListener('load', function () {
    initRobot();
});

function initRobot() {
    const canvas = document.getElementById('robotCanvas');
    if (!canvas) { console.error('[robot] Canvas tidak ditemukan!'); return; }

    const parent = canvas.parentElement;
    const getSize = function () {
        return { w: parent.clientWidth || window.innerWidth, h: parent.clientHeight || window.innerHeight };
    };

    var size = getSize();

    const renderer = new THREE.WebGLRenderer({
        canvas,
        alpha:              true,
        antialias:          true,
        premultipliedAlpha: true
    });
    renderer.setClearColor(0x000000, 0);
    renderer.setSize(size.w, size.h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled   = true;
    renderer.toneMapping         = THREE.ReinhardToneMapping;
    renderer.toneMappingExposure = 1.0;

    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(50, size.w / size.h, 0.1, 100);
    camera.position.set(0, 0, 8);
    camera.lookAt(0, 0, 0);

    // ── Lights ──
    scene.add(new THREE.AmbientLight(0x111827, 0.8));
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.2);
    keyLight.position.set(3, 6, 5);
    scene.add(keyLight);
    const rimLight = new THREE.DirectionalLight(0x06b6d4, 1.5);
    rimLight.position.set(-5, 3, -6);
    scene.add(rimLight);
    const fillLight = new THREE.PointLight(0x7c3aed, 1.0, 20);
    fillLight.position.set(-3, -3, 4);
    scene.add(fillLight);
    const accentLight = new THREE.PointLight(0x2563eb, 1.5, 15);
    scene.add(accentLight);

    // ── Bloom ──
    let composer = null;
    try {
        composer = new THREE.EffectComposer(renderer);
        composer.addPass(new THREE.RenderPass(scene, camera));
        composer.addPass(new THREE.UnrealBloomPass(
            new THREE.Vector2(size.w, size.h), 0.5, 0.4, 0.5
        ));
    } catch (e) { console.warn('[robot] Bloom:', e.message); }

    // ── Background particles ──
    var particleCount = 800;
    var pGeo = new THREE.BufferGeometry();
    var pPos = new Float32Array(particleCount * 3);
    var pCol = new Float32Array(particleCount * 3);
    var pVel = [];
    var palette = [
        [0.02, 0.71, 0.83],
        [0.29, 0.24, 0.93],
        [0.49, 0.18, 0.93],
        [0.96, 0.42, 0.71],
    ];
    for (var i = 0; i < particleCount; i++) {
        pPos[i*3]   = (Math.random() - 0.5) * 26;
        pPos[i*3+1] = (Math.random() - 0.5) * 14;
        pPos[i*3+2] = -2 - Math.random() * 8;
        var c = palette[Math.floor(Math.random() * palette.length)];
        pCol[i*3] = c[0]; pCol[i*3+1] = c[1]; pCol[i*3+2] = c[2];
        pVel.push({
            x: (Math.random() - 0.5) * 0.008,
            y: (Math.random() - 0.5) * 0.008,
            phase: Math.random() * Math.PI * 2
        });
    }
    pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    pGeo.setAttribute('color', new THREE.BufferAttribute(pCol, 3));
    var pMat = new THREE.PointsMaterial({
        size: 0.12, transparent: true, opacity: 0.7,
        blending: THREE.AdditiveBlending, vertexColors: true,
        depthWrite: false
    });
    var particles = new THREE.Points(pGeo, pMat);
    scene.add(particles);

    // ── Robots array ──
    var robots = [];
    const clock = new THREE.Clock();

    // ── Mouse ──
    document.addEventListener('mousemove', function (e) {
        var r = canvas.getBoundingClientRect();
        window._rMX = ((e.clientX - r.left) / r.width) * 2 - 1;
        window._rMY = -((e.clientY - r.top) / r.height) * 2 + 1;
    });

    // ── Factory ──
    function makeRobot(gltf, x, y, s, rotY) {
        var mesh = gltf.scene.clone();
        mesh.scale.set(s, s, s);
        mesh.position.set(x, y, 0);
        mesh.rotation.y = rotY;

        mesh.traverse(function (c) {
            if (c.isMesh) {
                c.castShadow = c.receiveShadow = true;
                if (c.material) { c.material.envMapIntensity = 1.2; c.material.needsUpdate = true; }
            }
        });
        scene.add(mesh);

        var mixer = new THREE.AnimationMixer(mesh);
        gltf.animations.forEach(function (clip) {
            var a = mixer.clipAction(clip);
            a.reset(); a.setLoop(THREE.LoopRepeat, Infinity); a.play();
        });

        // Cari bone tangan — pilih yang paling dalam (paling ujung = tangan/jari)
        var allArms = [];
        mesh.traverse(function (c) {
            if (!c.isBone) return;
            var n = (c.name || '').toLowerCase();
            if (/arm|hand|lengan|tangan|shoulder|radius|humerus|wrist|forearm|elbow|jari/.test(n)) allArms.push(c);
        });
        // Urut berdasarkan depth (parent chain) → paling dalam = tangan
        function depthOf(b) { var d = 0, p = b; while (p.parent) { d++; p = p.parent; } return d; }
        allArms.sort(function (a, b) { return depthOf(b) - depthOf(a); });
        var right = allArms.filter(function (a) { return /right|kanan/.test(a.name || ''); });
        var armBone = right.length > 0 ? right[0] : (allArms[0] || null);
        if (armBone) console.log('[robot] Bone wave:', armBone.name);

        return {
            mesh: mesh,
            mixer: mixer,
            armBone: armBone,
            origScale: s,
            isBusy: false,
            isWaving: false,
            wavePhase: 0,
            waveEndT: 0,
            driftVX: 0, driftVY: 0,
            driftTargetX: 0, driftTargetY: 0,
            timeOutside: 0,
            angryUntil: 0
        };
    }

    function triggerWave(r) {
        r.isWaving = true;
        r.wavePhase = 0;
        r.waveEndT = clock.elapsedTime + 2.0;
    }

    function triggerDrift(r, cb) {
        var steps = 5 + Math.floor(Math.random() * 4);
        var tl = gsap.timeline({ onComplete: function () { if (cb) cb(); } });
        for (var i = 0; i < steps; i++) {
            var dx = (Math.random() - 0.5) * 3;
            var dy = (Math.random() - 0.5) * 1.5;
            var lookY = -0.3 + (dx > 0 ? 0.25 : -0.25);
            var dur = 0.2 + Math.random() * 0.3;
            tl.to(r.mesh.rotation, { y: lookY, z: dx * 0.04, duration: dur * 0.4, ease: 'power1.out' });
            tl.to(r.mesh.position, { x: '+=' + dx, y: '+=' + dy, duration: dur, ease: 'power2.inOut' }, '+=0.03');
        }
    }

    function spawnCollision(scn, x, y) {
        var N = 25;
        var geo = new THREE.BufferGeometry();
        var arr = new Float32Array(N * 3);
        var vel = [];
        for (var i = 0; i < N; i++) {
            arr[i*3] = x + (Math.random() - 0.5) * 0.3;
            arr[i*3+1] = y + (Math.random() - 0.5) * 0.3;
            arr[i*3+2] = (Math.random() - 0.5) * 0.3;
            vel.push({
                x: (Math.random() - 0.5) * 0.4,
                y: (Math.random() - 0.5) * 0.4,
                z: (Math.random() - 0.5) * 0.2
            });
        }
        geo.setAttribute('position', new THREE.BufferAttribute(arr, 3));
        var mat = new THREE.PointsMaterial({
            color: 0xff4500, size: 0.15, transparent: true,
            blending: THREE.AdditiveBlending
        });
        var burst = new THREE.Points(geo, mat);
        scn.add(burst);
        var f = 0;
        (function loop() {
            f++;
            var p = burst.geometry.attributes.position.array;
            for (var i = 0; i < N; i++) {
                p[i*3] += vel[i].x; p[i*3+1] += vel[i].y; p[i*3+2] += vel[i].z;
                vel[i].y -= 0.01;
            }
            burst.geometry.attributes.position.needsUpdate = true;
            mat.opacity = 1 - f / 30;
            if (f < 30) requestAnimationFrame(loop);
            else { scn.remove(burst); geo.dispose(); mat.dispose(); }
        })();
    }

    // ── Load ──
    const loader = new THREE.GLTFLoader();
    loader.load(
        canvas.dataset.path || '/static/assets/robot.glb',

        function (gltf) {
            console.log('[robot] Loaded | Animasi:', gltf.animations.length);

            // Robot 1 — utama, kanan
            var r1 = makeRobot(gltf, 4, -0.8, 2.0, -0.3);
            robots.push(r1);

            // Robot 2 — teman, kiri
            var r2 = makeRobot(gltf, -2, 0.5, 1.5, 0.2);
            robots.push(r2);

            // Robot 3 — teman kecil, kiri jauh
            var r3 = makeRobot(gltf, -5, -0.3, 1.2, 0.4);
            robots.push(r3);

            console.log('[robot] Total robot:', robots.length);

            // ── Auto greet all ──
            setTimeout(function () {
                robots.forEach(function (r) { triggerWave(r); });
                console.log('[robot] Halo semua!');
            }, 800);

            // ── Click ──
            const ray = new THREE.Raycaster();
            const m2  = new THREE.Vector2();

            window.addEventListener('click', function (e) {
                var r = canvas.getBoundingClientRect();
                m2.x = ((e.clientX - r.left) / r.width) * 2 - 1;
                m2.y = -((e.clientY - r.top) / r.height) * 2 + 1;
                ray.setFromCamera(m2, camera);

                for (var i = robots.length - 1; i >= 0; i--) {
                    var rob = robots[i];
                    var hits = ray.intersectObject(rob.mesh, true);
                    if (hits.length > 0 && !rob.isBusy) {
                        rob.isBusy = true;
                        triggerWave(rob);
                        triggerDrift(rob, function () { rob.isBusy = false; });
                        break;
                    }
                }
            });

            animate();
        },

        function (xhr) {
            if (xhr.total > 0)
                console.log('[robot]', (xhr.loaded / xhr.total * 100).toFixed(0) + '%');
        },

        function (err) { console.error('[robot] Error:', err); }
    );

    // ── Animation loop ──
    function animate() {
        requestAnimationFrame(animate);
        const delta = clock.getDelta();
        const time  = clock.elapsedTime;

        // Update all robots — masing-masing punya ritme sendiri
        robots.forEach(function (r, idx) {
            if (r.mixer) r.mixer.update(delta);

            // Unique movement signature per robot biar ga sealur
            var speeds = [[0.5, 5, 1.5], [0.7, 4, 2], [0.9, 3, 1.2]];
            var s = speeds[idx] || speeds[0];
            var spd = s[0], rangeX = s[1], rangeY = s[2];
            var changeRate = 0.006 + idx * 0.004;

            if (!r.isBusy) {
                if (Math.random() < changeRate) r.driftTargetX = (Math.random() - 0.5) * rangeX;
                if (Math.random() < changeRate) r.driftTargetY = (Math.random() - 0.5) * rangeY;
                r.driftVX += (r.driftTargetX - r.driftVX) * 0.01;
                r.driftVY += (r.driftTargetY - r.driftVY) * 0.01;
                r.mesh.position.x += r.driftVX * delta * spd;
                r.mesh.position.y += r.driftVY * delta * spd;

                // Bebas tanpa batas, tapi kalau terlalu lama di luar layar → kembali
                var inView = r.mesh.position.x > -7 && r.mesh.position.x < 8
                          && r.mesh.position.y > -3 && r.mesh.position.y < 3;
                if (inView) {
                    r.timeOutside = 0;
                } else {
                    r.timeOutside += delta;
                    if (r.timeOutside > 3) {
                        r.driftTargetX = -r.mesh.position.x * 0.1;
                        r.driftTargetY = -r.mesh.position.y * 0.1;
                    }
                }

                var lookY = -0.3 + r.driftVX * 0.25;
                var lookZ = r.driftVX * 0.06;
                r.mesh.rotation.y += (lookY - r.mesh.rotation.y) * 0.03;
                r.mesh.rotation.z += (lookZ - r.mesh.rotation.z) * 0.03;
                r.mesh.position.y += Math.sin(time * 1.5 + idx * 2.1) * 0.004;
            }

            // Wave — via quaternion biar tidak bentrok animasi GLB
            if (r.isWaving && r.armBone) {
                if (time < r.waveEndT) {
                    r.wavePhase += delta * 6;
                    var amp = Math.min((time - (r.waveEndT - 2.0)) / 0.3, 1);
                    var fadeOut = Math.max((r.waveEndT - time) / 0.3, 0);
                    var e = amp * fadeOut;
                    // Ayunan Z (kipas samping) + sedikit X (angkat)
                    var sin = Math.sin(r.wavePhase);
                    var q = new THREE.Quaternion()
                        .multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), sin * 0.8 * e))
                        .multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -0.25 * e));
                    r.armBone.quaternion.premultiply(q);
                } else {
                    r.isWaving = false;
                }
            }
        });

        // Particles
        if (particles) {
            var pos = particles.geometry.attributes.position.array;
            for (var i = 0; i < particleCount; i++) {
                pos[i*3]   += pVel[i].x + Math.sin(time * 0.3 + pVel[i].phase) * 0.001;
                pos[i*3+1] += pVel[i].y + Math.cos(time * 0.2 + pVel[i].phase) * 0.001;
                if (pos[i*3] > 15) pos[i*3] = -15;
                if (pos[i*3] < -15) pos[i*3] = 15;
                if (pos[i*3+1] > 8) pos[i*3+1] = -8;
                if (pos[i*3+1] < -8) pos[i*3+1] = 8;
            }
            particles.geometry.attributes.position.needsUpdate = true;
        }

        // Accent light
        accentLight.position.x = Math.sin(time * 0.6) * 6;
        accentLight.position.z = Math.cos(time * 0.6) * 6;
        accentLight.position.y = 3;
        var cols = [0x2563eb, 0x06b6d4, 0x7c3aed, 0xf472b6];
        accentLight.color.setHex(cols[Math.floor(time * 0.4) % cols.length]);

        if (composer) composer.render();
        else renderer.render(scene, camera);
    }

    window.addEventListener('resize', function () {
        var s = getSize();
        camera.aspect = s.w / s.h;
        camera.updateProjectionMatrix();
        renderer.setSize(s.w, s.h);
        if (composer) composer.setSize(s.w, s.h);
    });
}
