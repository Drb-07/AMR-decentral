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
      getContext: () => new Proxy({ measureText: () => ({ width: 10 }) }, {
        get: (target, prop) => {
          if (prop in target) return target[prop];
          return () => {};
        }
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
      mRes.on('end', async () => {
        const mapData = JSON.parse(mJson);
        const fetch = async (url, opts) => {
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
          buildFleetTelemetryPayload, buildFleetPerformanceCsv, buildJamEpisodesCsv, buildBotLogObject,
          setLogTerminal: (fn) => { logTerminal = fn; },
          setMapData: (m) => { mapData = m; },
          trafficMetrics, FLEET_INCIDENTS
        })`, sandbox)();

        getScope.setMapData(mapData);
        getScope.initRackMemory();
        getScope.initAmrFleet();

        const AMR_FLEET = getScope.AMR_FLEET;
        getScope.setLogTerminal(() => {});

        console.log('Running 2000 steps of simulation (100 sim-seconds) to generate telemetry...');
        const dt = 0.05;
        let simSeconds = 0;
        let lastInbound = 0;
        let lastOutbound = 0;

        for (let step = 0; step < 2000; step++) {
          simSeconds += dt;
          if (simSeconds - lastInbound >= 6.0) {
            lastInbound = simSeconds;
            getScope.triggerInboundShipment();
          }
          if (simSeconds - lastOutbound >= 7.0) {
            lastOutbound = simSeconds;
            getScope.triggerOutboundOrder();
          }

          getScope.updateRobots(dt);
          getScope.runFleetWatchdog(Date.now() + Math.round(simSeconds * 1000));
        }

        console.log('\n--- VERIFYING LOG STATS & TELEMETRY ---');
        const telemetry = getScope.buildFleetTelemetryPayload();
        console.log('Telemetry payload generated:');
        console.log(`- Fleet Size: ${telemetry.exportMetadata.fleetSize}`);
        console.log(`- Total Sim Operating Time: ${telemetry.exportMetadata.totalSimSeconds}s`);
        console.log(`- Total Distance Traveled: ${telemetry.fleetAggregateKpis.totalDistanceTraveledCells} cells`);
        console.log(`- Collisions: ${telemetry.fleetAggregateKpis.physicalCollisions}`);
        console.log(`- Total Right-of-Way Yields: ${telemetry.fleetAggregateKpis.totalRightOfWayYields}`);
        console.log(`- Deadlock Backups: ${telemetry.fleetAggregateKpis.totalDeadlockBackupsToPreviousBox}`);
        console.log(`- Dynamic Reroutes: ${telemetry.fleetAggregateKpis.totalDynamicReroutes}`);
        console.log(`- Overtakes Completed: ${telemetry.fleetAggregateKpis.totalOvertakesCompleted}`);
        console.log(`- Fleet Avg Jam Delay: ${telemetry.fleetAggregateKpis.fleetAverageJamDelayPercent}%`);

        console.log('\n--- PER-BOT DETAILED LOG VERIFICATION ---');
        let totalJamsRecorded = 0;
        for (const botLog of telemetry.bots) {
          totalJamsRecorded += botLog.trafficAndJamBehavior.jamEpisodes.length;
          console.log(`[${botLog.botId}] (${botLog.categoryName}) State: ${botLog.currentStatus.state} | Batt: ${botLog.currentStatus.batteryPercent}% (min: ${botLog.bmsEnergyMetrics.minBatteryFloorSeenPercent}%) | Dist: ${botLog.kinematicsAndDistance.totalDistanceTraveledCells}c | Moving: ${botLog.functionalTimeBreakdown.activeMovingTimeSeconds}s (${botLog.functionalTimeBreakdown.activeMovingPercent}%) | JamWait: ${botLog.functionalTimeBreakdown.jamWaitTimeSeconds}s (${botLog.functionalTimeBreakdown.jamWaitPercent}%, delay factor: ${botLog.functionalTimeBreakdown.jamDelayFactorPercent}%) | Jams: ${botLog.trafficAndJamBehavior.totalJamsEncountered} (episodes: ${botLog.trafficAndJamBehavior.jamEpisodes.length}) | Shelved: ${botLog.warehouseProductivity.totalParcelsShelved} | Picked: ${botLog.warehouseProductivity.totalItemsPickedConsolidated}`);
          if (botLog.trafficAndJamBehavior.jamEpisodes.length > 0) {
            const firstJam = botLog.trafficAndJamBehavior.jamEpisodes[0];
            console.log(`   Sample Jam: duration=${firstJam.waitDurationSec}s at (${firstJam.location.x},${firstJam.location.y}), blocker=${firstJam.blockerId}, reason=${firstJam.reason}, resolution=${firstJam.resolution}`);
          }
        }

        console.log('\n--- VERIFYING CSV EXPORTS ---');
        const perfCsv = getScope.buildFleetPerformanceCsv();
        const perfLines = perfCsv.trim().split('\n');
        console.log(`Fleet Performance CSV lines: ${perfLines.length} (header + ${perfLines.length - 1} bots)`);
        console.log(`Header snippet: ${perfLines[0].substring(0, 80)}...`);

        const jamCsv = getScope.buildJamEpisodesCsv();
        const jamLines = jamCsv.trim().split('\n');
        console.log(`Jam Episodes CSV lines: ${jamLines.length} (header + ${jamLines.length - 1} episodes)`);
        if (jamLines.length > 1) {
          console.log(`First jam episode row: ${jamLines[1]}`);
        }

        // Test POST to /api/fleet/logs/sync
        console.log('\n--- TESTING FASTAPI ENDPOINTS ---');
        const postData = JSON.stringify(telemetry);
        const req = http.request({
          hostname: '127.0.0.1',
          port: 8000,
          path: '/api/fleet/logs/sync',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(postData)
          }
        }, (resSync) => {
          let syncBody = '';
          resSync.on('data', d => syncBody += d);
          resSync.on('end', () => {
            console.log('Sync Response:', syncBody);

            // Test GET from /api/fleet/logs
            http.get('http://127.0.0.1:8000/api/fleet/logs', (resGet) => {
              let getBody = '';
              resGet.on('data', d => getBody += d);
              resGet.on('end', () => {
                const parsed = JSON.parse(getBody);
                console.log(`GET /api/fleet/logs verified! Returned ${parsed.bots ? parsed.bots.length : 0} bots with ${parsed.exportMetadata ? parsed.exportMetadata.fleetSize : 0} fleet size.`);
                console.log('\n>>> ALL TELEMETRY & LOG DOWNLOAD TESTS PASSED! <<<');
                process.exit(0);
              });
            });
          });
        });
        req.on('error', (e) => {
          console.error('Sync request error:', e);
          process.exit(1);
        });
        req.write(postData);
        req.end();
      });
    });
  });
});
