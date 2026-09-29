const http = require('http');

http.get('http://127.0.0.1:8000', (res) => {
  let html = '';
  res.on('data', chunk => html += chunk);
  res.on('end', () => {
    const scriptStart = html.indexOf('<script>');
    const scriptEnd = html.lastIndexOf('</script>');
    const scriptCode = html.slice(scriptStart + 8, scriptEnd);

    const canvas = {
      width: 1920, height: 1080, parentElement: { clientWidth: 1920, clientHeight: 1080 },
      addEventListener: () => {},
      getContext: () => ({
        save: () => {}, restore: () => {}, beginPath: () => {}, arc: () => {}, fill: () => {}, stroke: () => {},
        fillRect: () => {}, strokeRect: () => {}, fillText: () => {}, measureText: () => ({ width: 10 }),
        translate: () => {}, scale: () => {}, setLineDash: () => {}, moveTo: () => {}, lineTo: () => {}, arcTo: () => {}, clearRect: () => {}
      })
    };
    const window = { addEventListener: () => {}, devicePixelRatio: 1, innerWidth: 1920, innerHeight: 1080 };
    const document = {
      getElementById: (id) => {
        if (id === 'viewport') return canvas;
        return {
          style: {}, classList: { add: () => {}, remove: () => {}, toggle: () => {} },
          innerText: '', innerHTML: '', appendChild: () => {}, removeChild: () => {}, children: []
        };
      },
      querySelectorAll: () => [],
      createElement: () => ({ className: '', setAttribute: () => {}, style: {}, innerHTML: '' })
    };
    const performance = { now: () => Date.now() };

    http.get('http://127.0.0.1:8000/api/map', (mRes) => {
      let mJson = '';
      mRes.on('data', c => mJson += c);
      mRes.on('end', () => {
        const mapData = JSON.parse(mJson);
        const fetch = async (url) => {
          if (url === '/api/map') return { json: async () => mapData };
          return { catch: () => {} };
        };

        const sandbox = {
          window, document, canvas, performance, fetch,
          requestAnimationFrame: () => {}, setInterval: () => {}, clearInterval: () => {}, setTimeout: () => {}, alert: () => {},
          Math, Date, Set, Object, Array, Int32Array, Uint8Array, parseInt, parseFloat,
          console: { log: () => {}, warn: () => {}, error: () => {} }
        };

        const vm = require('vm');
        vm.createContext(sandbox);
        vm.runInContext(scriptCode, sandbox);

        const getScope = vm.runInContext(`() => ({
          AMR_FLEET, inboundMissions, outboundMissions, inboundQueues, outboundOrders,
          getBestRobotForTask, evaluateMissionEnergyFeasibility, initRackMemory, initAmrFleet,
          updateRobots, runFleetWatchdog, triggerInboundShipment, triggerOutboundOrder,
          setLogTerminal: (fn) => { logTerminal = fn; },
          setMapData: (m) => { mapData = m; },
          trafficMetrics, FLEET_INCIDENTS
        })`, sandbox)();

        getScope.setMapData(mapData);
        getScope.initRackMemory();
        getScope.initAmrFleet();

        const AMR_FLEET = getScope.AMR_FLEET;
        getScope.setLogTerminal(() => {});

        let nonAdjacentPathViolations = 0;
        let rackPenetrations = 0;
        let kissingEvents = 0;

        const dt = 0.05;
        let simSeconds = 0;
        let lastInbound = 0;
        let lastOutbound = 0;

        for (let step = 0; step < 6000; step++) {
          simSeconds += dt;
          if (simSeconds - lastInbound >= 8.0) {
            lastInbound = simSeconds;
            getScope.triggerInboundShipment();
          }
          if (simSeconds - lastOutbound >= 9.0) {
            lastOutbound = simSeconds;
            getScope.triggerOutboundOrder();
          }

          getScope.updateRobots(dt);
          getScope.runFleetWatchdog(Date.now() + Math.round(simSeconds * 1000));

          // Invariant Check 1: Non-adjacent path steps
          for (const bot of AMR_FLEET) {
            if (bot.path && bot.path.length > 1) {
              for (let i = 0; i < bot.path.length - 1; i++) {
                const p1 = bot.path[i];
                const p2 = bot.path[i + 1];
                const manhattan = Math.abs(p1.x - p2.x) + Math.abs(p1.y - p2.y);
                if (manhattan > 1) {
                  nonAdjacentPathViolations++;
                  if (nonAdjacentPathViolations <= 5) {
                    console.log(`[VIOLATION] Non-adjacent step in ${bot.id}: (${p1.x},${p1.y}) -> (${p2.x},${p2.y}) dist=${manhattan} [isOvertaking=${bot.isOvertaking}, isRerouting=${bot.isRerouting}, state=${bot.state}]`);
                  }
                }
              }
            }

            // Invariant Check 2: Physical rack collision / penetration
            const gx = Math.round(bot.x);
            const gy = Math.round(bot.y);
            if (gx >= 0 && gx < mapData.width && gy >= 0 && gy < mapData.height) {
              if (mapData.grid[gx][gy] === 1) {
                rackPenetrations++;
                if (rackPenetrations <= 5) {
                  console.log(`[PENETRATION] ${bot.id} at (${bot.x.toFixed(2)}, ${bot.y.toFixed(2)}) inside rack (${gx},${gy})!`);
                }
              }
            }
          }

          // Invariant Check 3: "Kissing" (head-on < 0.70)
          for (let i = 0; i < AMR_FLEET.length; i++) {
            for (let j = i + 1; j < AMR_FLEET.length; j++) {
              const A = AMR_FLEET[i];
              const B = AMR_FLEET[j];
              const dist = Math.hypot(A.x - B.x, A.y - B.y);
              if (dist < 0.70 && A.state !== 'IDLE_CHARGING' && B.state !== 'IDLE_CHARGING') {
                kissingEvents++;
              }
            }
          }
        }

        console.log(`\nResults over 6000 steps (300 sim-seconds):`);
        console.log(`- Non-adjacent path jumps: ${nonAdjacentPathViolations}`);
        console.log(`- Rack pod penetrations: ${rackPenetrations}`);
        console.log(`- Kissing / overlap (<0.70) events: ${kissingEvents}`);
        process.exit(0);
      });
    });
  });
});
