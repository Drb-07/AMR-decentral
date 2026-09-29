import os
import re

# Read server.py
with open("server.py", "r", encoding="utf-8") as f:
    server_code = f.read()

s_idx = server_code.find("<script>")
e_idx = server_code.rfind("</script>")

html_pre = server_code[server_code.find("<!DOCTYPE html>"):s_idx]
js_engine = server_code[s_idx + 8:e_idx]
html_post = server_code[e_idx + 9:server_code.find('"""', e_idx + 9)]

# Read Three.js and OrbitControls
with open("static/three.min.js", "r", encoding="utf-8") as f:
    three_code = f.read()

with open("static/OrbitControls.js", "r", encoding="utf-8") as f:
    orbit_code = f.read()

# 1. Add Black & White Theme Overrides & 3D UI CSS
css_injection = """
    /* ========================================================
       BLACK & WHITE CYBER-INDUSTRIAL SLEEK THEME OVERRIDES
       ======================================================== */
    :root {
      --bg: #090b10;
      --panel: #0f1218;
      --panel-border: rgba(255, 255, 255, 0.16);
      --border: #1e222c;
      --text: #f8fafc;
      --text-muted: #8b949e;
      --accent: #ffffff;
      --accent-glow: rgba(255, 255, 255, 0.4);
      --rack: #141720;
      --rack-border: #2a2f3d;
      --aisle: #0b0d13;
    }

    body {
      background: #090b10;
      color: #f8fafc;
    }

    html, body {
      overflow: hidden !important;
      width: 100vw !important;
      height: 100vh !important;
      margin: 0;
      padding: 0;
    }
    header {
      background: #0f1218;
      border-bottom: 1px solid rgba(255, 255, 255, 0.15);
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.8);
      height: 52px !important;
      max-height: 52px !important;
      flex-shrink: 0 !important;
      overflow: hidden !important;
      box-sizing: border-box !important;
    }
    .hud-card {
      width: 330px !important;
      min-width: 330px !important;
      max-width: 330px !important;
      box-sizing: border-box !important;
      transition: none !important; /* CRITICAL: Prevents topology card shaking */
    }
    .hud-stat {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 5px;
      height: 18px;
    }
    .hud-val {
      font-weight: 600;
      color: #fff;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 195px;
      text-align: right;
    }
    .badge {
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    #hud-proximity-badge {
      width: 230px !important;
      min-width: 230px !important;
      max-width: 230px !important;
      display: inline-block !important;
      text-align: center !important;
      font-variant-numeric: tabular-nums !important;
      white-space: nowrap !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
      flex-shrink: 0 !important;
      box-sizing: border-box !important;
    }

    .brand-title {
      color: #ffffff;
      text-shadow: 0 0 12px rgba(255, 255, 255, 0.4);
    }

    .badge {
      background: rgba(255, 255, 255, 0.10);
      color: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.4);
      box-shadow: 0 0 10px rgba(255, 255, 255, 0.15);
    }

    /* 3D / 2D View Switcher & Camera Preset Bar */
    .view-mode-bar {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .view-toggle-btn {
      background: #151922;
      color: #94a3b8;
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 6px;
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }
    .view-toggle-btn:hover {
      color: #ffffff;
      background: #222735;
      border-color: rgba(255, 255, 255, 0.4);
    }
    .view-toggle-btn.active {
      background: #ffffff;
      color: #000000;
      border-color: #ffffff;
      box-shadow: 0 0 14px rgba(255, 255, 255, 0.45);
    }

    .cam-presets-bar {
      display: flex;
      align-items: center;
      gap: 4px;
      background: #090b10;
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 6px;
      padding: 2px 4px;
    }
    .cam-preset-btn {
      background: transparent;
      color: #8b949e;
      border: 1px solid transparent;
      border-radius: 4px;
      padding: 4px 8px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .cam-preset-btn:hover {
      color: #ffffff;
      background: rgba(255, 255, 255, 0.08);
    }
    .cam-preset-btn.active {
      background: rgba(255, 255, 255, 0.22);
      color: #ffffff;
      border-color: rgba(255, 255, 255, 0.35);
      box-shadow: 0 0 8px rgba(255, 255, 255, 0.25);
    }

    /* 3D Viewport Container */
    #viewport-3d {
      width: 100%;
      height: 100%;
      position: absolute;
      top: 0;
      left: 0;
      z-index: 1;
      display: block;
      background: #090b10;
      outline: none;
    }

        /* V2V Gateway Glassmorphism Drawer */
    .v2v-drawer {
      position: absolute;
      top: 14px;
      right: 18px;
      width: 380px;
      max-height: 520px;
      background: rgba(15, 18, 24, 0.94);
      backdrop-filter: blur(14px);
      border: 1px solid rgba(255, 255, 255, 0.25);
      border-radius: 10px;
      padding: 12px 14px;
      font-size: 11px;
      z-index: 10;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.85), 0 0 16px rgba(56, 189, 248, 0.2);
      display: flex;
      flex-direction: column;
      animation: trackHudSlideIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .v2v-drawer-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.12);
      margin-bottom: 8px;
    }
    .v2v-stats-row {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
      margin-bottom: 8px;
    }
    .v2v-stat-card {
      background: #11151f;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 6px;
      padding: 6px 4px;
      text-align: center;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .v2v-label {
      font-size: 8px;
      color: #8b949e;
      text-transform: uppercase;
      font-weight: 700;
    }
    .v2v-stat-card strong {
      color: #38bdf8;
      font-size: 12px;
    }
    .v2v-packet-container {
      flex: 1;
      overflow-y: auto;
      max-height: 240px;
      background: #090c12;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 6px;
      padding: 4px;
    }

    /* 3D RACK INSPECTOR CARD */
    .rack-inspector-card {
      position: absolute;
      bottom: 24px;
      left: 360px;
      background: rgba(15, 18, 24, 0.95);
      backdrop-filter: blur(14px);
      border: 1px solid rgba(255, 255, 255, 0.3);
      border-radius: 10px;
      padding: 14px 16px;
      font-size: 12px;
      z-index: 10;
      width: 320px;
      box-shadow: 0 14px 35px rgba(0, 0, 0, 0.8), 0 0 18px rgba(255, 255, 255, 0.15);
      animation: trackHudSlideIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .rack-insp-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.12);
      margin-bottom: 10px;
    }
    .rack-insp-badge {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.15);
      color: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.35);
      text-transform: uppercase;
    }
    .rack-tier-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 10px;
      margin-bottom: 4px;
      border-radius: 6px;
      background: #141822;
      border: 1px solid rgba(255, 255, 255, 0.08);
      font-size: 11px;
    }
    .rack-tier-row.occupied {
      background: #1b202e;
      border-color: rgba(255, 255, 255, 0.3);
    }
    .tier-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #424b60;
    }
    .tier-dot.active {
      background: #ffffff;
      box-shadow: 0 0 8px #ffffff;
    }

    /* 3D Overlay Help Tooltip */
    .view-3d-hint {
      position: absolute;
      top: 14px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(15, 18, 24, 0.88);
      backdrop-filter: blur(8px);
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 20px;
      padding: 5px 14px;
      font-size: 11px;
      color: #e2e8f0;
      display: flex;
      align-items: center;
      gap: 8px;
      z-index: 6;
      pointer-events: none;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.6);
    }
"""
html_pre = html_pre.replace("</style>", css_injection + "\n</style>")

# 2. Update Header with 3D/2D and Camera Controls
header_replacement = """
    <div class="view-mode-bar">
      <div style="display:flex; gap:4px; background:#090b10; padding:3px; border-radius:8px; border:1px solid rgba(255,255,255,0.14);">
        <button id="btn-view-3d" class="view-toggle-btn active" onclick="switchViewMode('3D')">📦 3D Model</button>
        <button id="btn-view-2d" class="view-toggle-btn" onclick="switchViewMode('2D')">🗺️ 2D Tactical</button>
      </div>

      <div id="cam-presets-bar" class="cam-presets-bar">
        <span style="font-size:10px; color:#8b949e; font-weight:700; margin-right:4px;">CAMERA:</span>
        <button class="cam-preset-btn active" id="btn-cam-orbit" onclick="setCameraMode('orbit')" title="Free 3D Orbit: Left Drag = Rotate, Right Drag = Pan, Scroll = Zoom">🌐 Orbit</button>
        <button class="cam-preset-btn" id="btn-cam-follow" onclick="setCameraMode('follow')" title="Lock 3D Camera Behind Tracked AMR">🎥 Follow AMR</button>
        <button class="cam-preset-btn" id="btn-cam-iso" onclick="setCameraMode('iso')" title="Isometric 45° Angle">🎬 Isometric</button>
        <button class="cam-preset-btn" id="btn-cam-top" onclick="setCameraMode('top')" title="Top-Down 3D Tactical">📐 Top-Down</button>
      </div>

      <div class="cam-presets-bar">
        <button class="cam-preset-btn active" id="btn-toggle-lidar" onclick="toggleLidarBeams()" title="Toggle Real-Time LiDAR Safety Scan Beams">⚡ LiDAR</button>
        <button class="cam-preset-btn active" id="btn-toggle-paths" onclick="toggle3DPaths()" title="Toggle 3D Trajectory Ribbons">〰️ Paths</button>
        <button class="cam-preset-btn active" id="btn-toggle-wire" onclick="toggleWireframe()" title="Toggle Wireframe Architecture">📐 Wire</button>
      </div>

      <div class="cam-presets-bar">
        <span class="badge" id="hud-proximity-badge" style="background:rgba(34, 197, 94, 0.15); color:#22c55e; border-color:#22c55e; font-size:10px; font-weight:700;">🟢 Min Dist: 1.18m (Safe)</span>
      </div>

      <div class="cam-presets-bar">
        <button class="cam-preset-btn active" id="btn-toggle-v2v" onclick="toggleV2VDrawer()" title="Open Decentralized V2V Mesh Gateway & Comms Monitor">📡 V2V Mesh <span id="v2v-links-badge" class="badge" style="font-size:9px; padding:1px 5px; margin-left:4px;">12</span></button>
        <button class="cam-preset-btn active" id="btn-toggle-obs" onclick="toggleDynamicObstacles()" title="Toggle Human Workers & Dynamic Obstacles">👷 Workers/Obs</button>
        <button class="cam-preset-btn" onclick="spawnDynamicWorker()" title="Spawn an Auditor Human Worker">➕ Worker</button>
      </div>
    </div>
"""
pattern = r'<div class="header-actions">.*?</div>\s*<div class="status-group">'
html_pre = re.sub(
    pattern,
    header_replacement + '\n    <div class="status-group">',
    html_pre,
    flags=re.DOTALL
)

# 3. Add 3D Viewport and 3D Rack Inspector Card inside #view-map
view_map_needle = '<div id="view-map" class="app-view active">'
view_map_replacement = """<div id="view-map" class="app-view active">
      <!-- 3D Three.js WebGL Viewport -->
      <div id="viewport-3d"></div>
      
      <!-- 3D View Interaction Help Hint -->
      <div class="view-3d-hint" id="view-3d-hint">
        <span>🎮 Left Click: Rotate | Right Click: Pan | Scroll: Zoom | Click any AMR or Rack to Inspect</span>
      </div>

      <!-- Decentralized V2V Mesh Gateway Drawer -->
      <div id="v2v-gateway-drawer" class="v2v-drawer" style="display:none;">
        <div class="v2v-drawer-header">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:16px;">📡</span>
            <div>
              <strong style="color:#ffffff; font-size:12px;">Decentralized V2V Mesh Gateway</strong>
              <div style="font-size:9px; color:#94a3b8;">C-V2X 5.9 GHz Peer-to-Peer Protocol (RF Range: 22m)</div>
            </div>
          </div>
          <button class="track-ctrl-close-btn" onclick="toggleV2VDrawer()" title="Close Gateway">✕</button>
        </div>
        <div class="v2v-stats-row">
          <div class="v2v-stat-card"><span class="v2v-label">Mesh Nodes</span><strong id="v2v-stat-nodes">8/8</strong></div>
          <div class="v2v-stat-card"><span class="v2v-label">Active RF Links</span><strong id="v2v-stat-links">12</strong></div>
          <div class="v2v-stat-card"><span class="v2v-label">Mesh Topology</span><strong id="v2v-stat-conn">100%</strong></div>
          <div class="v2v-stat-card"><span class="v2v-label">Hazards Broadcast</span><strong id="v2v-stat-hazards">0</strong></div>
        </div>
        <!-- Blue Line V2V Communication Explanation Card -->
        <div style="background:#0c1017; border:1px solid rgba(56, 189, 248, 0.25); border-radius:6px; padding:8px 10px; margin-bottom:8px;">
          <div style="color:#38bdf8; font-weight:700; font-size:10.5px; margin-bottom:3px; display:flex; align-items:center; gap:5px;">
            <span>🌐 What is the Blue Line? (Decentralized V2V Mesh)</span>
          </div>
          <div style="color:#94a3b8; font-size:9px; line-height:1.4;">
            The pulsing cyan line represents a <strong>C-V2X / IEEE 802.11p 5.9 GHz Peer-to-Peer RF Link</strong> active between AMRs within 22m range (RSSI: -38 to -70 dBm). AMRs exchange:
            <br>• <strong>2 Hz Heartbeats:</strong> Real-time (X, Y) coords, velocity vector, & 4-step path reservations.
            <br>• <strong>Obstacle Alerts:</strong> LiDAR hazard broadcasts so bots detour before reaching bottlenecks.
            <br>• <strong>Consensus Handshakes:</strong> Autonomous right-of-way resolution (lower battery passes, peer clears corridor).
          </div>
        </div>

        <div style="display:flex; gap:6px; margin:8px 0; flex-wrap:wrap;">
          <button class="cam-preset-btn active" id="btn-v2v-mesh-toggle" onclick="toggleV2VMeshView()">📡 Toggle RF Links</button>
          <button class="cam-preset-btn active" id="btn-obs-toggle" onclick="toggleDynamicObstacles()">👷 Toggle Workers</button>
          <button class="cam-preset-btn" onclick="spawnDynamicWorker()">➕ Spawn Worker</button>
          <button class="cam-preset-btn" onclick="spawnPalletObstacle()">📦 Spawn Cart</button>
        </div>
        <div style="font-size:10px; font-weight:700; color:#94a3b8; margin-bottom:4px; text-transform:uppercase; letter-spacing:0.5px;">LIVE DECENTRALIZED PACKET STREAM</div>
        <div id="v2v-packet-list" class="v2v-packet-container">
          <div style="font-size:10px; color:#64748b; padding:6px;">Awaiting V2V packet transmissions...</div>
        </div>
      </div>

      <!-- 3D Storage Rack Inspector Card (Black & White Theme) -->
      <div id="rack-inspector-card" class="rack-inspector-card" style="display:none;">
        <div class="rack-insp-header">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:16px;">🗄️</span>
            <div>
              <strong id="rack-insp-title" style="color:#fff; font-size:13px;">Storage Rack Pod</strong>
              <div id="rack-insp-cat-name" style="color:#94a3b8; font-size:10px;">Consumer Electronics</div>
            </div>
          </div>
          <button class="track-ctrl-close-btn" onclick="closeRackInspector()" title="Close Inspector">✕</button>
        </div>
        <div class="rack-insp-body">
          <div style="display:flex; justify-content:space-between; margin-bottom:8px; font-size:11px; color:#8b949e;">
            <span>Grid Pos: <strong id="rack-insp-coords" style="color:#fff;">(0, 0)</strong></span>
            <span>Capacity: <strong id="rack-insp-occ" style="color:#ffffff;">0 / 5 Tiers</strong></span>
          </div>
          <div id="rack-insp-tiers-list">
            <!-- 5 Tiers dynamically generated -->
          </div>
        </div>
      </div>
"""
html_pre = html_pre.replace(view_map_needle, view_map_replacement)

# Make 2D canvas initially hidden
html_pre = html_pre.replace(
    '<canvas id="viewport"></canvas>',
    '<canvas id="viewport" style="display:none;"></canvas>'
)

# 4. Modify loadMap to initialize 3D scene when WebGL is available
old_load_map = """    async function loadMap() {
      const res = await fetch('/api/map');
      mapData = await res.json();
      initRackMemory();
      initAmrFleet();
      resetView();
      lastAnimTime = performance.now();
      requestAnimationFrame(animateLoop);
    }"""

new_load_map = """    async function loadMap() {
      const res = await fetch('/api/map');
      mapData = await res.json();
      initRackMemory();
      initAmrFleet();
      resetView();
      if (isWebGLAvailable()) {
        init3DScene();
        build3DMap();
      }
      lastAnimTime = performance.now();
      requestAnimationFrame(animateLoop);
    }"""
js_engine = js_engine.replace(old_load_map, new_load_map)

# 5. Modify animateLoop: CRITICAL FIX TO CALL render3D(dt) WHEN IN 3D MODE!
old_anim_loop_render = """        if (trackedRobotId) {
          updateTrackingHud();
        }
        render();"""

new_anim_loop_render = """        if (trackedRobotId) {
          updateTrackingHud();
        }
        if (viewMode === '3D' && isWebGLAvailable() && renderer3D) {
          render3D(dt);
        } else {
          render();
        }"""
js_engine = js_engine.replace(old_anim_loop_render, new_anim_loop_render)

# 6. Build the 3D Digital Twin Engine Code with CACHED WebGL Check (Zero Context Leaks!)
js_3d_engine = """
    // =========================================================================
    // THREE.JS 3D DIGITAL TWIN & REAL AMR INDUSTRIAL MODEL SIMULATOR
    // =========================================================================
    let _webglCached = null;
    function isWebGLAvailable() {
      if (_webglCached !== null) return _webglCached;
      try {
        const c = document.createElement('canvas');
        _webglCached = !!(window.WebGLRenderingContext && (c.getContext('webgl') || c.getContext('experimental-webgl')));
      } catch (e) {
        _webglCached = false;
      }
      return _webglCached;
    }

    let viewMode = '3D'; // '3D' or '2D'
    let cameraMode = 'orbit'; // 'orbit', 'follow', 'iso', 'top'
    let showLidarBeams = true;
    let show3DPaths = true;
    let wireframeMode = false;

    let scene3D = null;
    let camera3D = null;
    let renderer3D = null;
    let controls3D = null;
    let amrModels3D = {};
    let rackPostsMesh = null;
    let rackShelvesMesh = null;
    let totesInstancedMesh = null;
    let raycaster3D = null;
    let mouse3D = null;
    let selected3DRack = null;
    let pathLineObjects3D = {};
    let rackHighlightBox = null;
    let floorMesh3D = null;

    const C_SIZE = 1.6; // 3D cell size in world units
    const HALF_W = 40;  // 80 / 2
    const HALF_H = 25;  // 50 / 2

    function gridTo3D(gx, gy, elevation = 0) {
      return {
        x: (gx - HALF_W + 0.5) * C_SIZE,
        y: elevation,
        z: (gy - HALF_H + 0.5) * C_SIZE
      };
    }

    function init3DScene() {
      if (!isWebGLAvailable() || typeof THREE === 'undefined') return;

      const container = document.getElementById('viewport-3d');
      if (!container) return;

      // 1. Scene setup
      scene3D = new THREE.Scene();
      scene3D.background = new THREE.Color(0x0a0c10); // Crisp deep slate background

      // 2. Camera setup - Positioned for sweeping overview of entire 80x50 warehouse
      const aspect = container.clientWidth / (container.clientHeight || 1);
      camera3D = new THREE.PerspectiveCamera(45, aspect, 0.5, 2000);
      camera3D.position.set(0, 58, 68);

      // 3. WebGL Renderer
      renderer3D = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
      renderer3D.setSize(container.clientWidth, container.clientHeight);
      renderer3D.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer3D.toneMapping = THREE.ACESFilmicToneMapping;
      renderer3D.toneMappingExposure = 1.25;
      container.innerHTML = '';
      container.appendChild(renderer3D.domElement);

      // 4. Orbit Controls
      if (typeof THREE.OrbitControls !== 'undefined') {
        controls3D = new THREE.OrbitControls(camera3D, renderer3D.domElement);
        controls3D.enableDamping = true;
        controls3D.dampingFactor = 0.08;
        controls3D.maxPolarAngle = Math.PI / 2 - 0.02; // Keep above floor
        controls3D.minDistance = 6;
        controls3D.maxDistance = 350;
        controls3D.target.set(0, 0, 0);
      }

      // 5. Studio Lighting (Black & White high-contrast industrial theme)
      const hemiLight = new THREE.HemisphereLight(0xffffff, 0x1e2430, 1.4);
      scene3D.add(hemiLight);

      const mainSpot = new THREE.DirectionalLight(0xffffff, 2.2);
      mainSpot.position.set(30, 90, 45);
      scene3D.add(mainSpot);

      const rimLight = new THREE.DirectionalLight(0xcfd8dc, 1.2);
      rimLight.position.set(-45, 65, -45);
      scene3D.add(rimLight);

      // 6. Interactive Raycasting
      raycaster3D = new THREE.Raycaster();
      mouse3D = new THREE.Vector2();

      renderer3D.domElement.addEventListener('pointerdown', on3DPointerDown);
      renderer3D.domElement.addEventListener('pointermove', on3DPointerMove);

      // 7. Selection Wireframe Box
      const boxGeo = new THREE.BoxGeometry(C_SIZE * 0.96, 2.5, C_SIZE * 0.96);
      const boxEdges = new THREE.EdgesGeometry(boxGeo);
      rackHighlightBox = new THREE.LineSegments(
        boxEdges,
        new THREE.LineBasicMaterial({ color: 0xffffff, linewidth: 2 })
      );
      rackHighlightBox.visible = false;
      scene3D.add(rackHighlightBox);
    }

    // =========================================================================
    // AUTHENTIC REAL AMR 3D ROBOT MODEL CONSTRUCTOR
    // =========================================================================
    function createRealAMR3D(botId, num) {
      const root = new THREE.Group();
      root.name = botId;

      // A. Lower Chassis (Industrial matte obsidian black base with safety bumpers)
      const chassisGeo = new THREE.BoxGeometry(1.24, 0.28, 0.96);
      const chassisMat = new THREE.MeshStandardMaterial({
        color: 0x141720,
        roughness: 0.5,
        metalness: 0.4
      });
      const chassis = new THREE.Mesh(chassisGeo, chassisMat);
      chassis.position.y = 0.20;
      root.add(chassis);

      // Front & rear safety bumpers (matte rubber with monochrome hazard bevels)
      const bumperGeo = new THREE.BoxGeometry(0.12, 0.20, 0.98);
      const bumperMat = new THREE.MeshStandardMaterial({ color: 0x050608, roughness: 0.9 });
      const frontBumper = new THREE.Mesh(bumperGeo, bumperMat);
      frontBumper.position.set(0.65, 0.20, 0);
      root.add(frontBumper);

      const rearBumper = new THREE.Mesh(bumperGeo, bumperMat);
      rearBumper.position.set(-0.65, 0.20, 0);
      root.add(rearBumper);

      // B. Upper Housing / Enclosure (Stark Polar White with black tech seam)
      const shellGeo = new THREE.BoxGeometry(1.14, 0.18, 0.88);
      const shellMat = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        roughness: 0.2,
        metalness: 0.1
      });
      const shell = new THREE.Mesh(shellGeo, shellMat);
      shell.position.y = 0.38;
      root.add(shell);

      // Center tech groove / pinstripe
      const groove = new THREE.Mesh(
        new THREE.BoxGeometry(1.16, 0.03, 0.26),
        new THREE.MeshStandardMaterial({ color: 0x0a0c10, roughness: 0.8 })
      );
      groove.position.y = 0.46;
      root.add(groove);

      // C. Drive Wheels (Textured rubber treads + bright silver center rims)
      const wheelGeo = new THREE.CylinderGeometry(0.18, 0.18, 0.08, 24);
      wheelGeo.rotateZ(Math.PI / 2);
      const tireMat = new THREE.MeshStandardMaterial({ color: 0x090b0e, roughness: 0.95 });
      const rimGeo = new THREE.CylinderGeometry(0.10, 0.10, 0.085, 16);
      rimGeo.rotateZ(Math.PI / 2);
      const rimMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.8, roughness: 0.2 });

      const leftWheel = new THREE.Group();
      leftWheel.add(new THREE.Mesh(wheelGeo, tireMat));
      leftWheel.add(new THREE.Mesh(rimGeo, rimMat));
      leftWheel.position.set(0, 0.18, 0.48);
      root.add(leftWheel);

      const rightWheel = new THREE.Group();
      rightWheel.add(new THREE.Mesh(wheelGeo, tireMat));
      rightWheel.add(new THREE.Mesh(rimGeo, rimMat));
      rightWheel.position.set(0, 0.18, -0.48);
      root.add(rightWheel);

      // Dual recessed swivel caster wheels
      const casterGeo = new THREE.SphereGeometry(0.08, 12, 12);
      const casterMat = new THREE.MeshStandardMaterial({ color: 0x27272a, metalness: 0.7 });
      const frontCaster = new THREE.Mesh(casterGeo, casterMat);
      frontCaster.position.set(0.44, 0.08, 0);
      root.add(frontCaster);
      const rearCaster = new THREE.Mesh(casterGeo, casterMat);
      rearCaster.position.set(-0.44, 0.08, 0);
      root.add(rearCaster);

      // D. Elevating / Rotating Turntable Lifting Deck
      const deckGroup = new THREE.Group();
      deckGroup.name = 'deckGroup';
      const turntableGeo = new THREE.CylinderGeometry(0.38, 0.38, 0.04, 32);
      const turntableMat = new THREE.MeshStandardMaterial({
        color: 0x272a33,
        metalness: 0.65,
        roughness: 0.35
      });
      const turntable = new THREE.Mesh(turntableGeo, turntableMat);
      deckGroup.add(turntable);

      // Non-slip concentric grip ring
      const gripRing = new THREE.Mesh(
        new THREE.TorusGeometry(0.26, 0.012, 8, 32),
        new THREE.MeshBasicMaterial({ color: 0x050608 })
      );
      gripRing.rotateX(Math.PI / 2);
      deckGroup.add(gripRing);

      // Telescoping scissor / hydraulic lift column
      const liftStem = new THREE.Mesh(
        new THREE.CylinderGeometry(0.10, 0.10, 0.22, 16),
        new THREE.MeshStandardMaterial({ color: 0xd4d4d8, metalness: 0.85, roughness: 0.2 })
      );
      liftStem.position.y = -0.11;
      deckGroup.add(liftStem);

      deckGroup.position.y = 0.44; // default down position
      root.add(deckGroup);

      // E. Active 360° Safety LiDAR Sensor Puck
      const lidarBase = new THREE.Mesh(
        new THREE.CylinderGeometry(0.06, 0.06, 0.05, 16),
        new THREE.MeshStandardMaterial({ color: 0x18181b, metalness: 0.6 })
      );
      lidarBase.position.set(0.44, 0.48, 0.28);
      root.add(lidarBase);

      const lidarDome = new THREE.Mesh(
        new THREE.CylinderGeometry(0.05, 0.05, 0.04, 16),
        new THREE.MeshStandardMaterial({ color: 0x000000, roughness: 0.1, metalness: 0.9 })
      );
      lidarDome.position.set(0.44, 0.52, 0.28);
      root.add(lidarDome);

      // Forward Safety LiDAR Laser Beam Fan (Semi-transparent pulsing cone)
      const laserGeo = new THREE.ConeGeometry(1.6, 1.3, 16, 1, true, -Math.PI / 4, Math.PI / 2);
      laserGeo.rotateZ(Math.PI / 2);
      laserGeo.rotateY(-Math.PI / 2);
      const laserMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.14,
        side: THREE.DoubleSide
      });
      const laserFan = new THREE.Mesh(laserGeo, laserMat);
      laserFan.position.set(0.50, 0.50, 0);
      laserFan.name = 'laserFan';
      root.add(laserFan);

      // F. Perimeter Status LED Halo
      const haloGeo = new THREE.BoxGeometry(1.26, 0.035, 0.98);
      const haloMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.95
      });
      const statusHalo = new THREE.Mesh(haloGeo, haloMat);
      statusHalo.position.y = 0.29;
      statusHalo.name = 'statusHalo';
      root.add(statusHalo);

      // Dual front headlights
      const hlMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
      const hlL = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.05, 0.08), hlMat);
      hlL.position.set(0.63, 0.29, 0.28);
      root.add(hlL);
      const hlR = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.05, 0.08), hlMat);
      hlR.position.set(0.63, 0.29, -0.28);
      root.add(hlR);

      // G. 3D Freight Cargo Tote Box (mounted on turntable)
      const cargoGroup = new THREE.Group();
      cargoGroup.name = 'cargoGroup';
      const toteGeo = new THREE.BoxGeometry(0.64, 0.36, 0.54);
      const toteMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.3, metalness: 0.1 });
      const tote = new THREE.Mesh(toteGeo, toteMat);
      tote.position.y = 0.18;
      cargoGroup.add(tote);

      // Dark reinforced lid
      const lid = new THREE.Mesh(
        new THREE.BoxGeometry(0.66, 0.05, 0.56),
        new THREE.MeshStandardMaterial({ color: 0x18181b, roughness: 0.6 })
      );
      lid.position.y = 0.38;
      cargoGroup.add(lid);

      // SKU / Barcode label
      const label = new THREE.Mesh(
        new THREE.PlaneGeometry(0.22, 0.13),
        new THREE.MeshBasicMaterial({ color: 0x090b0e })
      );
      label.position.set(0, 0.18, 0.272);
      cargoGroup.add(label);

      cargoGroup.visible = false;
      cargoGroup.position.y = 0.02;
      deckGroup.add(cargoGroup);

      // H. 3D Holographic Billboard Badge
      const spriteCanvas = document.createElement('canvas');
      spriteCanvas.width = 256;
      spriteCanvas.height = 128;
      const spriteCtx = spriteCanvas.getContext('2d');
      const spriteTexture = new THREE.CanvasTexture(spriteCanvas);
      const spriteMat = new THREE.SpriteMaterial({ map: spriteTexture, transparent: true });
      const billboard = new THREE.Sprite(spriteMat);
      billboard.position.set(0, 1.45, 0);
      billboard.scale.set(2.0, 1.0, 1.0);
      billboard.name = 'billboard';
      root.add(billboard);

      return {
        root,
        leftWheel,
        rightWheel,
        deckGroup,
        cargoGroup,
        lidarDome,
        laserFan,
        statusHalo,
        billboard,
        spriteCanvas,
        spriteCtx,
        spriteTexture
      };
    }

    // =========================================================================
    // BUILD 3D WAREHOUSE MAP, 5-TIER RACKS & STATIONS
    // =========================================================================
    function build3DMap() {
      if (!isWebGLAvailable() || typeof THREE === 'undefined' || !mapData || !scene3D) return;

      const floorW = mapData.width * C_SIZE;
      const floorH = mapData.height * C_SIZE;

      // 1. Warehouse Floor (Deep Matte Slate with Crisp White Guidelines)
      const floorCanvas = document.createElement('canvas');
      floorCanvas.width = 1024;
      floorCanvas.height = 1024;
      const fCtx = floorCanvas.getContext('2d');
      fCtx.fillStyle = '#11141b';
      fCtx.fillRect(0, 0, 1024, 1024);

      // Crisp white grid / lane markings
      fCtx.strokeStyle = 'rgba(255, 255, 255, 0.16)';
      fCtx.lineWidth = 1.5;
      for (let i = 0; i <= 1024; i += 64) {
        fCtx.beginPath(); fCtx.moveTo(i, 0); fCtx.lineTo(i, 1024); fCtx.stroke();
        fCtx.beginPath(); fCtx.moveTo(0, i); fCtx.lineTo(1024, i); fCtx.stroke();
      }

      // Outer boundary stripe
      fCtx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
      fCtx.lineWidth = 4;
      fCtx.strokeRect(4, 4, 1016, 1016);

      const floorTexture = new THREE.CanvasTexture(floorCanvas);
      floorTexture.wrapS = THREE.RepeatWrapping;
      floorTexture.wrapT = THREE.RepeatWrapping;
      floorTexture.repeat.set(mapData.width / 4, mapData.height / 4);

      const floorGeo = new THREE.PlaneGeometry(floorW, floorH);
      floorGeo.rotateX(-Math.PI / 2);
      const floorMat = new THREE.MeshStandardMaterial({
        map: floorTexture,
        roughness: 0.7,
        metalness: 0.2
      });
      floorMesh3D = new THREE.Mesh(floorGeo, floorMat);
      floorMesh3D.position.set(0, 0, 0);
      scene3D.add(floorMesh3D);

      // 2. High-Performance Multi-Tier Storage Racks (Black & White Theme)
      build3DStorageRacks();

      // 3. Functional Stations (Charging Bays, Inbound Docks, Outbound Bays)
      build3DStations();

      // 4. Autonomous Mobile Robots (AMR Fleet)
      build3DFleet();

      // 5. Dynamic 3D Trajectory Path Ribbons
      build3DPaths();
    }

    function build3DStorageRacks() {
      const rackPositions = [];
      for (let x = 1; x < mapData.width - 1; x++) {
        for (let y = 1; y < mapData.height - 1; y++) {
          if (mapData.grid[x][y] === 1) {
            rackPositions.push({ x, y });
          }
        }
      }

      const totalRacks = rackPositions.length;
      if (totalRacks === 0) return;

      // A. Corner Upright Steel Angle Posts (Matte Industrial Black Steel)
      const postGeo = new THREE.BoxGeometry(0.06, 2.4, 0.06);
      const postMat = new THREE.MeshStandardMaterial({
        color: 0x181c26,
        roughness: 0.5,
        metalness: 0.5
      });
      rackPostsMesh = new THREE.InstancedMesh(postGeo, postMat, totalRacks * 4);
      rackPostsMesh.name = 'rackPosts';

      // B. 5 Horizontal Shelf Decks (Stark Polar White / Brushed Silver)
      const shelfGeo = new THREE.BoxGeometry(C_SIZE * 0.92, 0.035, C_SIZE * 0.92);
      const shelfMat = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        roughness: 0.2,
        metalness: 0.2
      });
      rackShelvesMesh = new THREE.InstancedMesh(shelfGeo, shelfMat, totalRacks * 5);
      rackShelvesMesh.name = 'rackShelves';

      const dummy = new THREE.Object3D();
      let postIdx = 0;
      let shelfIdx = 0;

      const halfCell = C_SIZE * 0.44;
      const tierHeights = [0.45, 0.90, 1.35, 1.80, 2.25]; // 5 Shelf Tier Heights!

      for (let i = 0; i < totalRacks; i++) {
        const { x, y } = rackPositions[i];
        const pos = gridTo3D(x, y, 0);

        const corners = [
          [-halfCell, -halfCell],
          [halfCell, -halfCell],
          [-halfCell, halfCell],
          [halfCell, halfCell]
        ];
        for (const [cx, cz] of corners) {
          dummy.position.set(pos.x + cx, 1.2, pos.z + cz);
          dummy.updateMatrix();
          rackPostsMesh.setMatrixAt(postIdx++, dummy.matrix);
        }

        for (const th of tierHeights) {
          dummy.position.set(pos.x, th, pos.z);
          dummy.updateMatrix();
          rackShelvesMesh.setMatrixAt(shelfIdx++, dummy.matrix);
        }
      }

      rackPostsMesh.instanceMatrix.needsUpdate = true;
      rackShelvesMesh.instanceMatrix.needsUpdate = true;
      scene3D.add(rackPostsMesh);
      scene3D.add(rackShelvesMesh);

      // C. Dynamic 3D Parcel Totes on Racks
      const toteGeo = new THREE.BoxGeometry(0.55, 0.28, 0.45);
      const toteMat = new THREE.MeshStandardMaterial({
        color: 0xf8fafc,
        roughness: 0.3,
        metalness: 0.1
      });
      totesInstancedMesh = new THREE.InstancedMesh(toteGeo, toteMat, 3500);
      totesInstancedMesh.count = 0;
      totesInstancedMesh.name = 'rackTotes';
      scene3D.add(totesInstancedMesh);

      update3DRacksTotes();
    }

    function update3DRacksTotes() {
      if (!totesInstancedMesh || !rackMemory) return;

      const dummy = new THREE.Object3D();
      let toteCount = 0;
      const tierHeights = [0.60, 1.05, 1.50, 1.95, 2.40];

      for (const [key, rack] of Object.entries(rackMemory)) {
        if (!rack || !rack.floors) continue;
        const pos = gridTo3D(rack.x, rack.y, 0);

        for (let f = 0; f < 5; f++) {
          const item = rack.floors[f];
          if (item && !item.isReservedInbound) {
            dummy.position.set(pos.x, tierHeights[f], pos.z);
            dummy.updateMatrix();
            totesInstancedMesh.setMatrixAt(toteCount++, dummy.matrix);
            if (toteCount >= 3500) break;
          }
        }
        if (toteCount >= 3500) break;
      }

      totesInstancedMesh.count = toteCount;
      totesInstancedMesh.instanceMatrix.needsUpdate = true;
    }

    function build3DStations() {
      if (!mapData || !mapData.stations) return;

      for (const [sid, st] of Object.entries(mapData.stations)) {
        const pos = gridTo3D(st.x, st.y, 0);
        const type = st.station_type || st.type || '';

        if (type === 'charging' || sid.startsWith('CH')) {
          const padGeo = new THREE.BoxGeometry(C_SIZE * 0.90, 0.05, C_SIZE * 0.90);
          const padMat = new THREE.MeshStandardMaterial({
            color: 0x14532d,
            emissive: 0x22c55e,
            emissiveIntensity: 0.45
          });
          const pad = new THREE.Mesh(padGeo, padMat);
          pad.position.set(pos.x, 0.025, pos.z);
          scene3D.add(pad);

          const pylonGeo = new THREE.BoxGeometry(0.22, 1.5, 0.22);
          const pylonMat = new THREE.MeshStandardMaterial({ color: 0x1e2430, metalness: 0.8 });
          const pylon = new THREE.Mesh(pylonGeo, pylonMat);
          pylon.position.set(pos.x, 0.75, pos.z + (st.y < 25 ? -C_SIZE * 0.4 : C_SIZE * 0.4));
          scene3D.add(pylon);

          const ledGeo = new THREE.SphereGeometry(0.08, 12, 12);
          const ledMat = new THREE.MeshBasicMaterial({ color: 0x4ade80 });
          const led = new THREE.Mesh(ledGeo, ledMat);
          led.position.set(pos.x, 1.35, pos.z + (st.y < 25 ? -C_SIZE * 0.4 : C_SIZE * 0.4));
          scene3D.add(led);

        } else if (type === 'pickup' || sid.startsWith('P')) {
          const dockGeo = new THREE.BoxGeometry(C_SIZE * 0.92, 0.25, C_SIZE * 0.92);
          const dockMat = new THREE.MeshStandardMaterial({
            color: 0x1e293b,
            roughness: 0.5,
            metalness: 0.3
          });
          const dock = new THREE.Mesh(dockGeo, dockMat);
          dock.position.set(pos.x, 0.125, pos.z);
          scene3D.add(dock);

        } else if (type === 'dropoff' || sid.startsWith('D')) {
          const bayGeo = new THREE.BoxGeometry(C_SIZE * 0.92, 0.22, C_SIZE * 0.92);
          const bayMat = new THREE.MeshStandardMaterial({
            color: 0x1e293b,
            roughness: 0.5,
            metalness: 0.4
          });
          const bay = new THREE.Mesh(bayGeo, bayMat);
          bay.position.set(pos.x, 0.11, pos.z);
          scene3D.add(bay);
        }
      }
    }

    function build3DFleet() {
      for (const bot of AMR_FLEET) {
        const amrObj = createRealAMR3D(bot.id, bot.num);
        amrModels3D[bot.id] = amrObj;
        scene3D.add(amrObj.root);
      }
    }

    function build3DPaths() {
      for (const bot of AMR_FLEET) {
        const lineGeo = new THREE.BufferGeometry();
        const maxPoints = 120;
        const positions = new Float32Array(maxPoints * 3);
        lineGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));

        const lineMat = new THREE.LineDashedMaterial({
          color: 0xffffff,
          dashSize: 0.8,
          gapSize: 0.4,
          transparent: true,
          opacity: 0.55
        });
        const line = new THREE.Line(lineGeo, lineMat);
        line.computeLineDistances();
        line.visible = show3DPaths;
        scene3D.add(line);
        pathLineObjects3D[bot.id] = line;
      }
    }

    // =========================================================================
    // 3D SIMULATION SYNCHRONIZATION & ANIMATION UPDATE
    // =========================================================================
    function update3DRobots(dt) {
      if (!scene3D || !isWebGLAvailable() || typeof THREE === 'undefined') return;

      const nowMs = Date.now();

      for (const bot of AMR_FLEET) {
        const model = amrModels3D[bot.id];
        if (!model) continue;

        const worldPos = gridTo3D(bot.x, bot.y, 0);
        model.root.position.set(worldPos.x, 0, worldPos.z);
        model.root.rotation.y = -bot.heading + Math.PI / 2;

        if (bot.currentSpeed > 0.05 && !bot.isWaiting) {
          const spin = dt * bot.currentSpeed * 4.5;
          model.leftWheel.rotation.x += spin;
          model.rightWheel.rotation.x += spin;
        }

        model.lidarDome.rotation.y += 0.28;

        const hasInboundCargo = bot.isLoadedYellow || bot.state === 'LOADING_INBOUND' || bot.state === 'CARRYING_TO_RACK';
        const hasOrderBox = bot.orderBox !== null || bot.state === 'DELIVERING_ORDER_TO_BAY';
        const isLoaded = hasInboundCargo || hasOrderBox;

        if (isLoaded) {
          model.deckGroup.position.y = THREE.MathUtils.lerp(model.deckGroup.position.y, 0.58, 0.12);
          model.cargoGroup.visible = true;
        } else {
          model.deckGroup.position.y = THREE.MathUtils.lerp(model.deckGroup.position.y, 0.44, 0.12);
          model.cargoGroup.visible = false;
        }

        let haloColor = 0xffffff;
        if (bot.state === 'IDLE_CHARGING') {
          haloColor = 0x22c55e;
        } else if (bot.isWaiting) {
          haloColor = 0xf59e0b;
        } else if (bot.isOvertaking || bot.isRerouting) {
          haloColor = 0x38bdf8;
        } else if (hasInboundCargo) {
          haloColor = 0xfacc15;
        } else if (bot.battery <= 10.0 || bot.state === 'OUT_OF_CHARGE') {
          haloColor = 0xef4444;
        } else {
          haloColor = 0xffffff;
        }
        model.statusHalo.material.color.setHex(haloColor);

        model.laserFan.visible = showLidarBeams && bot.state !== 'IDLE_CHARGING';
        if (model.laserFan.visible) {
          const laserPulse = 0.12 + 0.06 * Math.sin(nowMs / 120);
          model.laserFan.material.opacity = laserPulse;
        }

        updateBotBillboard(model, bot);
        update3DPathForBot(bot);
      }

      if (Math.random() < 0.05) {
        update3DRacksTotes();
      }
    }

    function updateBotBillboard(model, bot) {
      const ctx = model.spriteCtx;
      ctx.clearRect(0, 0, 256, 128);

      ctx.fillStyle = 'rgba(9, 11, 16, 0.90)';
      ctx.strokeStyle = bot.id === trackedRobotId ? '#ffffff' : 'rgba(255, 255, 255, 0.28)';
      ctx.lineWidth = bot.id === trackedRobotId ? 3 : 1.5;

      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(10, 10, 236, 108, 12) : ctx.rect(10, 10, 236, 108);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 26px monospace';
      ctx.fillText(bot.id, 24, 46);

      const batPct = Math.round(bot.battery);
      let batColor = '#22c55e';
      if (batPct <= 20) batColor = '#ef4444';
      else if (batPct <= 45) batColor = '#f59e0b';

      ctx.fillStyle = batColor;
      ctx.font = 'bold 22px monospace';
      ctx.fillText(`${batPct}%`, 175, 46);

      ctx.fillStyle = '#1e222a';
      ctx.fillRect(24, 60, 208, 10);
      ctx.fillStyle = batColor;
      ctx.fillRect(24, 60, (208 * Math.max(0, Math.min(100, batPct))) / 100, 10);

      let stateLabel = bot.state.replace(/_/g, ' ');
      let labelColor = '#94a3b8';
      if (bot.state === 'IDLE_CHARGING') {
        stateLabel = '⚡ CHARGING';
        labelColor = '#4ade80';
      } else if (bot.state === 'RETURNING_HOME' || bot.battery <= 28.0) {
        stateLabel = '🔋 TO CHARGER (PRIORITY)';
        labelColor = '#34d399';
      } else if (bot.isOvertaking) {
        stateLabel = '🚀 OVERTAKING';
        labelColor = '#38bdf8';
      } else if (bot.statusBadge === 'SLOW') {
        stateLabel = '🟡 SLOW (CONTINUOUS)';
        labelColor = '#facc15';
      } else if (bot.isWaiting) {
        stateLabel = '⏳ YIELDING';
        labelColor = '#fbbf24';
      }

      ctx.fillStyle = labelColor;
      ctx.font = 'bold 14px sans-serif';
      ctx.fillText(stateLabel.slice(0, 24), 24, 96);

      model.spriteTexture.needsUpdate = true;
    }

    function update3DPathForBot(bot) {
      const line = pathLineObjects3D[bot.id];
      if (!line) return;

      line.visible = show3DPaths && bot.path && bot.path.length > bot.pathIndex;
      if (!line.visible) return;

      const pts = bot.path.slice(bot.pathIndex);
      const posAttr = line.geometry.attributes.position;
      const count = Math.min(pts.length + 1, 120);

      const botWorld = gridTo3D(bot.x, bot.y, 0.08);
      posAttr.setXYZ(0, botWorld.x, botWorld.y, botWorld.z);

      for (let i = 0; i < count - 1; i++) {
        const pt = pts[i];
        const wp = gridTo3D(pt.x, pt.y, 0.08);
        posAttr.setXYZ(i + 1, wp.x, wp.y, wp.z);
      }

      line.geometry.setDrawRange(0, count);
      posAttr.needsUpdate = true;
      line.computeLineDistances();

      if (bot.id === trackedRobotId) {
        line.material.color.setHex(0xffffff);
        line.material.opacity = 0.95;
      } else {
        line.material.color.setHex(0x94a3b8);
        line.material.opacity = 0.35;
      }
    }

    function update3DCamera(dt) {
      if (!camera3D || !controls3D) return;

      if (cameraMode === 'follow' && trackedRobotId) {
        const trackedBot = AMR_FLEET.find(b => b.id === trackedRobotId);
        if (trackedBot) {
          const bPos = gridTo3D(trackedBot.x, trackedBot.y, 0.4);
          const dirX = Math.cos(trackedBot.heading);
          const dirZ = Math.sin(trackedBot.heading);

          const camTargetPos = new THREE.Vector3(
            bPos.x - dirX * 9.0,
            6.5,
            bPos.z - dirZ * 9.0
          );
          camera3D.position.lerp(camTargetPos, 0.08);
          controls3D.target.lerp(new THREE.Vector3(bPos.x, 0.5, bPos.z), 0.1);
        }
      }

      controls3D.update();
    }

    // =========================================================================
    // INTERACTIVE RAYCASTING (CLICK & HOVER IN 3D)
    // =========================================================================
    function on3DPointerDown(e) {
      if (e.button !== 0 || !camera3D || !scene3D) return;

      const container = document.getElementById('viewport-3d');
      if (!container) return;
      const rect = container.getBoundingClientRect();

      mouse3D.x = ((e.clientX - rect.left) / container.clientWidth) * 2 - 1;
      mouse3D.y = -((e.clientY - rect.top) / container.clientHeight) * 2 + 1;

      raycaster3D.setFromCamera(mouse3D, camera3D);

      const robotRoots = Object.values(amrModels3D).map(m => m.root);
      const botHits = raycaster3D.intersectObjects(robotRoots, true);

      if (botHits.length > 0) {
        let hitObj = botHits[0].object;
        while (hitObj.parent && !hitObj.name.startsWith('AMR-')) {
          hitObj = hitObj.parent;
        }
        if (hitObj.name.startsWith('AMR-')) {
          trackBot(hitObj.name, true);
          return;
        }
      }

      if (floorMesh3D) {
        const floorHits = raycaster3D.intersectObject(floorMesh3D);
        if (floorHits.length > 0) {
          const hit = floorHits[0].point;
          const gx = Math.round(hit.x / C_SIZE + HALF_W - 0.5);
          const gy = Math.round(hit.z / C_SIZE + HALF_H - 0.5);

          if (gx >= 0 && gx < mapData.width && gy >= 0 && gy < mapData.height) {
            const cellType = mapData.grid[gx][gy];
            if (cellType === 1 && gx > 0 && gx < mapData.width - 1 && gy > 0 && gy < mapData.height - 1) {
              openRackInspector(gx, gy);
              return;
            }
          }
        }
      }

      closeRackInspector();
    }

    function on3DPointerMove(e) {
      if (!camera3D || !scene3D) return;
      const container = document.getElementById('viewport-3d');
      if (!container) return;
      const rect = container.getBoundingClientRect();

      mouse3D.x = ((e.clientX - rect.left) / container.clientWidth) * 2 - 1;
      mouse3D.y = -((e.clientY - rect.top) / container.clientHeight) * 2 + 1;

      raycaster3D.setFromCamera(mouse3D, camera3D);
      const robotRoots = Object.values(amrModels3D).map(m => m.root);
      const hits = raycaster3D.intersectObjects(robotRoots, true);

      if (hits.length > 0) {
        container.style.cursor = 'pointer';
      } else {
        container.style.cursor = 'default';
      }
    }

    function openRackInspector(gx, gy) {
      const rackKey = `${gx},${gy}`;
      const rack = rackMemory[rackKey];
      if (!rack) return;

      selected3DRack = rack;

      if (rackHighlightBox) {
        const wPos = gridTo3D(gx, gy, 1.25);
        rackHighlightBox.position.set(wPos.x, wPos.y, wPos.z);
        rackHighlightBox.visible = true;
      }

      const card = document.getElementById('rack-inspector-card');
      const title = document.getElementById('rack-insp-title');
      const catName = document.getElementById('rack-insp-cat-name');
      const coords = document.getElementById('rack-insp-coords');
      const occ = document.getElementById('rack-insp-occ');
      const tiersList = document.getElementById('rack-insp-tiers-list');

      if (!card || !title || !tiersList) return;

      title.innerText = `Rack Pod [${gx}, ${gy}]`;
      catName.innerText = rack.categoryFullName || rack.categoryName || 'General Goods';
      coords.innerText = `(${gx}, ${gy})`;

      const occCount = rack.floors.filter(f => f !== null && !f.isReservedInbound).length;
      occ.innerText = `${occCount} / 5 Tiers (${Math.round((occCount / 5) * 100)}%)`;

      let html = '';
      for (let f = 4; f >= 0; f--) {
        const item = rack.floors[f];
        const isOcc = item !== null && !item.isReservedInbound;
        html += `
          <div class="rack-tier-row ${isOcc ? 'occupied' : ''}">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="tier-dot ${isOcc ? 'active' : ''}"></span>
              <strong style="color:#ffffff;">Level ${f + 1}</strong>
            </div>
            <div>
              ${isOcc ? `<span style="color:#f8fafc; font-weight:600;">${item.parcel_id}</span> <span style="color:#94a3b8; font-size:10px;">(${item.weight})</span>` : '<span style="color:#64748b; font-style:italic;">Empty Shelf</span>'}
            </div>
          </div>
        `;
      }
      tiersList.innerHTML = html;
      card.style.display = 'block';
    }

    function closeRackInspector() {
      selected3DRack = null;
      if (rackHighlightBox) rackHighlightBox.visible = false;
      const card = document.getElementById('rack-inspector-card');
      if (card) card.style.display = 'none';
    }

    // =========================================================================
    // VIEW CONTROLS & CAMERA PRESETS
    // =========================================================================
    function switchViewMode(mode) {
      viewMode = mode;
      const btn3D = document.getElementById('btn-view-3d');
      const btn2D = document.getElementById('btn-view-2d');
      const view3D = document.getElementById('viewport-3d');
      const view2D = document.getElementById('viewport');
      const hint = document.getElementById('view-3d-hint');

      if (btn3D) btn3D.classList.toggle('active', mode === '3D');
      if (btn2D) btn2D.classList.toggle('active', mode === '2D');

      if (mode === '3D') {
        if (view3D) view3D.style.display = 'block';
        if (view2D) view2D.style.display = 'none';
        if (hint) hint.style.display = 'flex';
        resize3D();
      } else {
        if (view3D) view3D.style.display = 'none';
        if (view2D) view2D.style.display = 'block';
        if (hint) hint.style.display = 'none';
        resize();
        render();
      }
    }

    function setCameraMode(mode) {
      cameraMode = mode;
      const btns = ['orbit', 'follow', 'iso', 'top'];
      btns.forEach(b => {
        const el = document.getElementById(`btn-cam-${b}`);
        if (el) el.classList.toggle('active', b === mode);
      });

      if (!camera3D || !controls3D) return;

      if (mode === 'orbit') {
        controls3D.target.set(0, 0, 0);
      } else if (mode === 'iso') {
        camera3D.position.set(-50, 55, 55);
        controls3D.target.set(0, 0, 0);
      } else if (mode === 'top') {
        camera3D.position.set(0, 95, 0.001);
        controls3D.target.set(0, 0, 0);
      } else if (mode === 'follow') {
        if (!trackedRobotId && AMR_FLEET.length > 0) {
          trackBot(AMR_FLEET[0].id, true);
        }
      }
    }

    function toggleLidarBeams() {
      showLidarBeams = !showLidarBeams;
      const btn = document.getElementById('btn-toggle-lidar');
      if (btn) btn.classList.toggle('active', showLidarBeams);
    }

    function toggle3DPaths() {
      show3DPaths = !show3DPaths;
      const btn = document.getElementById('btn-toggle-paths');
      if (btn) btn.classList.toggle('active', show3DPaths);
    }

    function toggleWireframe() {
      wireframeMode = !wireframeMode;
      const btn = document.getElementById('btn-toggle-wire');
      if (btn) btn.classList.toggle('active', wireframeMode);
      if (rackPostsMesh) rackPostsMesh.material.wireframe = wireframeMode;
      if (rackShelvesMesh) rackShelvesMesh.material.wireframe = wireframeMode;
    }

    function resize3D() {
      if (!renderer3D || !camera3D) return;
      const container = document.getElementById('viewport-3d');
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w === 0 || h === 0) return;
      camera3D.aspect = w / h;
      camera3D.updateProjectionMatrix();
      renderer3D.setSize(w, h);
    }

    window.addEventListener('resize', () => {
      resize();
      resize3D();
    });

    // =========================================================================
    // 3D PROCEDURAL HUMAN WORKERS, OBSTACLES & DECENTRALIZED V2V MESH
    // =========================================================================
    let humanModels3D = {};
    let obstacleModels3D = {};
    let v2vMeshGroup3D = null;
    let v2vLines3D = null;

    function createHuman3DModel(worker) {
      const root = new THREE.Group();
      root.name = worker.id;

      const bodyGroup = new THREE.Group();

      // Boots
      const bootMat = new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.8 });
      const bootGeo = new THREE.BoxGeometry(0.12, 0.10, 0.22);
      const bootL = new THREE.Mesh(bootGeo, bootMat);
      bootL.position.set(-0.12, 0.05, 0.02);
      const bootR = new THREE.Mesh(bootGeo, bootMat);
      bootR.position.set(0.12, 0.05, 0.02);

      // Legs
      const pantsMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.7 });
      const legGeo = new THREE.CylinderGeometry(0.07, 0.065, 0.65, 12);
      const legL = new THREE.Mesh(legGeo, pantsMat);
      legL.position.set(-0.12, 0.42, 0);
      const legR = new THREE.Mesh(legGeo, pantsMat);
      legR.position.set(0.12, 0.42, 0);

      // Torso with High-Vis Safety Vest
      const vestMat = new THREE.MeshStandardMaterial({ color: 0xfacc15, roughness: 0.5 });
      const torsoGeo = new THREE.BoxGeometry(0.36, 0.52, 0.22);
      const torso = new THREE.Mesh(torsoGeo, vestMat);
      torso.position.set(0, 0.98, 0);

      // Reflective Silver Bands on Vest
      const stripeMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.2 });
      const stripeHoriz = new THREE.Mesh(new THREE.BoxGeometry(0.37, 0.08, 0.23), stripeMat);
      stripeHoriz.position.set(0, 0.96, 0);

      // Arms & Barcode Scanner Tablet
      const armMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.7 });
      const armGeo = new THREE.CylinderGeometry(0.05, 0.05, 0.42, 8);
      const armL = new THREE.Mesh(armGeo, armMat);
      armL.position.set(-0.24, 0.96, 0);
      armL.rotation.x = -0.3;

      const armR = new THREE.Mesh(armGeo, armMat);
      armR.position.set(0.24, 0.96, 0);
      armR.rotation.x = -0.3;

      const tabletMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.3, emissive: 0x00f0ff, emissiveIntensity: 0.4 });
      const tablet = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.12, 0.02), tabletMat);
      tablet.position.set(0, 0.88, 0.22);
      tablet.rotation.x = -0.5;

      // Head
      const headMat = new THREE.MeshStandardMaterial({ color: 0xfbd38d, roughness: 0.6 });
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 16), headMat);
      head.position.set(0, 1.34, 0);

      // Safety Hard Hat (White)
      const helmetMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 });
      const helmetDome = new THREE.Mesh(new THREE.SphereGeometry(0.14, 16, 16), helmetMat);
      helmetDome.position.set(0, 1.38, 0);
      helmetDome.scale.set(1.0, 0.8, 1.1);

      const helmetBrim = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.02, 16), helmetMat);
      helmetBrim.position.set(0, 1.32, 0);

      bodyGroup.add(bootL, bootR, legL, legR, torso, stripeHoriz, armL, armR, tablet, head, helmetDome, helmetBrim);
      root.add(bodyGroup);

      // Calibrated Tight ISO 3691-4 Safety Rings (0.80m Stop Halo, 1.35m Caution Halo)
      const innerRingGeo = new THREE.RingGeometry(0.78, 0.84, 32);
      innerRingGeo.rotateX(-Math.PI / 2);
      const innerRingMat = new THREE.MeshBasicMaterial({ color: 0xef4444, transparent: true, opacity: 0.55, side: THREE.DoubleSide });
      const innerRing = new THREE.Mesh(innerRingGeo, innerRingMat);
      innerRing.position.y = 0.03;
      root.add(innerRing);

      const outerRingGeo = new THREE.RingGeometry(1.30, 1.36, 32);
      outerRingGeo.rotateX(-Math.PI / 2);
      const outerRingMat = new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.35, side: THREE.DoubleSide });
      const outerRing = new THREE.Mesh(outerRingGeo, outerRingMat);
      outerRing.position.y = 0.02;
      root.add(outerRing);

      // Floating 3D Billboard Canvas Sprite
      const canvas = document.createElement('canvas');
      canvas.width = 256;
      canvas.height = 96;
      const ctx = canvas.getContext('2d');
      const spriteTexture = new THREE.CanvasTexture(canvas);
      spriteTexture.minFilter = THREE.LinearFilter;
      const spriteMat = new THREE.SpriteMaterial({ map: spriteTexture, transparent: true });
      const sprite = new THREE.Sprite(spriteMat);
      sprite.position.set(0, 1.85, 0);
      sprite.scale.set(2.8, 1.05, 1);
      root.add(sprite);

      return {
        root,
        bodyGroup,
        legL,
        legR,
        armL,
        armR,
        spriteCtx: ctx,
        spriteTexture,
        sprite
      };
    }

    function updateHumanBillboard(model, worker) {
      const ctx = model.spriteCtx;
      ctx.clearRect(0, 0, 256, 96);

      ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
      ctx.strokeStyle = '#facc15';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(8, 8, 240, 80, 10) : ctx.rect(8, 8, 240, 80);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 20px monospace';
      ctx.fillText(`👷 ${worker.name}`, 18, 38);

      ctx.fillStyle = '#facc15';
      ctx.font = 'bold 13px sans-serif';
      ctx.fillText(worker.currentAction ? worker.currentAction.slice(0, 24) : 'Patrolling', 18, 68);

      model.spriteTexture.needsUpdate = true;
    }

    function createPalletCart3DModel(cart) {
      const root = new THREE.Group();
      root.name = cart.id;
      const pos = gridTo3D(cart.x, cart.y, 0.0);
      root.position.set(pos.x, 0, pos.z);

      const palletMat = new THREE.MeshStandardMaterial({ color: 0x855a30, roughness: 0.9 });
      const pallet = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.16, 1.4), palletMat);
      pallet.position.set(0, 0.08, 0);
      root.add(pallet);

      const boxMat = new THREE.MeshStandardMaterial({ color: 0xd97706, roughness: 0.8 });
      const box1 = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.6, 0.55), boxMat);
      box1.position.set(-0.25, 0.46, -0.25);
      const box2 = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.6, 0.55), boxMat);
      box2.position.set(0.25, 0.46, 0.25);
      root.add(box1, box2);

      const beaconMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, emissive: 0xf59e0b, emissiveIntensity: 0.8, transparent: true, opacity: 0.9 });
      const beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.10, 0.18, 12), beaconMat);
      beacon.position.set(0, 0.85, 0);
      root.add(beacon);

      return { root, beacon };
    }

    function update3DObstacles(dt) {
      if (!scene3D || typeof DYNAMIC_OBSTACLES === 'undefined') return;

      for (const obs of DYNAMIC_OBSTACLES) {
        if (obs.type === 'human') {
          let hModel = humanModels3D[obs.id];
          if (!hModel) {
            hModel = createHuman3DModel(obs);
            humanModels3D[obs.id] = hModel;
            scene3D.add(hModel.root);
          }
          hModel.root.visible = (typeof dynamicObstaclesEnabled === 'undefined' || dynamicObstaclesEnabled);
          if (!hModel.root.visible) continue;

          const pos = gridTo3D(obs.x, obs.y, 0.0);
          hModel.root.position.set(pos.x, 0, pos.z);
          hModel.root.rotation.y = -obs.heading + Math.PI / 2;

          const isWalking = !obs.isPaused;
          const animTime = performance.now() / 150;
          if (isWalking) {
            hModel.legL.rotation.x = Math.sin(animTime) * 0.45;
            hModel.legR.rotation.x = -Math.sin(animTime) * 0.45;
            hModel.armL.rotation.x = -Math.sin(animTime) * 0.35;
          } else {
            hModel.legL.rotation.x = 0;
            hModel.legR.rotation.x = 0;
            hModel.armL.rotation.x = -0.3;
          }

          if (hModel.spriteCtx && Math.random() < 0.1) {
            updateHumanBillboard(hModel, obs);
          }
        } else if (obs.type === 'pallet_cart') {
          let cModel = obstacleModels3D[obs.id];
          if (!cModel) {
            cModel = createPalletCart3DModel(obs);
            obstacleModels3D[obs.id] = cModel;
            scene3D.add(cModel.root);
          }
          cModel.root.visible = (typeof dynamicObstaclesEnabled === 'undefined' || dynamicObstaclesEnabled);
          if (cModel.beacon) {
            cModel.beacon.material.opacity = 0.5 + 0.5 * Math.sin(performance.now() / 120);
          }
        }
      }
    }

    function update3DV2VMesh(dt) {
      if (!scene3D) return;

      if (!v2vMeshGroup3D) {
        v2vMeshGroup3D = new THREE.Group();
        v2vMeshGroup3D.name = 'v2vMeshGroup';
        scene3D.add(v2vMeshGroup3D);
      }

      v2vMeshGroup3D.visible = (typeof v2vMeshEnabled === 'undefined' || v2vMeshEnabled);
      if (!v2vMeshGroup3D.visible) return;

      const links = typeof v2vLinks !== 'undefined' ? v2vLinks : [];
      const lineCount = links.length;

      if (!v2vLines3D || v2vLines3D.userData.count !== lineCount) {
        v2vMeshGroup3D.clear();
        const positions = new Float32Array(Math.max(1, lineCount) * 6);
        const colors = new Float32Array(Math.max(1, lineCount) * 6);
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const mat = new THREE.LineBasicMaterial({
          vertexColors: true,
          transparent: true,
          opacity: 0.65,
          blending: THREE.AdditiveBlending
        });
        v2vLines3D = new THREE.LineSegments(geo, mat);
        v2vLines3D.userData.count = lineCount;
        v2vMeshGroup3D.add(v2vLines3D);
      }

      if (lineCount === 0) return;

      const posAttr = v2vLines3D.geometry.attributes.position;
      const colAttr = v2vLines3D.geometry.attributes.color;
      const now = performance.now() / 1000;

      for (let i = 0; i < lineCount; i++) {
        const link = links[i];
        const pA = gridTo3D(link.botA.x, link.botA.y, 0.42);
        const pB = gridTo3D(link.botB.x, link.botB.y, 0.42);

        posAttr.setXYZ(i * 2, pA.x, pA.y, pA.z);
        posAttr.setXYZ(i * 2 + 1, pB.x, pB.y, pB.z);

        const pulse = link.activePulse ? 1.0 : (0.28 + 0.15 * Math.sin(now * 4 + i));
        const r = link.activePulse ? 1.0 : 0.0;
        const g = link.activePulse ? 1.0 : 0.85 * pulse;
        const b = link.activePulse ? 1.0 : 1.0 * pulse;

        colAttr.setXYZ(i * 2, r, g, b);
        colAttr.setXYZ(i * 2 + 1, r, g, b);
      }

      posAttr.needsUpdate = true;
      colAttr.needsUpdate = true;
    }

    function render3D(dt) {
      if (!renderer3D || !scene3D || !camera3D) return;
      update3DRobots(dt);
      update3DObstacles(dt);
      update3DV2VMesh(dt);
      update3DCamera(dt);
      renderer3D.render(scene3D, camera3D);
    }
"""

# Combine into single index.html with EXACTLY ONE <script> and ONE </script>
full_index_html = (
    html_pre
    + "<script>\n"
    + "/* --- THREE.JS BUNDLE --- */\n"
    + three_code + "\n"
    + orbit_code + "\n"
    + "/* --- CORE FLEET SIMULATION LOGIC --- */\n"
    + js_engine + "\n"
    + "/* --- 3D DIGITAL TWIN & REAL AMR INDUSTRIAL MODEL --- */\n"
    + js_3d_engine + "\n"
    + "</script>"
    + html_post
)

with open("templates/index.html", "w", encoding="utf-8") as f:
    f.write(full_index_html)

print("Generated templates/index.html successfully!")
print("File size:", len(full_index_html), "bytes")
