// Headless simulation endurance test
const http = require('http');

http.get('http://127.0.0.1:8000', (res) => {
  let html = '';
  res.on('data', chunk => html += chunk);
  res.on('end', () => {
    // Extract script content
    const scriptStart = html.indexOf('<script>');
    const scriptEnd = html.lastIndexOf('</script>');
    const scriptCode = html.slice(scriptStart + 8, scriptEnd);

    // Mock browser environment
    const logs = [];
    const window = {
      addEventListener: () => {},
      devicePixelRatio: 1,
      innerWidth: 1920,
      innerHeight: 1080
    };
    const document = {
      getElementById: (id) => {
        if (id === 'viewport') return canvas;
        return {
          style: {},
          classList: { add: () => {}, remove: () => {}, toggle: () => {} },
          innerText: '',
          innerHTML: '',
          appendChild: () => {},
          removeChild: () => {},
          children: []
        };
      },
      querySelectorAll: () => [],
      createElement: () => ({
        className: '',
        setAttribute: () => {},
        style: {},
        innerHTML: ''
      })
    };
    const canvas = {
      width: 1920,
      height: 1080,
      parentElement: { clientWidth: 1920, clientHeight: 1080 },
      addEventListener: () => {},
      getContext: () => ({
        save: () => {},
        restore: () => {},
        beginPath: () => {},
        arc: () => {},
        fill: () => {},
        stroke: () => {},
        fillRect: () => {},
        strokeRect: () => {},
        fillText: () => {},
        measureText: () => ({ width: 10 }),
        translate: () => {},
        scale: () => {},
        rotate: () => {},
        arcTo: () => {},
        setLineDash: () => {},
        moveTo: () => {},
        lineTo: () => {},
        clearRect: () => {}
      })
    };
    const performance = { now: () => Date.now() };

    let totalActionCount = 0;
    let minBatterySeen = 100.0;
    let below10Count = 0;

    // Fetch map synchronously via HTTP to initialize mapData
    http.get('http://127.0.0.1:8000/api/map', (mRes) => {
      let mJson = '';
      mRes.on('data', c => mJson += c);
      mRes.on('end', () => {
        const mapData = JSON.parse(mJson);
        const fetch = async (url) => {
          if (url === '/api/map') return { json: async () => mapData };
          return { catch: () => {} };
        };

        // Construct sandbox
        const sandbox = {
          window,
          document,
          canvas,
          performance,
          fetch,
          requestAnimationFrame: () => {},
          setInterval: () => {},
          clearInterval: () => {},
          setTimeout: () => {},
          alert: () => {},
          Math,
          Date,
          Set,
          Object,
          Array,
          Int32Array,
          Uint8Array,
          parseInt,
          parseFloat,
          console: { log: () => {}, warn: () => {}, error: () => {} }
        };

        const vm = require('vm');
        vm.createContext(sandbox);

        // Run client script
        vm.runInContext(scriptCode, sandbox);

        // Bridge scope
        const getScope = vm.runInContext(`() => ({
          AMR_FLEET,
          inboundMissions,
          outboundMissions,
          inboundQueues,
          outboundOrders,
          getBestRobotForTask,
          evaluateMissionEnergyFeasibility,
          initRackMemory,
          initAmrFleet,
          updateRobots,
          runFleetWatchdog,
          triggerInboundShipment,
          triggerOutboundOrder,
          setLogTerminal: (fn) => { logTerminal = fn; },
          setMapData: (m) => { mapData = m; },
          trafficMetrics,
          FLEET_INCIDENTS
        })`, sandbox)();

        getScope.setMapData(mapData);
        getScope.initRackMemory();
        getScope.initAmrFleet();

        const AMR_FLEET = getScope.AMR_FLEET;
        console.log('Fleet initialized. AMRs:', AMR_FLEET.length);
        console.log('Starting endurance simulation for 600 seconds of warehouse ops...');

        // Override logTerminal to count actions
        getScope.setLogTerminal(function(type, tag, msg) {
          if (['DISPATCH', 'PICKUP', 'SHELVING', 'COMPLETE'].includes(type)) {
            totalActionCount++;
          }
        });

        // Step simulation
        const dt = 0.05;
        let simSeconds = 0;
        let lastInbound = 0;
        let lastOutbound = 0;

        for (let step = 0; step < 12000; step++) {
          simSeconds += dt;

          // Trigger shipments every 8s
          if (simSeconds - lastInbound >= 8.0) {
            lastInbound = simSeconds;
            getScope.triggerInboundShipment();
          }
          if (simSeconds - lastOutbound >= 9.0) {
            lastOutbound = simSeconds;
            getScope.triggerOutboundOrder();
          }

          // Update physics & movement
          getScope.updateRobots(dt);
          getScope.runFleetWatchdog(Date.now() + Math.round(simSeconds * 1000));

          // Check all robot batteries
          for (const bot of AMR_FLEET) {
            if (bot.battery < minBatterySeen) minBatterySeen = bot.battery;
            if (bot.battery < 10.0) below10Count++;
          }

          if (step % 2000 === 0) {
            console.log(`\n--- FLEET SNAPSHOT AT STEP ${step} (SimTime: ${simSeconds.toFixed(1)}s) ---`);
            for (const r of AMR_FLEET) {
              console.log(`  ${r.id}: ${r.state.padEnd(20)} | Battery: ${r.battery.toFixed(1).padStart(5)}% | Inb: ${(r.inboundMission ? r.inboundMission.id : '-').padEnd(8)} | Outb: ${(r.outboundMission ? r.outboundMission.orderId : '-').padEnd(8)} | Path: ${r.path ? r.path.length : 0}`);
            }
            console.log(`  Pending Inbound: ${getScope.inboundMissions.filter(m => m.status === 'PENDING').length} | Pending Outbound: ${getScope.outboundMissions.filter(m => m.status === 'PENDING').length}`);
            console.log('----------------------------------------------------------------------------\n');
          }

          if (step % 1000 === 0) {
            const completedCount = totalActionCount;
            const avgBatt = AMR_FLEET.reduce((s, b) => s + b.battery, 0) / AMR_FLEET.length;
            console.log(`[Step ${step}] SimTime: ${simSeconds.toFixed(1)}s | Actions: ${completedCount} | Min Batt: ${minBatterySeen.toFixed(1)}% | Avg Batt: ${avgBatt.toFixed(1)}% | Below 10%: ${below10Count}`);
          }
        }

        console.log('\n================ TEST RESULTS ================');
        console.log(`Total Actions Completed: ${totalActionCount}`);
        console.log(`Minimum Battery Reached: ${minBatterySeen.toFixed(2)}%`);
        console.log(`Battery Below 10% Violations: ${below10Count}`);
        console.log(`Any Bots Dead at 4%: ${AMR_FLEET.filter(b => b.battery <= 4.0).length}`);
        console.log(`Total Overtakes Completed: ${getScope.trafficMetrics.totalOvertakes}`);
        console.log(`Collisions Prevented (AEB & Right-of-Way): ${getScope.trafficMetrics.collisionsPrevented}`);
        console.log(`Physical Collisions: ${getScope.trafficMetrics.totalCollisions || 0}`);
        console.log(`Total Yields: ${getScope.trafficMetrics.totalYields}`);
        console.log(`Total Reroutes: ${getScope.trafficMetrics.totalReroutes}`);
        console.log('==============================================\n');

        if (totalActionCount > 250 && below10Count === 0 && minBatterySeen >= 10.0) {
          console.log('✅ TEST PASSED: Simulation runs smoothly well past 200 actions with ZERO battery violations (<10%)!');
          process.exit(0);
        } else {
          console.error('❌ TEST FAILED');
          process.exit(1);
        }
      });
    });
  });
});
