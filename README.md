# AMR Fleet Mission Control - Interactive 3D Digital Twin

A high-fidelity 3D Digital Twin and Mission Control simulator for autonomous warehouse operations featuring Autonomous Mobile Robots (AMRs), 5-tier storage racks, dynamic human worker obstacles, and a decentralized V2V communication mesh.

---

## 🌟 Key Features

### 1. 3D Digital Twin & Industrial Visuals
- **Black & White Industrial Theme**: High-contrast, clean matte black structural framing with stark white tier shelves and storage totes.
- **5-Tier Storage Racks**: 1,512 rack pods with 5 vertical tiers each (7,560 total storage locations).
- **Realistic AMR 3D Robot Models**:
  - Industrial low-profile dual-tone chassis with drive wheels and swivel casters.
  - Active rotating & elevating turntable cargo lift deck.
  - Front-mounted 360° LiDAR puck sensor with real-time beam sweep visualization.
  - Live 3D floating HUD info billboards above each robot showing ID, status, and battery SoC %.
  - Dynamic status LEDs (cyan = inbound carry, orange = outbound retrieve, green = transit, amber = yield, red = critical battery).
- **Interactive Camera Controls**:
  - **Orbit**: Left Click to rotate, Right Click to pan, Scroll to zoom.
  - **Follow AMR**: Locks the camera directly behind any selected robot in third-person chase-cam.
  - **Isometric & Top-Down**: One-click perspective switching.
  - **Toggles**: Real-time LiDAR sweeps, path trails, wireframe mode, V2V mesh links, and 3D/2D switch.
- **Direct Interactive Inspection**:
  - Click any AMR robot or rack pod to view real-time diagnostics (velocity, BMS power draw, cargo manifest, tier slot inventory).

### 2. Dynamic Obstacles & Human Workers (ISO 3691-4 Safety)
- **Procedural 3D Human Workers**:
  - Animated warehouse auditors (e.g., Alex, Sarah) walking inspection routes with leg swing and holding scanner tablets with glowing screens.
  - ISO 3691-4 safety field circles on the warehouse floor (Red Inner Emergency Stop Zone $r=1.8\text{m}$, Amber Outer Caution Slow Zone $r=3.2\text{m}$).
- **Staging Pallet Carts**:
  - Stationary obstacle carts with hazard warning stripes and flashing amber warning beacons.
- **LiDAR Perception & Safety Braking**:
  - **Emergency Stop Zone ($<1.8\text{m}$)**: Immediate AEB brake! AMRs yield absolute priority to humans.
  - **Deceleration Zone ($1.8\text{m} - 3.5\text{m}$)**: AMRs smoothly slow down to 35% speed.
  - **Autonomous Detour Rerouting**: If an obstacle persists ($>1.2\text{s}$), the AMR uses inner traffic simulation to compute an optimal bypass around the human without deadlocking.

### 3. Decentralized V2V Mesh Communication Gateway
- **Peer-to-Peer RF Mesh Network (C-V2X 5.9 GHz)**:
  - 22-meter wireless communication radius between AMRs with dynamic RSSI signal calculation.
  - Visualized as pulsing electric cyan RF links and active packet transmission waves.
- **Decentralized Protocols**:
  - **`OBSTACLE_ALERT`**: Any robot that perceives a human or obstacle immediately broadcasts a hazard packet across the mesh. Nearby robots proactively detour *before* reaching the blocked aisle!
  - **`RIGHT_OF_WAY_HANDSHAKE`**: Consensual arbitration when paths intersect (lowest battery & highest mission urgency wins priority; losing bot yields).
  - **`HEARTBEAT`**: Periodic status and planned trajectory reservation exchange.
- **V2V Gateway HUD Drawer**:
  - View real-time active nodes, RF link counts, mesh connectivity %, and live decentralized packet stream.
  - Interactive controls to toggle RF links, toggle workers, or spawn new human workers and pallet carts dynamically!

### 4. Autonomous Logistics & Fleet Logic
- **Decentralized Pathfinding & Collision Avoidance**:
  - A* search with dynamic reservation tables and shared V2V hazard costmaps.
  - Automatic yielding, safe priority overtaking, and anti-deadlock rerouting.
- **Multi-Tier Inventory Operations**:
  - Dynamic assignment for inbound receiving, tier shelving, and outbound picking.
- **Automated BMS Fast Charging**:
  - Smart battery management with automatic return-to-charger protocols.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.9+ installed on your system.

### Option 1: One-Click Run (Windows)
Double-click `run.bat`.

### Option 2: Command Line
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the Mission Control server:
   ```bash
   python server.py
   ```
3. Open your browser at:
   ```
   http://localhost:8000
   ```

---

## 🧪 Automated Verification & Testing
To run the simulation and collision verification suites (requires Node.js):

- **Endurance Simulation & Battery Verification**:
  ```bash
  node test_sim.js
  ```
- **Spatial Clipping & Overlap Verification**:
  ```bash
  node test_clipping.js
  ```
- **Telemetry & Event Log Verification**:
  ```bash
  node test_logs.js
  ```

---

## 📁 Project Structure
```
├── server.py              # FastAPI server, WebSocket dispatch, V2V mesh & simulation logic
├── warehouse_map.py       # 80x50 warehouse grid topology & zones
├── inventory.py           # 5-tier inventory management & SKU allocation
├── build_full_app.py      # 3D Digital Twin compiler with inlined Three.js & OrbitControls
├── static/                # Three.js & OrbitControls libraries
├── templates/             # index.html (Interactive 3D Mission Control & V2V Gateway)
├── run.bat                # Windows 1-click startup script
├── requirements.txt       # Python package dependencies
├── test_sim.js            # Automated fleet simulation endurance verification test
├── test_clipping.js       # Robot collision & clipping test
└── test_logs.js           # Event logging test
```
