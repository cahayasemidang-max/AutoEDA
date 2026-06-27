/* ═══════════════════════════════════════════════════════════════
   AUTH PAGE — DS Generator
   Three.js Wave 3D Background + Form Logic + Validation
   ═══════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ─── DOM REFS ───

    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const tabs = $$('.pill-btn');
    const panels = {
        signin: $('#panelSignin'),
        register: $('#panelRegister'),
    };
    const formSignin = $('#formSignin');
    const formRegister = $('#formRegister');
    const btnSignin = $('#btnSignin');
    const btnRegister = $('#btnRegister');
    const strengthBar = $('#strengthBar');
    const strengthFill = $('#strengthFill');
    const strengthLabel = $('#strengthLabel');
    const confirmStatus = $('#confirmStatus');
    const toastContainer = $('#toastContainer');
    const authCard = $('#authCard');
    const themeToggle = $('#themeToggle');
    const themeIcon = $('#themeIcon');

    // ─── STATE ───

    let currentTab = 'signin';
    const defaultTab = window.location.pathname.includes('register') ? 'register' : 'signin';

    // ─── THEME ───

    const theme = localStorage.getItem('ds-theme') || 'dark';
    if (theme === 'light') {
        document.body.classList.add('light-theme');
        themeIcon.className = 'fas fa-sun';
    }

    themeToggle.addEventListener('click', () => {
        const isLight = document.body.classList.toggle('light-theme');
        localStorage.setItem('ds-theme', isLight ? 'light' : 'dark');
        themeIcon.className = isLight ? 'fas fa-sun' : 'fas fa-moon';
    });

    // ─── PREMIUM 3D DATA WAVE NETWORK ───

    function initThree() {
        const canvas = document.getElementById('premium-3d-data-canvas');
        if (!canvas || typeof THREE === 'undefined') return;

        const isDark = !document.body.classList.contains('light-theme');

        const scene = new THREE.Scene();
        scene.fog = new THREE.FogExp2(isDark ? 0x0a0f1e : 0xe2e8f0, 0.006);

        const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 120);
        camera.position.set(0, 5, 15);
        camera.lookAt(0, 0, 0);

        const renderer = new THREE.WebGLRenderer({
            canvas: canvas,
            antialias: true,
            alpha: true,
        });
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setClearColor(isDark ? 0x0a0f1e : 0xe2e8f0, 0);

        const segments = 80;
        const size = 50;
        const geometry = new THREE.PlaneGeometry(size, size, segments, segments);
        geometry.rotateX(-Math.PI / 2);

        const origPos = geometry.attributes.position.array.slice();
        const vertexCount = origPos.length / 3;

        const wireColor = isDark ? 0x6d28d9 : 0x7c3aed;
        const emissiveColor = isDark ? 0x7c3aed : 0x6366f1;
        const pointColor = isDark ? 0xa78bfa : 0x818cf8;
        const solidColor = isDark ? 0x3b0764 : 0xddd6fe;
        const lineColor = isDark ? 0x4c1d95 : 0xa78bfa;

        const wireMat = new THREE.MeshPhongMaterial({
            color: wireColor,
            wireframe: true,
            emissive: emissiveColor,
            emissiveIntensity: isDark ? 0.5 : 0.2,
            transparent: true,
            opacity: isDark ? 0.5 : 0.3,
        });

        const waveMesh = new THREE.Mesh(geometry, wireMat);
        waveMesh.receiveShadow = false;
        scene.add(waveMesh);

        const solidMat = new THREE.MeshPhongMaterial({
            color: solidColor,
            transparent: true,
            opacity: isDark ? 0.12 : 0.08,
            side: THREE.DoubleSide,
            depthWrite: false,
        });

        const solidMesh = new THREE.Mesh(geometry.clone(), solidMat);
        solidMesh.position.y = -0.3;
        scene.add(solidMesh);

        const pointMat = new THREE.PointsMaterial({
            color: pointColor,
            size: 0.12,
            sizeAttenuation: true,
            transparent: true,
            opacity: isDark ? 0.9 : 0.6,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        });

        const points = new THREE.Points(geometry.clone(), pointMat);
        scene.add(points);

        // --- Connection lines ---
        const linePositions = [];
        for (let ix = 0; ix < segments; ix += 3) {
            for (let iz = 0; iz < segments; iz += 3) {
                const idx = ix * (segments + 1) + iz;
                if (ix < segments - 2) {
                    const nidx = (ix + 3) * (segments + 1) + iz;
                    linePositions.push(0, 0, 0, 0, 0, 0);
                }
                if (iz < segments - 2) {
                    const nidx = ix * (segments + 1) + (iz + 3);
                    linePositions.push(0, 0, 0, 0, 0, 0);
                }
            }
        }

        const lineGeo = new THREE.BufferGeometry();
        lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
        const lineMat = new THREE.LineBasicMaterial({
            color: lineColor,
            transparent: true,
            opacity: isDark ? 0.08 : 0.05,
        });
        const lineSegments = new THREE.LineSegments(lineGeo, lineMat);
        scene.add(lineSegments);

        // --- Ambient particles ---
        const particleCount = 400;
        const pPos = new Float32Array(particleCount * 3);
        const pSpeed = new Float32Array(particleCount);
        const pSize = new Float32Array(particleCount);
        for (let i = 0; i < particleCount; i++) {
            pPos[i * 3] = (Math.random() - 0.5) * 50;
            pPos[i * 3 + 1] = (Math.random() - 0.5) * 20;
            pPos[i * 3 + 2] = (Math.random() - 0.5) * 50;
            pSpeed[i] = 0.003 + Math.random() * 0.012;
            pSize[i] = 0.04 + Math.random() * 0.08;
        }
        const pGeo = new THREE.BufferGeometry();
        pGeo.setAttribute('position', new THREE.Float32BufferAttribute(pPos, 3));
        const pMat = new THREE.PointsMaterial({
            color: isDark ? 0x6366f1 : 0x818cf8,
            size: 0.06,
            transparent: true,
            opacity: isDark ? 0.4 : 0.2,
            sizeAttenuation: true,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        });
        const particles = new THREE.Points(pGeo, pMat);
        scene.add(particles);

        // --- 3D Floating Data Particles (Matrix Dust) ---
        const dustCount = 400;
        const dustPos = new Float32Array(dustCount * 3);
        const dustColors = new Float32Array(dustCount * 3);
        const dustSpeeds = new Float32Array(dustCount);
        const dustPhases = new Float32Array(dustCount);
        const cyan = new THREE.Color(0x00F3FF);
        const purple = new THREE.Color(0x7842FF);
        for (let i = 0; i < dustCount; i++) {
            dustPos[i * 3] = (Math.random() - 0.5) * 1000;
            dustPos[i * 3 + 1] = (Math.random() - 0.5) * 1000;
            dustPos[i * 3 + 2] = (Math.random() - 0.5) * 1000;
            dustSpeeds[i] = 0.02 + Math.random() * 0.06;
            dustPhases[i] = Math.random() * Math.PI * 2;
            const t = Math.random();
            const c = cyan.clone().lerp(purple, t);
            dustColors[i * 3] = c.r;
            dustColors[i * 3 + 1] = c.g;
            dustColors[i * 3 + 2] = c.b;
        }
        const dustGeo = new THREE.BufferGeometry();
        dustGeo.setAttribute('position', new THREE.Float32BufferAttribute(dustPos, 3));
        dustGeo.setAttribute('color', new THREE.Float32BufferAttribute(dustColors, 3));
        const dustMat = new THREE.PointsMaterial({
            size: 2.5,
            vertexColors: THREE.VertexColors,
            transparent: true,
            opacity: 0.6,
            sizeAttenuation: true,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        });
        const dustParticles = new THREE.Points(dustGeo, dustMat);
        scene.add(dustParticles);

        // --- Glow nodes overlay ---
        const glowMat = new THREE.PointsMaterial({
            color: isDark ? 0x7c3aed : 0xa78bfa,
            size: 0.3,
            transparent: true,
            opacity: isDark ? 0.12 : 0.06,
            sizeAttenuation: true,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        });
        const glowPoints = new THREE.Points(geometry.clone(), glowMat);
        scene.add(glowPoints);

        // --- Lighting ---
        const ambientLight = new THREE.AmbientLight(isDark ? 0x0f0a1e : 0xffffff, 0.6);
        scene.add(ambientLight);

        const light1 = new THREE.PointLight(isDark ? 0x7c3aed : 0x6366f1, isDark ? 2.5 : 1.5, 60);
        light1.position.set(0, 15, 0);
        scene.add(light1);

        const light2 = new THREE.PointLight(isDark ? 0x2563eb : 0x818cf8, isDark ? 1.5 : 0.8, 60);
        light2.position.set(-20, 8, 20);
        scene.add(light2);

        const light3 = new THREE.PointLight(isDark ? 0x06b6d4 : 0x38bdf8, isDark ? 0.8 : 0.4, 60);
        light3.position.set(20, 5, -20);
        scene.add(light3);

        // --- Interaction ---
        let mouseX = 0, mouseY = 0;
        document.addEventListener('mousemove', (e) => {
            mouseX = (e.clientX / window.innerWidth) * 2 - 1;
            mouseY = -(e.clientY / window.innerHeight) * 2 + 1;
        });

        // --- Animation loop ---
        function animate() {
            requestAnimationFrame(animate);

            const time = Date.now() * 0.0006;

            const positions = geometry.attributes.position.array;
            const solidPos = solidMesh.geometry.attributes.position.array;
            const pointPos = points.geometry.attributes.position.array;
            const glowPos = glowPoints.geometry.attributes.position.array;

            for (let i = 0; i < positions.length; i += 3) {
                const x = origPos[i];
                const z = origPos[i + 2] || 0;
                const dist = Math.sqrt(x * x + z * z);
                const y = (
                    Math.sin(x * 0.25 + time * 0.7) * Math.cos(z * 0.25 + time * 0.5) * 2.5 +
                    Math.sin(dist * 0.5 - time * 1.1) * 1.2 +
                    Math.cos(x * 0.15 + z * 0.15 + time * 0.3) * 0.8
                );
                positions[i + 1] = y;
                solidPos[i + 1] = y;
                pointPos[i + 1] = y;
                glowPos[i + 1] = y;
            }

            geometry.attributes.position.needsUpdate = true;
            solidMesh.geometry.attributes.position.needsUpdate = true;
            points.geometry.attributes.position.needsUpdate = true;
            glowPoints.geometry.attributes.position.needsUpdate = true;
            geometry.computeVertexNormals();

            // Update connection lines
            const lp = lineGeo.attributes.position.array;
            let li = 0;
            for (let ix = 0; ix < segments; ix += 3) {
                for (let iz = 0; iz < segments; iz += 3) {
                    const idx = (ix * (segments + 1) + iz) * 3;
                    if (ix < segments - 2) {
                        const nidx = ((ix + 3) * (segments + 1) + iz) * 3;
                        lp[li] = pointPos[idx]; lp[li + 1] = pointPos[idx + 1]; lp[li + 2] = pointPos[idx + 2];
                        lp[li + 3] = pointPos[nidx]; lp[li + 4] = pointPos[nidx + 1]; lp[li + 5] = pointPos[nidx + 2];
                        li += 6;
                    }
                    if (iz < segments - 2) {
                        const nidx = (ix * (segments + 1) + (iz + 3)) * 3;
                        lp[li] = pointPos[idx]; lp[li + 1] = pointPos[idx + 1]; lp[li + 2] = pointPos[idx + 2];
                        lp[li + 3] = pointPos[nidx]; lp[li + 4] = pointPos[nidx + 1]; lp[li + 5] = pointPos[nidx + 2];
                        li += 6;
                    }
                }
            }
            lineGeo.attributes.position.needsUpdate = true;

            // Update particles
            const pp = particles.geometry.attributes.position.array;
            for (let i = 0; i < particleCount; i++) {
                pp[i * 3 + 1] += pSpeed[i];
                if (pp[i * 3 + 1] > 12) {
                    pp[i * 3] = (Math.random() - 0.5) * 50;
                    pp[i * 3 + 1] = -12;
                    pp[i * 3 + 2] = (Math.random() - 0.5) * 50;
                }
            }
            particles.geometry.attributes.position.needsUpdate = true;

            // Update floating data particles
            const dp = dustParticles.geometry.attributes.position.array;
            for (let i = 0; i < dustCount; i++) {
                dp[i * 3 + 1] += dustSpeeds[i];
                dp[i * 3] += Math.sin(Date.now() * 0.0005 + dustPhases[i]) * 0.008;
                dp[i * 3 + 2] += Math.cos(Date.now() * 0.0005 + dustPhases[i]) * 0.008;
                if (dp[i * 3 + 1] > 500) {
                    dp[i * 3] = (Math.random() - 0.5) * 1000;
                    dp[i * 3 + 1] = -500;
                    dp[i * 3 + 2] = (Math.random() - 0.5) * 1000;
                }
            }
            dustParticles.geometry.attributes.position.needsUpdate = true;

            // Rotation with mouse parallax and auto-rotation
            const targetRotY = mouseX * 0.25;
            const targetRotX = mouseY * 0.12;
            waveMesh.rotation.y += (targetRotY - waveMesh.rotation.y + 0.002) * 0.02;
            waveMesh.rotation.x += (targetRotX - waveMesh.rotation.x) * 0.02;
            solidMesh.rotation.copy(waveMesh.rotation);
            points.rotation.copy(waveMesh.rotation);
            glowPoints.rotation.copy(waveMesh.rotation);
            dustParticles.rotation.copy(waveMesh.rotation);
            lineSegments.rotation.copy(waveMesh.rotation);
            particles.rotation.y += 0.0004;

            renderer.render(scene, camera);
        }

        animate();

        // --- Resize ---
        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        });
    }

    // ─── TAB SWITCHING ───

    function switchTab(tab) {
        if (tab === currentTab) return;
        const activePanel = panels[currentTab];
        const targetPanel = panels[tab];

        tabs.forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });

        activePanel.classList.remove('active');
        activePanel.classList.add('slide-out');

        setTimeout(() => {
            activePanel.classList.remove('slide-out');
            targetPanel.classList.add('active');
        }, 150);

        currentTab = tab;
    }

    tabs.forEach((btn) => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    $$('.switch-link').forEach((link) => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            switchTab(link.dataset.tab);
        });
    });

    // ─── TOGGLE PASSWORD ───

    $$('.toggle-pass').forEach((btn) => {
        btn.addEventListener('click', () => {
            const input = btn.parentElement.querySelector('.auth-input');
            if (!input) return;
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
            btn.querySelector('i').className = isPassword ? 'far fa-eye-slash' : 'far fa-eye';
        });
    });

    // ─── TOAST ───

    function showToast(message, type) {
        const toast = document.createElement('div');
        toast.className = 'toast toast-' + type;
        const icon = type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle';
        toast.innerHTML = '<i class="fas ' + icon + '"></i> ' + message;
        toastContainer.appendChild(toast);

        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                if (toast.parentElement) toast.remove();
            }, 400);
        }, 3000);
    }

    // ─── EMAIL VALIDATION ───

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    const regEmail = $('#regEmail');
    if (regEmail) {
        regEmail.addEventListener('blur', () => {
            const val = regEmail.value.trim();
            if (val && !emailRegex.test(val)) {
                regEmail.classList.add('error');
                regEmail.classList.remove('success');
            } else if (val) {
                regEmail.classList.remove('error');
                regEmail.classList.add('success');
            } else {
                regEmail.classList.remove('error', 'success');
            }
        });

        regEmail.addEventListener('input', () => {
            if (regEmail.classList.contains('error') || regEmail.classList.contains('success')) {
                const val = regEmail.value.trim();
                if (val && !emailRegex.test(val)) {
                    regEmail.classList.add('error');
                    regEmail.classList.remove('success');
                } else if (val) {
                    regEmail.classList.remove('error');
                    regEmail.classList.add('success');
                } else {
                    regEmail.classList.remove('error', 'success');
                }
            }
        });
    }

    // ─── PASSWORD STRENGTH ───

    const regPassword = $('#regPassword');
    if (regPassword) {
        regPassword.addEventListener('input', () => {
            const val = regPassword.value;
            updateStrength(val);
        });

        regPassword.addEventListener('focus', () => {
            if (regPassword.value) {
                strengthBar.classList.remove('hidden');
            }
        });

        regPassword.addEventListener('blur', () => {
            if (!regPassword.value) {
                strengthBar.classList.add('hidden');
            }
        });
    }

    function updateStrength(password) {
        if (!password) {
            strengthBar.classList.add('hidden');
            return;
        }

        strengthBar.classList.remove('hidden');

        let score = 0;
        if (password.length >= 8) score++;
        if (password.length >= 12) score++;
        if (/[0-9]/.test(password)) score++;
        if (/[^a-zA-Z0-9]/.test(password)) score++;
        if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;

        let level, cls;
        if (score <= 2) {
            level = 'weak';
            cls = 'weak';
        } else if (score <= 3) {
            level = 'medium';
            cls = 'medium';
        } else {
            level = 'strong';
            cls = 'strong';
        }

        strengthFill.className = 'strength-fill ' + cls;
        strengthLabel.className = 'strength-label ' + cls;

        strengthLabel.textContent = I18N.t('auth_strength_' + level);
    }

    // ─── CONFIRM PASSWORD ───

    const regConfirm = $('#regConfirm');
    if (regConfirm) {
        function checkConfirm() {
            const pw = regPassword ? regPassword.value : '';
            const confirm = regConfirm.value;

            if (!confirm) {
                confirmStatus.textContent = '';
                confirmStatus.className = 'confirm-status';
                regConfirm.classList.remove('error', 'success');
                return;
            }

            if (confirm === pw) {
                confirmStatus.textContent = '✓';
                confirmStatus.className = 'confirm-status match';
                regConfirm.classList.remove('error');
                regConfirm.classList.add('success');
            } else {
                confirmStatus.textContent = '✗';
                confirmStatus.className = 'confirm-status nomatch';
                regConfirm.classList.remove('success');
                regConfirm.classList.add('error');
            }
        }

        regConfirm.addEventListener('input', checkConfirm);

        if (regPassword) {
            regPassword.addEventListener('input', () => {
                if (regConfirm.value) checkConfirm();
            });
        }
    }

    // ─── SHAKE INPUT ───

    function shakeInput(input) {
        input.classList.add('shake');
        setTimeout(() => input.classList.remove('shake'), 500);
    }

    function shakeCard() {
        authCard.classList.add('shake');
        setTimeout(() => authCard.classList.remove('shake'), 500);
    }

    // ─── LOADING STATE ───

    function setLoading(btn, loading) {
        const text = btn.querySelector('.btn-text');
        const icon = btn.querySelector('.btn-icon');
        const spinner = btn.querySelector('.spinner');
        const btnText = I18N.t('auth_processing');

        if (loading) {
            btn.disabled = true;
            if (text) {
                btn.dataset.originalText = text.textContent;
                text.textContent = btnText;
            }
            if (icon) icon.classList.add('hidden');
            if (spinner) spinner.classList.remove('hidden');
        } else {
            btn.disabled = false;
            if (text && btn.dataset.originalText) {
                text.textContent = btn.dataset.originalText;
            }
            if (spinner) spinner.classList.add('hidden');
            if (icon) icon.classList.remove('hidden');
        }
    }

    // ─── REMEMBER ME ───

    const rememberCheck = $('#rememberMe');
    const loginUser = $('#loginUsername');

    function loadRemembered() {
        try {
            const saved = localStorage.getItem('ds_remember_user');
            if (saved && loginUser) {
                const data = JSON.parse(saved);
                if (data.username) {
                    loginUser.value = data.username;
                    if (rememberCheck) rememberCheck.checked = true;
                }
            }
        } catch (_) { /* ignore */ }
    }

    function saveRemembered() {
        if (rememberCheck && rememberCheck.checked && loginUser) {
            localStorage.setItem('ds_remember_user', JSON.stringify({
                username: loginUser.value,
            }));
        } else {
            localStorage.removeItem('ds_remember_user');
        }
    }

    loadRemembered();

    // ─── FETCH API HELPERS ───

    async function apiLogin(username, password) {
        const res = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ login: username, password }),
        });
        return res.json();
    }

    async function apiRegister(username, email, password) {
        const res = await fetch('/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password, confirm_password: password }),
        });
        return res.json();
    }

    // ─── FORM SUBMIT: SIGN IN ───

    formSignin.addEventListener('submit', async (e) => {
        e.preventDefault();

        const username = loginUser.value.trim();
        const password = $('#loginPassword').value;

        let hasError = false;

        if (!username) {
            shakeInput(loginUser);
            hasError = true;
        }
        if (!password) {
            shakeInput($('#loginPassword'));
            hasError = true;
        }

        if (hasError) {
            showToast(I18N.t('auth_login_empty'), 'error');
            shakeCard();
            return;
        }

        setLoading(btnSignin, true);

        try {
            const data = await apiLogin(username, password);
            if (data.status === 'success') {
                saveRemembered();
                showToast(I18N.t('auth_login_success'), 'success');
                setTimeout(() => {
                    window.location.href = data.redirect || '/upload';
                }, 800);
            } else {
                showToast(data.message || I18N.t('auth_login_invalid'), 'error');
                shakeCard();
                setLoading(btnSignin, false);
            }
        } catch (_) {
            showToast(I18N.t('auth_connection_failed'), 'error');
            shakeCard();
            setLoading(btnSignin, false);
        }
    });

    // ─── FORM SUBMIT: REGISTER ───

    const regUsername = $('#regUsername');

    function getRegisterData() {
        return {
            username: regUsername.value.trim(),
            email: regEmail.value.trim(),
            password: regPassword.value,
            confirm: regConfirm.value,
        };
    }

    function validateRegister(data) {
        const errors = [];

        if (!data.username) {
            shakeInput(regUsername);
            errors.push('username');
        }

        if (!data.email) {
            shakeInput(regEmail);
            errors.push('email');
        } else if (!emailRegex.test(data.email)) {
            regEmail.classList.add('error');
            shakeInput(regEmail);
            errors.push('email_invalid');
        }

        if (!data.password) {
            shakeInput(regPassword);
            errors.push('password');
        }

        if (!data.confirm) {
            shakeInput(regConfirm);
            errors.push('confirm');
        } else if (data.password && data.confirm !== data.password) {
            shakeInput(regConfirm);
            errors.push('mismatch');
        }

        return errors;
    }

    formRegister.addEventListener('submit', async (e) => {
        e.preventDefault();
        const data = getRegisterData();
        const validationErrors = validateRegister(data);

        if (validationErrors.length > 0) {
            showToast(I18N.t('auth_err_' + validationErrors[0]), 'error');
            shakeCard();
            return;
        }

        setLoading(btnRegister, true);

        try {
            const result = await apiRegister(data.username, data.email, data.password);
            if (result.status === 'success') {
                showToast(I18N.t('auth_register_success'), 'success');
                setTimeout(() => {
                    window.location.href = result.redirect || '/upload';
                }, 800);
            } else {
                showToast(result.message || I18N.t('auth_register_failed'), 'error');
                shakeCard();
                setLoading(btnRegister, false);
            }
        } catch (_) {
            showToast(I18N.t('auth_connection_failed'), 'error');
            shakeCard();
            setLoading(btnRegister, false);
        }
    });

    // ─── INIT ───

    initThree();
    if (defaultTab !== currentTab) {
        switchTab(defaultTab);
    }

})();
