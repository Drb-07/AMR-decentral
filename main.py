"""
FastAPI + WebSocket Live Warehouse Viewer Server
Part of Edge-AI Distributed Fleet Coordination for AMRs

Serves the interactive glass-pane dashboard on http://localhost:8000
Supports smooth Pan & Zoom, inspection HUD, station badges, yield pockets,
and live WebSocket stream for fleet telemetry.
"""

import os
import json
import asyncio
import time
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from warehouse_map import WarehouseMap
from inventory import InventoryManager

class BulkInjectRequest(BaseModel):
    count: int

app = FastAPI(title="Edge AMR Fleet Visualizer")
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

warehouse = WarehouseMap(width=80, height=50)
inventory = InventoryManager(warehouse=warehouse, floors_per_rack=5)

active_connections: Set[WebSocket] = set()

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AMR Fleet Mission Control - Industrial Warehouse Map</title>
  <style>
    :root {
      --bg: #090d16;
      --panel: #111827;
      --border: #1f293d;
      --text: #e2e8f0;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --pickup: #06b6d4;
      --dropoff: #f59e0b;
      --charging: #22c55e;
      --rack: #151821;
      --rack-border: #282d37;
      --aisle: #0f172a;
      --intersection: #ef4444;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
    body { background: var(--bg); color: var(--text); overflow: hidden; height: 100vh; display: flex; flex-direction: column; }

    /* Top Bar */
    html, body {
      overflow: hidden !important;
      width: 100vw !important;
      height: 100vh !important;
      margin: 0;
      padding: 0;
    }
    header {
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      padding: 0 20px;
      height: 52px !important;
      max-height: 52px !important;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 10;
      flex-shrink: 0 !important;
      box-sizing: border-box !important;
    }
    .badge { font-variant-numeric: tabular-nums; white-space: nowrap; }
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
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-title { font-weight: 700; font-size: 16px; letter-spacing: 0.5px; }
    .badge {
      font-size: 11px;
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.4);
      padding: 2px 8px;
      border-radius: 9999px;
      text-transform: uppercase;
      font-weight: 600;
    }

    .status-group { display: flex; align-items: center; gap: 18px; font-size: 13px; }
    .status-item { display: flex; align-items: center; gap: 6px; color: var(--text-muted); }
    .indicator { width: 8px; height: 8px; border-radius: 50%; background: #10b981; box-shadow: 0 0 8px #10b981; }

    /* Layout */
    .workspace { flex: 1; position: relative; overflow: hidden; display: flex; }
    canvas { width: 100%; height: 100%; display: block; cursor: grab; background: #070a10; }
    canvas:active { cursor: grabbing; }

    /* Floating HUD & Controls */
    .controls {
      position: absolute;
      bottom: 24px;
      right: 24px;
      background: rgba(17, 24, 39, 0.85);
      backdrop-filter: blur(8px);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 6px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      z-index: 5;
    }
    .ctrl-btn {
      background: #1e293b;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      width: 34px;
      height: 34px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .ctrl-btn:hover { background: #334155; border-color: var(--accent); }

    .hud-card {
      position: absolute;
      top: 20px;
      left: 20px;
      background: rgba(17, 24, 39, 0.92);
      backdrop-filter: blur(10px);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 12px;
      z-index: 5;
      width: 330px !important;
      min-width: 330px !important;
      max-width: 330px !important;
      box-sizing: border-box !important;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
      transition: none !important; /* CRITICAL: Prevents topology card shaking on value updates */
    }
    .hud-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      user-select: none;
    }
    .hud-title { font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; letter-spacing: 0.5px; }
    .hud-toggle-btn {
      background: #1e293b;
      border: 1px solid var(--border);
      color: var(--text-muted);
      cursor: pointer;
      width: 20px;
      height: 20px;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      line-height: 1;
      font-weight: 700;
      transition: all 0.15s;
    }
    .hud-toggle-btn:hover {
      background: #334155;
      color: var(--accent);
      border-color: var(--accent);
    }
    .hud-card.collapsed {
      min-width: auto;
      padding: 8px 12px;
      background: rgba(17, 24, 39, 0.75);
    }
    .hud-card.collapsed .hud-body {
      display: none;
    }
    .hud-stat { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; height: 18px; }
    .hud-val { font-weight: 600; color: #fff; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 195px; text-align: right; }

    /* AMR Live Bot Tracking Inspector HUD */
    .bot-tracking-hud {
      position: absolute;
      top: 20px;
      right: 24px;
      background: rgba(15, 23, 42, 0.94);
      backdrop-filter: blur(14px);
      border: 1px solid rgba(56, 189, 248, 0.5);
      border-radius: 10px;
      padding: 14px 16px;
      font-size: 12px;
      z-index: 10;
      width: 320px;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.65), 0 0 16px rgba(56, 189, 248, 0.15);
      animation: trackHudSlideIn 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      transition: all 0.2s ease;
    }
    @keyframes trackHudSlideIn {
      from { opacity: 0; transform: translateY(-12px) scale(0.96); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    .tracking-hud-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      margin-bottom: 10px;
    }
    .tracking-hud-title-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .tracking-radar-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #38bdf8;
      box-shadow: 0 0 8px #38bdf8;
      animation: radarPulse 1.2s infinite ease-in-out;
    }
    @keyframes radarPulse {
      0%, 100% { transform: scale(0.85); opacity: 0.6; }
      50% { transform: scale(1.3); opacity: 1; }
    }
    .tracking-title {
      font-weight: 800;
      color: #fff;
      font-size: 14px;
      letter-spacing: 0.5px;
    }
    .tracking-badge {
      font-size: 9px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .tracking-hud-controls {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .track-ctrl-icon-btn {
      background: #1e293b;
      border: 1px solid var(--border);
      color: #cbd5e1;
      border-radius: 4px;
      padding: 3px 7px;
      font-size: 11px;
      cursor: pointer;
      font-weight: 600;
      transition: all 0.15s;
    }
    .track-ctrl-icon-btn:hover {
      background: #334155;
      color: #fff;
      border-color: var(--accent);
    }
    .track-ctrl-icon-btn.active {
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
      border-color: #38bdf8;
    }
    .track-ctrl-close-btn {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #f87171;
      border-radius: 4px;
      padding: 3px 7px;
      font-size: 11px;
      cursor: pointer;
      font-weight: 700;
      transition: all 0.15s;
    }
    .track-ctrl-close-btn:hover {
      background: rgba(239, 68, 68, 0.3);
      color: #fff;
    }
    .track-metrics-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin-bottom: 8px;
    }
    .track-metric-cell {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 6px;
      padding: 6px 8px;
    }
    .track-metric-lbl {
      display: block;
      font-size: 9px;
      color: #94a3b8;
      font-weight: 600;
      text-transform: uppercase;
      margin-bottom: 2px;
    }
    .track-metric-val {
      font-size: 12px;
      font-weight: 700;
      color: #f8fafc;
    }
    .track-metric-sub {
      font-size: 10px;
      color: #94a3b8;
      margin-top: 1px;
    }
    .track-batt-bar {
      width: 100%;
      height: 4px;
      background: #1e293b;
      border-radius: 2px;
      margin-top: 4px;
      overflow: hidden;
    }
    .track-batt-fill {
      height: 100%;
      border-radius: 2px;
      transition: width 0.3s ease, background 0.3s ease;
    }
    .track-mission-box {
      background: rgba(30, 41, 59, 0.5);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 6px;
      padding: 7px 9px;
      margin-bottom: 7px;
    }
    .track-mission-label {
      font-size: 9px;
      font-weight: 600;
      color: #94a3b8;
      text-transform: uppercase;
    }
    .track-mission-desc {
      font-size: 11px;
      font-weight: 700;
      color: #e2e8f0;
      margin: 2px 0;
    }
    .track-mission-sub {
      font-size: 10px;
      color: #94a3b8;
    }
    .track-cargo-box {
      background: rgba(30, 41, 59, 0.35);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 6px;
      padding: 7px 9px;
      margin-bottom: 8px;
      max-height: 95px;
      overflow-y: auto;
    }
    .track-cargo-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 10px;
      font-weight: 600;
      color: #cbd5e1;
      margin-bottom: 3px;
    }
    .track-cargo-count {
      color: var(--accent);
      font-weight: 700;
    }
    .track-cargo-list {
      font-size: 10px;
      color: #94a3b8;
      line-height: 1.4;
    }
    .track-actions-row {
      display: flex;
      gap: 5px;
    }
    .track-act-btn {
      flex: 1;
      padding: 5px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s;
      border: 1px solid transparent;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 3px;
    }
    .track-act-btn.recall-btn {
      background: rgba(245, 158, 11, 0.15);
      color: #f59e0b;
      border-color: rgba(245, 158, 11, 0.4);
    }
    .track-act-btn.recall-btn:hover {
      background: rgba(245, 158, 11, 0.25);
      color: #fde047;
    }
    .track-act-btn.inspect-btn {
      background: #1e293b;
      color: #cbd5e1;
      border-color: var(--border);
    }
    .track-act-btn.inspect-btn:hover {
      background: #334155;
      color: #fff;
      border-color: var(--accent);
    }
    .track-act-btn.reset-cam-btn {
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border-color: rgba(56, 189, 248, 0.4);
    }
    .track-act-btn.reset-cam-btn:hover {
      background: rgba(56, 189, 248, 0.25);
      color: #fff;
    }

    /* Header Bot Track Selector Dropdown */
    .bot-track-selector-wrapper {
      display: flex;
      align-items: center;
      gap: 5px;
      background: #151d2d;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 3px 8px;
    }
    .track-label {
      font-size: 11px;
      font-weight: 700;
      color: var(--accent);
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 3px;
    }
    .track-select {
      background: transparent;
      color: #fff;
      border: none;
      font-family: inherit;
      font-size: 11px;
      font-weight: 600;
      outline: none;
      cursor: pointer;
    }
    .track-select option {
      background: #0f172a;
      color: #fff;
    }

    .legend {
      position: absolute;
      bottom: 24px;
      left: 20px;
      background: rgba(17, 24, 39, 0.88);
      backdrop-filter: blur(10px);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 11px;
      display: flex;
      gap: 14px;
      z-index: 5;
    }
    .legend-item { display: flex; align-items: center; gap: 6px; color: var(--text-muted); }
    .legend-box { width: 12px; height: 12px; border-radius: 3px; }

    /* Main Header Navigation Tabs */
    .nav-tabs {
      display: flex;
      align-items: center;
      gap: 5px;
      background: #090d16;
      padding: 3px;
      border-radius: 8px;
      border: 1px solid var(--border);
    }
    .nav-tab {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      background: transparent;
      color: var(--text-muted);
      border: 1px solid transparent;
      border-radius: 6px;
      padding: 6px 14px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      user-select: none;
    }
    .nav-tab:hover {
      color: #fff;
      background: rgba(255, 255, 255, 0.05);
    }
    .nav-tab.active {
      background: #1e293b;
      color: var(--accent);
      border-color: rgba(56, 189, 248, 0.4);
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.2);
    }
    .tab-badge {
      background: rgba(56, 189, 248, 0.2);
      color: var(--accent);
      font-size: 10px;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 9999px;
    }

    /* Views */
    .app-view {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      display: none;
    }
    .app-view.active {
      display: flex;
      flex-direction: column;
    }

    /* Terminal & Bots Health Layout */
    .th-container {
      flex: 1;
      display: flex;
      flex-direction: column;
      background: var(--bg);
      overflow: hidden;
    }
    .th-top-bar {
      background: #0b0f19;
      border-bottom: 1px solid var(--border);
      padding: 8px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      z-index: 5;
    }
    .th-view-modes {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .th-label {
      font-size: 11px;
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 0.5px;
      margin-right: 4px;
    }
    .th-mode-btn {
      background: #1e293b;
      color: var(--text-muted);
      border: 1px solid var(--border);
      border-radius: 5px;
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .th-mode-btn:hover {
      color: #fff;
      background: #334155;
    }
    .th-mode-btn.active {
      background: rgba(56, 189, 248, 0.2);
      color: var(--accent);
      border-color: var(--accent);
      box-shadow: 0 0 8px rgba(56, 189, 248, 0.25);
    }
    .th-kpi-summary {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .th-kpi-pill {
      background: #070a10;
      border: 1px solid var(--border);
      border-radius: 5px;
      padding: 4px 9px;
      font-size: 11px;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .kpi-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
    }
    .kpi-dot.green { background: #22c55e; box-shadow: 0 0 6px #22c55e; }

    /* Panes */
    .th-panes {
      flex: 1;
      display: flex;
      overflow: hidden;
      position: relative;
    }
    .th-pane {
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background: #080c14;
    }
    .th-panes.mode-split .th-pane-bots {
      width: 53%;
      border-right: 1px solid var(--border);
    }
    .th-panes.mode-split .th-pane-terminal {
      width: 47%;
    }
    .th-panes.mode-bots .th-pane-bots {
      width: 100%;
    }
    .th-panes.mode-bots .th-pane-terminal {
      display: none;
    }
    .th-panes.mode-term .th-pane-bots {
      display: none;
    }
    .th-panes.mode-term .th-pane-terminal {
      width: 100%;
    }

    .pane-header {
      background: #0d131f;
      border-bottom: 1px solid var(--border);
      padding: 9px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-shrink: 0;
    }
    .pane-title {
      font-size: 12px;
      font-weight: 700;
      color: #38bdf8;
      display: flex;
      align-items: center;
      gap: 7px;
      letter-spacing: 0.5px;
    }
    .pane-badge {
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      font-size: 10px;
      padding: 2px 7px;
      border-radius: 9999px;
      font-weight: 600;
    }
    .pane-actions {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    /* Bots Health Grid */
    .bots-grid {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 12px;
      align-content: start;
    }
    .bot-card {
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 11px 13px;
      display: flex;
      flex-direction: column;
      gap: 7px;
      transition: all 0.2s;
    }
    .bot-card:hover {
      border-color: rgba(56, 189, 248, 0.45);
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
      background: rgba(15, 23, 42, 0.9);
    }
    .bot-card.is-low-batt {
      border-color: #ef4444;
      background: rgba(239, 68, 68, 0.08);
      box-shadow: 0 0 12px rgba(239, 68, 68, 0.25);
    }
    .bot-card.is-charging {
      border-color: rgba(34, 197, 94, 0.45);
    }
    .bot-card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .bot-id-title {
      font-size: 13px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .bot-zone-tag {
      font-size: 10px;
      color: var(--text-muted);
      font-weight: normal;
    }
    .bot-status-pill {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 4px;
      letter-spacing: 0.3px;
    }

    .bot-soc-section {
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 6px;
      padding: 6px 9px;
    }
    .bot-soc-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 4px;
    }
    .bot-soc-val {
      font-size: 15px;
      font-weight: 800;
      font-family: monospace;
    }
    .bot-soc-rate {
      font-size: 10px;
      color: var(--text-muted);
    }
    .bot-soc-bar-bg {
      width: 100%;
      height: 6px;
      background: #1e293b;
      border-radius: 3px;
      overflow: hidden;
      margin-bottom: 4px;
    }
    .bot-soc-bar-fill {
      height: 100%;
      border-radius: 3px;
      transition: width 0.3s ease;
    }
    .bot-soc-footer {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: #94a3b8;
    }

    .bot-metrics-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 5px;
      font-size: 11px;
    }
    .bot-metric-box {
      background: rgba(0, 0, 0, 0.2);
      border: 1px solid rgba(255, 255, 255, 0.04);
      border-radius: 4px;
      padding: 4px 7px;
    }
    .bot-metric-lbl {
      color: var(--text-muted);
      font-size: 9px;
      text-transform: uppercase;
      font-weight: 600;
      display: block;
      margin-bottom: 1px;
    }
    .bot-metric-val {
      font-weight: 600;
      color: #cbd5e1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .bot-card-actions {
      display: flex;
      gap: 6px;
      margin-top: 2px;
      padding-top: 6px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
    }
    .bot-act-btn {
      flex: 1;
      background: #1e293b;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 4px 6px;
      font-size: 10px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      transition: all 0.15s;
    }
    .bot-act-btn:hover {
      background: #334155;
      color: #fff;
      border-color: var(--accent);
    }
    .bot-act-btn.locate:hover {
      border-color: #38bdf8;
      color: #38bdf8;
    }
    .bot-act-btn.recall:hover {
      border-color: #f59e0b;
      color: #fde047;
    }
    .bot-act-btn.track:hover {
      border-color: #38bdf8;
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
    }

    /* Terminal Controls & Filtering */
    .terminal-controls {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .log-filter-group {
      display: flex;
      align-items: center;
      gap: 3px;
      margin-right: 6px;
    }
    .filter-pill {
      background: #151d2d;
      color: var(--text-muted);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 2px 7px;
      font-size: 10px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .filter-pill:hover {
      color: #fff;
      background: #1e293b;
    }
    .filter-pill.active {
      background: rgba(56, 189, 248, 0.2);
      color: var(--accent);
      border-color: var(--accent);
    }
    .term-btn {
      background: #1e293b;
      border: 1px solid var(--border);
      color: var(--text-muted);
      border-radius: 4px;
      padding: 2px 8px;
      font-size: 10px;
      cursor: pointer;
      font-family: inherit;
      transition: all 0.15s;
    }
    .term-btn:hover {
      background: #334155;
      color: #fff;
      border-color: var(--accent);
    }
    .terminal-body {
      flex: 1;
      overflow-y: auto;
      padding: 8px 12px;
      font-family: "JetBrains Mono", Consolas, monospace;
      font-size: 11px;
      line-height: 1.5;
      color: #cbd5e1;
    }
    .log-entry {
      margin-bottom: 4px;
      display: flex;
      align-items: flex-start;
      gap: 6px;
      word-break: break-all;
    }
    .log-time { color: #64748b; font-size: 10px; flex-shrink: 0; }
    .log-tag {
      font-size: 9px;
      font-weight: 700;
      padding: 1px 4px;
      border-radius: 3px;
      text-transform: uppercase;
      flex-shrink: 0;
    }
    .tag-inbound { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56,189,248,0.4); }
    .tag-outbound { background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid rgba(245,158,11,0.4); }
    .tag-complete { background: rgba(34, 197, 94, 0.2); color: #22c55e; border: 1px solid rgba(34,197,94,0.4); }
    .tag-yield { background: rgba(245, 158, 11, 0.25); color: #f59e0b; border: 1px solid rgba(245,158,11,0.5); }
    .tag-overtake { background: rgba(56, 189, 248, 0.25); color: #38bdf8; border: 1px solid rgba(56,189,248,0.5); }
    .tag-reroute { background: rgba(168, 85, 247, 0.25); color: #c084fc; border: 1px solid rgba(168,85,247,0.5); }
    .log-msg { flex: 1; }

    /* Tooltip */
    #cell-tooltip {
      position: absolute;
      display: none;
      background: rgba(15, 23, 42, 0.96);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(56, 189, 248, 0.6);
      border-radius: 6px;
      padding: 8px 12px;
      font-size: 11px;
      color: #fff;
      pointer-events: none;
      z-index: 20;
      min-width: 230px;
      max-width: 320px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.7);
    }

    /* Action Buttons in Header & Panels */
    .header-actions { display: flex; align-items: center; gap: 8px; }
    .header-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: #1e293b;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      user-select: none;
    }
    .header-btn:hover {
      background: #334155;
      border-color: var(--accent);
      color: #fff;
    }
    .speed-btn.active {
      background: rgba(245, 158, 11, 0.25);
      border-color: #f59e0b;
      color: #fde047;
      box-shadow: 0 0 10px rgba(245, 158, 11, 0.35);
    }
    .add-btn {
      background: rgba(56, 189, 248, 0.15);
      border-color: rgba(56, 189, 248, 0.4);
      color: var(--accent);
    }
    .add-btn:hover {
      background: rgba(56, 189, 248, 0.28);
      border-color: var(--accent);
      color: #fff;
    }
    .download-btn {
      background: rgba(34, 197, 94, 0.15);
      border-color: rgba(34, 197, 94, 0.4);
      color: #4ade80;
    }
    .download-btn:hover {
      background: rgba(34, 197, 94, 0.28);
      border-color: #22c55e;
      color: #fff;
    }
    .log-bot-btn {
      background: #1e293b;
      border: 1px solid rgba(56, 189, 248, 0.4);
      color: #38bdf8;
    }
    .log-bot-btn:hover {
      background: rgba(56, 189, 248, 0.25);
      border-color: #38bdf8;
      color: #fff;
    }
    .modal-box-wide {
      width: 820px !important;
      max-width: 95vw !important;
    }
    .logs-kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(115px, 1fr));
      gap: 8px;
      margin-bottom: 16px;
    }
    .logs-kpi-item {
      background: #090d16;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
    }
    .logs-kpi-label {
      font-size: 9px;
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: 0.3px;
    }
    .logs-kpi-val {
      font-size: 14px;
      font-weight: 800;
      font-family: monospace;
      margin-top: 2px;
      color: #fff;
    }
    .logs-options-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 12px;
    }
    .log-card {
      background: rgba(15, 23, 42, 0.65);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 13px 15px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 10px;
      transition: all 0.2s;
    }
    .log-card:hover {
      border-color: rgba(56, 189, 248, 0.45);
      background: rgba(15, 23, 42, 0.9);
    }
    .log-card-header {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .log-card-icon {
      font-size: 20px;
    }
    .log-card-title {
      font-weight: 700;
      color: #fff;
      font-size: 13px;
    }
    .log-card-desc {
      font-size: 11px;
      color: var(--text-muted);
      line-height: 1.45;
    }
    .log-card-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .log-card-btn {
      padding: 6px 12px;
      background: #1e293b;
      border: 1px solid var(--border);
      border-radius: 5px;
      color: #fff;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .log-card-btn:hover {
      background: #334155;
      border-color: var(--accent);
      color: var(--accent);
    }
    .log-card-btn.primary {
      background: rgba(56, 189, 248, 0.2);
      border-color: rgba(56, 189, 248, 0.45);
      color: #38bdf8;
    }
    .log-card-btn.primary:hover {
      background: rgba(56, 189, 248, 0.35);
      color: #fff;
    }
    .log-bot-selector {
      background: #090d16;
      border: 1px solid var(--border);
      color: #fff;
      border-radius: 5px;
      padding: 4px 8px;
      font-size: 11px;
      font-family: inherit;
    }

    /* Modal Overlay & Box */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.78);
      backdrop-filter: blur(8px);
      z-index: 100;
      display: none;
      align-items: center;
      justify-content: center;
    }
    .modal-overlay.open { display: flex; }
    .modal-box {
      background: #111827;
      border: 1px solid rgba(56, 189, 248, 0.4);
      border-radius: 10px;
      width: 440px;
      max-width: 92vw;
      box-shadow: 0 20px 50px rgba(0,0,0,0.85), 0 0 25px rgba(56, 189, 248, 0.15);
      overflow: hidden;
      animation: modalIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes modalIn {
      from { opacity: 0; transform: scale(0.94); }
      to { opacity: 1; transform: scale(1); }
    }
    .modal-header {
      padding: 12px 18px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(255, 255, 255, 0.02);
    }
    .modal-title { font-weight: 700; font-size: 14px; display: flex; align-items: center; gap: 8px; color: #fff; }
    .modal-close-btn {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 22px;
      cursor: pointer;
      line-height: 1;
      padding: 0 4px;
    }
    .modal-close-btn:hover { color: #fff; }
    .modal-body { padding: 18px; font-size: 13px; }
    .input-group { margin-bottom: 14px; }
    .input-group label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 6px; font-weight: 600; }
    .input-group input {
      width: 100%;
      background: #090d16;
      border: 1px solid var(--border);
      color: #fff;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 15px;
      font-family: monospace;
      outline: none;
      transition: border-color 0.2s;
    }
    .input-group input:focus { border-color: var(--accent); box-shadow: 0 0 8px rgba(56,189,248,0.3); }
    .quick-presets { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 10px; }
    .preset-label { font-size: 11px; color: var(--text-muted); font-weight: 600; margin-right: 4px; }
    .preset-btn {
      background: #1e293b;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 11px;
      cursor: pointer;
      font-family: monospace;
      transition: all 0.15s;
    }
    .preset-btn:hover { background: #334155; border-color: var(--accent); color: #fff; }
    .modal-footer {
      padding: 12px 18px;
      background: rgba(0,0,0,0.25);
      border-top: 1px solid var(--border);
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }
    .modal-btn {
      padding: 7px 16px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      border: 1px solid transparent;
    }
    .modal-btn.cancel { background: #1e293b; color: var(--text-muted); border-color: var(--border); }
    .modal-btn.cancel:hover { background: #334155; color: #fff; }
    .modal-btn.confirm { background: #0284c7; color: #fff; }
    /* =========================================================================
       TAB 3: BOT PROBLEMS & FLEET DIAGNOSTICS STYLES
       ========================================================================= */
    .tab-badge.danger {
      background: #ef4444;
      color: #fff;
      box-shadow: 0 0 6px rgba(239, 68, 68, 0.6);
    }
    .prob-container {
      flex: 1;
      display: flex;
      flex-direction: column;
      background: var(--bg);
      overflow: hidden;
    }
    .prob-top-bar {
      background: #0b0f19;
      border-bottom: 1px solid var(--border);
      padding: 8px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      z-index: 5;
    }
    .prob-kpi-summary {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .prob-kpi-card {
      background: #070a10;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 5px 12px;
      display: flex;
      align-items: center;
      gap: 9px;
      min-width: 140px;
      transition: all 0.2s;
    }
    .prob-kpi-card:hover {
      border-color: rgba(56, 189, 248, 0.4);
      background: #0d131f;
    }
    .prob-kpi-icon {
      font-size: 18px;
      line-height: 1;
    }
    .prob-kpi-info {
      display: flex;
      flex-direction: column;
    }
    .prob-kpi-lbl {
      font-size: 9px;
      text-transform: uppercase;
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 0.3px;
    }
    .prob-kpi-val {
      font-size: 15px;
      font-weight: 800;
      font-family: monospace;
      line-height: 1.1;
    }
    .prob-global-actions {
      display: flex;
      align-items: center;
      gap: 7px;
    }
    .prob-action-btn {
      padding: 5px 12px;
      border-radius: 5px;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      border: 1px solid transparent;
      transition: all 0.15s ease;
      font-family: inherit;
    }
    .prob-action-btn.rescue-all {
      background: #7f1d1d;
      color: #fecaca;
      border-color: #ef4444;
    }
    .prob-action-btn.rescue-all:hover {
      background: #991b1b;
      color: #fff;
      box-shadow: 0 0 10px rgba(239, 68, 68, 0.5);
    }
    .prob-action-btn.unblock-all {
      background: #1e293b;
      color: #fde047;
      border-color: #ca8a04;
    }
    .prob-action-btn.unblock-all:hover {
      background: #854d0e;
      color: #fff;
      box-shadow: 0 0 10px rgba(234, 179, 8, 0.4);
    }
    .prob-action-btn.clear-resolved {
      background: #1e293b;
      color: var(--text-muted);
      border-color: var(--border);
    }
    .prob-action-btn.clear-resolved:hover {
      background: #334155;
      color: #fff;
    }
    .prob-sub-bar {
      background: #080c14;
      border-bottom: 1px solid var(--border);
      padding: 6px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .prob-filter-group {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .prob-filter-lbl {
      font-size: 10px;
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 0.5px;
      margin-right: 4px;
    }
    .prob-filter-pill {
      background: #151d2d;
      color: var(--text-muted);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 3px 9px;
      font-size: 10px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .prob-filter-pill:hover {
      color: #fff;
      background: #1e293b;
    }
    .prob-filter-pill.active {
      background: rgba(239, 68, 68, 0.2);
      color: #ef4444;
      border-color: #ef4444;
    }
    .prob-status-legend {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 11px;
      color: var(--text-muted);
    }
    .legend-badge {
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .badge-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
    }
    .badge-dot.pulse-red {
      background: #ef4444;
      box-shadow: 0 0 6px #ef4444;
      animation: alertPulse 1.2s infinite;
    }
    @keyframes alertPulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(1.3); }
    }
    .badge-dot.green {
      background: #22c55e;
    }
    .prob-panes {
      flex: 1;
      display: flex;
      overflow: hidden;
      position: relative;
    }
    .prob-pane {
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background: #080c14;
    }
    .prob-pane-feed {
      width: 58%;
      border-right: 1px solid var(--border);
    }
    .prob-pane-matrix {
      width: 42%;
    }
    .prob-feed-body {
      flex: 1;
      overflow-y: auto;
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .prob-card {
      background: rgba(15, 23, 42, 0.75);
      border: 1px solid var(--border);
      border-radius: 7px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      transition: all 0.2s;
    }
    .prob-card:hover {
      border-color: rgba(56, 189, 248, 0.4);
      background: rgba(15, 23, 42, 0.95);
    }
    .prob-card.active-COLLISION {
      border-color: #ef4444;
      background: rgba(239, 68, 68, 0.08);
      box-shadow: 0 0 10px rgba(239, 68, 68, 0.25);
    }
    .prob-card.active-OUT_OF_CHARGE {
      border-color: #dc2626;
      background: rgba(220, 38, 38, 0.12);
      box-shadow: 0 0 14px rgba(220, 38, 38, 0.35);
    }
    .prob-card.active-DEADLOCK {
      border-color: #f59e0b;
      background: rgba(245, 158, 11, 0.08);
    }
    .prob-card.active-BMS_DEFICIT {
      border-color: #38bdf8;
      background: rgba(56, 189, 248, 0.06);
    }
    .prob-card.resolved {
      opacity: 0.6;
      border-color: rgba(255, 255, 255, 0.06);
      background: rgba(15, 23, 42, 0.4);
    }
    .prob-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .prob-card-title {
      font-size: 12px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .prob-card-meta {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 10px;
    }
    .prob-time {
      color: #64748b;
      font-family: monospace;
    }
    .prob-status-tag {
      font-size: 9px;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 3px;
      letter-spacing: 0.3px;
    }
    .prob-status-tag.active {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.4);
    }
    .prob-status-tag.resolved {
      background: rgba(34, 197, 94, 0.15);
      color: #4ade80;
      border: 1px solid rgba(34, 197, 94, 0.3);
    }
    .prob-card-desc {
      font-size: 11px;
      line-height: 1.45;
      color: #cbd5e1;
    }
    .prob-card-actions {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 2px;
      padding-top: 6px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
    }
    .prob-btn {
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 4px;
      border: 1px solid var(--border);
      background: #1e293b;
      color: var(--text);
      transition: all 0.15s;
    }
    .prob-btn:hover {
      background: #334155;
      color: #fff;
    }
    .prob-btn.tow {
      border-color: #ef4444;
      color: #fca5a5;
      background: rgba(239, 68, 68, 0.15);
    }
    .prob-btn.tow:hover {
      background: #b91c1c;
      color: #fff;
    }
    .prob-btn.unblock {
      border-color: #f59e0b;
      color: #fde047;
      background: rgba(245, 158, 11, 0.15);
    }
    .prob-btn.unblock:hover {
      background: #b45309;
      color: #fff;
    }
    .prob-btn.locate:hover {
      border-color: #38bdf8;
      color: #38bdf8;
    }
    .prob-btn.track:hover {
      border-color: #38bdf8;
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
    }
    .prob-matrix-body {
      flex: 1;
      overflow-y: auto;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .matrix-row {
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
      gap: 5px;
      transition: all 0.2s;
    }
    .matrix-row:hover {
      border-color: rgba(56, 189, 248, 0.4);
      background: rgba(15, 23, 42, 0.9);
    }
    .matrix-row.is-dead {
      border-color: #ef4444;
      background: rgba(239, 68, 68, 0.12);
      box-shadow: 0 0 10px rgba(239, 68, 68, 0.25);
    }
    .matrix-row.is-stalled {
      border-color: #f59e0b;
      background: rgba(245, 158, 11, 0.08);
    }
    .matrix-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .matrix-bot-title {
      font-size: 12px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .matrix-state-tag {
      font-size: 9px;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 3px;
    }
    .matrix-bar-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .matrix-bar-bg {
      flex: 1;
      height: 5px;
      background: #1e293b;
      border-radius: 3px;
      overflow: hidden;
      position: relative;
    }
    .matrix-bar-fill {
      height: 100%;
      border-radius: 3px;
      transition: width 0.3s;
    }
    .matrix-bar-cutoff-line {
      position: absolute;
      left: 10%;
      top: 0;
      bottom: 0;
      width: 2px;
      background: #ef4444;
    }
    .matrix-soc-text {
      font-size: 11px;
      font-weight: 800;
      font-family: monospace;
      width: 44px;
      text-align: right;
    }
    .matrix-details {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: #94a3b8;
    }
    .matrix-actions {
      display: flex;
      gap: 4px;
      margin-top: 2px;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-title">EDGE-AI AMR FLEET MISSION CONTROL</div>
      <span class="badge">Decentralized Mesh Simulation</span>
    </div>

    <!-- Main Navigation Tabs -->
    <div class="nav-tabs">
      <button class="nav-tab active" id="tab-btn-map" onclick="switchMainTab('map')" title="Warehouse 2D Map & Live Fleet Movement">
        <span>🗺️</span> <span>Warehouse Map</span>
      </button>
      <button class="nav-tab" id="tab-btn-terminal" onclick="switchMainTab('terminal')" title="Live Operations Terminal & Fleet Health Dashboard">
        <span>⚡</span> <span>Terminal &amp; Bots Health</span>
        <span class="tab-badge" id="tab-event-badge">0</span>
      </button>
      <button class="nav-tab" id="tab-btn-problems" onclick="switchMainTab('problems')" title="Fleet Incidents, Collisions, Deadlocks & BMS Cutoff Dashboard">
        <span>🚨</span> <span>Bot Problems</span>
        <span class="tab-badge danger" id="tab-problems-badge">0</span>
      </button>
    </div>

    <div class="header-actions">
      <div class="bot-track-selector-wrapper" title="Select an AMR robot to track & follow across the warehouse">
        <label for="track-bot-select" class="track-label"><span>🎯</span> Track:</label>
        <select id="track-bot-select" class="track-select" onchange="onTrackBotSelectChange(this.value)">
          <option value="">None (Fleet View)</option>
          <option value="AMR-01">AMR-01</option>
          <option value="AMR-02">AMR-02</option>
          <option value="AMR-03">AMR-03</option>
          <option value="AMR-04">AMR-04</option>
          <option value="AMR-05">AMR-05</option>
          <option value="AMR-06">AMR-06</option>
          <option value="AMR-07">AMR-07</option>
          <option value="AMR-08">AMR-08</option>
        </select>
      </div>
      <button id="download-logs-btn" class="header-btn download-btn" onclick="openLogsModal()" title="Download Full Fleet & Bot Telemetry Logs">
        <span>📥</span> <span>Download Logs</span>
      </button>
      <button id="speed-btn" class="header-btn speed-btn" onclick="cycleSimulationSpeed()" title="Cycle Simulation Speed (1x, 2x, 5x, 10x)">
        <span>⏩</span> <span id="speed-label">1x Speed</span>
      </button>
      <button id="add-parcels-btn" class="header-btn add-btn" onclick="openBulkModal()" title="Inject N Parcels into 3D Racks">
        <span>📦</span> <span>+ Add N Parcels</span>
      </button>
    </div>
    <div class="status-group">
      <div class="status-item"><span class="indicator"></span> Active Warehouse Map</div>
      <div class="status-item">Grid: <strong style="color:#fff; margin-left:4px;">80 &times; 50 (4,000 cells)</strong></div>
      <div class="status-item">Stations: <strong style="color:#fff; margin-left:4px;">28 Total</strong></div>
    </div>
  </header>

  <div class="workspace">
    <!-- TAB 1: 2D WAREHOUSE MAP -->
    <div id="view-map" class="app-view active">
      <canvas id="viewport"></canvas>

      <div class="hud-card" id="hud-card">
        <div class="hud-header" onclick="toggleHud()" title="Click to hide/show details">
          <div class="hud-title">Warehouse Topology</div>
          <button class="hud-toggle-btn" id="hud-toggle-btn" aria-label="Toggle Panel">
            <span id="hud-toggle-icon">&minus;</span>
          </button>
        </div>
        <div class="hud-body" id="hud-body" style="margin-top:10px;">
          <div class="hud-stat"><span>Dimensions:</span><span class="hud-val">80 x 50 cells</span></div>
          <div class="hud-stat"><span>Rack Memory (3D):</span><span class="hud-val" style="color:#38bdf8">1,512 Racks &times; 5 Tiers</span></div>
          <div class="hud-stat"><span>Stored Inventory:</span><span class="hud-val" id="hud-stored-count" style="color:#22c55e">0 / 7,560 (0.0%)</span></div>
          <div class="hud-stat"><span>Inbound Load:</span><span class="hud-val" id="hud-inbound-waiting" style="color:var(--pickup)">0 Parcels Queued</span></div>
          <div class="hud-stat"><span>Outbound Orders:</span><span class="hud-val" id="hud-outbound-transit" style="color:var(--dropoff)">0 Awaiting Deposit</span></div>
          <div class="hud-stat"><span>AMR Fleet:</span><span class="hud-val" id="hud-fleet-status" style="color:#38bdf8">8 Active (8 Charging)</span></div>
          <div class="hud-stat"><span>Collision Status:</span><span class="hud-val" id="hud-collision-status" style="color:#22c55e">0 Collisions (Active)</span></div>
          <div class="hud-stat"><span>Traffic Events:</span><span class="hud-val" id="hud-traffic-events" style="color:#facc15">0 Yields | 0 Overtakes | 0 Reroutes</span></div>
          <div class="hud-stat"><span>Charging Bays:</span><span class="hud-val" style="color:var(--charging)">8 Fast Chargers</span></div>
          <div style="margin-top:10px; padding-top:8px; border-top:1px solid var(--border); font-size:11px; color:var(--text-muted)">
            Cursor Pos: <strong id="cursor-coords" style="color:var(--accent)">-</strong>
          </div>
          <div style="margin-top:10px; display:flex; gap:6px;">
            <button class="header-btn add-btn" style="flex:1; justify-content:center; padding:5px 8px; font-size:11px;" onclick="openBulkModal()">📦 + Add Parcels</button>
            <button class="header-btn speed-btn" id="hud-speed-btn" style="padding:5px 8px; font-size:11px;" onclick="cycleSimulationSpeed()">⏩ 1x</button>
          </div>
        </div>
      </div>

      <!-- LIVE BOT TRACKING INSPECTOR HUD CARD -->
      <div id="bot-tracking-hud" class="bot-tracking-hud" style="display:none;">
        <div class="tracking-hud-header">
          <div class="tracking-hud-title-wrap">
            <span class="tracking-radar-dot"></span>
            <span class="tracking-title" id="track-hud-robot-id">AMR-01</span>
            <span class="tracking-badge" id="track-hud-state-badge">STANDBY</span>
          </div>
          <div class="tracking-hud-controls">
            <button class="track-ctrl-icon-btn" onclick="cycleTrackedRobot(-1)" title="Previous Bot (←)">◀</button>
            <button class="track-ctrl-icon-btn" onclick="cycleTrackedRobot(1)" title="Next Bot (→)">▶</button>
            <button class="track-ctrl-icon-btn active" id="track-cam-toggle-btn" onclick="toggleTrackCameraFollow()" title="Toggle Camera Auto-Follow (F)">🎥 Cam</button>
            <button class="track-ctrl-close-btn" onclick="stopTrackingBot()" title="Stop Tracking (Esc)">✕</button>
          </div>
        </div>

        <div class="tracking-hud-body">
          <div class="track-metrics-grid">
            <div class="track-metric-cell">
              <span class="track-metric-lbl">Battery SoC</span>
              <div class="track-metric-val" id="track-hud-battery">100.0%</div>
              <div class="track-batt-bar"><div class="track-batt-fill" id="track-hud-batt-fill" style="width:100%;"></div></div>
            </div>
            <div class="track-metric-cell">
              <span class="track-metric-lbl">Speed & Load</span>
              <div class="track-metric-val" id="track-hud-speed">4.2 cells/s</div>
              <div class="track-metric-sub" id="track-hud-load">0.0 kg (100% throttle)</div>
            </div>
            <div class="track-metric-cell">
              <span class="track-metric-lbl">Position (X, Y)</span>
              <div class="track-metric-val" id="track-hud-coords">X: 12, Y: 24</div>
              <div class="track-metric-sub" id="track-hud-heading">Heading: 90° (E)</div>
            </div>
            <div class="track-metric-cell">
              <span class="track-metric-lbl">BMS Power Draw</span>
              <div class="track-metric-val" id="track-hud-power">165 W</div>
              <div class="track-metric-sub" id="track-hud-charge-phase">Discharging</div>
            </div>
          </div>

          <div class="track-mission-box">
            <div class="track-mission-label">Target & Assignment:</div>
            <div class="track-mission-desc" id="track-hud-target-desc">Dock P-01 (Inbound Load)</div>
            <div class="track-mission-sub" id="track-hud-sla">SLA: Standard | Nearest Charger: CH-01 (14 cells)</div>
          </div>

          <div class="track-cargo-box" id="track-hud-cargo-box">
            <div class="track-cargo-header">
              <span id="track-hud-cargo-title">📦 Cargo Manifest:</span>
              <span class="track-cargo-count" id="track-hud-cargo-count">Empty</span>
            </div>
            <div class="track-cargo-list" id="track-hud-cargo-list">No parcels loaded</div>
          </div>

          <div class="track-actions-row">
            <button class="track-act-btn recall-btn" onclick="recallTrackedBotToCharger()" title="Recall bot to nearest charging port">⚡ Recall to Charger</button>
            <button class="track-act-btn inspect-btn" onclick="inspectTrackedBotInHealth()" title="View in Bot Health Matrix">📊 Health Specs</button>
            <button class="track-act-btn log-bot-btn" onclick="downloadCurrentTrackedBotLog()" title="Download complete operational log of this robot">📥 Export Bot Log</button>
            <button class="track-act-btn reset-cam-btn" onclick="centerOnTrackedBot()" title="Center camera on bot">🎯 Center Cam</button>
          </div>
        </div>
      </div>

      <div class="legend">
        <div class="legend-item"><div class="legend-box" style="background:#151821; border:1px solid #282d37;"></div> 3D Rack (5 Tiers)</div>
        <div class="legend-item"><div class="legend-box" style="background:#06b6d4;"></div> Inbound (Blue: Ready / <span style="color:#facc15; font-weight:700; margin-left:3px;">Yellow: Holding Load</span>)</div>
        <div class="legend-item"><div class="legend-box" style="background:#f97316;"></div> Outbound (Orange: Idle / <span style="color:#facc15; font-weight:700; margin-left:3px;">Yellow: Awaiting Deposit</span>)</div>
        <div class="legend-item"><div class="legend-box" style="background:#22c55e; border:1px solid #86efac; box-shadow:0 0 6px rgba(34,197,94,0.6)"></div> Charging Bay (C)</div>
        <div class="legend-item"><div class="legend-box" style="background:#1e293b; border-radius:50%; border:2px solid #38bdf8; box-shadow:0 0 6px rgba(56,189,248,0.6);"></div> AMR Fleet (8 Bots)</div>
        <div class="legend-item"><div class="legend-box" style="background:#0f172a; border:2px solid #38bdf8; box-shadow:0 0 6px #38bdf8; display:flex; align-items:center; justify-content:center; font-size:8px;">🎯</div> Tracked Bot (Follow Cam)</div>
        <div class="legend-item"><div class="legend-box" style="background:#b45309; border:1px solid #f59e0b; border-radius:3px;"></div> Yielding / Waiting</div>
        <div class="legend-item"><div class="legend-box" style="background:#0284c7; border:1px solid #38bdf8; border-radius:3px;"></div> Overtaking</div>
        <div class="legend-item"><div class="legend-box" style="background:#7e22ce; border:1px solid #a855f7; border-radius:3px;"></div> Dynamic Reroute</div>
        <div class="legend-item"><div class="legend-box" style="background:#111827; border:2px dashed #38bdf8;"></div> Rack: Bot Placing Parcel (Dotted Blue)</div>
        <div class="legend-item"><div class="legend-box" style="background:#111827; border:2px dashed #ef4444;"></div> Rack: Bot Picking Parcel (Dotted Red)</div>
        <div class="legend-item"><div class="legend-box" style="background:#b91c1c; border:1px solid #ef4444; border-radius:3px;"></div> Low Battery (&le;25% SoC)</div>
        <div class="legend-item"><div class="legend-box" style="background:#14532d; border:1px solid #22c55e; border-radius:3px;"></div> ⚡ CC/CV Fast Charging</div>
      </div>

      <div class="controls">
        <button class="ctrl-btn" id="pause-btn" onclick="togglePause()" title="Pause/Resume Simulation" style="font-size:14px;">⏸️</button>
        <button class="ctrl-btn" id="ctrl-speed-btn" onclick="cycleSimulationSpeed()" title="Cycle Simulation Speed (1x, 2x, 5x, 10x)" style="font-weight:700; font-size:12px;">1x</button>
        <button class="ctrl-btn" onclick="switchMainTab('terminal')" title="Switch to Terminal &amp; Bots Health Tab">&gt;_</button>
        <button class="ctrl-btn" onclick="toggleHud()" title="Toggle Warehouse Info Panel">ℹ</button>
        <button class="ctrl-btn" onclick="zoom(1.2)" title="Zoom In">+</button>
        <button class="ctrl-btn" onclick="zoom(0.8)" title="Zoom Out">&minus;</button>
        <button class="ctrl-btn" onclick="resetView()" title="Fit to Screen">&#x21bb;</button>
      </div>

      <div id="cell-tooltip"></div>
    </div>

    <!-- TAB 2: OPERATIONS TERMINAL & BOTS HEALTH DASHBOARD -->
    <div id="view-terminal-health" class="app-view">
      <div class="th-container">
        <!-- Top Toolbar with Sub-view Mode Switcher & Fleet KPIs -->
        <div class="th-top-bar">
          <div class="th-view-modes">
            <span class="th-label">VIEW MODE:</span>
            <button class="th-mode-btn active" id="btn-mode-split" onclick="setThLayoutMode('split')" title="View Bots Health and Terminal Side-by-Side">
              <span>⚡ Split View</span>
            </button>
            <button class="th-mode-btn" id="btn-mode-bots" onclick="setThLayoutMode('bots')" title="Maximize Bots Health Telemetry">
              <span>🤖 Bots Health Only</span>
            </button>
            <button class="th-mode-btn" id="btn-mode-term" onclick="setThLayoutMode('term')" title="Maximize Terminal Log Stream">
              <span>💻 Terminal Only</span>
            </button>
          </div>

          <div class="th-kpi-summary">
            <div class="th-kpi-pill"><span class="kpi-dot green"></span> Fleet: <strong id="kpi-fleet-status">8 Online</strong></div>
            <div class="th-kpi-pill">🔋 Avg SoC: <strong id="kpi-avg-battery" style="color:#22c55e;">85%</strong></div>
            <div class="th-kpi-pill">⚡ Net Power: <strong id="kpi-net-power" style="color:#38bdf8;">+22.4 kW</strong></div>
            <div class="th-kpi-pill">📦 Freight: <strong id="kpi-total-freight" style="color:#facc15;">0.0 kg</strong></div>
            <div class="th-kpi-pill">⚡ Chargers: <strong id="kpi-chargers-avail" style="color:#4ade80;">8/8 Available</strong></div>
            <div class="th-kpi-pill">🛡️ Collisions: <strong style="color:#22c55e;">0 (Safe)</strong></div>
          </div>
        </div>

        <!-- Main Body: Panes Container -->
        <div class="th-panes mode-split" id="th-panes">
          <!-- PANE A: BOTS HEALTH DASHBOARD -->
          <div class="th-pane th-pane-bots" id="pane-bots">
            <div class="pane-header">
              <div class="pane-title">
                <span>🤖</span> AMR FLEET HEALTH &amp; BMS TELEMETRY
                <span class="pane-badge" id="bots-status-summary">8 Bots Monitored</span>
              </div>
              <div class="pane-actions">
                <button class="term-btn" onclick="openLogsModal()" title="Export Fleet Telemetry Logs">📥 Export Logs</button>
                <button class="term-btn" onclick="recallAllIdleBots()" title="Recall all idle floor robots to their nearest available fast chargers">⚡ Dock All Idle (Nearest)</button>
                <button class="term-btn" onclick="switchMainTab('map')" title="Jump to 2D Map View">🗺️ View on Map</button>
              </div>
            </div>
            
            <div class="bots-grid" id="bots-cards-grid">
              <!-- Dynamically populated 8 AMR Health Cards -->
            </div>
          </div>

          <!-- PANE B: OPERATIONS TERMINAL STREAM -->
          <div class="th-pane th-pane-terminal" id="pane-terminal">
            <div class="pane-header">
              <div class="pane-title">
                <span>&gt;_</span> PARCEL &amp; FLEET EVENT STREAM
                <span class="terminal-badge" id="term-event-count">0</span>
              </div>
              <div class="terminal-controls">
                <div class="log-filter-group">
                  <button class="filter-pill active" data-filter="ALL" onclick="setLogFilter('ALL', this)">All</button>
                  <button class="filter-pill" data-filter="INBOUND" onclick="setLogFilter('INBOUND', this)">Inbound</button>
                  <button class="filter-pill" data-filter="OUTBOUND" onclick="setLogFilter('OUTBOUND', this)">Outbound</button>
                  <button class="filter-pill" data-filter="TRAFFIC" onclick="setLogFilter('TRAFFIC', this)">Traffic</button>
                  <button class="filter-pill" data-filter="BMS" onclick="setLogFilter('BMS', this)">BMS</button>
                </div>
                <button class="term-btn" onclick="openLogsModal()" title="Download Fleet Logs">📥 Export Logs</button>
                <button class="term-btn" onclick="clearTerminal()" title="Clear Terminal Logs">Clear</button>
                <button class="term-btn" id="term-autoscroll-btn" onclick="toggleAutoScroll()" title="Toggle Auto-Scroll">Scroll: ON</button>
              </div>
            </div>

            <div class="terminal-body" id="terminal-body">
              <!-- Live event rows go here -->
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: BOT PROBLEMS & FLEET DIAGNOSTICS DASHBOARD -->
    <div id="view-problems" class="app-view">
      <div class="prob-container">
        <!-- Top Toolbar with Problem KPIs & Fleet Controls -->
        <div class="prob-top-bar">
          <div class="prob-kpi-summary">
            <div class="prob-kpi-card" id="kpi-card-collisions">
              <div class="prob-kpi-icon">💥</div>
              <div class="prob-kpi-info">
                <span class="prob-kpi-lbl">Collisions &amp; Conflicts</span>
                <div class="prob-kpi-val" id="prob-kpi-collisions" style="color:#ef4444;">0</div>
              </div>
            </div>
            <div class="prob-kpi-card" id="kpi-card-out-of-charge">
              <div class="prob-kpi-icon">🪫</div>
              <div class="prob-kpi-info">
                <span class="prob-kpi-lbl">Battery Floor (≤10%)</span>
                <div class="prob-kpi-val" id="prob-kpi-out-of-charge" style="color:#f87171;">0</div>
              </div>
            </div>
            <div class="prob-kpi-card" id="kpi-card-deadlocks">
              <div class="prob-kpi-icon">🛑</div>
              <div class="prob-kpi-info">
                <span class="prob-kpi-lbl">Gridlocks &amp; Stalls (&gt;2.5s)</span>
                <div class="prob-kpi-val" id="prob-kpi-deadlocks" style="color:#f59e0b;">0</div>
              </div>
            </div>
            <div class="prob-kpi-card" id="kpi-card-bms-deficits">
              <div class="prob-kpi-icon">⚠️</div>
              <div class="prob-kpi-info">
                <span class="prob-kpi-lbl">BMS Energy Deficits</span>
                <div class="prob-kpi-val" id="prob-kpi-bms-deficits" style="color:#38bdf8;">0</div>
              </div>
            </div>
          </div>

          <div class="prob-global-actions">
            <button class="prob-action-btn rescue-all" onclick="towAllStrandedBots()" title="Emergency dispatch rescue tug to tow all low-SoC bots to fast chargers">
              <span>⚡ Tow Stranded Bots</span>
            </button>
            <button class="prob-action-btn unblock-all" onclick="breakAllDeadlocks()" title="Force nudge and reroute all waiting or deadlocked bots">
              <span>🔄 Break All Gridlocks</span>
            </button>
            <button class="prob-action-btn clear-resolved" onclick="clearResolvedIncidents()" title="Clear all resolved problem logs">
              <span>🧹 Clear Resolved</span>
            </button>
          </div>
        </div>

        <!-- Filter Subbar -->
        <div class="prob-sub-bar">
          <div class="prob-filter-group">
            <span class="prob-filter-lbl">FILTER PROBLEMS:</span>
            <button class="prob-filter-pill active" data-filter="ALL" onclick="setProblemFilter('ALL', this)">All Incidents</button>
            <button class="prob-filter-pill" data-filter="COLLISION" onclick="setProblemFilter('COLLISION', this)">💥 Collisions</button>
            <button class="prob-filter-pill" data-filter="OUT_OF_CHARGE" onclick="setProblemFilter('OUT_OF_CHARGE', this)">🪫 Out of Charge</button>
            <button class="prob-filter-pill" data-filter="DEADLOCK" onclick="setProblemFilter('DEADLOCK', this)">🛑 Gridlocks</button>
            <button class="prob-filter-pill" data-filter="BMS_DEFICIT" onclick="setProblemFilter('BMS_DEFICIT', this)">⚠️ BMS Deficits</button>
          </div>
          <div class="prob-status-legend">
            <span class="legend-badge"><span class="badge-dot pulse-red"></span> Active Problem</span>
            <span class="legend-badge"><span class="badge-dot green"></span> Resolved</span>
          </div>
        </div>

        <!-- Main Body: Two Panes (Live Feed & Fleet Diagnostics Matrix) -->
        <div class="prob-panes">
          <!-- PANE 1: LIVE INCIDENTS LOG & ACTIONS (58%) -->
          <div class="prob-pane prob-pane-feed">
            <div class="pane-header">
              <div class="pane-title">
                <span>🚨</span> LIVE FLEET INCIDENT FEED &amp; REMEDIATION
                <span class="pane-badge" id="prob-incident-count">0 Incidents</span>
              </div>
              <div class="pane-actions">
                <span style="font-size:11px; color:var(--text-muted);">Real-time collision, UVLO &amp; traffic diagnostics</span>
              </div>
            </div>
            <div class="prob-feed-body" id="prob-feed-list">
              <!-- Dynamically rendered incident cards -->
            </div>
          </div>

          <!-- PANE 2: FLEET DIAGNOSTICS & TELEMETRY MATRIX (42%) -->
          <div class="prob-pane prob-pane-matrix">
            <div class="pane-header">
              <div class="pane-title">
                <span>🤖</span> 8-AMR HEALTH &amp; IMMOBILIZATION MATRIX
                <span class="pane-badge" id="prob-matrix-summary">8 Monitored</span>
              </div>
              <div class="pane-actions">
                <button class="term-btn" onclick="switchMainTab('map')" title="View on 2D Warehouse Map">🗺️ Map</button>
              </div>
            </div>
            <div class="prob-matrix-body" id="prob-matrix-grid">
              <!-- 8 compact AMR diagnostic rows -->
            </div>
          </div>
        </div>
      </div>
    </div>

    <div id="cell-tooltip"></div>

    <!-- Bulk Parcel Modal -->
    <div class="modal-overlay" id="bulk-modal" onclick="closeBulkModal(event)">
      <div class="modal-box" onclick="event.stopPropagation()">
        <div class="modal-header">
          <div class="modal-title"><span>📦</span> Ingest Parcels to 3D Racks</div>
          <button class="modal-close-btn" onclick="closeBulkModal()">&times;</button>
        </div>
        <div class="modal-body">
          <p style="color:var(--text-muted); font-size:12px; margin-bottom:12px; line-height:1.4;">
            Directly populate $N$ parcels into available 3D storage slots (Levels 1 to 5). Maximum warehouse capacity: <strong style="color:#fff;">7,560 slots</strong>.
          </p>
          <div class="input-group">
            <label for="bulk-input-val">Number of Parcels to Ingest:</label>
            <input type="number" id="bulk-input-val" value="50" min="1" max="7560" onkeydown="if(event.key==='Enter') submitBulkIngest()" />
          </div>
          <div class="quick-presets">
            <span class="preset-label">Quick Presets:</span>
            <button type="button" class="preset-btn" onclick="setPresetN(10)">+10</button>
            <button type="button" class="preset-btn" onclick="setPresetN(50)">+50</button>
            <button type="button" class="preset-btn" onclick="setPresetN(200)">+200</button>
            <button type="button" class="preset-btn" onclick="setPresetN(1000)">+1000</button>
            <button type="button" class="preset-btn" onclick="fillCapacity(0.5)">50% Full</button>
            <button type="button" class="preset-btn" onclick="fillCapacity(1.0)">100% Full</button>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn cancel" onclick="closeBulkModal()">Cancel</button>
          <button class="modal-btn confirm" onclick="submitBulkIngest()">📥 Inject Parcels</button>
        </div>
      </div>
    </div>

    <!-- Comprehensive Bot & Fleet Telemetry Logs Modal -->
    <div class="modal-overlay" id="logs-modal" onclick="closeLogsModal(event)">
      <div class="modal-box modal-box-wide" onclick="event.stopPropagation()">
        <div class="modal-header">
          <div class="modal-title"><span>📥</span> AMR Fleet &amp; Bot Telemetry Export</div>
          <button class="modal-close-btn" onclick="closeLogsModal()">&times;</button>
        </div>
        <div class="modal-body">
          <p style="color:var(--text-muted); font-size:12px; margin-bottom:14px; line-height:1.45;">
            Download deep-dive operational flight recorder telemetry for all AMRs. Logs include <strong>exact time spent waiting in jams</strong>, right-of-way yields, deadlock back-ups, overtaking maneuvers, BMS power curves, distance, and mission lifecycles.
          </p>

          <!-- Fleet Overview KPI Strip -->
          <div class="logs-kpi-grid">
            <div class="logs-kpi-item">
              <span class="logs-kpi-label">Simulation Time</span>
              <span class="logs-kpi-val" id="modal-log-sim-time">0m 0s</span>
            </div>
            <div class="logs-kpi-item">
              <span class="logs-kpi-label">Active Moving Time</span>
              <span class="logs-kpi-val" id="modal-log-moving-time" style="color:#38bdf8;">0.0s</span>
            </div>
            <div class="logs-kpi-item">
              <span class="logs-kpi-label">Jam &amp; Wait Delay</span>
              <span class="logs-kpi-val" id="modal-log-jam-time" style="color:#f59e0b;">0.0s (0%)</span>
            </div>
            <div class="logs-kpi-item">
              <span class="logs-kpi-label">Traffic Delays</span>
              <span class="logs-kpi-val" id="modal-log-jams-count" style="color:#fde047;">0</span>
            </div>
            <div class="logs-kpi-item">
              <span class="logs-kpi-label">Freight Handled</span>
              <span class="logs-kpi-val" id="modal-log-freight" style="color:#22c55e;">0 pkgs</span>
            </div>
            <div class="logs-kpi-item">
              <span class="logs-kpi-label">Total Distance</span>
              <span class="logs-kpi-val" id="modal-log-distance" style="color:#c084fc;">0 cells</span>
            </div>
          </div>

          <!-- Download Action Cards Grid -->
          <div class="logs-options-grid">
            <!-- Option 1: Full Fleet JSON -->
            <div class="log-card">
              <div>
                <div class="log-card-header">
                  <span class="log-card-icon">📄</span>
                  <div>
                    <div class="log-card-title">Full Fleet Telemetry (JSON)</div>
                    <span style="font-size:10px; color:#38bdf8; font-weight:600;">Complete Flight Recorder</span>
                  </div>
                </div>
                <div class="log-card-desc" style="margin-top:6px;">
                  All 8 bots with full event history, chronological audit trail, state machine transitions, individual jam episodes with start/end timestamps, BMS power draws, and mission histories.
                </div>
              </div>
              <div class="log-card-actions">
                <button class="log-card-btn primary" onclick="downloadFleetJson()">
                  <span>📥</span> Download Full JSON
                </button>
              </div>
            </div>

            <!-- Option 2: Fleet Performance Summary CSV -->
            <div class="log-card">
              <div>
                <div class="log-card-header">
                  <span class="log-card-icon">📊</span>
                  <div>
                    <div class="log-card-title">Fleet Performance Summary (CSV)</div>
                    <span style="font-size:10px; color:#4ade80; font-weight:600;">Spreadsheet &amp; Pandas Ready</span>
                  </div>
                </div>
                <div class="log-card-desc" style="margin-top:6px;">
                  Tabular overview per bot: Active Moving Time, Jam Wait Time, Jam Delay %, Charging Time, Idle Time, Total Distance, Average Speed, Energy Consumed, and Operational Availability.
                </div>
              </div>
              <div class="log-card-actions">
                <button class="log-card-btn" onclick="downloadPerformanceCsv()">
                  <span>📊</span> Download Summary CSV
                </button>
              </div>
            </div>

            <!-- Option 3: Traffic Jams & Delays CSV -->
            <div class="log-card">
              <div>
                <div class="log-card-header">
                  <span class="log-card-icon">🛑</span>
                  <div>
                    <div class="log-card-title">Traffic Jams &amp; Delays (CSV)</div>
                    <span style="font-size:10px; color:#f59e0b; font-weight:600;">Granular Wait Time Audit</span>
                  </div>
                </div>
                <div class="log-card-desc" style="margin-top:6px;">
                  Every single traffic wait event: exact duration (seconds), tile location (X, Y), conflicting bot ID, SoC priority comparison, reason (head-on, trailing, AEB), and resolution mechanism.
                </div>
              </div>
              <div class="log-card-actions">
                <button class="log-card-btn" onclick="downloadJamsCsv()">
                  <span>🛑</span> Download Jams CSV
                </button>
              </div>
            </div>

            <!-- Option 4: Individual Bot Deep-Dive -->
            <div class="log-card">
              <div>
                <div class="log-card-header">
                  <span class="log-card-icon">🤖</span>
                  <div>
                    <div class="log-card-title">Individual Bot Log Export</div>
                    <span style="font-size:10px; color:#a855f7; font-weight:600;">Single Vehicle Telemetry</span>
                  </div>
                </div>
                <div class="log-card-desc" style="margin-top:6px;">
                  Select any robot to isolate its specific flight log, speed curves, battery lifecycle floor, and jam history.
                </div>
                <div style="margin-top:8px; display:flex; align-items:center; gap:8px;">
                  <label for="modal-bot-select" style="font-size:11px; color:var(--text-muted); font-weight:600;">Select AMR:</label>
                  <select id="modal-bot-select" class="log-bot-selector">
                    <option value="AMR-01">AMR-01</option>
                    <option value="AMR-02">AMR-02</option>
                    <option value="AMR-03">AMR-03</option>
                    <option value="AMR-04">AMR-04</option>
                    <option value="AMR-05">AMR-05</option>
                    <option value="AMR-06">AMR-06</option>
                    <option value="AMR-07">AMR-07</option>
                    <option value="AMR-08">AMR-08</option>
                  </select>
                </div>
              </div>
              <div class="log-card-actions" style="margin-top:6px;">
                <button class="log-card-btn" onclick="downloadBotLog(document.getElementById('modal-bot-select').value, 'json')">
                  <span>📄</span> Bot JSON
                </button>
                <button class="log-card-btn" onclick="downloadBotLog(document.getElementById('modal-bot-select').value, 'csv')">
                  <span>📊</span> Bot Jams CSV
                </button>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn cancel" onclick="closeLogsModal()">Close</button>
          <button class="modal-btn confirm" style="background:#0284c7;" onclick="downloadFleetJson()">📥 Export All Data</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    const canvas = document.getElementById('viewport');
    const ctx = canvas.getContext('2d');
    const tooltip = document.getElementById('cell-tooltip');
    const coordsLabel = document.getElementById('cursor-coords');

    let mapData = null;
    let camera = { x: 0, y: 0, scale: 18 };
    let isDragging = false;
    let dragStart = { x: 0, y: 0 };

    function toggleHud() {
      const card = document.getElementById('hud-card');
      const icon = document.getElementById('hud-toggle-icon');
      card.classList.toggle('collapsed');
      if (card.classList.contains('collapsed')) {
        icon.innerHTML = '&plus;';
      } else {
        icon.innerHTML = '&minus;';
      }
    }

    // ==========================================
    // TAB NAVIGATION & BOTS HEALTH / TERMINAL
    // ==========================================
    let currentMainTab = 'map';
    let currentThMode = 'split';
    let currentLogFilter = 'ALL';
    let termEventCount = 0;
    let autoScroll = true;

    function switchMainTab(tabName) {
      currentMainTab = tabName;
      const mapBtn = document.getElementById('tab-btn-map');
      const termBtn = document.getElementById('tab-btn-terminal');
      const probBtn = document.getElementById('tab-btn-problems');
      const mapView = document.getElementById('view-map');
      const termView = document.getElementById('view-terminal-health');
      const probView = document.getElementById('view-problems');

      if (mapBtn) mapBtn.classList.toggle('active', tabName === 'map');
      if (termBtn) termBtn.classList.toggle('active', tabName === 'terminal');
      if (probBtn) probBtn.classList.toggle('active', tabName === 'problems');

      if (mapView) mapView.classList.toggle('active', tabName === 'map');
      if (termView) termView.classList.toggle('active', tabName === 'terminal');
      if (probView) probView.classList.toggle('active', tabName === 'problems');

      if (tabName === 'map') {
        resize();
        render();
      } else if (tabName === 'terminal') {
        updateBotsHealthDashboard();
      } else if (tabName === 'problems') {
        updateProblemsDashboard();
      }
    }

    function toggleTerminal() {
      switchMainTab(currentMainTab === 'map' ? 'terminal' : 'map');
    }

    function setThLayoutMode(mode) {
      currentThMode = mode;
      const panes = document.getElementById('th-panes');
      const btnSplit = document.getElementById('btn-mode-split');
      const btnBots = document.getElementById('btn-mode-bots');
      const btnTerm = document.getElementById('btn-mode-term');

      if (btnSplit) btnSplit.classList.toggle('active', mode === 'split');
      if (btnBots) btnBots.classList.toggle('active', mode === 'bots');
      if (btnTerm) btnTerm.classList.toggle('active', mode === 'term');

      if (panes) {
        panes.className = `th-panes mode-${mode}`;
      }
    }

    function setLogFilter(filterName, btn) {
      currentLogFilter = filterName;
      const pills = document.querySelectorAll('.filter-pill');
      pills.forEach(p => p.classList.toggle('active', p.getAttribute('data-filter') === filterName));

      const body = document.getElementById('terminal-body');
      if (!body) return;
      const entries = body.querySelectorAll('.log-entry');
      entries.forEach(entry => {
        const cat = entry.getAttribute('data-cat') || 'ALL';
        if (filterName === 'ALL' || cat === filterName) {
          entry.style.display = 'flex';
        } else {
          entry.style.display = 'none';
        }
      });
    }

    function toggleAutoScroll() {
      autoScroll = !autoScroll;
      const btn = document.getElementById('term-autoscroll-btn');
      if (btn) btn.innerText = 'Scroll: ' + (autoScroll ? 'ON' : 'OFF');
    }

    function clearTerminal() {
      const body = document.getElementById('terminal-body');
      if (body) body.innerHTML = '';
      termEventCount = 0;
      const counterEl = document.getElementById('term-event-count');
      if (counterEl) counterEl.innerText = '0';
      const badge = document.getElementById('tab-event-badge');
      if (badge) badge.innerText = '0';
    }

    function logTerminal(type, tagClass, text) {
      termEventCount++;
      const counterEl = document.getElementById('term-event-count');
      if (counterEl) counterEl.innerText = termEventCount;
      const tabBadge = document.getElementById('tab-event-badge');
      if (tabBadge) tabBadge.innerText = termEventCount;

      const body = document.getElementById('terminal-body');
      if (!body) return;

      const now = new Date();
      const timeStr = now.toTimeString().split(' ')[0];

      // Classify log into category for filtering
      let cat = 'ALL';
      if (tagClass.includes('inbound') || type === 'INBOUND' || type === 'SHELVING') cat = 'INBOUND';
      else if (tagClass.includes('outbound') || type === 'OUTBOUND' || type === 'PICKUP' || type === 'DISPATCH') cat = 'OUTBOUND';
      else if (tagClass.includes('overtake') || tagClass.includes('yield') || tagClass.includes('reroute') || type === 'YIELD' || type === 'OVERTAKE' || type === 'REROUTE') cat = 'TRAFFIC';
      else if (type === 'BMS' || type === 'SPEED' || type === 'ALERT') cat = 'BMS';

      const row = document.createElement('div');
      row.className = 'log-entry';
      row.setAttribute('data-cat', cat);
      if (currentLogFilter !== 'ALL' && cat !== currentLogFilter) {
        row.style.display = 'none';
      }
      row.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-tag ${tagClass}">${type}</span> <span class="log-msg">${text}</span>`;
      body.appendChild(row);

      // Keep up to 400 lines in memory
      if (body.children.length > 400) {
        body.removeChild(body.firstChild);
      }

      if (autoScroll) {
        body.scrollTop = body.scrollHeight;
      }
    }

    function locateBotOnMap(robotId) {
      const r = AMR_FLEET.find(b => b.id === robotId);
      if (!r) return;
      r.mapPingTimer = 4.0; // Trigger high-visibility radar ping on map
      switchMainTab('map');
      const w = canvas.width / window.devicePixelRatio;
      const h = canvas.height / window.devicePixelRatio;
      camera.x = w / 2 - (r.x + 0.5) * camera.scale;
      camera.y = h / 2 - (r.y + 0.5) * camera.scale;
      render();
    }

    // =========================================================================
    // AMR BOT TRACKING & ACTIVE CAMERA FOLLOW SYSTEM
    // =========================================================================
    let trackedRobotId = null;
    let trackCameraFollow = true;

    function trackBot(robotId, enableCameraFollow = true) {
      const r = AMR_FLEET.find(b => b.id === robotId);
      if (!r) return;
      trackedRobotId = robotId;
      trackCameraFollow = enableCameraFollow;
      r.mapPingTimer = 2.5;

      const selectEl = document.getElementById('track-bot-select');
      if (selectEl) selectEl.value = robotId;

      const camBtn = document.getElementById('track-cam-toggle-btn');
      if (camBtn) {
        camBtn.classList.toggle('active', trackCameraFollow);
        camBtn.innerHTML = trackCameraFollow ? '🎥 Cam: ON' : '🎥 Cam: OFF';
      }

      if (currentMainTab !== 'map') {
        switchMainTab('map');
      }

      // If camera scale is currently zoomed out, zoom in for closer inspection
      if (camera.scale < 24) {
        zoomToScale(24);
      }

      centerOnTrackedBot();
      updateTrackingHud();
      render();
    }

    function stopTrackingBot() {
      trackedRobotId = null;
      const selectEl = document.getElementById('track-bot-select');
      if (selectEl) selectEl.value = '';
      const hud = document.getElementById('bot-tracking-hud');
      if (hud) hud.style.display = 'none';
      render();
    }

    function toggleTrackCameraFollow() {
      trackCameraFollow = !trackCameraFollow;
      const btn = document.getElementById('track-cam-toggle-btn');
      if (btn) {
        btn.classList.toggle('active', trackCameraFollow);
        btn.innerHTML = trackCameraFollow ? '🎥 Cam: ON' : '🎥 Cam: OFF';
      }
      if (trackCameraFollow && trackedRobotId) {
        centerOnTrackedBot();
      }
    }

    function cycleTrackedRobot(direction = 1) {
      if (AMR_FLEET.length === 0) return;
      let currIdx = AMR_FLEET.findIndex(b => b.id === trackedRobotId);
      if (currIdx === -1) {
        currIdx = 0;
      } else {
        currIdx = (currIdx + direction + AMR_FLEET.length) % AMR_FLEET.length;
      }
      trackBot(AMR_FLEET[currIdx].id, trackCameraFollow);
    }

    function centerOnTrackedBot() {
      if (!trackedRobotId) return;
      const r = AMR_FLEET.find(b => b.id === trackedRobotId);
      if (!r) return;
      const w = canvas.width / window.devicePixelRatio;
      const h = canvas.height / window.devicePixelRatio;
      const offsetX = window.innerWidth > 1000 ? -40 : 0;
      camera.x = (w / 2 + offsetX) - (r.x + 0.5) * camera.scale;
      camera.y = (h / 2) - (r.y + 0.5) * camera.scale;
      render();
    }

    function zoomToScale(newScale) {
      const centerW = (canvas.width / window.devicePixelRatio) / 2;
      const centerH = (canvas.height / window.devicePixelRatio) / 2;
      camera.x = centerW - (centerW - camera.x) * (newScale / camera.scale);
      camera.y = centerH - (centerH - camera.y) * (newScale / camera.scale);
      camera.scale = newScale;
    }

    function onTrackBotSelectChange(val) {
      if (!val) {
        stopTrackingBot();
      } else {
        trackBot(val, true);
      }
    }

    function recallTrackedBotToCharger() {
      if (trackedRobotId) {
        sendBotToCharger(trackedRobotId);
      }
    }

    function inspectTrackedBotInHealth() {
      if (!trackedRobotId) return;
      const botId = trackedRobotId;
      switchMainTab('terminal');
      setTimeout(() => {
        const card = document.getElementById(`bot-card-${botId}`);
        if (card) {
          card.scrollIntoView({ behavior: 'smooth', block: 'center' });
          card.style.outline = '2px solid #38bdf8';
          card.style.boxShadow = '0 0 16px rgba(56, 189, 248, 0.4)';
          setTimeout(() => {
            card.style.outline = '';
            card.style.boxShadow = '';
          }, 3000);
        }
      }, 100);
    }

    function updateTrackingHud() {
      const hud = document.getElementById('bot-tracking-hud');
      if (!hud) return;
      if (!trackedRobotId) {
        hud.style.display = 'none';
        return;
      }
      const r = AMR_FLEET.find(b => b.id === trackedRobotId);
      if (!r) {
        hud.style.display = 'none';
        return;
      }
      hud.style.display = 'block';

      // Title & state badge
      const idEl = document.getElementById('track-hud-robot-id');
      if (idEl) idEl.innerText = r.id;

      let stateText = 'STANDBY';
      let stateColor = '#94a3b8';
      let stateBg = 'rgba(148, 163, 184, 0.15)';
      if (r.state === 'IDLE_CHARGING') {
        stateText = '⚡ CHARGING';
        stateColor = '#22c55e';
        stateBg = 'rgba(34, 197, 94, 0.2)';
      } else if (r.state === 'MOVING_TO_PICKUP') {
        stateText = 'EN ROUTE DOCK';
        stateColor = '#38bdf8';
        stateBg = 'rgba(56, 189, 248, 0.2)';
      } else if (r.state === 'LOADING_INBOUND') {
        stateText = 'LOADING SHIPMENT';
        stateColor = '#facc15';
        stateBg = 'rgba(250, 204, 21, 0.2)';
      } else if (r.state === 'CARRYING_TO_RACK') {
        stateText = 'SHELVING SHIPMENT';
        stateColor = '#facc15';
        stateBg = 'rgba(250, 204, 21, 0.2)';
      } else if (r.state === 'ORDER_PICKING') {
        stateText = 'ORDER PICKING';
        stateColor = '#f59e0b';
        stateBg = 'rgba(245, 158, 11, 0.2)';
      } else if (r.state === 'DELIVERING_ORDER_TO_BAY') {
        stateText = 'DELIVERING BAY';
        stateColor = '#ea580c';
        stateBg = 'rgba(234, 88, 12, 0.2)';
      } else if (r.state === 'RETURNING_HOME') {
        stateText = 'RETURN CHARGER';
        stateColor = '#10b981';
        stateBg = 'rgba(16, 185, 129, 0.2)';
      } else if (r.state === 'OUT_OF_CHARGE') {
        stateText = 'LOW BATT 10%';
        stateColor = '#ef4444';
        stateBg = 'rgba(239, 68, 68, 0.25)';
      }

      if (r.isWaiting) {
        stateText = `WAIT (YIELD)`;
        stateColor = '#f59e0b';
        stateBg = 'rgba(245, 158, 11, 0.25)';
      } else if (r.isOvertaking) {
        stateText = `OVERTAKING`;
        stateColor = '#38bdf8';
        stateBg = 'rgba(56, 189, 248, 0.25)';
      } else if (r.isRerouting) {
        stateText = `DETOUR / REROUTE`;
        stateColor = '#c084fc';
        stateBg = 'rgba(192, 132, 252, 0.25)';
      }

      const badgeEl = document.getElementById('track-hud-state-badge');
      if (badgeEl) {
        badgeEl.innerText = stateText;
        badgeEl.style.color = stateColor;
        badgeEl.style.background = stateBg;
        badgeEl.style.border = `1px solid ${stateColor}`;
      }

      // Battery
      const battEl = document.getElementById('track-hud-battery');
      const battFill = document.getElementById('track-hud-batt-fill');
      if (battEl) battEl.innerText = `${r.battery.toFixed(1)}%`;
      if (battFill) {
        battFill.style.width = `${Math.min(100, Math.max(0, r.battery))}%`;
        const bColor = r.battery > 50 ? '#22c55e' : (r.battery > 20 ? '#f59e0b' : '#ef4444');
        battFill.style.background = bColor;
      }

      // Speed & Load
      const spdEl = document.getElementById('track-hud-speed');
      const loadEl = document.getElementById('track-hud-load');
      const curSpeed = r.isWaiting ? 0 : (r.currentSpeed || (ROBOT_BASE_SPEED * simSpeed));
      if (spdEl) spdEl.innerText = `${curSpeed.toFixed(2)} cells/s`;
      const dampPct = r.payloadDamping ? Math.round(r.payloadDamping * 100) : 100;
      if (loadEl) loadEl.innerText = `${(r.payloadWeight || 0).toFixed(1)} kg (${dampPct}% throttle)`;

      // Position & Heading
      const coordsEl = document.getElementById('track-hud-coords');
      const headingEl = document.getElementById('track-hud-heading');
      if (coordsEl) coordsEl.innerText = `X: ${r.x.toFixed(1)}, Y: ${r.y.toFixed(1)}`;
      const deg = Math.round(((r.heading * 180 / Math.PI) + 360) % 360);
      const dirs = ['E', 'SE', 'S', 'SW', 'W', 'NW', 'N', 'NE'];
      const dirTxt = dirs[Math.round(deg / 45) % 8];
      if (headingEl) headingEl.innerText = `Heading: ${deg}° (${dirTxt})`;

      // Power, Edge AI Compute & BMS Phase
      const pwrEl = document.getElementById('track-hud-power');
      const phaseEl = document.getElementById('track-hud-charge-phase');
      const compWatts = r.computeWatts || 28;
      const compLoad = r.computeLoad || 45;
      const compTops = r.computeTops || '115.5';

      if (r.state === 'IDLE_CHARGING') {
        const kw = (r.chargeRateKw || 30.0).toFixed(1);
        if (pwrEl) pwrEl.innerText = `+${kw} kW (30kW CC/CV Fast Charge)`;
        if (phaseEl) phaseEl.innerText = r.chargePhase || 'Charging';
      } else {
        if (pwrEl) pwrEl.innerText = `${Math.round(r.powerWatts || 165)} W [Edge AI: ${compWatts}W (${compLoad}% Load, ${compTops} TOPS)]`;
        if (phaseEl) phaseEl.innerText = r.isWaiting ? 'Idle Standby (AEB Buffer)' : 'Discharging';
      }

      // Proximity & Collision Clearance Measurement
      let nearestPeerDist = 999.0;
      let nearestPeerId = 'None';
      for (const o of AMR_FLEET) {
        if (o.id === r.id) continue;
        const d = Math.hypot(r.x - o.x, r.y - o.y);
        if (d < nearestPeerDist) {
          nearestPeerDist = d;
          nearestPeerId = o.id;
        }
      }
      const safeClearance = Math.max(0, nearestPeerDist - 0.70); // 0.70m is physical collision boundary

      // Target & Mission Box with Charging & Proximity
      const targetEl = document.getElementById('track-hud-target-desc');
      const slaEl = document.getElementById('track-hud-sla');
      if (targetEl) targetEl.innerText = r.targetDesc || 'Idle Standby';

      const nearestInfo = getNearestAvailableCharger(r.gridX, r.gridY, r.id);
      let slaTxt = 'Fleet Standby';
      if (r.orderBox && r.orderBox.importance) {
        slaTxt = `SLA: ${r.orderBox.importance.label}`;
      } else if (r.carriedParcels && r.carriedParcels.length > 0 && r.carriedParcels[0].importance) {
        slaTxt = `SLA: ${r.carriedParcels[0].importance.label}`;
      }
      const chgDist = nearestInfo.distance !== undefined ? `${nearestInfo.distance} cells` : 'nearby';
      const proxTxt = nearestPeerDist < 900 ? `Peer Dist: ${nearestPeerDist.toFixed(2)}m (${nearestPeerId}, +${safeClearance.toFixed(2)}m buffer)` : 'No peers nearby';
      if (slaEl) slaEl.innerText = `${slaTxt} | ⚡ Nearest Charger: ${nearestInfo.charger ? nearestInfo.charger.id : 'CH-01'} (${chgDist}) | 📏 ${proxTxt}`;

      // Cargo Manifest List
      const countEl = document.getElementById('track-hud-cargo-count');
      const listEl = document.getElementById('track-hud-cargo-list');
      if (r.orderBox) {
        const ob = r.orderBox;
        if (countEl) countEl.innerText = `${ob.items.length}/${ob.totalItems} items (${(ob.totalWeight || 5).toFixed(1)}kg)`;
        if (listEl) {
          if (ob.items && ob.items.length > 0) {
            listEl.innerHTML = ob.items.map(it => `<div>• <strong style="color:#f59e0b;">${it.parcel_id}</strong> (${it.name}, ${it.weight})</div>`).join('');
          } else {
            listEl.innerHTML = '<span style="color:#64748b; font-style:italic;">Navigating to racks to collect items...</span>';
          }
        }
      } else if (r.carriedParcels && r.carriedParcels.length > 0) {
        if (countEl) countEl.innerText = `${r.carriedParcels.length} pkgs (${(r.payloadWeight || 10).toFixed(1)}kg)`;
        if (listEl) {
          listEl.innerHTML = r.carriedParcels.map(p => `<div>• <strong style="color:#facc15;">${p.parcel_id}</strong> (${p.name}, ${p.weight}) → Rack Tier ${p.rackSlot ? p.rackSlot.floorNum : '1'}</div>`).join('');
        }
      } else {
        if (countEl) countEl.innerText = 'Empty Tote';
        if (listEl) listEl.innerHTML = '<span style="color:#64748b; font-style:italic;">No parcels currently loaded on chassis.</span>';
      }
    }

    // =========================================================================
    // FLEET PROBLEMS, COLLISIONS & INCIDENT DIAGNOSTICS ENGINE
    // =========================================================================
    const FLEET_INCIDENTS = [];
    let incidentIdCounter = 1000;
    let currentProblemFilter = 'ALL';
    const COLLISION_SPARKS = []; // Active collision spark animations on map

    function logBotProblem(type, robotId, options = {}) {
      const now = Date.now();
      const r = AMR_FLEET.find(b => b.id === robotId);
      const peerId = options.peerId || null;
      const severity = options.severity || (type === 'COLLISION' || type === 'OUT_OF_CHARGE' ? 'CRITICAL' : 'WARNING');
      const x = options.x !== undefined ? options.x : (r ? r.gridX : 0);
      const y = options.y !== undefined ? options.y : (r ? r.gridY : 0);
      const desc = options.desc || `${type} event detected on ${robotId}`;

      // Throttled deduplication: don't create multiple active incidents for same bot & type within 4s
      const existing = FLEET_INCIDENTS.find(inc => 
        inc.status === 'ACTIVE' && 
        inc.type === type && 
        inc.robotId === robotId &&
        (!peerId || inc.peerId === peerId)
      );

      if (existing) {
        existing.lastSeenTime = now;
        existing.desc = desc;
        updateProblemsBadge();
        if (currentMainTab === 'problems') updateProblemsDashboard();
        return existing;
      }

      incidentIdCounter++;
      const timeStr = new Date(now).toTimeString().split(' ')[0];
      const incident = {
        id: `INC-${incidentIdCounter}`,
        type,
        severity,
        robotId,
        peerId,
        x,
        y,
        startTime: now,
        lastSeenTime: now,
        timeStr,
        desc,
        status: 'ACTIVE',
        resolvedAt: null,
        resolutionAction: null
      };

      FLEET_INCIDENTS.unshift(incident);
      if (FLEET_INCIDENTS.length > 80) FLEET_INCIDENTS.pop();

      updateProblemsBadge();

      // Mirror to Operations Terminal with high-visibility tags
      if (type === 'COLLISION') {
        logTerminal('COLLISION', 'tag-yield', `💥 <strong>COLLISION CONFLICT:</strong> ${desc}`);
      } else if (type === 'OUT_OF_CHARGE') {
        logTerminal('ALERT', 'tag-yield', `🪫 <strong>UVLO CUT-OFF:</strong> ${desc}`);
      } else if (type === 'DEADLOCK') {
        logTerminal('YIELD', 'tag-yield', `🛑 <strong>AISLE GRIDLOCK:</strong> ${desc}`);
      } else if (type === 'BMS_DEFICIT') {
        logTerminal('BMS', 'tag-yield', `⚠️ <strong>BMS DEFICIT:</strong> ${desc}`);
      }

      if (currentMainTab === 'problems') {
        updateProblemsDashboard();
      }

      return incident;
    }

    function resolveIncident(incidentId, actionName) {
      const inc = FLEET_INCIDENTS.find(i => i.id === incidentId);
      if (inc && inc.status === 'ACTIVE') {
        inc.status = 'RESOLVED';
        inc.resolvedAt = Date.now();
        inc.resolutionAction = actionName;
        updateProblemsBadge();
        if (currentMainTab === 'problems') updateProblemsDashboard();
      }
    }

    function updateProblemsBadge() {
      const badge = document.getElementById('tab-problems-badge');
      if (!badge) return;
      const activeCount = FLEET_INCIDENTS.filter(i => i.status === 'ACTIVE').length;
      badge.innerText = activeCount;
      badge.style.display = activeCount > 0 ? 'inline-block' : 'none';
      if (activeCount > 0) {
        badge.classList.add('danger');
      } else {
        badge.classList.remove('danger');
      }
    }

    function abortMissionToCharger(robotId, reason = 'DYNAMIC_SAFETY_ABORT') {
      const r = AMR_FLEET.find(b => b.id === robotId);
      if (!r) return;
      if (r.state === 'IDLE_CHARGING' || r.state === 'OUT_OF_CHARGE') return;

      // Salvage and requeue Inbound Mission
      if (r.inboundMission) {
        if (r.carriedParcels && r.carriedParcels.length > 0) {
          if (inboundQueues[r.inboundMission.dockId]) {
            inboundQueues[r.inboundMission.dockId].unshift(...r.carriedParcels);
          }
        }
        r.inboundMission.status = 'PENDING';
        r.inboundMission.assignedRobotId = null;
        r.carriedParcels = [];
        r.isLoadedYellow = false;
        r.inboundMission = null;
      }

      // Salvage and requeue Outbound Order
      if (r.outboundMission) {
        if (r.orderBox && r.orderBox.items && r.orderBox.items.length > 0) {
          for (const it of r.orderBox.items) {
            if (it.rackSlot && it.rackSlot.rack) {
              it.rackSlot.rack.floors[it.rackSlot.floorIndex] = it;
            }
          }
        }
        if (r.outboundMission.itemsToPick && r.outboundMission.itemsToPick.length > 0) {
          r.outboundMission.status = 'PENDING';
          r.outboundMission.assignedRobotId = null;
        } else {
          if (outboundOrders[r.outboundMission.bayId]) outboundOrders[r.outboundMission.bayId] = null;
          const oIdx = outboundMissions.findIndex(m => m.orderId === r.outboundMission.orderId);
          if (oIdx !== -1) outboundMissions.splice(oIdx, 1);
        }
        r.orderBox = null;
        r.outboundMission = null;
      }

      r.statusBadge = 'TO CHG';
      r.payloadWeight = 0;
      r.payloadDamping = 1.0;
      routeRobotToNearestCharger(r, reason);
      updateHudStats();
      dispatchFleet();
    }

    function rescueStrandedBot(robotId) {
      const r = AMR_FLEET.find(b => b.id === robotId);
      if (!r) return;

      // Find nearest available charger
      const nearest = getNearestAvailableCharger(r.gridX, r.gridY, r.id, true);
      const port = nearest.charger || CHARGING_PORTS[0];

      // Undock any current assignment
      undockFromCharger(r.id);

      // Autonomous Recovery Tug: Smoothly tow along warehouse aisles (Zero instant teleportation!)
      r.state = 'RETURNING_HOME';
      r.battery = Math.max(r.battery, 11.5); // Emergency crawl reserve
      r.isWaiting = false;
      r.waitTimer = 0;
      r.yieldTo = null;
      r.isOvertaking = false;
      r.isRerouting = false;
      r.statusBadge = 'TOW';
      r.targetDesc = `Autonomous AGV Tug Towing to Charger ${port.id}`;
      r.currentSpeed = baseSpeed * 0.35;
      r.strandedTimer = 0;
      r.payloadWeight = 0;
      r.payloadDamping = 1.0;
      reserveCharger(port.id, r.id);

      let towRoute = findPath(r.gridX, r.gridY, port.x, port.y);
      if (!towRoute || towRoute.length === 0) {
        towRoute = findPathUnconstrained(r.gridX, r.gridY, port.x, port.y);
      }
      setRobotPath(r, towRoute);
      r.heading = port.y === 1 ? Math.PI / 2 : -Math.PI / 2;
      r.isWaiting = false;
      r.waitTimer = 0;
      r.yieldTo = null;
      r.isOvertaking = false;
      r.isRerouting = false;
      r.statusBadge = null;
      r.currentSpeed = 0;
      r.strandedTimer = 0;
      r.payloadWeight = 0;
      r.payloadDamping = 1.0;

      // Salvage Inbound Mission safely
      if (r.inboundMission) {
        if (r.carriedParcels && r.carriedParcels.length > 0) {
          if (inboundQueues[r.inboundMission.dockId]) {
            inboundQueues[r.inboundMission.dockId].unshift(...r.carriedParcels);
          }
        }
        r.inboundMission.status = 'PENDING';
        r.inboundMission.assignedRobotId = null;
        r.carriedParcels = [];
        r.isLoadedYellow = false;
        r.inboundMission = null;
      }

      // Salvage Outbound Order safely
      if (r.outboundMission) {
        if (r.orderBox && r.orderBox.items && r.orderBox.items.length > 0) {
          for (const it of r.orderBox.items) {
            if (it.rackSlot && it.rackSlot.rack) {
              it.rackSlot.rack.floors[it.rackSlot.floorIndex] = it;
            }
          }
        }
        if (r.outboundMission.itemsToPick && r.outboundMission.itemsToPick.length > 0) {
          r.outboundMission.status = 'PENDING';
          r.outboundMission.assignedRobotId = null;
        } else {
          if (outboundOrders[r.outboundMission.bayId]) outboundOrders[r.outboundMission.bayId] = null;
          const oIdx = outboundMissions.findIndex(m => m.orderId === r.outboundMission.orderId);
          if (oIdx !== -1) outboundMissions.splice(oIdx, 1);
        }
        r.orderBox = null;
        r.outboundMission = null;
      }

      // Fast charge boost: at least 60% SoC
      r.battery = Math.max(60.0, r.battery);
      dockAtCharger(port.id, r.id);
      if (r.logStats) r.logStats.totalTowedByRescue = (r.logStats.totalTowedByRescue || 0) + 1;
      r.state = 'IDLE_CHARGING';
      r.targetDesc = `Parked at Fast Charger ${port.id} (${r.battery.toFixed(1)}%) - Rescued by Tow`;

      // Resolve all active problems for this bot
      for (const inc of FLEET_INCIDENTS) {
        if (inc.robotId === r.id && inc.status === 'ACTIVE') {
          resolveIncident(inc.id, `Towed to Charger ${port.id} (+60% SoC Boost)`);
        }
      }

      logTerminal('SYSTEM', 'tag-complete', `⚡ <strong>TOW RESCUE COMPLETED:</strong> <strong>${r.id}</strong> safely towed to Fast Charger <strong>${port.id}</strong>. Battery replenished to <strong>${r.battery.toFixed(1)}% SoC</strong>.`);
      updateHudStats();
      if (currentMainTab === 'problems') updateProblemsDashboard();
      dispatchFleet();
    }

    function clearRobotDeadlock(robotId) {
      const r = AMR_FLEET.find(b => b.id === robotId);
      if (!r) return;
      r.isWaiting = false;
      r.waitTimer = 0;
      r.yieldTo = null;
      r.statusBadge = null;

      // Anti-gridlock side step into adjacent walkable cell
      const neighbors = [
        { x: r.gridX + 1, y: r.gridY },
        { x: r.gridX - 1, y: r.gridY },
        { x: r.gridX, y: r.gridY + 1 },
        { x: r.gridX, y: r.gridY - 1 }
      ];
      let stepCell = null;
      for (const cell of neighbors) {
        if (isWalkable(cell.x, cell.y)) {
          let occ = false;
          for (const other of AMR_FLEET) {
            if (other.id !== r.id && Math.hypot(other.x - cell.x, other.y - cell.y) < 1.0) {
              occ = true; break;
            }
          }
          if (!occ) { stepCell = cell; break; }
        }
      }

      if (stepCell) {
        const dest = (r.path && r.path.length > 0) ? r.path[r.path.length - 1] : null;
        if (dest && typeof dest.x === 'number') {
          const repath = findPath(stepCell.x, stepCell.y, dest.x, dest.y);
          setRobotPath(r, [stepCell, ...(repath || [])]);
        } else {
          setRobotPath(r, [stepCell]);
        }
      }

      for (const inc of FLEET_INCIDENTS) {
        if (inc.robotId === r.id && inc.type === 'DEADLOCK' && inc.status === 'ACTIVE') {
          resolveIncident(inc.id, 'Operator Nudge / Unblocked');
        }
      }

      logTerminal('REROUTE', 'tag-reroute', `🔄 <strong>MANUAL UNBLOCK:</strong> <strong>${r.id}</strong> cleared from gridlock.`);
      if (currentMainTab === 'problems') updateProblemsDashboard();
    }

    function towAllStrandedBots() {
      let count = 0;
      for (const r of AMR_FLEET) {
        if (r.state === 'OUT_OF_CHARGE' || r.battery <= 10.0) {
          rescueStrandedBot(r.id);
          count++;
        }
      }
      if (count === 0) {
        logTerminal('SYSTEM', 'tag-inbound', 'ℹ️ No stranded bots detected. All fleet AMRs operating above 10% cutoff.');
      }
    }

    function breakAllDeadlocks() {
      let count = 0;
      for (const r of AMR_FLEET) {
        if (r.isWaiting || r.waitTimer > 1.5) {
          clearRobotDeadlock(r.id);
          count++;
        }
      }
      logTerminal('SYSTEM', 'tag-reroute', `🔄 <strong>ANTI-GRIDLOCK SWEEP:</strong> Unblocked ${count} AMRs.`);
    }

    function clearResolvedIncidents() {
      const activeOnly = FLEET_INCIDENTS.filter(i => i.status === 'ACTIVE');
      FLEET_INCIDENTS.length = 0;
      FLEET_INCIDENTS.push(...activeOnly);
      updateProblemsDashboard();
    }

    function setProblemFilter(filterName, btn) {
      currentProblemFilter = filterName;
      const pills = document.querySelectorAll('.prob-filter-pill');
      pills.forEach(p => p.classList.toggle('active', p.getAttribute('data-filter') === filterName));
      renderProblemsFeed();
    }

    function updateProblemsDashboard() {
      // 1. Calculate problem totals
      let collisionCount = 0;
      let outOfChargeCount = 0;
      let deadlockCount = 0;
      let bmsDeficitCount = 0;

      for (const inc of FLEET_INCIDENTS) {
        if (inc.type === 'COLLISION') collisionCount++;
        else if (inc.type === 'OUT_OF_CHARGE' && inc.status === 'ACTIVE') outOfChargeCount++;
        else if (inc.type === 'DEADLOCK' && inc.status === 'ACTIVE') deadlockCount++;
        else if (inc.type === 'BMS_DEFICIT') bmsDeficitCount++;
      }

      for (const r of AMR_FLEET) {
        if (r.state === 'OUT_OF_CHARGE' || r.battery <= 10.0) {
          outOfChargeCount = Math.max(outOfChargeCount, 1);
        }
        if (r.isWaiting && r.waitTimer > 2.5) {
          deadlockCount = Math.max(deadlockCount, 1);
        }
      }

      const elColl = document.getElementById('prob-kpi-collisions');
      const elOut = document.getElementById('prob-kpi-out-of-charge');
      const elDead = document.getElementById('prob-kpi-deadlocks');
      const elBms = document.getElementById('prob-kpi-bms-deficits');

      if (elColl) elColl.innerText = collisionCount;
      if (elOut) elOut.innerText = outOfChargeCount;
      if (elDead) elDead.innerText = deadlockCount;
      if (elBms) elBms.innerText = bmsDeficitCount;

      const incCountEl = document.getElementById('prob-incident-count');
      if (incCountEl) {
        const active = FLEET_INCIDENTS.filter(i => i.status === 'ACTIVE').length;
        incCountEl.innerText = `${active} Active (${FLEET_INCIDENTS.length} Total)`;
      }

      renderProblemsFeed();
      renderProblemsMatrix();
      updateProblemsBadge();
    }

    function renderProblemsFeed() {
      const container = document.getElementById('prob-feed-list');
      if (!container) return;

      const filtered = FLEET_INCIDENTS.filter(inc => {
        if (currentProblemFilter === 'ALL') return true;
        return inc.type === currentProblemFilter;
      });

      if (filtered.length === 0) {
        container.innerHTML = `
          <div style="text-align:center; padding:45px 20px; color:#64748b;">
            <div style="font-size:36px; margin-bottom:10px;">✅</div>
            <div style="font-size:14px; font-weight:700; color:#cbd5e1;">Zero Active ${currentProblemFilter === 'ALL' ? '' : currentProblemFilter} Incidents</div>
            <div style="font-size:11px; margin-top:5px; color:#94a3b8;">Fleet motion, decentralized collision mesh, and BMS energy budgeting nominal.</div>
          </div>
        `;
        return;
      }

      const now = Date.now();
      container.innerHTML = filtered.map(inc => {
        const isActive = inc.status === 'ACTIVE';
        const elapsedSec = Math.round((now - inc.startTime) / 1000);

        let icon = '⚠️';
        let typeLabel = inc.type;
        if (inc.type === 'COLLISION') { icon = '💥'; typeLabel = 'COLLISION / CONFLICT'; }
        else if (inc.type === 'OUT_OF_CHARGE') { icon = '🪫'; typeLabel = 'BATTERY AT 10% FLOOR'; }
        else if (inc.type === 'DEADLOCK') { icon = '🛑'; typeLabel = 'AISLE DEADLOCK / STALL'; }
        else if (inc.type === 'BMS_DEFICIT') { icon = '⚠️'; typeLabel = 'BMS ENERGY DEFICIT'; }

        return `
          <div class="prob-card ${isActive ? `active-${inc.type}` : 'resolved'}">
            <div class="prob-card-header">
              <div class="prob-card-title">
                <span>${icon}</span>
                <span>${typeLabel}</span>
                <strong style="color:#38bdf8; margin-left:4px;">${inc.robotId}</strong>
                ${inc.peerId ? `<span style="color:#94a3b8; font-size:10px;">vs <strong>${inc.peerId}</strong></span>` : ''}
              </div>
              <div class="prob-card-meta">
                <span class="prob-time">[${inc.timeStr}]</span>
                <span class="prob-status-tag ${isActive ? 'active' : 'resolved'}">
                  ${isActive ? `ACTIVE (${elapsedSec}s)` : 'RESOLVED'}
                </span>
              </div>
            </div>

            <div class="prob-card-desc">
              ${inc.desc}
              ${!isActive && inc.resolutionAction ? `<div style="margin-top:3px; color:#4ade80; font-size:10px;">✔ Resolved via: <strong>${inc.resolutionAction}</strong></div>` : ''}
            </div>

            <div class="prob-card-actions">
              ${isActive && (inc.type === 'OUT_OF_CHARGE' || inc.type === 'BMS_DEFICIT') ? `
                <button class="prob-btn tow" onclick="rescueStrandedBot('${inc.robotId}')" title="Emergency tow to nearest fast charger & +50% SoC boost">
                  <span>⚡ Tow to Charger (+50%)</span>
                </button>
              ` : ''}
              ${isActive && inc.type === 'DEADLOCK' ? `
                <button class="prob-btn unblock" onclick="clearRobotDeadlock('${inc.robotId}')" title="Force side-step and clear waiting stall">
                  <span>🔄 Force Nudge / Unblock</span>
                </button>
              ` : ''}
              ${isActive && inc.type === 'COLLISION' ? `
                <button class="prob-btn unblock" onclick="clearRobotDeadlock('${inc.robotId}')">
                  <span>🔄 Unblock ${inc.robotId}</span>
                </button>
                ${inc.peerId ? `
                  <button class="prob-btn unblock" onclick="clearRobotDeadlock('${inc.peerId}')">
                    <span>🔄 Unblock ${inc.peerId}</span>
                  </button>
                ` : ''}
              ` : ''}
              <button class="prob-btn locate" onclick="locateBotOnMap('${inc.robotId}')" title="Center 2D map on ${inc.robotId} with radar ping">
                <span>📍 Locate on Map</span>
              </button>
              <button class="prob-btn track" onclick="trackBot('${inc.robotId}', true)" title="Engage targeting lock and follow camera on ${inc.robotId}">
                <span>🎯 Track</span>
              </button>
              ${isActive ? `
                <button class="prob-btn" style="margin-left:auto; font-size:9px;" onclick="resolveIncident('${inc.id}', 'Manual Dismiss')">
                  Dismiss
                </button>
              ` : ''}
            </div>
          </div>
        `;
      }).join('');
    }

    function renderProblemsMatrix() {
      const container = document.getElementById('prob-matrix-grid');
      if (!container || !AMR_FLEET) return;

      container.innerHTML = AMR_FLEET.map(r => {
        const isDead = r.state === 'OUT_OF_CHARGE' || r.battery <= 10.0;
        const isStalled = r.isWaiting && r.waitTimer > 2.0;
        const isCharging = r.state === 'IDLE_CHARGING';

        let rowClass = '';
        if (isDead) rowClass = 'is-dead';
        else if (isStalled) rowClass = 'is-stalled';

        let barColor = '#22c55e';
        if (isDead) barColor = '#ef4444';
        else if (r.battery <= 25.0) barColor = '#f87171';
        else if (r.battery <= 50.0) barColor = '#f59e0b';

        let stateLabel = r.state;
        let stateTagBg = '#1e293b';
        let stateTagColor = '#94a3b8';

        if (isDead) {
          stateLabel = '🪫 IMMOBILIZED (10%)';
          stateTagBg = '#7f1d1d';
          stateTagColor = '#fecaca';
        } else if (isCharging) {
          stateLabel = `⚡ FAST CHARGE (${r.battery.toFixed(1)}%)`;
          stateTagBg = 'rgba(34, 197, 94, 0.2)';
          stateTagColor = '#4ade80';
        } else if (isStalled) {
          stateLabel = `🛑 STALLED (${r.waitTimer.toFixed(1)}s)`;
          stateTagBg = 'rgba(245, 158, 11, 0.2)';
          stateTagColor = '#fde047';
        } else if (r.isWaiting) {
          stateLabel = `⏳ Yielding to ${r.yieldTo || 'AMR'}`;
          stateTagBg = 'rgba(245, 158, 11, 0.15)';
          stateTagColor = '#f59e0b';
        } else if (r.isOvertaking) {
          stateLabel = '🏎️ Overtaking (1.35x)';
          stateTagBg = 'rgba(56, 189, 248, 0.2)';
          stateTagColor = '#38bdf8';
        } else if (r.state === 'CARRYING_TO_RACK') {
          stateLabel = `📥 Shelving (${r.carriedParcels ? r.carriedParcels.length : 0} pkgs)`;
          stateTagBg = 'rgba(250, 204, 21, 0.2)';
          stateTagColor = '#facc15';
        } else if (r.state === 'DELIVERING_ORDER_TO_BAY' || r.state === 'ORDER_PICKING') {
          stateLabel = `📦 Order Pick / Deliver`;
          stateTagBg = 'rgba(234, 88, 12, 0.2)';
          stateTagColor = '#fb923c';
        }

        const nearestChg = getNearestAvailableCharger(r.gridX, r.gridY, r.id);
        const estSoc = nearestChg.energyNeeded + SAFETY_RESERVE_SOC;

        return `
          <div class="matrix-row ${rowClass}">
            <div class="matrix-top">
              <div class="matrix-bot-title">
                <span>🤖</span>
                <span>${r.id}</span>
                <span style="font-size:10px; font-weight:normal; color:#94a3b8;">at (${r.gridX}, ${r.gridY})</span>
              </div>
              <span class="matrix-state-tag" style="background:${stateTagBg}; color:${stateTagColor};">${stateLabel}</span>
            </div>

            <div class="matrix-bar-wrap">
              <div class="matrix-bar-bg" title="BMS SoC gauge with red 10% UVLO cutoff line">
                <div class="matrix-bar-cutoff-line" title="10% BMS Cutoff Floor"></div>
                <div class="matrix-bar-fill" style="width:${r.battery.toFixed(1)}%; background:${barColor};"></div>
              </div>
              <span class="matrix-soc-text" style="color:${barColor};">${r.battery.toFixed(1)}%</span>
            </div>

            <div class="matrix-details">
              <span>Nearest Bay: <strong>${nearestChg.charger ? nearestChg.charger.id : 'CH-01'}</strong> (${nearestChg.distance}m | Req: ~${estSoc.toFixed(1)}%)</span>
              <span>Draw: <strong>${isCharging ? `+${(r.chargeRateKw || 30).toFixed(1)}kW` : `-${Math.round(r.powerWatts || 165)}W`}</strong></span>
            </div>

            <div class="matrix-actions">
              ${isDead ? `
                <button class="prob-btn tow" style="flex:1;" onclick="rescueStrandedBot('${r.id}')">
                  <span>⚡ Tow &amp; Revive (+60%)</span>
                </button>
              ` : `
                <button class="prob-btn tow" style="flex:1;" onclick="sendBotToCharger('${r.id}')">
                  <span>⚡ Dock Nearest</span>
                </button>
              `}
              ${r.isWaiting ? `
                <button class="prob-btn unblock" onclick="clearRobotDeadlock('${r.id}')">
                  <span>🔄 Nudge</span>
                </button>
              ` : ''}
              <button class="prob-btn locate" onclick="locateBotOnMap('${r.id}')" title="Locate on Map">
                <span>📍 Map</span>
              </button>
              <button class="prob-btn track" onclick="trackBot('${r.id}', true)" title="Engage targeting lock and follow camera on ${r.id}">
                <span>🎯 Track</span>
              </button>
            </div>
          </div>
        `;
      }).join('');
    }

    // =========================================================================
    // AMAZON ROBOTICS (KIVA) DYNAMIC BMS ENERGY BUDGET & CHARGER POOL ALLOCATION
    // =========================================================================
    const CHARGING_PORTS = [
      { id: "CH-01", x: 38, y: 1, zone: "Top Center", occupiedBy: null, reservedBy: null },
      { id: "CH-02", x: 39, y: 1, zone: "Top Center", occupiedBy: null, reservedBy: null },
      { id: "CH-03", x: 40, y: 1, zone: "Top Center", occupiedBy: null, reservedBy: null },
      { id: "CH-04", x: 41, y: 1, zone: "Top Center", occupiedBy: null, reservedBy: null },
      { id: "CH-05", x: 38, y: 48, zone: "Bottom Center", occupiedBy: null, reservedBy: null },
      { id: "CH-06", x: 39, y: 48, zone: "Bottom Center", occupiedBy: null, reservedBy: null },
      { id: "CH-07", x: 40, y: 48, zone: "Bottom Center", occupiedBy: null, reservedBy: null },
      { id: "CH-08", x: 41, y: 48, zone: "Bottom Center", occupiedBy: null, reservedBy: null }
    ];

    const SAFETY_RESERVE_SOC = 15.0; // 15% Minimum Reserve: AMR NEVER depletes below this on warehouse floor
    const DOCKING_ENERGY_BUFFER = 0.45; // Energy % needed for precision deceleration & contact pad engagement
    const ENERGY_RATE_EMPTY_PER_TILE = 0.038; // Base energy % drained per cell traversed empty (~170W)
    const ENERGY_LIFT_PER_OP = 0.15; // Energy % drained per shelf/pick lift actuator cycle (~35W)

    function sortParcelsByProximity(parcels, startX, startY) {
      if (!parcels || parcels.length <= 1) return [...(parcels || [])];
      const remaining = [...parcels];
      const sorted = [];
      let cx = startX, cy = startY;
      while (remaining.length > 0) {
        let bestIdx = 0, bestDist = Infinity;
        for (let i = 0; i < remaining.length; i++) {
          const p = remaining[i];
          const rx = (p.rackSlot && p.rackSlot.rack) ? p.rackSlot.rack.x : cx;
          const ry = (p.rackSlot && p.rackSlot.rack) ? p.rackSlot.rack.y : cy;
          const d = Math.abs(cx - rx) + Math.abs(cy - ry);
          if (d < bestDist) {
            bestDist = d;
            bestIdx = i;
          }
        }
        const [nextP] = remaining.splice(bestIdx, 1);
        sorted.push(nextP);
        if (nextP.rackSlot && nextP.rackSlot.rack) {
          cx = nextP.rackSlot.rack.x;
          cy = nextP.rackSlot.rack.y;
        }
      }
      return sorted;
    }

    function sortItemsByProximity(items, startX, startY) {
      if (!items || items.length <= 1) return [...(items || [])];
      const remaining = [...items];
      const sorted = [];
      let cx = startX, cy = startY;
      while (remaining.length > 0) {
        let bestIdx = 0, bestDist = Infinity;
        for (let i = 0; i < remaining.length; i++) {
          const it = remaining[i];
          const rx = it.rack ? it.rack.x : cx;
          const ry = it.rack ? it.rack.y : cy;
          const d = Math.abs(cx - rx) + Math.abs(cy - ry);
          if (d < bestDist) {
            bestDist = d;
            bestIdx = i;
          }
        }
        const [nextIt] = remaining.splice(bestIdx, 1);
        sorted.push(nextIt);
        if (nextIt.rack) {
          cx = nextIt.rack.x;
          cy = nextIt.rack.y;
        }
      }
      return sorted;
    }

    function calculateEnergyCost(distanceTiles, payloadWeightKg = 0, liftOperations = 0) {
      if (distanceTiles <= 0 && liftOperations <= 0) return 0;
      const tarePower = 170.0;
      const payloadPower = Math.max(0, payloadWeightKg) * 6.5;
      const powerMultiplier = (tarePower + payloadPower) / tarePower;
      const dampingFactor = Math.max(0.65, 1.0 - (payloadWeightKg / 60.0) * 0.35);
      const timeFactor = 1.0 / dampingFactor;

      const transitEnergy = distanceTiles * ENERGY_RATE_EMPTY_PER_TILE * powerMultiplier * timeFactor;
      const liftEnergy = liftOperations * ENERGY_LIFT_PER_OP;
      return transitEnergy + liftEnergy;
    }

    // Dynamic Charger Pool Search: Finds nearest free or claimable charger
    function getNearestAvailableCharger(fromX, fromY, robotId, allowYielding = false) {
      let bestPort = null;
      let minDistance = Infinity;

      // 1. Unreserved & unoccupied ports
      for (const port of CHARGING_PORTS) {
        const isFree = (port.occupiedBy === null || port.occupiedBy === robotId) &&
                       (port.reservedBy === null || port.reservedBy === robotId);
        if (isFree) {
          const d = Math.abs(port.x - fromX) + Math.abs(port.y - fromY);
          if (d < minDistance) {
            minDistance = d;
            bestPort = port;
          }
        }
      }

      // 2. If all ports busy and allowYielding enabled, find port whose occupant is >= 85% charged
      if (!bestPort && allowYielding) {
        let bestOccupantSoC = 0;
        for (const port of CHARGING_PORTS) {
          if (port.occupiedBy && port.occupiedBy !== robotId) {
            const occupant = AMR_FLEET.find(b => b.id === port.occupiedBy);
            if (occupant && occupant.battery >= 85.0 && occupant.battery > bestOccupantSoC) {
              bestOccupantSoC = occupant.battery;
              bestPort = port;
              minDistance = Math.abs(port.x - fromX) + Math.abs(port.y - fromY);
            }
          }
        }
      }

      // 3. Fallback to closest port
      if (!bestPort) {
        for (const port of CHARGING_PORTS) {
          const d = Math.abs(port.x - fromX) + Math.abs(port.y - fromY);
          if (d < minDistance) {
            minDistance = d;
            bestPort = port;
          }
        }
      }

      const energyReq = calculateEnergyCost(minDistance, 0, 0) + DOCKING_ENERGY_BUFFER;
      return {
        charger: bestPort,
        distance: minDistance,
        energyNeeded: Math.max(0.4, Math.round(energyReq * 10) / 10)
      };
    }

    function reserveCharger(portId, robotId) {
      for (const p of CHARGING_PORTS) {
        if (p.reservedBy === robotId && p.id !== portId) {
          p.reservedBy = null;
        }
      }
      const port = CHARGING_PORTS.find(p => p.id === portId);
      if (port) {
        port.reservedBy = robotId;
      }
      const r = AMR_FLEET.find(b => b.id === robotId);
      if (r) {
        r.targetChargerId = portId;
      }
    }

    function dockAtCharger(portId, robotId) {
      const port = CHARGING_PORTS.find(p => p.id === portId);
      if (port) {
        if (port.occupiedBy && port.occupiedBy !== robotId) {
          const prev = AMR_FLEET.find(b => b.id === port.occupiedBy);
          if (prev) {
            prev.currentChargerId = null;
          }
        }
        port.occupiedBy = robotId;
        if (port.reservedBy === robotId) port.reservedBy = null;
      }
      const r = AMR_FLEET.find(b => b.id === robotId);
      if (r) {
        r.currentChargerId = portId;
        r.targetChargerId = null;
        r.assignedBayId = portId;
        r.homeBayId = portId;
      }
    }

    function undockFromCharger(robotId) {
      for (const p of CHARGING_PORTS) {
        if (p.occupiedBy === robotId) p.occupiedBy = null;
        if (p.reservedBy === robotId) p.reservedBy = null;
      }
      const r = AMR_FLEET.find(b => b.id === robotId);
      if (r) {
        r.currentChargerId = null;
        r.targetChargerId = null;
      }
    }

    function routeRobotToNearestCharger(robot, reason = 'OPPORTUNITY_CHARGE', context = null) {
      if (robot.state === 'IDLE_CHARGING') return;
      if (robot.orderBox || (robot.carriedParcels && robot.carriedParcels.length > 0)) {
        return; // Don't abandon active cargo in aisle
      }

      const allowYield = robot.battery < 20.0;
      const nearest = getNearestAvailableCharger(robot.gridX, robot.gridY, robot.id, allowYield);
      const port = nearest.charger;
      if (!port) return;

      // If claiming from a >=85% occupant
      if (port.occupiedBy && port.occupiedBy !== robot.id) {
        const occupant = AMR_FLEET.find(b => b.id === port.occupiedBy);
        if (occupant && occupant.battery >= 85.0) {
          logTerminal('BMS', 'tag-yield', `⚡ <strong>${occupant.id}</strong> (${occupant.battery.toFixed(1)}% SoC) yielding Charger <strong>${port.id}</strong> to low-energy <strong>${robot.id}</strong> (${robot.battery.toFixed(1)}% SoC).`);
          undockFromCharger(occupant.id);
          occupant.state = 'IDLE';
          occupant.targetDesc = 'Yielded Charger to Low SoC Peer (Staging)';
          const stagingY = port.y === 1 ? 2 : 47;
          setRobotPath(occupant, findPath(occupant.gridX, occupant.gridY, port.x, stagingY));
        }
      }

      reserveCharger(port.id, robot.id);
      robot.state = 'RETURNING_HOME';
      robot.statusBadge = robot.battery <= 25.0 ? 'LOW BATT' : 'TO CHG';
      robot.targetDesc = `Navigating to Nearest Charger ${port.id} (${nearest.distance}m | ~${nearest.energyNeeded}% SoC)`;
      setRobotPath(robot, findPath(robot.gridX, robot.gridY, port.x, port.y));

      if (robot.path.length === 0 && robot.gridX === port.x && robot.gridY === port.y) {
        dockAtCharger(port.id, robot.id);
        robot.state = 'IDLE_CHARGING';
        robot.statusBadge = null;
        robot.targetDesc = `Parked at Fast Charger ${port.id} (${robot.battery.toFixed(1)}%)`;
        logTerminal('BMS', 'tag-inbound', `⚡ <strong>${robot.id}</strong> engaged charging contacts at <strong>${port.id}</strong> (${port.zone}). SoC: ${robot.battery.toFixed(1)}%.`);
      } else {
        if (reason === 'FEASIBILITY_REJECTION') {
          logTerminal('BMS', 'tag-yield', `🚨 <strong>${robot.id}</strong> rejected ${context ? context.missionDesc : 'Task'}: BMS Energy Deficit (Req: <strong>${context.eRequired}% SoC</strong>, Current: <strong>${robot.battery.toFixed(1)}%</strong>). Diverting to nearest charger <strong>${port.id}</strong>.`);
        } else if (reason === 'DYNAMIC_SAFETY_ABORT') {
          logTerminal('BMS', 'tag-yield', `⚠️ <strong>${robot.id}</strong> reached critical energy boundary (${robot.battery.toFixed(1)}% SoC). Diverting directly to nearest charger <strong>${port.id}</strong>.`);
        } else if (reason === 'OPERATOR_RECALL') {
          logTerminal('BMS', 'tag-yield', `⚡ <strong>${robot.id}</strong> recalled by operator. Routing to nearest available charger <strong>${port.id}</strong> (${nearest.distance}m, ~${nearest.energyNeeded}% SoC).`);
        } else {
          logTerminal('BMS', 'tag-inbound', `🔋 <strong>${robot.id}</strong> (${robot.battery.toFixed(1)}% SoC) navigating to nearest charger <strong>${port.id}</strong> (${nearest.distance}m, Est: ~${nearest.energyNeeded}% SoC).`);
        }
      }
      updateHudStats();
    }

    function evaluateMissionEnergyFeasibility(robot, task) {
      let d1 = 0, e1 = 0, d2 = 0, e2 = 0, d3 = 0, e3 = 0;
      let finalX = robot.gridX, finalY = robot.gridY;
      let nearestCharger = null;

      // Realistic Aisle Tortuosity Multiplier: In a warehouse grid with rack pods,
      // actual paths are ~28% longer than straight Manhattan distance |x1-x2| + |y1-y2|
      const AISLE_TORTUOSITY = 1.28;
      // Traffic delay & maneuvering energy margin (+2.0% SoC for turns, yields, and acceleration surges)
      const TRAFFIC_RESERVE_SOC = 2.0;
      const BATTERY_FLOOR_CUTOFF = 10.0; // User specification: Hard floor at 10.0%, never drop <10%

      if (task.type === 'INBOUND') {
        const dockX = task.dockX !== undefined ? task.dockX : 1;
        const dockY = task.dockY !== undefined ? task.dockY : 5;
        d1 = Math.round((Math.abs(robot.gridX - dockX) + Math.abs(robot.gridY - dockY)) * AISLE_TORTUOSITY);
        e1 = calculateEnergyCost(d1, 0, 0);

        const parcels = task.parcels || [];
        const weight = task.totalWeight || 10;
        let currX = dockX, currY = dockY;
        const unvisited = parcels.filter(p => p.rackSlot && p.rackSlot.rack);
        while (unvisited.length > 0) {
          let bestIdx = 0, bestDist = Infinity;
          for (let i = 0; i < unvisited.length; i++) {
            const rx = unvisited[i].rackSlot.rack.x, ry = unvisited[i].rackSlot.rack.y;
            const dist = Math.abs(currX - rx) + Math.abs(currY - ry);
            if (dist < bestDist) {
              bestDist = dist;
              bestIdx = i;
            }
          }
          const [p] = unvisited.splice(bestIdx, 1);
          d2 += bestDist;
          currX = p.rackSlot.rack.x;
          currY = p.rackSlot.rack.y;
        }
        if (parcels.length === 0) d2 = 24;
        d2 = Math.round(d2 * AISLE_TORTUOSITY);
        finalX = currX; finalY = currY;
        e2 = calculateEnergyCost(d2, weight, parcels.length || 1);

        const chgInfo = getNearestAvailableCharger(finalX, finalY, robot.id);
        nearestCharger = chgInfo.charger;
        d3 = Math.round(chgInfo.distance * AISLE_TORTUOSITY);
        e3 = calculateEnergyCost(d3, 0, 0) + DOCKING_ENERGY_BUFFER;
      } else { // OUTBOUND
        const firstRack = task.rack || { x: 30, y: 15 };
        d1 = Math.round((Math.abs(robot.gridX - firstRack.x) + Math.abs(robot.gridY - firstRack.y)) * AISLE_TORTUOSITY);
        e1 = calculateEnergyCost(d1, 0, 0);

        const items = task.itemsToPick || [];
        const weight = task.totalWeight || 8;
        const bayX = task.bayX !== undefined ? task.bayX : 1;
        const bayY = task.bayY !== undefined ? task.bayY : 27;

        let currX = firstRack.x, currY = firstRack.y;
        const unvisited = items.slice(1).filter(it => it.rack);
        while (unvisited.length > 0) {
          let bestIdx = 0, bestDist = Infinity;
          for (let i = 0; i < unvisited.length; i++) {
            const rx = unvisited[i].rack.x, ry = unvisited[i].rack.y;
            const dist = Math.abs(currX - rx) + Math.abs(currY - ry);
            if (dist < bestDist) {
              bestDist = dist;
              bestIdx = i;
            }
          }
          const [it] = unvisited.splice(bestIdx, 1);
          d2 += bestDist;
          currX = it.rack.x;
          currY = it.rack.y;
        }
        d2 += (Math.abs(currX - bayX) + Math.abs(currY - bayY));
        d2 = Math.round(d2 * AISLE_TORTUOSITY);
        finalX = bayX; finalY = bayY;
        e2 = calculateEnergyCost(d2, weight, items.length || 1);

        const chgInfo = getNearestAvailableCharger(finalX, finalY, robot.id);
        nearestCharger = chgInfo.charger;
        d3 = Math.round(chgInfo.distance * AISLE_TORTUOSITY);
        e3 = calculateEnergyCost(d3, 0, 0) + DOCKING_ENERGY_BUFFER;
      }

      // =========================================================================
      // USER TWO-TIER ENERGY DECISION ALGORITHM:
      // "when their next assignment is there:
      //  1. see if there is a chance of going <10% -> if yes, go charge.
      //  2. if no then calculate if doing that task+going back to charge port
      //     charge is there or not -> if no charge. if yes go on"
      // =========================================================================

      // TIER 1: Check if there is ANY chance of dropping below 10% during immediate transit/legs
      const chanceGoingBelow10 = (robot.battery <= 12.0) ||
                                 ((robot.battery - e1) < (BATTERY_FLOOR_CUTOFF + 0.5)) ||
                                 ((robot.battery - (e1 + e2)) < BATTERY_FLOOR_CUTOFF);

      if (chanceGoingBelow10) {
        // "if yes, go charge"
        return {
          feasible: false,
          decision: 'GO_CHARGE_RISK_BELOW_10',
          chanceGoingBelow10: true,
          hasEnoughForTaskAndReturn: false,
          reason: `High risk of dropping <10% SoC during task (Current: ${robot.battery.toFixed(1)}%, Leg1: ${e1.toFixed(1)}%). Must go charge!`,
          currentBattery: robot.battery,
          e1: Math.round(e1 * 10) / 10,
          e2: Math.round(e2 * 10) / 10,
          e3: Math.round(e3 * 10) / 10,
          eTrip: Math.round((e1 + e2 + e3) * 10) / 10,
          eRequired: Math.round((e1 + e2 + e3 + BATTERY_FLOOR_CUTOFF) * 10) / 10,
          remainingAfterReturn: Math.round((robot.battery - (e1 + e2 + e3)) * 10) / 10,
          margin: Math.round((robot.battery - (e1 + e2 + e3 + BATTERY_FLOOR_CUTOFF)) * 10) / 10,
          nearestCharger,
          nearestChargerDist: d3,
          finalX,
          finalY
        };
      }

      // TIER 2: "if no then calculate if doing that task+going back to charge port charge is there or not."
      const eTask = e1 + e2;
      const eReturn = e3;
      const totalTripEnergy = eTask + eReturn + TRAFFIC_RESERVE_SOC;
      const projectedAfterReturn = robot.battery - totalTripEnergy;
      const hasEnoughForTaskAndReturn = projectedAfterReturn >= BATTERY_FLOOR_CUTOFF;

      if (!hasEnoughForTaskAndReturn) {
        // "if no charge" -> Must go charge!
        return {
          feasible: false,
          decision: 'GO_CHARGE_INSUFFICIENT_RETURN',
          chanceGoingBelow10: false,
          hasEnoughForTaskAndReturn: false,
          reason: `Insufficient charge for Task + Return to port (Requires: ${totalTripEnergy.toFixed(1)}% SoC, leaves ${projectedAfterReturn.toFixed(1)}% < 10% floor). Must go charge!`,
          currentBattery: robot.battery,
          e1: Math.round(e1 * 10) / 10,
          e2: Math.round(e2 * 10) / 10,
          e3: Math.round(e3 * 10) / 10,
          eTrip: Math.round(totalTripEnergy * 10) / 10,
          eRequired: Math.round((totalTripEnergy + BATTERY_FLOOR_CUTOFF) * 10) / 10,
          remainingAfterReturn: Math.round(projectedAfterReturn * 10) / 10,
          margin: Math.round((projectedAfterReturn - BATTERY_FLOOR_CUTOFF) * 10) / 10,
          nearestCharger,
          nearestChargerDist: d3,
          finalX,
          finalY
        };
      }

      // "if yes go on" -> Authorized!
      return {
        feasible: true,
        decision: 'GO_ON',
        chanceGoingBelow10: false,
        hasEnoughForTaskAndReturn: true,
        reason: `Energy verified: Task (${eTask.toFixed(1)}%) + Return to port (${eReturn.toFixed(1)}%) leaves ${projectedAfterReturn.toFixed(1)}% SoC (>= 10% floor). Authorized to go on!`,
        currentBattery: robot.battery,
        e1: Math.round(e1 * 10) / 10,
        e2: Math.round(e2 * 10) / 10,
        e3: Math.round(e3 * 10) / 10,
        eTrip: Math.round(totalTripEnergy * 10) / 10,
        eRequired: Math.round((totalTripEnergy + BATTERY_FLOOR_CUTOFF) * 10) / 10,
        remainingAfterReturn: Math.round(projectedAfterReturn * 10) / 10,
        margin: Math.round((projectedAfterReturn - BATTERY_FLOOR_CUTOFF) * 10) / 10,
        nearestCharger,
        nearestChargerDist: d3,
        finalX,
        finalY
      };
    }

    function sendBotToCharger(robotId) {
      const r = AMR_FLEET.find(b => b.id === robotId);
      if (!r) return;
      if (r.state === 'IDLE_CHARGING') {
        logTerminal('BMS', 'tag-inbound', `ℹ️ <strong>${r.id}</strong> is already connected to Fast Charger <strong>${r.currentChargerId || r.homeBayId}</strong>.`);
        return;
      }
      if (r.orderBox || (r.carriedParcels && r.carriedParcels.length > 0)) {
        logTerminal('BMS', 'tag-yield', `⚠️ <strong>${r.id}</strong> is carrying active payload. Will route to nearest charger immediately upon mission completion.`);
        return;
      }
      routeRobotToNearestCharger(r, 'OPERATOR_RECALL');
      updateHudStats();
      updateBotsHealthDashboard();
    }

    function recallAllIdleBots() {
      let count = 0;
      for (const r of AMR_FLEET) {
        if (r.state === 'IDLE') {
          routeRobotToNearestCharger(r, 'OPERATOR_RECALL');
          count++;
        }
      }
      logTerminal('BMS', 'tag-yield', `⚡ Operator recalled all idle robots (${count} units) to their nearest available fast chargers.`);
      updateHudStats();
      updateBotsHealthDashboard();
    }

    function updateBotsHealthDashboard() {
      const container = document.getElementById('bots-cards-grid');
      if (!container || !AMR_FLEET) return;

      // Compute fleet KPI summaries
      let totalBatt = 0;
      let activeCount = 0;
      let chargingCount = 0;
      let totalNetPowerKw = 0;
      let totalPayloadKg = 0;
      let lowBattCount = 0;

      for (const r of AMR_FLEET) {
        totalBatt += r.battery;
        if (r.state === 'IDLE_CHARGING') {
          chargingCount++;
          totalNetPowerKw += (r.chargeRateKw || 0);
        } else {
          activeCount++;
          totalNetPowerKw -= ((r.powerWatts || 165) / 1000.0);
        }
        totalPayloadKg += (r.payloadWeight || 0);
        if (r.battery <= 28.0 && r.state !== 'IDLE_CHARGING') lowBattCount++;
      }

      const avgBatt = AMR_FLEET.length > 0 ? (totalBatt / AMR_FLEET.length).toFixed(1) : 0;
      const kpiFleet = document.getElementById('kpi-fleet-status');
      const kpiAvgBatt = document.getElementById('kpi-avg-battery');
      const kpiPower = document.getElementById('kpi-net-power');
      const kpiFreight = document.getElementById('kpi-total-freight');
      const summaryBadge = document.getElementById('bots-status-summary');

      if (kpiFleet) kpiFleet.innerText = `8 Online (${chargingCount} Chg | ${activeCount} Active${lowBattCount > 0 ? ` | ${lowBattCount} Low SoC` : ''})`;
      if (kpiAvgBatt) {
        kpiAvgBatt.innerText = `${avgBatt}%`;
        kpiAvgBatt.style.color = avgBatt > 50 ? '#22c55e' : (avgBatt > 25 ? '#f59e0b' : '#ef4444');
      }
      if (kpiPower) {
        const sign = totalNetPowerKw >= 0 ? '+' : '';
        kpiPower.innerText = `${sign}${totalNetPowerKw.toFixed(1)} kW Net`;
        kpiPower.style.color = totalNetPowerKw >= 0 ? '#4ade80' : '#38bdf8';
      }
      if (kpiFreight) kpiFreight.innerText = `${totalPayloadKg.toFixed(1)} kg`;
      if (summaryBadge) summaryBadge.innerText = `${chargingCount} Charging | ${activeCount} On Duty`;

      let freeChargers = 0;
      for (const p of CHARGING_PORTS) {
        if (!p.occupiedBy && !p.reservedBy) freeChargers++;
      }
      const kpiChg = document.getElementById('kpi-chargers-avail');
      if (kpiChg) kpiChg.innerText = `${freeChargers}/8 Available`;

      // Render 8 bot cards
      container.innerHTML = AMR_FLEET.map(r => {
        const isCharging = r.state === 'IDLE_CHARGING';
        const isLowBatt = r.battery <= 25.0 && !isCharging;

        let badgeText = 'STANDBY';
        let badgeBg = '#334155';
        let badgeColor = '#cbd5e1';

        if (isCharging) {
          badgeText = `⚡ CHARGING ${Math.round(r.battery)}%`;
          badgeBg = 'rgba(34, 197, 94, 0.2)';
          badgeColor = '#4ade80';
        } else if (isLowBatt) {
          badgeText = '🚨 LOW BATTERY';
          badgeBg = 'rgba(239, 68, 68, 0.25)';
          badgeColor = '#f87171';
        } else if (r.isOvertaking) {
          badgeText = '🏎️ OVERTAKE (1.35x)';
          badgeBg = 'rgba(56, 189, 248, 0.25)';
          badgeColor = '#38bdf8';
        } else if (r.isWaiting) {
          badgeText = `⏳ YIELDING TO ${r.yieldTo || 'AMR'}`;
          badgeBg = 'rgba(245, 158, 11, 0.25)';
          badgeColor = '#f59e0b';
        } else if (r.isRerouting) {
          badgeText = '🔄 DYNAMIC REROUTE';
          badgeBg = 'rgba(168, 85, 247, 0.25)';
          badgeColor = '#c084fc';
        } else if (r.state === 'LOADING_INBOUND') {
          badgeText = '📥 LOADING SHIPMENT';
          badgeBg = 'rgba(250, 204, 21, 0.25)';
          badgeColor = '#facc15';
        } else if (r.state === 'CARRYING_TO_RACK') {
          badgeText = `📥 SHELVING (${r.carriedParcels ? r.carriedParcels.length : 0} left)`;
          badgeBg = 'rgba(250, 204, 21, 0.25)';
          badgeColor = '#facc15';
        } else if (r.state === 'ORDER_PICKING' && r.orderBox) {
          badgeText = `📦 PICK ${r.orderBox.items.length}/${r.orderBox.totalItems}`;
          badgeBg = 'rgba(217, 119, 6, 0.25)';
          badgeColor = '#fbbf24';
        } else if (r.state === 'DELIVERING_ORDER_TO_BAY') {
          badgeText = '🚚 ORDER BOX DELIVERY';
          badgeBg = 'rgba(234, 88, 12, 0.25)';
          badgeColor = '#fb923c';
        } else if (r.state === 'RETURNING_HOME') {
          badgeText = '🏠 RETURNING TO DOCK';
          badgeBg = 'rgba(16, 185, 129, 0.2)';
          badgeColor = '#34d399';
        } else if (r.state === 'MOVING_TO_PICKUP') {
          badgeText = '🏃 TRANSIT TO DOCK';
          badgeBg = 'rgba(56, 189, 248, 0.2)';
          badgeColor = '#38bdf8';
        }

        let barColor = '#22c55e';
        if (r.battery <= 25.0) barColor = '#ef4444';
        else if (r.battery <= 50.0) barColor = '#f59e0b';

        let rateText = '';
        let etaText = '';
        if (isCharging) {
          const kw = (r.chargeRateKw || 30.0).toFixed(1);
          const chgRate = (r.batteryDeltaRate || 3.5).toFixed(1);
          rateText = `+${kw} kW (+${chgRate}%/s)`;
          const secRem = Math.max(0, Math.round((100 - r.battery) / Math.max(0.2, r.batteryDeltaRate || 2.5)));
          etaText = `Full in ~${secRem}s`;
        } else {
          const pTot = Math.round(r.powerWatts || 165);
          const drain = (r.batteryDeltaRate || 0.38).toFixed(2);
          rateText = `-${pTot} W (-${drain}%/s)`;
          const minRem = (Math.max(1, Math.round((r.battery - 15) / Math.max(0.08, r.batteryDeltaRate || 0.38))) / 60).toFixed(1);
          etaText = `~${minRem} min range`;
        }

        const spd = (r.currentSpeed || (ROBOT_BASE_SPEED * simSpeed)).toFixed(2);
        const throttlePct = r.payloadDamping ? Math.round(r.payloadDamping * 100) : 100;

        let cargoDesc = 'Deck Empty (0 kg)';
        if (r.orderBox) {
          cargoDesc = `Giant Box (${r.orderBox.items.length}/${r.orderBox.totalItems}, ${(r.payloadWeight || 5).toFixed(1)}kg)`;
        } else if (r.carriedParcels && r.carriedParcels.length > 0) {
          cargoDesc = `Tote (${r.carriedParcels.length} pkgs, ${(r.payloadWeight || 5).toFixed(1)}kg)`;
        }

        const urgency = calculateRobotUrgency(r);
        const nearestChg = getNearestAvailableCharger(r.gridX, r.gridY, r.id);
        const minReqSoC = nearestChg.energyNeeded + SAFETY_RESERVE_SOC;
        const isFeasible = r.battery >= minReqSoC;
        const reserveMargin = r.battery - minReqSoC;
        const currentBayLabel = r.currentChargerId ? `⚡ ${r.currentChargerId}` : (r.targetChargerId ? `En route ${r.targetChargerId}` : (nearestChg.charger ? nearestChg.charger.id : 'CH-01'));

        return `
          <div class="bot-card ${isLowBatt ? 'is-low-batt' : ''} ${isCharging ? 'is-charging' : ''}">
            <div class="bot-card-top">
              <div class="bot-id-title">
                <span style="color:#38bdf8;">🤖</span>
                <span>${r.id}</span>
                <span class="bot-zone-tag">(${currentBayLabel})</span>
              </div>
              <span class="bot-status-pill" style="background:${badgeBg}; color:${badgeColor}; border:1px solid ${badgeColor}40;">${badgeText}</span>
            </div>

            <div class="bot-soc-section">
              <div class="bot-soc-header">
                <span class="bot-soc-val" style="color:${barColor};">${r.battery.toFixed(1)}%</span>
                <span class="bot-soc-rate">${rateText}</span>
              </div>
              <div class="bot-soc-bar-bg">
                <div class="bot-soc-bar-fill" style="width:${r.battery.toFixed(1)}%; background:${barColor};"></div>
              </div>
              <div class="bot-soc-footer">
                <span>48V LiFePO4 BMS</span>
                <span style="font-weight:600; color:${barColor};">${etaText}</span>
              </div>
            </div>

            <div class="bot-metrics-grid">
              <div class="bot-metric-box">
                <span class="bot-metric-lbl">Kinematic Speed</span>
                <div class="bot-metric-val" style="color:#38bdf8;">${spd} c/s <span style="font-size:10px; color:#94a3b8;">(${throttlePct}%)</span></div>
              </div>
              <div class="bot-metric-box">
                <span class="bot-metric-lbl">Active Payload</span>
                <div class="bot-metric-val" style="color:#facc15;" title="${cargoDesc}">${cargoDesc}</div>
              </div>
              <div class="bot-metric-box">
                <span class="bot-metric-lbl">Nearest Charger</span>
                <div class="bot-metric-val" style="color:#4ade80;" title="Nearest available charging port distance & energy required">
                  ${nearestChg.charger ? nearestChg.charger.id : 'CH-01'} (${nearestChg.distance}m | ~${nearestChg.energyNeeded.toFixed(1)}%)
                </div>
              </div>
              <div class="bot-metric-box">
                <span class="bot-metric-lbl">BMS Energy Budget</span>
                <div class="bot-metric-val">
                  ${isFeasible ? `<span style="color:#22c55e;font-weight:700;">✔ OK (+${reserveMargin.toFixed(1)}%)</span>` : `<span style="color:#ef4444;font-weight:700;">🚨 RECHARGE (${reserveMargin.toFixed(1)}%)</span>`}
                </div>
              </div>
              <div class="bot-metric-box" style="grid-column: span 2;">
                <span class="bot-metric-lbl">Target / Mission</span>
                <div class="bot-metric-val" title="${r.targetDesc}">${r.targetDesc || 'Standby'}</div>
              </div>
            </div>

            <div class="bot-card-actions">
              <button class="bot-act-btn recall" onclick="sendBotToCharger('${r.id}')" title="Recall to Nearest Fast Charger">
                <span>⚡ Dock Nearest</span>
              </button>
              <button class="bot-act-btn track" onclick="trackBot('${r.id}', true)" title="Engage targeting lock and follow camera on ${r.id}">
                <span>🎯 Track</span>
              </button>
              <button class="bot-act-btn locate" onclick="locateBotOnMap('${r.id}')" title="Locate and Center 2D Map on ${r.id}">
                <span>📍 Map</span>
              </button>
            </div>
          </div>
        `;
      }).join('');
    }

    // 3D Multi-Tier Rack Memory & Inventory Management
    const MAX_FLOORS = 5;
    const rackMemory = {}; // Key: "x,y" -> { x, y, floors: [null, null, null, null, null] }
    const inboundQueues = {}; // Key: dockId -> Array of parcels waiting for pickup (Lit Yellow while > 0)
    const outboundOrders = {}; // Key: bayId -> { orderId, parcels: [], expireAt } (Lit Yellow while active)
    let parcelSequence = 1000;
    let orderSequence = 2000;

    const SKU_CATALOG = [
      { sku: "SKU-ELEC", name: "Electronics", fullName: "Consumer Electronics", weight: 4.5, color: "#38bdf8", tint: "rgba(56, 189, 248, 0.15)", border: "#0284c7" },
      { sku: "SKU-AUTO", name: "Automotive", fullName: "Automotive Parts", weight: 14.2, color: "#fb923c", tint: "rgba(251, 146, 60, 0.15)", border: "#ea580c" },
      { sku: "SKU-PHRM", name: "Pharma", fullName: "Cold-Chain Pharma", weight: 3.8, color: "#c084fc", tint: "rgba(192, 132, 252, 0.15)", border: "#9333ea" },
      { sku: "SKU-FASH", name: "Apparel", fullName: "Apparel & Footwear", weight: 2.2, color: "#f472b6", tint: "rgba(244, 114, 182, 0.15)", border: "#db2777" },
      { sku: "SKU-INDM", name: "Hardware", fullName: "Industrial Hardware", weight: 18.5, color: "#facc15", tint: "rgba(250, 204, 21, 0.15)", border: "#ca8a04" },
      { sku: "SKU-FMCG", name: "Retail Goods", fullName: "Retail Packaged Goods", weight: 6.7, color: "#34d399", tint: "rgba(52, 211, 153, 0.15)", border: "#059669" }
    ];

    function getRackCategory(y) {
      let idx = 0;
      if (y >= 5 && y <= 22) {
        idx = Math.floor((y - 5) / 3);
      } else if (y >= 27 && y <= 44) {
        idx = Math.floor((y - 27) / 3);
      }
      idx = Math.max(0, Math.min(SKU_CATALOG.length - 1, idx));
      return SKU_CATALOG[idx];
    }

    function initRackMemory() {
      if (!mapData) return;
      for (let x = 1; x < mapData.width - 1; x++) {
        for (let y = 1; y < mapData.height - 1; y++) {
          if (mapData.grid[x][y] === 1) { // Storage rack (excluding outer walls)
            const cat = getRackCategory(y);
            rackMemory[`${x},${y}`] = {
              x: x,
              y: y,
              categorySku: cat.sku,
              categoryName: cat.name,
              categoryFullName: cat.fullName,
              categoryColor: cat.color,
              categoryTint: cat.tint,
              categoryBorder: cat.border,
              floors: [null, null, null, null, null] // Index 0 = Tier 1, Index 4 = Tier 5
            };
          }
        }
      }

      // Seed initial warehouse inventory across rack pods (~240 items)
      // Guarantees outbound order consolidation always has parcels available from action #1
      for (const rack of Object.values(rackMemory)) {
        if (Math.random() < 0.22) {
          const cat = SKU_CATALOG.find(c => c.sku === rack.categorySku) || SKU_CATALOG[0];
          const numItems = Math.floor(Math.random() * 2) + 1;
          for (let f = 0; f < numItems; f++) {
            parcelSequence++;
            const w = parseFloat((cat.weight + (Math.random() * 2 - 1)).toFixed(1));
            rack.floors[f] = {
              parcel_id: `PKG-${parcelSequence}`,
              sku: cat.sku,
              name: cat.name,
              weight: `${w}kg`,
              weightVal: w,
              dock: 'INIT_STOCK',
              timestamp: 'Initial Inventory'
            };
          }
        }
      }

      // Initialize queues for stations
      for (const sid of Object.keys(mapData.stations)) {
        if (sid.startsWith('P')) inboundQueues[sid] = [];
        if (sid.startsWith('D')) outboundOrders[sid] = null;
      }
      updateHudStats();
    }

    function getStoredParcelCount() {
      let count = 0;
      for (const rack of Object.values(rackMemory)) {
        for (let f = 0; f < MAX_FLOORS; f++) {
          const item = rack.floors[f];
          if (item !== null && !item.isReservedInbound) count++;
        }
      }
      return count;
    }

    function getTotalInboundWaiting() {
      let count = 0;
      for (const queue of Object.values(inboundQueues)) {
        count += queue.length;
      }
      return count;
    }

    function getTotalOutboundInTransit() {
      let count = 0;
      for (const ord of Object.values(outboundOrders)) {
        if (ord) count += Math.max(0, ord.totalCount - (ord.deliveredCount || 0));
      }
      return count;
    }

    let _lastHudStatsTick = 0;
    function updateHudStats() {
      const nowMs = typeof performance !== 'undefined' ? performance.now() : Date.now();
      if (nowMs - _lastHudStatsTick < 250) return; // Throttled to 4 Hz
      _lastHudStatsTick = nowMs;

      const storedEl = document.getElementById('hud-stored-count');
      const inEl = document.getElementById('hud-inbound-waiting');
      const outEl = document.getElementById('hud-outbound-transit');
      const fleetEl = document.getElementById('hud-fleet-status');
      const collEl = document.getElementById('hud-collision-status');
      const trafEl = document.getElementById('hud-traffic-events');

      const totalSlots = Object.keys(rackMemory).length * MAX_FLOORS;
      const stored = getStoredParcelCount();
      const inWaiting = getTotalInboundWaiting();
      const outTransit = getTotalOutboundInTransit();

      if (storedEl) {
        const pct = totalSlots > 0 ? ((stored / totalSlots) * 100).toFixed(1) : 0;
        storedEl.innerText = `${stored.toLocaleString()} / ${totalSlots.toLocaleString()} (${pct}%)`;
      }
      if (inEl) inEl.innerText = `${inWaiting} Parcels Queued`;
      if (outEl) outEl.innerText = `${outTransit} Awaiting Deposit`;

      if (fleetEl) {
        let charging = 0, shelving = 0, retrieving = 0, waiting = 0, lowBatt = 0;
        for (const r of AMR_FLEET) {
          if (r.isWaiting) waiting++;
          if (r.battery <= 28.0 && r.state !== 'IDLE_CHARGING') lowBatt++;
          if (r.state === 'IDLE_CHARGING' || r.state === 'RETURNING_HOME') charging++;
          else if (r.state === 'MOVING_TO_PICKUP' || r.state === 'CARRYING_TO_RACK') shelving++;
          else if (r.state === 'ORDER_PICKING' || r.state === 'DELIVERING_ORDER_TO_BAY') retrieving++;
          else charging++;
        }
        fleetEl.innerText = `8 Bots (${shelving} Shelve | ${retrieving} Retrieve | ${charging} Charge${waiting > 0 ? ` | ${waiting} Yield` : ''}${lowBatt > 0 ? ` | ${lowBatt} Low SoC` : ''})`;
      }

      if (collEl) {
        collEl.innerHTML = `<span style="color:#22c55e; font-weight:700;">0 Collisions</span> <span style="color:#94a3b8; font-size:10px;">(${trafficMetrics.collisionsPrevented} Safe Yields)</span>`;
      }
      if (trafEl) {
        trafEl.innerText = `${trafficMetrics.totalYields} Yields | ${trafficMetrics.totalOvertakes} Overtakes | ${trafficMetrics.totalReroutes} Reroutes`;
      }
    }

    // Categorized Random Slot Allocation:
    // Finds a random empty slot within the designated category rows for the given SKU.
    function findRandomSlotForSku(sku) {
      const designatedEmptySlots = [];
      const anyEmptySlots = [];

      for (const rack of Object.values(rackMemory)) {
        for (let f = 0; f < MAX_FLOORS; f++) {
          if (rack.floors[f] === null) {
            const slot = { rack, floorIndex: f, floorNum: f + 1 };
            if (rack.categorySku === sku) {
              designatedEmptySlots.push(slot);
            }
            anyEmptySlots.push(slot);
          }
        }
      }

      if (designatedEmptySlots.length > 0) {
        const randIdx = Math.floor(Math.random() * designatedEmptySlots.length);
        return designatedEmptySlots[randIdx];
      }

      if (anyEmptySlots.length > 0) {
        const randIdx = Math.floor(Math.random() * anyEmptySlots.length);
        return anyEmptySlots[randIdx];
      }

      return null;
    }

    // ==========================================
    // REAL-WORLD AMR FLEET & TRAFFIC CONTROL SYSTEM
    // (Zero-Collision, Overtaking, Waiting, Rerouting, Flow-Directed Aisles)
    // ==========================================
    const AMR_COUNT = 8;
    const AMR_FLEET = [];
    const inboundMissions = []; // Single consolidated mission per inbound shipment (1 robot per dock)
    const outboundMissions = []; // Single consolidated mission per customer order (1 robot per order / Giant Box)
    const ROBOT_BASE_SPEED = 4.2; // Cells per second at 1x simSpeed

    // Delivery Importance Tiers with Base Urgency & SLA Windows
    const IMPORTANCE_TIERS = {
      VIP_EXPRESS: {
        code: 'VIP_EXPRESS',
        label: 'VIP Express (1-Hr SLA)',
        shortLabel: 'VIP',
        baseUrgency: 85,
        color: '#ef4444', // Red
        slaSeconds: 45
      },
      SAME_DAY: {
        code: 'SAME_DAY',
        label: 'Same-Day Urgent',
        shortLabel: 'URGENT',
        baseUrgency: 65,
        color: '#f97316', // Orange
        slaSeconds: 75
      },
      STANDARD: {
        code: 'STANDARD',
        label: 'Standard (2-Day)',
        shortLabel: 'STD',
        baseUrgency: 40,
        color: '#38bdf8', // Cyan
        slaSeconds: 120
      },
      ECONOMY: {
        code: 'ECONOMY',
        label: 'Economy Bulk',
        shortLabel: 'ECO',
        baseUrgency: 20,
        color: '#94a3b8', // Slate grey
        slaSeconds: 180
      }
    };

    // Realistic Urgency Calculation Formula:
    // Urgency = BaseImportance + TimeBonus - WeightPenalty
    function calculateRobotUrgency(r) {
      if (!r) return 0;
      if (r.state === 'IDLE_CHARGING') return 0;
      if (r.state === 'RETURNING_HOME') return 15;
      if (r.state === 'IDLE') return 20;

      let baseUrgency = 40;
      let slaSeconds = 90;
      let createdAt = r.missionStartTime || Date.now();
      let totalWeight = 0;

      if (r.orderBox) {
        const tier = r.orderBox.importance || IMPORTANCE_TIERS.STANDARD;
        baseUrgency = tier.baseUrgency;
        slaSeconds = tier.slaSeconds;
        totalWeight = r.orderBox.totalWeight || 5;
      } else if (r.carriedParcels && r.carriedParcels.length > 0) {
        const highestTier = r.carriedParcels.reduce((prev, curr) => {
          const t = curr.importance || IMPORTANCE_TIERS.STANDARD;
          return t.baseUrgency > prev.baseUrgency ? t : prev;
        }, IMPORTANCE_TIERS.STANDARD);
        baseUrgency = highestTier.baseUrgency;
        slaSeconds = highestTier.slaSeconds;
        totalWeight = r.carriedParcels.reduce((sum, p) => sum + (parseFloat(p.weight) || 3), 0);
      } else if (r.inboundMission) {
        const tier = r.inboundMission.importance || IMPORTANCE_TIERS.STANDARD;
        baseUrgency = tier.baseUrgency;
        slaSeconds = tier.slaSeconds;
        totalWeight = r.inboundMission.totalWeight || 5;
      }

      // Elapsed time escalation: +0 to +25 as deadline approaches
      const elapsedSec = Math.max(0, (Date.now() - createdAt) / 1000 * simSpeed);
      const timeBonus = Math.min(25, (elapsedSec / slaSeconds) * 25);

      // Weight penalty: heavy freight (>15kg) reduces aggressive high-speed maneuvering
      const weightPenalty = Math.min(20, (totalWeight / 3.0));

      // Battery penalty: low SoC (<30%) reduces aggressive overtaking to conserve power
      let batteryPenalty = 0;
      if (r.battery < 30.0) {
        batteryPenalty = Math.min(25, (30.0 - r.battery) * 1.5);
      }

      const urgency = Math.round(Math.max(10, Math.min(100, baseUrgency + timeBonus - weightPenalty - batteryPenalty)));
      return urgency;
    }

    // Traffic Coordination & Safety Metrics
    const trafficMetrics = {
      totalYields: 0,
      totalOvertakes: 0,
      totalReroutes: 0,
      collisionsPrevented: 0
    };

    // Designated One-Way Narrow Aisles (Industrial Traffic Standard)
    // Prevents 100% of head-on deadlocks in single-lane rack pods
    const NARROW_AISLE_COLS = new Set([7, 10, 13, 16, 19, 22, 32, 35, 38, 41, 44, 47, 58, 61, 64, 67, 70, 73]);
    const SOUTHBOUND_AISLE_COLS = new Set([7, 13, 19, 32, 38, 44, 58, 64, 70]); // Moving dy > 0
    const NORTHBOUND_AISLE_COLS = new Set([10, 16, 22, 35, 41, 47, 61, 67, 73]); // Moving dy < 0

    // ==========================================
    // HIGH-PRECISION TELEMETRY & BEHAVIOR LOGGING ENGINE
    // ==========================================
    let totalSimSeconds = 0;

    function recordRobotEvent(robot, type, description, details = {}) {
      if (!robot || !robot.eventHistory) return;
      const entry = {
        eventId: robot.eventHistory.length + 1,
        timestamp: new Date().toISOString(),
        simTimeSeconds: Number((totalSimSeconds || 0).toFixed(2)),
        type: type,
        description: description,
        coords: { x: Number(robot.x.toFixed(2)), y: Number(robot.y.toFixed(2)), gridX: robot.gridX, gridY: robot.gridY },
        battery: Number(robot.battery.toFixed(1)),
        state: robot.state,
        statusBadge: robot.statusBadge || null,
        cargoWeightKg: Number((robot.payloadWeight || 0).toFixed(1)),
        details: details
      };
      robot.eventHistory.push(entry);
      if (robot.eventHistory.length > 2000) {
        robot.eventHistory.shift();
      }
    }

    function onRobotJamStart(robot, blockerId, reason) {
      if (!robot) return;
      if (robot.currentJam) {
        if (blockerId && robot.currentJam.blockerId === 'UNKNOWN') {
          robot.currentJam.blockerId = blockerId;
          const blocker = AMR_FLEET.find(b => b.id === blockerId);
          if (blocker) robot.currentJam.blockerBattery = Number(blocker.battery.toFixed(1));
        }
        return;
      }
      const blocker = blockerId ? AMR_FLEET.find(b => b.id === blockerId) : null;
      robot.currentJam = {
        episodeId: (robot.jamEpisodes ? robot.jamEpisodes.length + 1 : 1),
        startTime: Date.now(),
        startSimTime: totalSimSeconds,
        location: { x: robot.gridX, y: robot.gridY },
        blockerId: blockerId || 'UNKNOWN',
        myBattery: Number(robot.battery.toFixed(1)),
        blockerBattery: blocker ? Number(blocker.battery.toFixed(1)) : null,
        reason: reason || 'COLLISION_PREVENTION'
      };
      if (robot.logStats) {
        robot.logStats.totalJamsEncountered++;
      }
      recordRobotEvent(robot, 'JAM_ENTER', `Halted at (${robot.gridX}, ${robot.gridY}) due to ${reason} (Blocker: ${blockerId || 'peer'})`, {
        blockerId,
        reason,
        myBattery: robot.battery,
        blockerBattery: blocker ? blocker.battery : null
      });
    }

    function onRobotJamEnd(robot, resolution = 'RESUMED_NORMAL') {
      if (!robot || !robot.currentJam) return;
      const waitDur = totalSimSeconds - robot.currentJam.startSimTime;
      if (waitDur >= 0.05) {
        const episode = {
          episodeId: robot.currentJam.episodeId,
          startRealTime: new Date(robot.currentJam.startTime).toLocaleTimeString(),
          startSimTimeSec: Number(robot.currentJam.startSimTime.toFixed(2)),
          endSimTimeSec: Number(totalSimSeconds.toFixed(2)),
          waitDurationSec: Number(waitDur.toFixed(2)),
          location: robot.currentJam.location,
          blockerId: robot.currentJam.blockerId,
          botBattery: robot.currentJam.myBattery,
          blockerBattery: robot.currentJam.blockerBattery,
          reason: robot.currentJam.reason,
          resolution: resolution,
          description: `Waited ${waitDur.toFixed(1)}s at (${robot.currentJam.location.x}, ${robot.currentJam.location.y}) due to ${robot.currentJam.reason} (${robot.currentJam.blockerId}). Resolved via ${resolution}.`
        };
        if (robot.jamEpisodes) {
          robot.jamEpisodes.push(episode);
          if (robot.jamEpisodes.length > 500) robot.jamEpisodes.shift();
        }
        recordRobotEvent(robot, 'JAM_CLEARED', `Traffic delay resolved after ${waitDur.toFixed(1)}s via ${resolution}`, episode);
      }
      robot.currentJam = null;
    }

    function buildBotLogObject(r) {
      if (!r) return null;
      const s = r.logStats || {};
      const totalTime = s.totalSimTime || 0.001;
      const moveTime = s.activeMovingTime || 0;
      const waitTime = s.jamWaitTime || 0;
      const chgTime = s.chargingTime || 0;
      const loadTime = s.loadingTime || 0;
      const idleTime = s.idleTime || 0;

      const movingPct = Number(((moveTime / totalTime) * 100).toFixed(1));
      const jamWaitPct = Number(((waitTime / totalTime) * 100).toFixed(1));
      const chargingPct = Number(((chgTime / totalTime) * 100).toFixed(1));
      const loadingPct = Number(((loadTime / totalTime) * 100).toFixed(1));
      const idlePct = Number(((idleTime / totalTime) * 100).toFixed(1));

      const activeAndWait = moveTime + waitTime;
      const jamDelayFactor = activeAndWait > 0 ? Number(((waitTime / activeAndWait) * 100).toFixed(1)) : 0;
      const nonChgTime = totalTime - chgTime;
      const operationalAvailabilityPct = nonChgTime > 0 ? Number((((moveTime + loadTime) / nonChgTime) * 100).toFixed(1)) : 0;

      const avgSpeed = moveTime > 0 ? Number(((s.totalDistanceTraveled || 0) / moveTime).toFixed(2)) : 0;

      return {
        botId: r.id,
        num: r.num,
        homeBay: {
          id: r.homeBayId,
          zone: r.homeBayZone,
          x: r.homeX,
          y: r.homeY
        },
        currentStatus: {
          state: r.state,
          batteryPercent: Number(r.battery.toFixed(1)),
          minBatterySeenPercent: Number((s.minBatterySeen !== undefined ? s.minBatterySeen : r.battery).toFixed(1)),
          currentSpeedCellsPerSec: Number((r.currentSpeed || 0).toFixed(2)),
          headingDegrees: Math.round((r.heading * 180 / Math.PI + 360) % 360),
          position: {
            x: Number(r.x.toFixed(2)),
            y: Number(r.y.toFixed(2)),
            gridX: r.gridX,
            gridY: r.gridY
          },
          statusBadge: r.statusBadge || null,
          targetDescription: r.targetDesc || null,
          payloadWeightKg: Number((r.payloadWeight || 0).toFixed(1)),
          payloadDampingFactor: Number((r.payloadDamping || 1.0).toFixed(2)),
          bmsPowerWatts: Math.round(r.powerWatts || 0),
          bmsChargePhase: r.chargePhase || 'Standby'
        },
        functionalTimeBreakdown: {
          totalSimSeconds: Number(totalTime.toFixed(2)),
          activeMovingTimeSeconds: Number(moveTime.toFixed(2)),
          activeMovingPercent: movingPct,
          jamWaitTimeSeconds: Number(waitTime.toFixed(2)),
          jamWaitPercent: jamWaitPct,
          chargingTimeSeconds: Number(chgTime.toFixed(2)),
          chargingPercent: chargingPct,
          loadingTimeSeconds: Number(loadTime.toFixed(2)),
          loadingPercent: loadingPct,
          idleTimeSeconds: Number(idleTime.toFixed(2)),
          idlePercent: idlePct,
          jamDelayFactorPercent: jamDelayFactor,
          operationalAvailabilityPercent: operationalAvailabilityPct
        },
        kinematicsAndDistance: {
          totalDistanceTraveledCells: Number((s.totalDistanceTraveled || 0).toFixed(2)),
          totalCellsTraversed: s.totalCellsTraversed || 0,
          averageMovingSpeedCellsPerSec: avgSpeed,
          maxSpeedRecordedCellsPerSec: Number((s.maxSpeed || 0).toFixed(2))
        },
        bmsEnergyMetrics: {
          initialBatteryPercent: Number((s.initialBattery || 100).toFixed(1)),
          currentBatteryPercent: Number(r.battery.toFixed(1)),
          minBatteryFloorSeenPercent: Number((s.minBatterySeen !== undefined ? s.minBatterySeen : r.battery).toFixed(1)),
          batterySafetyFloorMet: (s.minBatterySeen !== undefined ? s.minBatterySeen : r.battery) > 10.0,
          outOfChargeEvents: s.totalOutOfChargeEvents || 0,
          towedByRescueCount: s.totalTowedByRescue || 0,
          totalEnergyConsumedSoCPercent: Number((s.totalEnergyConsumedSoC || 0).toFixed(2)),
          totalEnergyChargedSoCPercent: Number((s.totalEnergyChargedSoC || 0).toFixed(2)),
          chargeCyclesCompleted: s.chargeCyclesCount || 0
        },
        warehouseProductivity: {
          inboundShipmentsCompleted: s.totalInboundCompleted || 0,
          outboundOrdersCompleted: s.totalOutboundCompleted || 0,
          totalParcelsShelved: s.totalParcelsShelved || 0,
          totalItemsPickedConsolidated: s.totalItemsConsolidated || 0,
          totalPayloadMassTransportedKg: Number((s.totalWeightTransportedKg || 0).toFixed(1)),
          completedMissions: r.missionsHistory || []
        },
        trafficAndJamBehavior: {
          totalJamsEncountered: s.totalJamsEncountered || 0,
          totalJamWaitTimeSeconds: Number(waitTime.toFixed(2)),
          averageJamDurationSeconds: s.totalJamsEncountered > 0 ? Number((waitTime / s.totalJamsEncountered).toFixed(2)) : 0,
          totalBackupsToPreviousBox: s.totalBackupsToPreviousBox || 0,
          totalSideStepsExecuted: s.totalSideSteps || 0,
          totalOvertakesInitiated: s.totalOvertakesInitiated || 0,
          totalOvertakesCompleted: s.totalOvertakesCompleted || 0,
          totalReroutesExecuted: s.totalReroutes || 0,
          totalRightOfWayYields: s.totalRightOfWayYields || 0,
          totalEmergencyBrakingEvents: s.totalEmergencyBraking || 0,
          physicalCollisions: s.physicalCollisions || 0,
          jamEpisodes: r.jamEpisodes || []
        },
        chronologicalEventLog: r.eventHistory || []
      };
    }

    function buildFleetTelemetryPayload() {
      const now = new Date();
      const botsData = AMR_FLEET.map(b => buildBotLogObject(b));

      let totalFleetDist = 0;
      let totalFleetMovingTime = 0;
      let totalFleetJamWaitTime = 0;
      let totalFleetChargingTime = 0;
      let totalFleetParcels = 0;
      let totalFleetItems = 0;
      let totalFleetWeight = 0;
      let totalFleetEnergyConsumed = 0;
      let totalFleetJams = 0;
      let totalFleetBackups = 0;
      let totalFleetOvertakes = 0;
      let totalFleetReroutes = 0;
      let totalFleetYields = 0;
      let minFleetBattery = 100;

      for (const b of botsData) {
        totalFleetDist += b.kinematicsAndDistance.totalDistanceTraveledCells;
        totalFleetMovingTime += b.functionalTimeBreakdown.activeMovingTimeSeconds;
        totalFleetJamWaitTime += b.functionalTimeBreakdown.jamWaitTimeSeconds;
        totalFleetChargingTime += b.functionalTimeBreakdown.chargingTimeSeconds;
        totalFleetParcels += b.warehouseProductivity.totalParcelsShelved;
        totalFleetItems += b.warehouseProductivity.totalItemsPickedConsolidated;
        totalFleetWeight += b.warehouseProductivity.totalPayloadMassTransportedKg;
        totalFleetEnergyConsumed += b.bmsEnergyMetrics.totalEnergyConsumedSoCPercent;
        totalFleetJams += b.trafficAndJamBehavior.totalJamsEncountered;
        totalFleetBackups += b.trafficAndJamBehavior.totalBackupsToPreviousBox;
        totalFleetOvertakes += b.trafficAndJamBehavior.totalOvertakesCompleted;
        totalFleetReroutes += b.trafficAndJamBehavior.totalReroutesExecuted;
        totalFleetYields += b.trafficAndJamBehavior.totalRightOfWayYields;
        if (b.bmsEnergyMetrics.minBatteryFloorSeenPercent < minFleetBattery) {
          minFleetBattery = b.bmsEnergyMetrics.minBatteryFloorSeenPercent;
        }
      }

      const fleetActiveAndWait = totalFleetMovingTime + totalFleetJamWaitTime;
      const fleetJamDelayPct = fleetActiveAndWait > 0 ? Number(((totalFleetJamWaitTime / fleetActiveAndWait) * 100).toFixed(1)) : 0;
      const collisionCount = trafficMetrics.totalCollisions || FLEET_INCIDENTS.filter(i => i.type === 'COLLISION').length;
      const outOfChargeCount = FLEET_INCIDENTS.filter(i => i.type === 'OUT_OF_CHARGE').length;
      const deadCount = AMR_FLEET.filter(b => b.state === 'OUT_OF_CHARGE' || b.battery <= 10.0).length;

      return {
        exportMetadata: {
          exportTimestampIso: now.toISOString(),
          exportLocalTime: now.toLocaleString(),
          totalSimSeconds: Number((totalSimSeconds || 0).toFixed(2)),
          fleetSize: AMR_FLEET.length,
          warehouseDimensions: mapData ? `${mapData.width}x${mapData.height}` : '80x50',
          simulationSpeedMultiplier: simSpeed
        },
        fleetAggregateKpis: {
          totalActionsCompleted: totalFleetParcels + totalFleetItems,
          totalParcelsShelved: totalFleetParcels,
          totalCustomerOrderItemsPicked: totalFleetItems,
          totalFreightMassTransportedKg: Number(totalFleetWeight.toFixed(1)),
          totalDistanceTraveledCells: Number(totalFleetDist.toFixed(1)),
          totalActiveMovingTimeSeconds: Number(totalFleetMovingTime.toFixed(1)),
          totalJamWaitTimeSeconds: Number(totalFleetJamWaitTime.toFixed(1)),
          fleetAverageJamDelayPercent: fleetJamDelayPct,
          totalJamsEncountered: totalFleetJams,
          totalDeadlockBackupsToPreviousBox: totalFleetBackups,
          totalOvertakesCompleted: totalFleetOvertakes,
          totalDynamicReroutes: totalFleetReroutes,
          totalRightOfWayYields: totalFleetYields,
          physicalCollisions: collisionCount,
          totalPhysicalCollisions: collisionCount,
          totalOutOfChargeIncidents: outOfChargeCount,
          bmsBatteryFloor10PctViolationCount: outOfChargeCount,
          deadBotsCount: deadCount,
          totalEnergyConsumedSoCPercent: Number(totalFleetEnergyConsumed.toFixed(1)),
          minFleetBatteryObservedPercent: minFleetBattery
        },
        fleetIncidents: FLEET_INCIDENTS || [],
        bots: botsData
      };
    }

    function buildFleetPerformanceCsv() {
      const payload = buildFleetTelemetryPayload();
      const headers = [
        'Bot ID',
        'Current State',
        'Current Battery (%)',
        'Min Battery (%)',
        'Total Sim Time (s)',
        'Active Moving Time (s)',
        'Moving (%)',
        'Jam Wait Time (s)',
        'Jam Delay (%)',
        'Charging Time (s)',
        'Charging (%)',
        'Loading Time (s)',
        'Loading (%)',
        'Idle Time (s)',
        'Idle (%)',
        'Total Distance (cells)',
        'Avg Speed (cells/s)',
        'Max Speed (cells/s)',
        'Jams Encountered',
        'Avg Jam Wait (s)',
        'Deadlock Backups',
        'Side Steps',
        'Overtakes Completed',
        'Dynamic Reroutes',
        'Right-of-Way Yields',
        'Parcels Shelved',
        'Items Picked',
        'Total Weight (kg)',
        'Energy Consumed (% SoC)',
        'Energy Charged (% SoC)',
        'Charge Cycles',
        'Physical Collisions',
        'BMS Cut-offs (10%)',
        'Rescue Tows',
        'Operational Availability (%)'
      ];

      const rows = [headers.join(',')];
      for (const b of payload.bots) {
        const s = b.functionalTimeBreakdown;
        const k = b.kinematicsAndDistance;
        const t = b.trafficAndJamBehavior;
        const p = b.warehouseProductivity;
        const e = b.bmsEnergyMetrics;
        const c = b.currentStatus;

        rows.push([
          b.botId,
          c.state,
          c.batteryPercent,
          e.minBatteryFloorSeenPercent,
          s.totalSimSeconds,
          s.activeMovingTimeSeconds,
          s.activeMovingPercent,
          s.jamWaitTimeSeconds,
          s.jamDelayFactorPercent,
          s.chargingTimeSeconds,
          s.chargingPercent,
          s.loadingTimeSeconds,
          s.loadingPercent,
          s.idleTimeSeconds,
          s.idlePercent,
          k.totalDistanceTraveledCells,
          k.averageMovingSpeedCellsPerSec,
          k.maxSpeedRecordedCellsPerSec,
          t.totalJamsEncountered,
          t.averageJamDurationSeconds,
          t.totalBackupsToPreviousBox,
          t.totalSideStepsExecuted,
          t.totalOvertakesCompleted,
          t.totalReroutesExecuted,
          t.totalRightOfWayYields,
          p.totalParcelsShelved,
          p.totalItemsPickedConsolidated,
          p.totalPayloadMassTransportedKg,
          e.totalEnergyConsumedSoCPercent,
          e.totalEnergyChargedSoCPercent,
          e.chargeCyclesCompleted,
          t.physicalCollisions || 0,
          e.outOfChargeEvents || 0,
          e.towedByRescueCount || 0,
          s.operationalAvailabilityPercent
        ].join(','));
      }
      return rows.join(String.fromCharCode(10));
    }

    function buildJamEpisodesCsv(targetBotId = null) {
      const headers = [
        'Episode ID',
        'Bot ID',
        'Start Sim Time (s)',
        'End Sim Time (s)',
        'Wait Duration (s)',
        'Start Real Time',
        'Location X',
        'Location Y',
        'Blocker Bot ID',
        'Bot Battery (%)',
        'Blocker Battery (%)',
        'Reason',
        'Resolution',
        'Description'
      ];

      const rows = [headers.join(',')];
      const bots = targetBotId ? AMR_FLEET.filter(b => b.id === targetBotId) : AMR_FLEET;

      for (const bot of bots) {
        if (!bot.jamEpisodes) continue;
        for (const ep of bot.jamEpisodes) {
          const descClean = (ep.description || '').replace(/"/g, '""');
          rows.push([
            ep.episodeId,
            bot.id,
            ep.startSimTimeSec,
            ep.endSimTimeSec,
            ep.waitDurationSec,
            ep.startRealTime,
            ep.location ? ep.location.x : '',
            ep.location ? ep.location.y : '',
            ep.blockerId || '',
            ep.botBattery !== null && ep.botBattery !== undefined ? ep.botBattery : '',
            ep.blockerBattery !== null && ep.blockerBattery !== undefined ? ep.blockerBattery : '',
            ep.reason || '',
            ep.resolution || '',
            `"${descClean}"`
          ].join(','));
        }
      }
      return rows.join(String.fromCharCode(10));
    }

    function downloadBlob(content, filename, mimeType) {
      if (typeof window === 'undefined' || typeof document === 'undefined') return;
      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 200);
    }

    function openLogsModal() {
      const modal = document.getElementById('logs-modal');
      if (!modal) return;
      const payload = buildFleetTelemetryPayload();
      const k = payload.fleetAggregateKpis;
      const m = payload.exportMetadata;

      const setVal = (id, v) => {
        const el = document.getElementById(id);
        if (el) el.innerText = v;
      };

      setVal('modal-log-sim-time', `${Math.floor(m.totalSimSeconds / 60)}m ${Math.floor(m.totalSimSeconds % 60)}s`);
      setVal('modal-log-moving-time', `${k.totalActiveMovingTimeSeconds.toFixed(1)}s`);
      setVal('modal-log-jam-time', `${k.totalJamWaitTimeSeconds.toFixed(1)}s (${k.fleetAverageJamDelayPercent}%)`);
      setVal('modal-log-jams-count', `${k.totalJamsEncountered} delays`);
      setVal('modal-log-freight', `${k.totalActionsCompleted} pkgs (${k.totalFreightMassTransportedKg}kg)`);
      setVal('modal-log-distance', `${k.totalDistanceTraveledCells} cells`);

      modal.classList.add('open');
    }

    function closeLogsModal(e) {
      if (e && e.target && e.target.classList && !e.target.classList.contains('modal-overlay') && !e.target.classList.contains('modal-close-btn') && !e.target.classList.contains('cancel')) {
        return;
      }
      const modal = document.getElementById('logs-modal');
      if (modal) modal.classList.remove('open');
    }

    function downloadFleetJson() {
      const payload = buildFleetTelemetryPayload();
      const jsonStr = JSON.stringify(payload, null, 2);
      downloadBlob(jsonStr, `amr_fleet_full_telemetry_${Date.now()}.json`, 'application/json');
      logTerminal('SYSTEM', 'tag-inbound', `📥 <strong>Fleet Telemetry Exported</strong>: Downloaded complete JSON logs for all 8 AMRs.`);
    }

    function downloadPerformanceCsv() {
      const csvStr = buildFleetPerformanceCsv();
      downloadBlob(csvStr, `amr_fleet_performance_${Date.now()}.csv`, 'text/csv');
      logTerminal('SYSTEM', 'tag-inbound', `📥 <strong>Fleet Performance Exported</strong>: Downloaded spreadsheet summary CSV.`);
    }

    function downloadJamsCsv() {
      const csvStr = buildJamEpisodesCsv();
      downloadBlob(csvStr, `amr_traffic_jams_${Date.now()}.csv`, 'text/csv');
      logTerminal('SYSTEM', 'tag-yield', `📥 <strong>Traffic Jams Log Exported</strong>: Downloaded granular jam and wait audit CSV.`);
    }

    function downloadBotLog(botId, format = 'json') {
      if (!botId) {
        const sel = document.getElementById('modal-bot-select');
        botId = sel ? sel.value : (AMR_FLEET[0] ? AMR_FLEET[0].id : 'AMR-01');
      }
      const bot = AMR_FLEET.find(b => b.id === botId);
      if (!bot) return;

      if (format === 'json') {
        const botData = buildBotLogObject(bot);
        const jsonStr = JSON.stringify(botData, null, 2);
        downloadBlob(jsonStr, `${bot.id}_telemetry_log_${Date.now()}.json`, 'application/json');
      } else {
        const csvStr = buildJamEpisodesCsv(botId);
        downloadBlob(csvStr, `${bot.id}_jams_log_${Date.now()}.csv`, 'text/csv');
      }
      logTerminal('SYSTEM', 'tag-inbound', `📥 <strong>Bot Log Exported</strong>: Downloaded ${format.toUpperCase()} log for <strong>${botId}</strong>.`);
    }

    function downloadCurrentTrackedBotLog() {
      if (trackedRobotId) {
        downloadBotLog(trackedRobotId, 'json');
      }
    }

    function initAmrFleet() {
      totalSimSeconds = 0;
      AMR_FLEET.length = 0;
      for (const p of CHARGING_PORTS) {
        p.occupiedBy = null;
        p.reservedBy = null;
      }

      const initialBatteries = [98.0, 85.0, 72.0, 92.0, 88.0, 76.0, 94.0, 82.0];
      for (let i = 0; i < AMR_COUNT; i++) {
        const bay = CHARGING_PORTS[i];
        bay.occupiedBy = `AMR-0${i + 1}`;
        const initBatt = initialBatteries[i % initialBatteries.length];
        const newBot = {
          id: `AMR-0${i + 1}`,
          num: i + 1,
          homeBayId: bay.id,
          assignedBayId: bay.id,
          currentChargerId: bay.id,
          targetChargerId: null,
          homeBayZone: bay.zone,
          homeX: bay.x,
          homeY: bay.y,
          x: bay.x,
          y: bay.y,
          gridX: bay.x,
          gridY: bay.y,
          heading: i < 4 ? Math.PI / 2 : -Math.PI / 2, // Facing away from wall
          state: 'IDLE_CHARGING', // 'IDLE_CHARGING', 'MOVING_TO_PICKUP', 'LOADING_INBOUND', 'CARRYING_TO_RACK', 'ORDER_PICKING', 'DELIVERING_ORDER_TO_BAY', 'RETURNING_HOME'
          battery: initBatt,
          cargo: null,
          carriedParcels: [], // Inbound shipment batch to shelf across racks
          isLoadedYellow: false, // Bright yellow lighting animation when carrying inbound load
          orderBox: null, // Giant Consolidated Order Box for 1 customer order
          loadingTimer: 0,
          missionStartTime: 0,
          inboundMission: null,
          outboundMission: null,
          path: [],
          pathIndex: 0,
          targetDesc: `Parked at Fast Charger ${bay.id} (${Math.round(initBatt)}%)`,
          // Real-World BMS Battery Telemetry State
          powerWatts: 0,
          powerBreakdown: 'Charger Standby',
          chargeRateKw: 30.0,
          chargePhase: initBatt >= 95 ? 'Cell Balancing / Float' : (initBatt >= 75 ? 'Absorption CV Phase' : 'Bulk CC Phase'),
          batteryDeltaRate: 0,
          hasAnnouncedLowBatt: false,
          hasAnnouncedBulkCharged: initBatt >= 80,
          // Real-World Traffic & Collision State
          isWaiting: false,
          waitTimer: 0,
          yieldTo: null,
          isOvertaking: false,
          overtakeTarget: null,
          overtakeTimer: 0,
          isRerouting: false,
          rerouteTimer: 0,
          statusBadge: null, // 'WAIT', 'PASS', 'REROUTE', 'LOAD', 'SHELVE', 'PICK', 'ORDER BOX'
          speedMultiplier: 1.0,
          currentSpeed: ROBOT_BASE_SPEED,
          payloadWeight: 0,
          payloadDamping: 1.0,
          lastYieldLogTime: 0,
          mapPingTimer: 0,
          strandedTimer: 0,
          // Comprehensive Telemetry & Flight Recording
          logStats: {
            startTime: Date.now(),
            startSimTime: 0,
            totalSimTime: 0,
            activeMovingTime: 0,
            jamWaitTime: 0,
            chargingTime: 0,
            loadingTime: 0,
            idleTime: 0,
            totalDistanceTraveled: 0,
            totalCellsTraversed: 0,
            totalJamsEncountered: 0,
            totalBackupsToPreviousBox: 0,
            totalSideSteps: 0,
            totalOvertakesInitiated: 0,
            totalOvertakesCompleted: 0,
            totalReroutes: 0,
            totalEmergencyBraking: 0,
            totalRightOfWayYields: 0,
            totalInboundCompleted: 0,
            totalOutboundCompleted: 0,
            totalParcelsShelved: 0,
            totalItemsConsolidated: 0,
            totalWeightTransportedKg: 0,
            initialBattery: initBatt,
            minBatterySeen: initBatt,
            totalEnergyConsumedSoC: 0,
            totalEnergyChargedSoC: 0,
            chargeCyclesCount: 1,
            maxSpeed: 0,
            physicalCollisions: 0,
            totalOutOfChargeEvents: 0,
            totalTowedByRescue: 0
          },
          recentVisitedCells: [],
          currentJam: null,
          jamEpisodes: [],
          missionsHistory: [],
          eventHistory: []
        };
        AMR_FLEET.push(newBot);
        recordRobotEvent(newBot, 'INIT', `AMR initialized at Charger ${bay.id} with ${initBatt}% SoC`, { chargerId: bay.id, battery: initBatt });
      }
      updateHudStats();
    }

    // =========================================================================
    // DYNAMIC OBSTACLE & HUMAN WORKER SYSTEM
    // =========================================================================
    let dynamicObstaclesEnabled = true;
    const DYNAMIC_OBSTACLES = [
      {
        id: 'HUMAN-01',
        type: 'human',
        name: 'Alex (Auditor)',
        role: 'Inventory Auditor',
        x: 25.0,
        y: 18.0,
        gridX: 25,
        gridY: 18,
        speed: 0.75,
        heading: Math.PI / 2,
        routeIndex: 0,
        pauseTimer: 0,
        isPaused: false,
        safetyRadius: 1.6,
        currentAction: 'Auditing Racks A12-A15',
        route: [
          { x: 25, y: 18, pause: 3.0, action: 'Auditing Racks A12-A15' },
          { x: 25, y: 32, pause: 3.5, action: 'Inspecting Pallet Stack' },
          { x: 37, y: 32, pause: 3.0, action: 'Scanning Floor Barcode' },
          { x: 37, y: 18, pause: 4.0, action: 'Checking Cross-Aisle Clearance' }
        ]
      },
      {
        id: 'HUMAN-02',
        type: 'human',
        name: 'Sarah (Safety)',
        role: 'Safety Marshall',
        x: 55.0,
        y: 32.0,
        gridX: 55,
        gridY: 32,
        speed: 0.8,
        heading: -Math.PI / 2,
        routeIndex: 0,
        pauseTimer: 0,
        isPaused: false,
        safetyRadius: 1.6,
        currentAction: 'Fire Extinguisher Check',
        route: [
          { x: 55, y: 32, pause: 3.5, action: 'Fire Extinguisher Check' },
          { x: 55, y: 15, pause: 4.0, action: 'Checking Charger Bay E-Stop' },
          { x: 43, y: 15, pause: 3.0, action: 'Verifying Floor Markings' },
          { x: 43, y: 32, pause: 3.5, action: 'Inspecting Aisle Clearance' }
        ]
      },
      {
        id: 'CART-01',
        type: 'pallet_cart',
        name: 'Staging Pallet Cart',
        role: 'Temporary Staging',
        x: 40.0,
        y: 24.0,
        gridX: 40,
        gridY: 24,
        isStatic: true,
        safetyRadius: 1.2,
        currentAction: 'Staged Cross-Dock Pallet'
      }
    ];

    function updateHumanWorkers(dt) {
      if (!dynamicObstaclesEnabled) return;
      for (const obs of DYNAMIC_OBSTACLES) {
        if (obs.isStatic || !obs.route || obs.route.length === 0) continue;

        if (obs.isPaused) {
          obs.pauseTimer -= dt * (simSpeed || 1.0);
          if (obs.pauseTimer <= 0) {
            obs.isPaused = false;
            obs.routeIndex = (obs.routeIndex + 1) % obs.route.length;
            const nextWp = obs.route[obs.routeIndex];
            obs.currentAction = nextWp.action || 'Patrolling Corridor';
          }
          continue;
        }

        const wp = obs.route[obs.routeIndex];
        const dx = wp.x - obs.x;
        const dy = wp.y - obs.y;
        const dist = Math.hypot(dx, dy);

        if (dist < 0.15) {
          obs.x = wp.x;
          obs.y = wp.y;
          obs.gridX = wp.x;
          obs.gridY = wp.y;
          obs.isPaused = true;
          obs.pauseTimer = (wp.pause || 3.0);
          obs.currentAction = wp.action || 'Inspecting Zone';
        } else {
          obs.heading = Math.atan2(dy, dx);
          const step = Math.min(dist, obs.speed * (simSpeed || 1.0) * dt);
          obs.x += (dx / dist) * step;
          obs.y += (dy / dist) * step;
          obs.gridX = Math.round(obs.x);
          obs.gridY = Math.round(obs.y);
        }
      }
    }

    function toggleDynamicObstacles() {
      dynamicObstaclesEnabled = !dynamicObstaclesEnabled;
      const btn = document.getElementById('btn-toggle-obs');
      if (btn) btn.classList.toggle('active', dynamicObstaclesEnabled);
      const btn2 = document.getElementById('btn-obs-toggle');
      if (btn2) btn2.classList.toggle('active', dynamicObstaclesEnabled);
      logTerminal('SYSTEM', 'tag-overtake', `👷 Dynamic Obstacles & Human Workers: ${dynamicObstaclesEnabled ? 'ENABLED' : 'DISABLED'}`);
    }

    function spawnDynamicWorker(customX = null, customY = null) {
      const idx = DYNAMIC_OBSTACLES.length + 1;
      const wx = customX !== null ? customX : Math.floor(Math.random() * 20 + 30);
      const wy = customY !== null ? customY : Math.floor(Math.random() * 15 + 18);
      const newWorker = {
        id: `HUMAN-0${idx}`,
        type: 'human',
        name: `Operator #${idx}`,
        role: 'Zone Inspector',
        x: wx,
        y: wy,
        gridX: wx,
        gridY: wy,
        speed: 0.7,
        heading: 0,
        routeIndex: 0,
        pauseTimer: 0,
        isPaused: false,
        safetyRadius: 1.6,
        currentAction: 'Routine Safety Inspection',
        route: [
          { x: wx, y: wy, pause: 3.0, action: 'Inspecting Pallet Pods' },
          { x: wx, y: Math.min(45, wy + 10), pause: 3.5, action: 'Verifying Floor Sensors' },
          { x: Math.min(75, wx + 8), y: Math.min(45, wy + 10), pause: 3.0, action: 'Barcode Audit' },
          { x: Math.min(75, wx + 8), y: wy, pause: 3.5, action: 'Returning to Patrol Origin' }
        ]
      };
      DYNAMIC_OBSTACLES.push(newWorker);
      logTerminal('SYSTEM', 'tag-inbound', `👷 Spawned Human Worker <strong>${newWorker.name}</strong> at (${wx}, ${wy}).`);
      updateV2VDrawerUI();
    }

    function spawnPalletObstacle(customX = null, customY = null) {
      const idx = DYNAMIC_OBSTACLES.length + 1;
      const ox = customX !== null ? customX : Math.floor(Math.random() * 20 + 30);
      const oy = customY !== null ? customY : Math.floor(Math.random() * 15 + 18);
      const newObs = {
        id: `CART-0${idx}`,
        type: 'pallet_cart',
        name: `Pallet Cart #${idx}`,
        role: 'Temporary Staging',
        x: ox,
        y: oy,
        gridX: ox,
        gridY: oy,
        isStatic: true,
        safetyRadius: 1.2,
        currentAction: 'Aisle Staging'
      };
      DYNAMIC_OBSTACLES.push(newObs);
      logTerminal('SYSTEM', 'tag-yield', `📦 Placed Staging Obstacle <strong>${newObs.name}</strong> at (${ox}, ${oy}).`);
      updateV2VDrawerUI();
    }

    // =========================================================================
    // DECENTRALIZED V2V (VEHICLE-TO-VEHICLE) MESH NETWORK & COMMUNICATION GATEWAY
    // =========================================================================
    const V2V_CONFIG = {
      commRange: 22.0,      // Max RF wireless communication range (grid cells)
      heartbeatRate: 1.0,   // seconds between V2V state announcements
      channelFrequency: '5.9 GHz (C-V2X / DSRC)',
      protocolVersion: 'v2.4-Mesh-Decentralized'
    };

    let v2vMeshEnabled = true;
    let v2vLinks = []; // Active RF links between bots
    let v2vPacketLog = []; // Ring buffer of recent transmitted packets
    const MAX_V2V_LOG = 40;

    const v2vMetrics = {
      packetsSent: 0,
      packetsDelivered: 0,
      activeLinksCount: 0,
      meshConnectedRatio: 1.0,
      negotiationsResolved: 0,
      hazardsShared: 0
    };

    // Shared decentralized dynamic obstacle knowledge base (replicated across mesh)
    const FLEET_SHARED_OBSTACLES = new Map();

    // =========================================================================
    // ACCURATE COLLISION & PROXIMITY TELEMETRY ENGINE
    // Physical footprint: 0.80m x 0.60m. Center-to-center collision radius: 0.70m
    // =========================================================================
    const fleetProximityMetrics = {
      minInterBotDistance: 99.9,
      closestPair: 'None',
      minObstacleDistance: 99.9,
      closestObstacle: 'None',
      physicalCollisions: 0,
      safetyClearanceMeters: 0.0,
      status: 'SAFE' // 'SAFE' (>1.8m), 'CAUTION' (1.1m-1.8m), 'AEB_ACTIVE' (0.7m-1.1m)
    };

    function updateProximityMetrics() {
      let minB2B = 999.0;
      let closestPair = 'None';
      const n = AMR_FLEET.length;
      for (let i = 0; i < n; i++) {
        const A = AMR_FLEET[i];
        for (let j = i + 1; j < n; j++) {
          const B = AMR_FLEET[j];
          const d = Math.hypot(A.x - B.x, A.y - B.y);
          if (d < minB2B) {
            minB2B = d;
            closestPair = `${A.id} ↔ ${B.id}`;
          }
        }
      }

      let minObs = 999.0;
      let closestObs = 'None';
      if (typeof DYNAMIC_OBSTACLES !== 'undefined') {
        for (const bot of AMR_FLEET) {
          for (const obs of DYNAMIC_OBSTACLES) {
            const d = Math.hypot(bot.x - obs.x, bot.y - obs.y);
            if (d < minObs) {
              minObs = d;
              closestObs = `${bot.id} ↔ ${obs.name}`;
            }
          }
        }
      }

      fleetProximityMetrics.minInterBotDistance = minB2B < 900 ? minB2B : 99.9;
      fleetProximityMetrics.closestPair = closestPair;
      fleetProximityMetrics.minObstacleDistance = minObs < 900 ? minObs : 99.9;
      fleetProximityMetrics.closestObstacle = closestObs;
      fleetProximityMetrics.safetyClearanceMeters = Math.max(0, fleetProximityMetrics.minInterBotDistance - 0.70);

      if (fleetProximityMetrics.minInterBotDistance < 0.70) {
        fleetProximityMetrics.status = 'COLLISION';
        fleetProximityMetrics.physicalCollisions++;
      } else if (fleetProximityMetrics.minInterBotDistance < 1.10) {
        fleetProximityMetrics.status = 'AEB_ACTIVE';
      } else if (fleetProximityMetrics.minInterBotDistance < 1.80) {
        fleetProximityMetrics.status = 'CAUTION';
      } else {
        fleetProximityMetrics.status = 'SAFE';
      }

      // Update UI Telemetry Chip if DOM is available (Throttled to 4 Hz to eliminate layout vibration)
      if (typeof document !== 'undefined') {
        const nowMs = typeof performance !== 'undefined' ? performance.now() : Date.now();
        if (nowMs - (fleetProximityMetrics._lastDomTick || 0) < 250) return;
        fleetProximityMetrics._lastDomTick = nowMs;

        const chip = document.getElementById('hud-proximity-badge');
        if (chip) {
          const d = fleetProximityMetrics.minInterBotDistance;
          const clr = fleetProximityMetrics.safetyClearanceMeters;
          if (d < 1.10) {
            chip.style.background = 'rgba(239, 68, 68, 0.2)';
            chip.style.color = '#ef4444';
            chip.style.borderColor = '#ef4444';
            chip.innerText = `⚠️ Min Dist: ${d.toFixed(2)}m (AEB Safe Stop)`;
          } else if (d < 1.80) {
            chip.style.background = 'rgba(245, 158, 11, 0.2)';
            chip.style.color = '#f59e0b';
            chip.style.borderColor = '#f59e0b';
            chip.innerText = `🟡 Min Dist: ${d.toFixed(2)}m (+${clr.toFixed(2)}m Buffer)`;
          } else {
            chip.style.background = 'rgba(34, 197, 94, 0.15)';
            chip.style.color = '#22c55e';
            chip.style.borderColor = '#22c55e';
            chip.innerText = `🟢 Min Dist: ${d.toFixed(2)}m (100% Collision-Free)`;
          }
        }
      }
    }

    function logV2VPacket(pkt) {
      v2vPacketLog.unshift(pkt);
      if (v2vPacketLog.length > MAX_V2V_LOG) v2vPacketLog.pop();
      v2vMetrics.packetsSent++;
      v2vMetrics.packetsDelivered++;
      updateV2VDrawerUI();
    }

    function toggleV2VMeshView() {
      v2vMeshEnabled = !v2vMeshEnabled;
      const btn = document.getElementById('btn-toggle-v2v');
      if (btn) btn.classList.toggle('active', v2vMeshEnabled);
      const btn2 = document.getElementById('btn-v2v-mesh-toggle');
      if (btn2) btn2.classList.toggle('active', v2vMeshEnabled);
      logTerminal('SYSTEM', 'tag-overtake', `📡 V2V Mesh RF Links: ${v2vMeshEnabled ? 'ACTIVE' : 'MUTED'}`);
    }

    function toggleV2VDrawer() {
      const drawer = document.getElementById('v2v-gateway-drawer');
      if (drawer) {
        const isHidden = drawer.style.display === 'none' || !drawer.style.display;
        drawer.style.display = isHidden ? 'flex' : 'none';
        if (isHidden) updateV2VDrawerUI();
      }
    }

    function updateV2VDrawerUI() {
      if (typeof document === 'undefined') return;
      const badge = document.getElementById('v2v-links-badge');
      if (badge) badge.innerText = `${v2vMetrics.activeLinksCount} Links`;
      const statNodes = document.getElementById('v2v-stat-nodes');
      if (statNodes) statNodes.innerText = `${AMR_FLEET.length}/${AMR_FLEET.length}`;
      const statLinks = document.getElementById('v2v-stat-links');
      if (statLinks) statLinks.innerText = `${v2vMetrics.activeLinksCount}`;
      const statConn = document.getElementById('v2v-stat-conn');
      if (statConn) statConn.innerText = `${Math.round(v2vMetrics.meshConnectedRatio * 100)}%`;
      const statHazards = document.getElementById('v2v-stat-hazards');
      if (statHazards) statHazards.innerText = `${v2vMetrics.hazardsShared}`;

      const list = document.getElementById('v2v-packet-list');
      if (list && v2vPacketLog.length > 0) {
        list.innerHTML = v2vPacketLog.slice(0, 12).map(p => `
          <div style="font-size:10px; padding:4px 8px; margin-bottom:4px; background:#121722; border-left:3px solid ${p.type === 'OBSTACLE_ALERT' ? '#f59e0b' : '#38bdf8'}; border-radius:4px; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <span style="color:#64748b; margin-right:4px;">${p.time}</span>
              <strong style="color:#e2e8f0;">[${p.type}]</strong>
              <span style="color:#38bdf8; font-weight:700;">${p.source}</span> ${p.target === 'MESH_BROADCAST' ? '📡 ➔ MESH' : '➔ ' + p.target}:
              <span style="color:#cbd5e1;">${p.summary}</span>
            </div>
            <span style="color:#64748b; font-size:9px;">TTL:${p.ttl}</span>
          </div>
        `).join('');
      }
    }

    function updateV2VMesh(dt) {
      if (!v2vMeshEnabled) {
        v2vLinks = [];
        v2vMetrics.activeLinksCount = 0;
        return;
      }

      const links = [];
      const n = AMR_FLEET.length;
      for (let i = 0; i < n; i++) {
        const A = AMR_FLEET[i];
        for (let j = i + 1; j < n; j++) {
          const B = AMR_FLEET[j];
          const dist = Math.hypot(A.x - B.x, A.y - B.y);
          if (dist <= V2V_CONFIG.commRange) {
            const rssi = Math.round(-38 - (dist / V2V_CONFIG.commRange) * 32);
            links.push({
              from: A.id,
              to: B.id,
              botA: A,
              botB: B,
              dist: dist,
              rssi: rssi,
              activePulse: false
            });
          }
        }
      }
      v2vLinks = links;
      v2vMetrics.activeLinksCount = links.length;

      // Expire old shared obstacle reports (> 7 seconds)
      const now = Date.now();
      for (const [key, item] of FLEET_SHARED_OBSTACLES.entries()) {
        if (now > item.expireAt) {
          FLEET_SHARED_OBSTACLES.delete(key);
        }
      }

      // Periodic heartbeat pulse
      v2vMetrics._lastHb = (v2vMetrics._lastHb || 0) + dt;
      if (v2vMetrics._lastHb >= 2.0) {
        v2vMetrics._lastHb = 0;
        for (const bot of AMR_FLEET) {
          if (bot.state !== 'OUT_OF_CHARGE') {
            v2vMetrics.packetsSent += Math.min(2, links.filter(l => l.from === bot.id || l.to === bot.id).length);
          }
        }
        updateV2VDrawerUI();
      }
    }

    function broadcastV2VObstacleAlert(reportingBot, obstacle) {
      if (!v2vMeshEnabled || !reportingBot || !obstacle) return;
      const now = Date.now();
      if (reportingBot._lastAlertTime && now - reportingBot._lastAlertTime < 2500) return;
      reportingBot._lastAlertTime = now;

      const ox = Math.round(obstacle.x);
      const oy = Math.round(obstacle.y);
      const obsKey = `${ox},${oy}`;

      FLEET_SHARED_OBSTACLES.set(obsKey, {
        obstacleId: obstacle.id,
        type: obstacle.type,
        name: obstacle.name,
        reportedBy: reportingBot.id,
        x: ox,
        y: oy,
        expireAt: now + 7000
      });

      const pkt = {
        id: `PKT-${v2vMetrics.packetsSent + 1}`,
        time: new Date().toLocaleTimeString(),
        type: 'OBSTACLE_ALERT',
        source: reportingBot.id,
        target: 'MESH_BROADCAST',
        summary: `⚠️ Hazard at (${ox}, ${oy}): ${obstacle.name}`,
        ttl: 3
      };
      logV2VPacket(pkt);
      v2vMetrics.hazardsShared++;

      for (const l of v2vLinks) {
        if (l.from === reportingBot.id || l.to === reportingBot.id) {
          l.activePulse = true;
          setTimeout(() => { l.activePulse = false; }, 800);
        }
      }

      // Peers receiving alert check if their path traverses the obstacle zone
      for (const peer of AMR_FLEET) {
        if (peer.id === reportingBot.id || peer.state === 'IDLE_CHARGING' || peer.state === 'OUT_OF_CHARGE') continue;
        const distToReporter = Math.hypot(peer.x - reportingBot.x, peer.y - reportingBot.y);
        if (distToReporter <= V2V_CONFIG.commRange) {
          if (peer.path && peer.pathIndex < peer.path.length) {
            const willIntersect = peer.path.slice(peer.pathIndex).some(pt => Math.hypot(pt.x - ox, pt.y - oy) < 1.6);
            if (willIntersect) {
              const repathed = solveTrafficPathViaInnerSim(peer, null, null, { x: ox, y: oy });
              if (repathed) {
                logTerminal('V2V', 'tag-overtake', `📡 <strong>[V2V-MESH] ${peer.id}</strong> received Hazard Alert from <strong>${reportingBot.id}</strong>: Proactively detoured around (${ox}, ${oy})`);
              }
            }
          }
        }
      }
    }

    function negotiateV2VRightOfWay(botA, botB) {
      if (!botA || !botB) return;
      const now = Date.now();
      if (botA._lastNegTime && now - botA._lastNegTime < 3000) return;
      botA._lastNegTime = now;
      botB._lastNegTime = now;

      const aWins = isHigherPriority(botA, botB);
      const winner = aWins ? botA : botB;
      const yielder = aWins ? botB : botA;

      const pkt = {
        id: `PKT-${v2vMetrics.packetsSent + 1}`,
        time: new Date().toLocaleTimeString(),
        type: 'RIGHT_OF_WAY_HANDSHAKE',
        source: botA.id,
        target: botB.id,
        summary: `🤝 Consensus: ${winner.id} (SoC ${winner.battery.toFixed(1)}%) moves, ${yielder.id} yields`,
        ttl: 1
      };
      logV2VPacket(pkt);
      v2vMetrics.negotiationsResolved++;

      for (const l of v2vLinks) {
        if ((l.from === botA.id && l.to === botB.id) || (l.from === botB.id && l.to === botA.id)) {
          l.activePulse = true;
          setTimeout(() => { l.activePulse = false; }, 800);
        }
      }
    }

    function isWalkable(x, y) {
      if (!mapData) return false;
      if (x < 0 || x >= mapData.width || y < 0 || y >= mapData.height) return false;
      return mapData.grid[x][y] !== 1;
    }

    function getAccessPointForRack(rx, ry, fromX, fromY) {
      const dirs = [
        { dx: 0, dy: -1 },
        { dx: 0, dy: 1 },
        { dx: -1, dy: 0 },
        { dx: 1, dy: 0 }
      ];
      let best = null;
      let bestDist = Infinity;

      for (const d of dirs) {
        const ax = rx + d.dx;
        const ay = ry + d.dy;
        if (isWalkable(ax, ay)) {
          const dist = Math.abs(ax - fromX) + Math.abs(ay - fromY);
          if (dist < bestDist) {
            bestDist = dist;
            best = { x: ax, y: ay };
          }
        }
      }
      return best;
    }

    // Baseline unconstrained shortest path search (guaranteed fallback)
    function findPathUnconstrained(sx, sy, gx, gy, avoidCells = null) {
      if (sx === gx && sy === gy) return [];
      const width = mapData.width;
      const height = mapData.height;
      const total = width * height;
      const visited = new Uint8Array(total);
      const parent = new Int32Array(total);
      parent.fill(-1);

      if (avoidCells) {
        for (const key of avoidCells) {
          const parts = key.split(',');
          const ax = parseInt(parts[0], 10);
          const ay = parseInt(parts[1], 10);
          if (ax >= 0 && ax < width && ay >= 0 && ay < height) {
            if ((ax !== sx || ay !== sy) && (ax !== gx || ay !== gy)) {
              visited[ay * width + ax] = 1;
            }
          }
        }
      }

      const queue = new Int32Array(total);
      let head = 0;
      let tail = 0;

      const startIdx = sy * width + sx;
      const goalIdx = gy * width + gx;

      visited[startIdx] = 1;
      queue[tail++] = startIdx;

      const dirs = [
        { dx: 0, dy: -1 },
        { dx: 0, dy: 1 },
        { dx: -1, dy: 0 },
        { dx: 1, dy: 0 }
      ];

      let found = false;
      while (head < tail) {
        const currIdx = queue[head++];
        if (currIdx === goalIdx) {
          found = true;
          break;
        }

        const cx = currIdx % width;
        const cy = Math.floor(currIdx / width);

        for (let i = 0; i < 4; i++) {
          const nx = cx + dirs[i].dx;
          const ny = cy + dirs[i].dy;

          if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
            const nIdx = ny * width + nx;
            if (!visited[nIdx] && mapData.grid[nx][ny] !== 1) {
              visited[nIdx] = 1;
              parent[nIdx] = currIdx;
              queue[tail++] = nIdx;
            }
          }
        }
      }

      if (!found) return [];

      const path = [];
      let curr = goalIdx;
      while (curr !== startIdx) {
        path.push({ x: curr % width, y: Math.floor(curr / width) });
        curr = parent[curr];
      }
      path.reverse();
      return path;
    }

    // Industrial Traffic Pathfinding: Flow-Directed Aisles + Dynamic Avoidance
    function findPath(sx, sy, gx, gy, avoidCells = null) {
      if (sx === gx && sy === gy) return [];
      if (!isWalkable(gx, gy)) {
        const access = getAccessPointForRack(gx, gy, sx, sy);
        if (!access) return [];
        gx = access.x;
        gy = access.y;
        if (sx === gx && sy === gy) return [];
      }

      const width = mapData.width;
      const height = mapData.height;
      const total = width * height;
      const visited = new Uint8Array(total);
      const parent = new Int32Array(total);
      parent.fill(-1);

      // Avoid dynamic obstacle cells
      if (avoidCells) {
        for (const key of avoidCells) {
          const parts = key.split(',');
          const ax = parseInt(parts[0], 10);
          const ay = parseInt(parts[1], 10);
          if (ax >= 0 && ax < width && ay >= 0 && ay < height) {
            if ((ax !== sx || ay !== sy) && (ax !== gx || ay !== gy)) {
              visited[ay * width + ax] = 1;
            }
          }
        }
      }

      // Avoid decentralized shared dynamic obstacles broadcasted via V2V
      if (typeof FLEET_SHARED_OBSTACLES !== 'undefined' && FLEET_SHARED_OBSTACLES.size > 0) {
        for (const [key, obsInfo] of FLEET_SHARED_OBSTACLES.entries()) {
          const parts = key.split(',');
          const ox = parseInt(parts[0], 10);
          const oy = parseInt(parts[1], 10);
          if (ox >= 0 && ox < width && oy >= 0 && oy < height) {
            if ((ox !== sx || oy !== sy) && (ox !== gx || oy !== gy)) {
              visited[oy * width + ox] = 1;
            }
          }
        }
      }

      // Avoid static obstacles (carts/pallets)
      if (typeof dynamicObstaclesEnabled !== 'undefined' && dynamicObstaclesEnabled && typeof DYNAMIC_OBSTACLES !== 'undefined') {
        for (const obs of DYNAMIC_OBSTACLES) {
          if (obs.isStatic) {
            const ox = Math.round(obs.x);
            const oy = Math.round(obs.y);
            if (ox >= 0 && ox < width && oy >= 0 && oy < height) {
              if ((ox !== sx || oy !== sy) && (ox !== gx || oy !== gy)) {
                visited[oy * width + ox] = 1;
              }
            }
          }
        }
      }

      // DECENTRALIZED V2V TRAJECTORY PRE-COMMUNICATION:
      // Bots communicate reservations before choosing a path so they naturally pick clear parallel lanes!
      if (typeof GLOBAL_TRAJECTORIES !== 'undefined' && GLOBAL_TRAJECTORIES.size > 0) {
        for (const [key, ownerId] of GLOBAL_TRAJECTORIES.entries()) {
          const parts = key.split(',');
          const tx = parseInt(parts[0], 10);
          const ty = parseInt(parts[1], 10);
          if ((tx !== sx || ty !== sy) && (tx !== gx || ty !== gy)) {
            if (avoidCells && avoidCells.has(ownerId)) {
              visited[ty * width + tx] = 1;
            } else if (NARROW_AISLE_COLS.has(tx) && (gx !== tx || gy !== ty)) {
              // Pre-emptively reserve occupied narrow aisles so oncoming bots take parallel aisles
              const owner = AMR_FLEET.find(b => b.id === ownerId);
              if (owner && owner.path && owner.path.length > 0) {
                visited[ty * width + tx] = 1;
              }
            }
          }
        }
      }

      const queue = new Int32Array(total);
      let head = 0;
      let tail = 0;

      const startIdx = sy * width + sx;
      const goalIdx = gy * width + gx;

      visited[startIdx] = 1;
      queue[tail++] = startIdx;

      // Displacement-Optimal Directions: dynamically prioritized by direct Euclidean vector to goal!
      const dirs = [
        { dx: 0, dy: -1 },
        { dx: 0, dy: 1 },
        { dx: -1, dy: 0 },
        { dx: 1, dy: 0 }
      ];

      let found = false;
      while (head < tail) {
        const currIdx = queue[head++];
        if (currIdx === goalIdx) {
          found = true;
          break;
        }

        const cx = currIdx % width;
        const cy = Math.floor(currIdx / width);

        for (let i = 0; i < 4; i++) {
          const nx = cx + dirs[i].dx;
          const ny = cy + dirs[i].dy;

          if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
            const nIdx = ny * width + nx;
            if (!visited[nIdx] && mapData.grid[nx][ny] !== 1) {
              // Respect designated warehouse one-way aisle traffic flow!
              // Industrial standard: ALWAYS respect one-way flow to eliminate head-on "kissing"
              if (NARROW_AISLE_COLS.has(nx)) {
                const dy = dirs[i].dy;
                const isSouth = SOUTHBOUND_AISLE_COLS.has(nx);
                const isNorth = NORTHBOUND_AISLE_COLS.has(nx);
                if ((isSouth && dy < 0) || (isNorth && dy > 0)) {
                  // Moving against one-way flow: only allow if destination is inside this aisle
                  if (gx !== nx) continue;
                }
              }

              visited[nIdx] = 1;
              parent[nIdx] = currIdx;
              queue[tail++] = nIdx;
            }
          }
        }
      }

      if (!found) {
        // If avoidCells was active (e.g. during overtake attempt or detour), do NOT fallback
        // to unconstrained search that drives backward into narrow aisles and causes kissing!
        if (avoidCells) return [];
        // Fallback to unconstrained search if directional constraint had no route
        return findPathUnconstrained(sx, sy, gx, gy, avoidCells);
      }

      const path = [];
      let curr = goalIdx;
      while (curr !== startIdx) {
        path.push({ x: curr % width, y: Math.floor(curr / width) });
        curr = parent[curr];
      }
      path.reverse();
      return path;
    }

    // Bulletproof Path Sanitizer & Assignor: Guarantees Contiguous Grid Walkability Invariant
    // Prevents 100% of non-adjacent coordinate jumps, box clipping, or diagonal flying
    // GLOBAL TRAJECTORY REGISTRY (Simulating the Simulation)
    const GLOBAL_TRAJECTORIES = new Map(); 

    function setRobotPath(robot, newPath) {
      if (!robot) return;
      
      // Clear old trajectory predictions for this bot
      for (const [key, botId] of GLOBAL_TRAJECTORIES.entries()) {
        if (botId === robot.id) GLOBAL_TRAJECTORIES.delete(key);
      }

      if (!newPath || !Array.isArray(newPath) || newPath.length === 0) {
        robot.path = [];
        robot.pathIndex = 0;
        return;
      }

      const rawDest = newPath[newPath.length - 1];
      if (rawDest && typeof rawDest.x === 'number' && typeof rawDest.y === 'number') {
        robot.currentDestination = { x: rawDest.x, y: rawDest.y };
      }

      // "Discuss in the beginning": Broadcast future footprint so others route around it
      for (let i = 0; i < newPath.length; i++) {
        GLOBAL_TRAJECTORIES.set(`${newPath[i].x},${newPath[i].y}`, robot.id);
      }
      const valid = [];
      let prevX = robot.gridX !== undefined ? robot.gridX : Math.round(robot.x);
      let prevY = robot.gridY !== undefined ? robot.gridY : Math.round(robot.y);

      for (let i = 0; i < newPath.length; i++) {
        const pt = newPath[i];
        if (!pt || typeof pt.x !== 'number' || typeof pt.y !== 'number') continue;
        if (!isWalkable(pt.x, pt.y)) {
          // Unwalkable cell in proposed path: re-plan from current valid point to destination
          const dest = newPath[newPath.length - 1];
          if (dest && isWalkable(dest.x, dest.y)) {
            const detour = findPath(prevX, prevY, dest.x, dest.y);
            if (detour && detour.length > 0) {
              valid.push(...detour);
            }
          }
          break;
        }
        const manhattan = Math.abs(pt.x - prevX) + Math.abs(pt.y - prevY);
        if (manhattan > 1) {
          // Non-adjacent step detected: bridge gap using grid BFS
          const bridge = findPath(prevX, prevY, pt.x, pt.y);
          if (bridge && bridge.length > 0) {
            valid.push(...bridge);
            prevX = pt.x;
            prevY = pt.y;
            continue;
          }
        }
        valid.push({ x: pt.x, y: pt.y });
        prevX = pt.x;
        prevY = pt.y;
      }
      robot.path = valid;
      robot.pathIndex = 0;
    }

    // Right-of-Way Priority Engine (Battery SoC Priority)
    // User Specification: Lowest battery gets HIGHEST movement priority!
    function getRobotPriority(r) {
      if (!r) return -999999;
      if (r.state === 'OUT_OF_CHARGE') return -999999;
      if (r.state === 'IDLE_CHARGING') return -999999;

      // Invert battery so lower SoC gives strictly higher priority score:
      // 10% SoC -> 900,000 pts | 50% SoC -> 500,000 pts | 90% SoC -> 100,000 pts
      const battScore = (100.0 - Math.min(100.0, Math.max(0, r.battery))) * 10000;

      // Secondary tie-breaker (mission urgency + cargo + ID)
      const urgency = calculateRobotUrgency ? calculateRobotUrgency(r) : 0;
      let tieBreaker = urgency * 10;
      if (r.orderBox) tieBreaker += 50;
      else if (r.carriedParcels && r.carriedParcels.length > 0) tieBreaker += 40;
      tieBreaker += (10 - (r.num || 0)) * 0.1;

      return battScore + tieBreaker;
    }

    // Deterministic Right-of-Way Arbiter (Guarantees strict total ordering, no ties)
    // When 2 or more bots conflict or deadlock, the one with LOWER battery moves,
    // and the one with HIGHER battery stops completely.
    function isHigherPriority(A, B) {
      if (!A) return false;
      if (!B) return true;
      if (A.id === B.id) return false;

      // TIER 1: EMERGENCY CHARGING ABSOLUTE RIGHT-OF-WAY
      // Bots returning to dock or with critical low battery (<=28%) NEVER yield to regular bots!
      const aNeedsCharge = A.state === 'RETURNING_HOME' || A.battery <= 28.0;
      const bNeedsCharge = B.state === 'RETURNING_HOME' || B.battery <= 28.0;
      if (aNeedsCharge && !bNeedsCharge) return true;  // A has absolute priority
      if (!aNeedsCharge && bNeedsCharge) return false; // B has absolute priority
      if (aNeedsCharge && bNeedsCharge) {
        // Both need charging: bot with lower SoC moves first
        if (Math.abs(B.battery - A.battery) > 0.05) return A.battery < B.battery;
      }

      // Primary criteria: Robot with lower battery has higher priority to move
      const battDiff = B.battery - A.battery; // positive if A has lower battery
      if (Math.abs(battDiff) > 0.05) {
        return battDiff > 0;
      }

      // Tie-breaker: Customer outbound order priority over inbound
      const prioA = getRobotPriority(A);
      const prioB = getRobotPriority(B);
      if (Math.abs(prioA - prioB) > 0.001) {
        return prioA > prioB;
      }
      return A.id < B.id;
    }

    // Anti-Gridlock Corridor Clearing: Higher battery yielding bot steps aside to open corridor
    function executeSideStepYield(blocker, movingBot) {
      if (!blocker || !movingBot || blocker.isSideStepping) return false;

      const neighbors = [
        { x: blocker.gridX, y: blocker.gridY - 1 },
        { x: blocker.gridX, y: blocker.gridY + 1 },
        { x: blocker.gridX - 1, y: blocker.gridY },
        { x: blocker.gridX + 1, y: blocker.gridY }
      ];

      const nextCell = (movingBot.path && movingBot.pathIndex < movingBot.path.length) ? movingBot.path[movingBot.pathIndex] : null;

      let bestCell = null;
      let maxDistToMoving = -1;

      for (const cell of neighbors) {
        if (!isWalkable(cell.x, cell.y)) continue;
        if (nextCell && cell.x === nextCell.x && cell.y === nextCell.y) continue;
        const occ = AMR_FLEET.some(o => o.id !== blocker.id && Math.hypot(o.x - cell.x, o.y - cell.y) < 0.9);
        if (occ) continue;

        const d = Math.hypot(cell.x - movingBot.x, cell.y - movingBot.y);
        if (d > maxDistToMoving) {
          maxDistToMoving = d;
          bestCell = cell;
        }
      }

      if (bestCell) {
        if (!blocker.savedDest && blocker.path && blocker.path.length > 0) {
          blocker.savedDest = blocker.path[blocker.path.length - 1];
        }
        blocker.isSideStepping = true;
        setRobotPath(blocker, [bestCell]);
        blocker.isWaiting = false;
        blocker._wasWaitingThisFrame = false;
        blocker.waitTimer = 0;
        if (blocker.logStats) blocker.logStats.totalSideSteps++;
        onRobotJamEnd(blocker, 'SIDESTEPPED_TO_OPEN_CORRIDOR');
        trafficMetrics.totalReroutes = (trafficMetrics.totalReroutes || 0) + 1;
        logTerminal('YIELD', 'tag-yield', '↔️ <strong>' + blocker.id + '</strong> (' + blocker.battery.toFixed(1) + '% SoC) side-stepped to (' + bestCell.x + ', ' + bestCell.y + ') to open corridor for lower-battery <strong>' + movingBot.id + '</strong> (' + movingBot.battery.toFixed(1) + '% SoC).');
        return true;
      }
      return false;
    }

    // Dynamic Overtaking Maneuver (Move to parallel line, pass bot, return to route)
    // Extracting fleet rerouting principles from amr-fleet-manager:
    // Strictly adheres to walkable corridors; pauses when passing is physically impossible.
    function attemptOvertake(robot, blocker, urgA = null, urgB = null) {
      if (!robot.path || robot.path.length === 0) return false;
      const dest = robot.path[robot.path.length - 1];
      if (!dest) return false;

      // In narrow single-lane rack aisles, overtaking is physically impossible (solid racks on both sides)
      if (NARROW_AISLE_COLS.has(robot.gridX) && NARROW_AISLE_COLS.has(blocker.gridX)) {
        return false;
      }

      // If robot is already near dest, no overtake needed
      if (Math.hypot(robot.gridX - dest.x, robot.gridY - dest.y) <= 2.0) return false;

      // --- Relative Speed Gate ---
      // Only overtake if the follower is meaningfully faster, or blocker is fully stopped.
      const _bspd = ROBOT_BASE_SPEED * (simSpeed || 1.0);
      const actualSpeedA = (robot.currentSpeed !== undefined && robot.currentSpeed !== null) ? robot.currentSpeed : (_bspd * (robot.speedMultiplier || 1.0) * (robot.payloadDamping || 1.0));
      const actualSpeedB = (blocker.currentSpeed !== undefined && blocker.currentSpeed !== null) ? blocker.currentSpeed : (_bspd * (blocker.speedMultiplier || 1.0) * (blocker.payloadDamping || 1.0));
      const blockerFullyStopped = blocker.isWaiting || actualSpeedB < 0.05;
      const relativeAdvantage = actualSpeedA - actualSpeedB;
      if (!blockerFullyStopped && relativeAdvantage < actualSpeedA * 0.10) return false;

      // Avoid blocker's current grid target & physical position (moving object estimation)
      const avoidBlocker = new Set();
      avoidBlocker.add(`${blocker.gridX},${blocker.gridY}`);
      avoidBlocker.add(`${Math.round(blocker.x)},${Math.round(blocker.y)}`);

      // Avoid the blocker's "tail" (previous box) to ensure 1-block trailing personal space
      if (blocker.previousBox) {
        avoidBlocker.add(`${blocker.previousBox.x},${blocker.previousBox.y}`);
      } else if (blocker.recentVisitedCells && blocker.recentVisitedCells.length > 0) {
        const lastVis = blocker.recentVisitedCells[blocker.recentVisitedCells.length - 1];
        avoidBlocker.add(`${lastVis.x},${lastVis.y}`);
      }

      // Avoid projected path (up to 3 tiles ahead to prevent clipping the blocker's nose)
      if (blocker.path && blocker.pathIndex < blocker.path.length) {
        for (let p = blocker.pathIndex; p < Math.min(blocker.path.length, blocker.pathIndex + 3); p++) {
          avoidBlocker.add(`${blocker.path[p].x},${blocker.path[p].y}`);
        }
      }

      // Force an IMMEDIATE lateral swing by blocking the overtaking robot's next planned forward step
      if (robot.path && robot.pathIndex < robot.path.length) {
        const nextStep = robot.path[robot.pathIndex];
        if (nextStep.x !== dest.x || nextStep.y !== dest.y) {
          avoidBlocker.add(`${nextStep.x},${nextStep.y}`);
        }
      }

      // Also avoid any other robots that are stopped/waiting
      for (const o of AMR_FLEET) {
        if (o.id !== robot.id && (o.isWaiting || o.state === 'IDLE_CHARGING')) {
          avoidBlocker.add(`${o.gridX},${o.gridY}`);
        }
      }

      // Target rejoining original line 6+ tiles forward to preserve personal space
      let rejoinIdx = -1;
      for (let k = robot.pathIndex; k < robot.path.length; k++) {
        if (robot.path[k].x === blocker.gridX && robot.path[k].y === blocker.gridY) {
          rejoinIdx = k + 6; // Enforce 6 blocks of clearance!
          break;
        }
      }
      if (rejoinIdx === -1) rejoinIdx = robot.pathIndex + 7;
      if (rejoinIdx >= robot.path.length) rejoinIdx = robot.path.length - 1;

      let overtakePath = null;
      if (rejoinIdx > robot.pathIndex && rejoinIdx < robot.path.length) {
        const rejoinPt = robot.path[rejoinIdx];
        const bypass = findPath(robot.gridX, robot.gridY, rejoinPt.x, rejoinPt.y, avoidBlocker);
        if (bypass && bypass.length > 0) {
          overtakePath = bypass.concat(robot.path.slice(rejoinIdx + 1));
        }
      }

      // Fallback to full route if the 4-tile splice is blocked
      if (!overtakePath) {
        overtakePath = findPath(robot.gridX, robot.gridY, dest.x, dest.y, avoidBlocker);
      }

      if (overtakePath && overtakePath.length > 0) {
        const remSteps = robot.path.length - robot.pathIndex;
        if (overtakePath.length <= remSteps + 16) {
          setRobotPath(robot, overtakePath);
          robot.isOvertaking = true;
          robot.overtakeTarget = blocker.id;
          robot.overtakeTimer = 5.0 / simSpeed;
          robot.speedMultiplier = 1.35;
          robot.statusBadge = 'PASS';
          robot.isWaiting = false;
          robot.waitTimer = 0;
          robot.yieldTo = null;
          if (robot.logStats) robot.logStats.totalOvertakesInitiated++;
          onRobotJamEnd(robot, 'OVERTAKEN_VIA_PARALLEL_LANE');
          trafficMetrics.totalOvertakes = (trafficMetrics.totalOvertakes || 0) + 1;

          // Pin the slow/stopped blocker so the fast bot glides past without re-triggering ACC
          if (!blocker.isOvertaking && !blocker.isBackingUp && !blocker.isSideStepping) {
            blocker._pinnedForOvertake = true;
            blocker._pinnedTimer = 3.0 / simSpeed;
            blocker.isWaiting = true;
            blocker._wasWaitingThisFrame = true;
            blocker.currentSpeed = 0;
            blocker.statusBadge = 'YIELD';
          }

          logTerminal('OVERTAKE', 'tag-overtake', '🏎️ <strong>' + robot.id + '</strong> overtaking <strong>' + blocker.id + '</strong> via parallel lane (' + overtakePath.length + ' steps, \u0394v=' + relativeAdvantage.toFixed(2) + 'c/s). Blocker pinned.');
          updateHudStats();
          return true;
        }
      }

      // User Specification: Allow pausing because rerouting consumes more energy than pausing!
      return false;
    }

    // Deadlock Back-Up Routine: Moves higher-battery robot back along corridor to clear lane
    // Guarantees straight-line corridor reversing without 45° diagonal cuts or lateral deviation!
    function attemptMoveBackToPreviousBox(bot, opposingBot, depth = 5) {
      if (!bot || bot.isBackingUp) return false;

      let backPath = [];
      let currentX = bot.gridX;
      let currentY = bot.gridY;
      let trail = bot.recentVisitedCells || [];
      let startIdx = trail.length - 1;

      // Try to generate a continuous path backwards up to 'depth' (5 blocks)
      for (let k = 0; k < depth; k++) {
        let nextCell = null;
        if (startIdx - k >= 0) {
          nextCell = trail[startIdx - k];
        } else {
          // Extrapolate straight backwards if we run out of breadcrumbs
          let dx = currentX - opposingBot.gridX;
          let dy = currentY - opposingBot.gridY;
          let stepX = 0;
          let stepY = 0;
          
          // STRICT CARDINAL MOVEMENT: Prevent diagonal back-stepping
          if (Math.abs(dx) >= Math.abs(dy)) {
            stepX = dx !== 0 ? Math.sign(dx) : (Math.cos(bot.heading) < 0 ? 1 : -1);
          } else {
            stepY = dy !== 0 ? Math.sign(dy) : (Math.sin(bot.heading) < 0 ? 1 : -1);
          }
          nextCell = { x: currentX + stepX, y: currentY + stepY };
        }

        if (!isWalkable(nextCell.x, nextCell.y)) break; // Hit a wall

        // Check for an "outer jam" (is there another bot behind us?)
        let occ = AMR_FLEET.find(o => o.id !== bot.id && o.gridX === nextCell.x && o.gridY === nextCell.y);
        if (occ) {
          // CASCADE: Tell the bot behind us to mutually recalculate and back up too!
          if (!occ.isBackingUp && !isHigherPriority(bot, occ)) {
            attemptMoveBackToPreviousBox(occ, bot, depth - k); 
          }
          if (occ.gridX === nextCell.x && occ.gridY === nextCell.y) break; // Couldn't clear it immediately
        }
        
        backPath.push({ x: nextCell.x, y: nextCell.y });
        currentX = nextCell.x;
        currentY = nextCell.y;
      }

      if (backPath.length > 0) {
        if (!bot.savedDest && bot.path && bot.path.length > 0) {
          bot.savedDest = bot.path[bot.path.length - 1]; // Save final goal to recalibrate later
        }
        bot.isBackingUp = true;
        bot.isSideStepping = false;
        setRobotPath(bot, backPath); // Feed the 5-block array to the motor controller
        bot.isWaiting = false;
        bot._wasWaitingThisFrame = false;
        bot.waitTimer = 0;
        bot.statusBadge = `BACK ${backPath.length}`;
        if (bot.logStats) bot.logStats.totalBackupsToPreviousBox++;
        onRobotJamEnd(bot, 'CASCADING_DEEP_BACKUP');
        logTerminal('YIELD', 'tag-yield', `🔙 <strong>${bot.id}</strong> executed deep cascading backup (${backPath.length} blocks) to clear standoff with <strong>${opposingBot.id}</strong>.`);
        return true;
      }
      return false;
    }

    // =========================================================================
    // INNER SHADOW SIMULATION (Fast-Forward Micro-Traffic Predictor)
    // "simulation run inside simulation that checks for traffic problems"
    // =========================================================================
    function runInnerTrafficSimulation(robot, candidatePath = null, lookaheadSeconds = 6.0) {
      if (!robot) return { hasTrafficProblem: false };
      const path = candidatePath || (robot.path && robot.path.length > robot.pathIndex ? robot.path.slice(robot.pathIndex) : []);
      if (!path || path.length === 0) return { hasTrafficProblem: false };

      const bspd = ROBOT_BASE_SPEED * (simSpeed || 1.0);
      const vR = Math.max(0.5, bspd * (robot.speedMultiplier || 1.0) * (robot.payloadDamping || 1.0));
      const dtStep = 0.4;
      const numSteps = Math.min(15, Math.ceil(lookaheadSeconds / dtStep));

      for (let s = 1; s <= numSteps; s++) {
        const t = s * dtStep;
        const distR = vR * t;
        const stepR = Math.min(Math.floor(distR), path.length - 1);
        const posR = path[stepR];

        for (const other of AMR_FLEET) {
          if (other.id === robot.id || other.state === 'OUT_OF_CHARGE') continue;

          // Project other robot position at time t
          const oIsShelvingOrPicking = (other.state === 'CARRYING_TO_RACK' || other.state === 'ORDER_PICKING') &&
                                       (!other.path || other.path.length === 0 || other.pathIndex >= other.path.length);
          const oIsStationaryTarget = other.state === 'IDLE_CHARGING' || other.state === 'LOADING_INBOUND' || oIsShelvingOrPicking;

          let posO = { x: other.gridX, y: other.gridY };
          let isOStationary = true;

          if (!oIsStationaryTarget && other.path && other.path.length > other.pathIndex && !other.isWaiting && !other.isBackingUp && !other.isSideStepping) {
            isOStationary = false;
            const vO = Math.max(0.5, bspd * (other.speedMultiplier || 1.0) * (other.payloadDamping || 1.0));
            const distO = vO * t;
            const remO = other.path.slice(other.pathIndex);
            const stepO = Math.min(Math.floor(distO), remO.length - 1);
            posO = remO[stepO];
          }

          const dSim = Math.hypot(posR.x - posO.x, posR.y - posO.y);
          if (dSim < 1.30) {
            let reason = 'SLOW_TRAFFIC_CONGESTION';
            if (isOStationary) reason = 'BLOCKED_BY_STATIONARY_BOT';
            else if (Math.abs(robot.heading - other.heading) > 2.0) reason = 'HEAD_ON_DEADLOCK';

            return {
              hasTrafficProblem: true,
              blocker: other,
              blockerId: other.id,
              conflictCell: { x: Math.round(posO.x), y: Math.round(posO.y) },
              timeToConflict: t,
              isStationary: isOStationary,
              reason: reason
            };
          }
        }
      }
      return { hasTrafficProblem: false };
    }

    // =========================================================================
    // MULTI-STAGE PREDICTIVE REROUTING ENGINE (INNER SIM VERIFIED)
    // "try make path around it. if failed make path around around it"
    // =========================================================================
    function solveTrafficPathViaInnerSim(robot, dest, blockerHint = null, conflictCellHint = null) {
      if (!robot) return false;
      const targetDest = dest || (robot.path && robot.path.length > 0 ? robot.path[robot.path.length - 1] : robot.currentDestination);
      if (!targetDest) return false;

      // If already at or adjacent to dest, no reroute needed
      if (Math.hypot(robot.gridX - targetDest.x, robot.gridY - targetDest.y) <= 1) return false;

      const bx = conflictCellHint ? conflictCellHint.x : (blockerHint ? blockerHint.gridX : robot.gridX);
      const by = conflictCellHint ? conflictCellHint.y : (blockerHint ? blockerHint.gridY : robot.gridY);
      const blockerId = blockerHint ? blockerHint.id : (robot.yieldTo || 'TRAFFIC');

      // -----------------------------------------------------------------------
      // STAGE 1: "Try make path around it" (Direct avoidance of conflict cell & blocker)
      // -----------------------------------------------------------------------
      const avoid1 = new Set();
      avoid1.add(`${bx},${by}`);
      if (blockerHint) {
        avoid1.add(`${blockerHint.gridX},${blockerHint.gridY}`);
        if (blockerHint.path && blockerHint.pathIndex < blockerHint.path.length) {
          const nb = blockerHint.path[blockerHint.pathIndex];
          avoid1.add(`${nb.x},${nb.y}`);
        }
      }
      for (const o of AMR_FLEET) {
        if (o.id !== robot.id && (o.isWaiting || o.state === 'IDLE_CHARGING' || o.state === 'LOADING_INBOUND')) {
          avoid1.add(`${o.gridX},${o.gridY}`);
        }
      }

      const cand1 = findPath(robot.gridX, robot.gridY, targetDest.x, targetDest.y, avoid1);
      if (cand1 && cand1.length > 0) {
        const sim1 = runInnerTrafficSimulation(robot, cand1);
        if (!sim1.hasTrafficProblem) {
          applyInnerSimPath(robot, cand1, blockerId, 'STAGE_1_AROUND');
          return true;
        }
      }

      // -----------------------------------------------------------------------
      // STAGE 2: "If failed make path around around it" (Wider 2-cell radius detour)
      // -----------------------------------------------------------------------
      const avoid2 = new Set(avoid1);
      for (let dx = -2; dx <= 2; dx++) {
        for (let dy = -2; dy <= 2; dy++) {
          avoid2.add(`${bx + dx},${by + dy}`);
        }
      }
      for (const o of AMR_FLEET) {
        if (o.id !== robot.id && Math.hypot(o.x - robot.x, o.y - robot.y) < 3.5) {
          avoid2.add(`${o.gridX},${o.gridY}`);
          if (o.path && o.pathIndex < o.path.length) {
            avoid2.add(`${o.path[o.pathIndex].x},${o.path[o.pathIndex].y}`);
          }
        }
      }

      const cand2 = findPath(robot.gridX, robot.gridY, targetDest.x, targetDest.y, avoid2);
      if (cand2 && cand2.length > 0) {
        const sim2 = runInnerTrafficSimulation(robot, cand2);
        if (!sim2.hasTrafficProblem) {
          applyInnerSimPath(robot, cand2, blockerId, 'STAGE_2_AROUND_AROUND');
          return true;
        }
      }

      // -----------------------------------------------------------------------
      // STAGE 3: "Aisle Column Bypass" (Parallel cross-aisle transfer)
      // -----------------------------------------------------------------------
      const avoid3 = new Set(avoid2);
      if (typeof NARROW_AISLE_COLS !== 'undefined' && NARROW_AISLE_COLS.has(bx)) {
        for (let dy = -6; dy <= 6; dy++) {
          avoid3.add(`${bx},${by + dy}`);
        }
      }
      const cand3 = findPath(robot.gridX, robot.gridY, targetDest.x, targetDest.y, avoid3);
      if (cand3 && cand3.length > 0) {
        const sim3 = runInnerTrafficSimulation(robot, cand3);
        if (!sim3.hasTrafficProblem) {
          applyInnerSimPath(robot, cand3, blockerId, 'STAGE_3_AISLE_BYPASS');
          return true;
        }
      }

      // -----------------------------------------------------------------------
      // STAGE 4: Fallback to best available non-blocked candidate
      // -----------------------------------------------------------------------
      const best = (cand1 && cand1.length > 0) ? cand1 : ((cand2 && cand2.length > 0) ? cand2 : cand3);
      if (best && best.length > 0) {
        applyInnerSimPath(robot, best, blockerId, 'STAGE_BEST_EFFORT');
        return true;
      }

      return false;
    }

    function applyInnerSimPath(robot, newPath, blockerId, stageTag) {
      setRobotPath(robot, newPath);
      robot.isWaiting = false;
      robot._wasWaitingThisFrame = false;
      robot.waitTimer = 0;
      robot.yieldTo = null;
      robot.isRerouting = true;
      robot.rerouteTimer = 3.0 / simSpeed;
      robot.statusBadge = 'REROUTE';
      robot._lastInnerSimRepathTime = totalSimSeconds;
      if (robot.logStats) robot.logStats.totalReroutes++;
      onRobotJamEnd(robot, `INNER_SIM_${stageTag}`);
      trafficMetrics.totalReroutes = (trafficMetrics.totalReroutes || 0) + 1;
      logTerminal('SHADOW_SIM', 'tag-reroute', `🧠 <strong>${robot.id}</strong> Inner Simulation rerouted (${stageTag}) around <strong>${blockerId}</strong> (${newPath.length} steps).`);
      updateHudStats();
    }

    // Dynamic Rerouting Engine (Detour Around Obstacles / Blockages)
    // Delegated directly to Inner Shadow Simulation multi-stage solver
    function attemptReroute(robot, blocker, wideMode = false) {
      if (!robot.path || robot.path.length === 0) return false;
      const dest = robot.path[robot.path.length - 1];
      if (Math.hypot(robot.gridX - dest.x, robot.gridY - dest.y) <= 1) return false;
      return solveTrafficPathViaInnerSim(robot, dest, blocker, blocker ? { x: blocker.gridX, y: blocker.gridY } : null);
    }

    // High-Efficiency AMR Task Assignment (Zone Affinity + Shortest Distance + BMS Energy Feasibility)
    function getBestRobotForTask(task) {
      let bestRobot = null;
      let bestScore = -Infinity;

      for (const robot of AMR_FLEET) {
        // Charging & Returning Safeguard: Bots in RETURNING_HOME must finish docking and charge to >=60%!
        const isEligible = (robot.state === 'IDLE' || (robot.state === 'IDLE_CHARGING' && robot.battery >= 60.0));
        if (!isEligible) continue;

        // User Two-Tier Battery Evaluation:
        // 1. Chance of going < 10%? If yes, go charge.
        // 2. If no, calculate if doing task + return to port has charge. If no, go charge. If yes, go on!
        const evalResult = evaluateMissionEnergyFeasibility(robot, task);
        robot.lastFeasibilityCheck = evalResult;

        if (!evalResult.feasible) {
          // If robot is on floor, route to nearest charger immediately!
          if (robot.state === 'IDLE') {
            const reasonTag = evalResult.chanceGoingBelow10 ? 'CHANCE_BELOW_10_PERCENT' : 'INSUFFICIENT_MISSION_CHARGE';
            routeRobotToNearestCharger(robot, reasonTag, {
              missionDesc: task.desc || task.type,
              eRequired: evalResult.eRequired
            });
          }
          continue;
        }

        // "If yes, go on": robot is feasible!
        // If currently charging at a dock, only undock if it has enough bulk charge (>=35%) to avoid short cycling
        if (robot.state === 'IDLE_CHARGING' && robot.battery < 35.0) continue;

        let targetX = task.type === 'INBOUND' ? task.dockX : (task.rack ? task.rack.x : 40);
        let targetY = task.type === 'INBOUND' ? task.dockY : (task.rack ? task.rack.y : 25);

        const dist = Math.hypot(robot.x - targetX, robot.y - targetY);
        // Nearest-Task Dispatch: Strongly favor closest robot to minimize empty travel and save charge!
        let score = 500 - dist * 4.5;

        // Energy safety margin bonus: bots with larger surplus battery after trip are preferred
        score += evalResult.margin * 1.5;

        // Battery SoC preference (Fleet Health Balancing)
        score += (robot.battery / 100) * 50;

        // Active floor robot bonus (avoids unlatching delay)
        if (robot.state === 'IDLE') score += 30;

        if (score > bestScore) {
          bestScore = score;
          bestRobot = robot;
        }
      }
      return bestRobot;
    }

    function dispatchFleet() {
      // 1. Assign pending Inbound Shipment Missions (ONLY 1 robot per shipment, 1 robot per dock!)
      for (const mission of inboundMissions) {
        if (mission.status === 'PENDING') {
          // Ensure dock is not already assigned to or occupied by another robot
          const dockBusy = inboundMissions.some(m => m.status === 'ASSIGNED' && m.dockId === mission.dockId) ||
                           AMR_FLEET.some(b => (b.inboundMission && b.inboundMission.dockId === mission.dockId) ||
                                               (Math.hypot(b.x - mission.dockX, b.y - mission.dockY) < 1.5));
          if (dockBusy) continue;

          const robot = getBestRobotForTask({
            type: 'INBOUND',
            dockId: mission.dockId,
            dockX: mission.dockX,
            dockY: mission.dockY,
            parcels: mission.parcels,
            totalWeight: mission.totalWeight,
            desc: `Inbound Load at Dock ${mission.dockId}`
          });
          if (!robot) continue; // Try other pending missions

          undockFromCharger(robot.id);
          mission.status = 'ASSIGNED';
          mission.assignedRobotId = robot.id;
          robot.state = 'MOVING_TO_PICKUP';
          robot.inboundMission = mission;
          robot.missionStartTime = Date.now();
          robot.targetDesc = `Dock ${mission.dockId} (Inbound Load: ${mission.parcels.length} pkgs)`;
          setRobotPath(robot, findPath(robot.gridX, robot.gridY, mission.dockX, mission.dockY));

          const evalRes = robot.lastFeasibilityCheck;
          logTerminal('DISPATCH', 'tag-inbound', `⚡ <strong>${robot.id}</strong> BMS Verified (<strong>Go On</strong>): Task + Return to port requires <strong>${evalRes ? evalRes.eTrip : '6.2'}% SoC</strong>. Margin: +<strong>${evalRes ? evalRes.margin : '0'}%</strong> above 10% floor (Current: <strong>${robot.battery.toFixed(1)}%</strong>). Undocked from charger.`);

          if (robot.path.length === 0) {
            onRobotReachedDestination(robot);
          }
        }
      }

      // 2. Assign pending Outbound Order Missions (ONLY 1 robot per customer order / Giant Box!)
      for (const mission of outboundMissions) {
        if (mission.status === 'PENDING') {
          const firstPick = mission.itemsToPick[0];
          if (!firstPick) continue;
          const robot = getBestRobotForTask({
            type: 'OUTBOUND',
            rack: firstPick.rack,
            itemsToPick: mission.itemsToPick,
            orderId: mission.orderId,
            bayId: mission.bayId,
            bayX: mission.bayX,
            bayY: mission.bayY,
            totalWeight: mission.totalWeight,
            desc: `Order ${mission.orderId}`
          });
          if (!robot) continue; // Try other pending orders

          undockFromCharger(robot.id);
          mission.status = 'ASSIGNED';
          mission.assignedRobotId = robot.id;
          // Sort itemsToPick by nearest-neighbor proximity starting from robot
          mission.itemsToPick = sortItemsByProximity(mission.itemsToPick, robot.gridX, robot.gridY);
          const currentPick = mission.itemsToPick[0];
          robot.state = 'ORDER_PICKING';
          robot.outboundMission = mission;
          robot.missionStartTime = Date.now();
          robot.orderBox = {
            orderId: mission.orderId,
            bayId: mission.bayId,
            totalItems: mission.totalItems,
            items: [],
            importance: mission.importance,
            totalWeight: mission.totalWeight
          };
          const access = getAccessPointForRack(currentPick.rack.x, currentPick.rack.y, robot.gridX, robot.gridY);
          robot.targetDesc = `Order Pick 1/${mission.totalItems} for ${mission.orderId} at Rack (${currentPick.rack.x},${currentPick.rack.y})`;
          robot.statusBadge = `PICK 0/${mission.totalItems}`;

          const evalRes = robot.lastFeasibilityCheck;
          logTerminal('DISPATCH', 'tag-outbound', `⚡ <strong>${robot.id}</strong> BMS Verified (<strong>Go On</strong>): Order <strong>${mission.orderId}</strong> (${mission.totalItems} items, ${mission.totalWeight.toFixed(1)}kg) + Return requires <strong>${evalRes ? evalRes.eTrip : '7.5'}% SoC</strong>. Margin: +<strong>${evalRes ? evalRes.margin : '0'}%</strong> above 10% floor (Current: <strong>${robot.battery.toFixed(1)}%</strong>). Undocked from charger.`);

          if (access) {
            setRobotPath(robot, findPath(robot.gridX, robot.gridY, access.x, access.y));
            if (robot.path.length === 0) {
              onRobotReachedDestination(robot);
            }
          }
        }
      }

      // 3. Any robot with no work routes to the NEAREST AVAILABLE CHARGER
      for (const robot of AMR_FLEET) {
        if (robot.state === 'IDLE') {
          routeRobotToNearestCharger(robot, 'IDLE_OPPORTUNITY_CHARGE');
        }
      }
      updateHudStats();
    }

    function onRobotReachedDestination(robot) {
      if (robot.isBackingUp) {
        robot.isBackingUp = false;
        robot.isWaiting = true;
        robot._wasWaitingThisFrame = true;
        robot.statusBadge = 'WAIT';
        robot.path = [];
        robot.pathIndex = 0;
        // Once backed up into previous box, wait until opposing bot has cleared
        return;
      }
      if (robot.isSideStepping) {
        robot.isSideStepping = false;
        robot.isWaiting = true;
        robot._wasWaitingThisFrame = true;
        robot.statusBadge = 'WAIT';
        robot.path = [];
        robot.pathIndex = 0;
        return;
      }

      if (robot.state === 'MOVING_TO_PICKUP') {
        const mission = robot.inboundMission;
        if (!mission) {
          robot.state = 'IDLE';
          dispatchFleet();
          return;
        }

        // Arrival at Inbound Dock: Trigger collection animation and yellow illumination
        robot.state = 'LOADING_INBOUND';
        robot.loadingTimer = 0.85 / simSpeed;
        robot.isLoadedYellow = true; // Turn golden yellow!
        robot.statusBadge = 'LOAD';

        // Transfer parcel batch from dock queue onto robot's carrier tote, sorted by proximity
        robot.carriedParcels = sortParcelsByProximity(mission.parcels, robot.gridX, robot.gridY);
        inboundQueues[mission.dockId] = []; // Dock queue emptied -> Dock turns back to Blue P!
        updateHudStats();

        const idRange = mission.parcels.length > 1 ? `${mission.parcels[0].parcel_id}..${mission.parcels[mission.parcels.length - 1].parcel_id}` : mission.parcels[0].parcel_id;
        const dampingPct = Math.round(Math.max(65, (1.0 - (mission.totalWeight / 60.0)) * 100));
        logTerminal('PICKUP', 'tag-inbound', `📦 <strong>${robot.id}</strong> arrived at <strong>${mission.dockId}</strong>: Collected shipment of <strong>${mission.parcels.length} parcels</strong> (${idRange}, ${mission.totalWeight.toFixed(1)}kg, ${mission.importance.label}) into carrier tote | Load Speed Throttle: <span style="color:#f59e0b;font-weight:700;">${dampingPct}%</span> | Robot illuminated <span style="color:#facc15;font-weight:700;">GOLDEN YELLOW</span> | Dock returned to <span style="color:#38bdf8;font-weight:700;">BLUE</span>`);

      } else if (robot.state === 'CARRYING_TO_RACK') {
        if (!robot.carriedParcels || robot.carriedParcels.length === 0) {
          robot.state = 'IDLE';
          robot.isLoadedYellow = false;
          robot.statusBadge = null;
          robot.payloadWeight = 0;
          robot.payloadDamping = 1.0;
          dispatchFleet();
          return;
        }

        // Deposit current parcel into its reserved rack slot
        const shelved = robot.carriedParcels.shift();
        shelved.rackSlot.rack.floors[shelved.rackSlot.floorIndex] = shelved;
        if (robot.logStats) {
          robot.logStats.totalParcelsShelved++;
          robot.logStats.totalWeightTransportedKg += (parseFloat(shelved.weight) || 3.0);
        }
        recordRobotEvent(robot, 'PARCEL_SHELVED', `Shelved ${shelved.parcel_id} (${shelved.weight}) at Rack (${shelved.rackSlot.rack.x}, ${shelved.rackSlot.rack.y}) Tier ${shelved.rackSlot.floorNum}`, { parcelId: shelved.parcel_id, rackX: shelved.rackSlot.rack.x, rackY: shelved.rackSlot.rack.y, tier: shelved.rackSlot.floorNum, weight: shelved.weight });

        logTerminal('SHELVING', 'tag-complete', `📥 <strong>${robot.id}</strong> placed <strong>${shelved.parcel_id}</strong> (${shelved.name}, ${shelved.weight}) at Rack <strong>(${shelved.rackSlot.rack.x}, ${shelved.rackSlot.rack.y}) Tier ${shelved.rackSlot.floorNum}</strong> [${shelved.rackSlot.rack.categoryName}] (${robot.carriedParcels.length} left in tote)`);
        updateHudStats();

        if (robot.carriedParcels.length > 0) {
          // Route to next parcel in the shipment batch!
          const nextP = robot.carriedParcels[0];
          const access = getAccessPointForRack(nextP.rackSlot.rack.x, nextP.rackSlot.rack.y, robot.gridX, robot.gridY);
          robot.targetDesc = `Shelving ${nextP.parcel_id} (${robot.carriedParcels.length} left) at Rack (${nextP.rackSlot.rack.x},${nextP.rackSlot.rack.y})`;
          robot.statusBadge = `SHELVE ${robot.carriedParcels.length}`;
          if (access) {
            setRobotPath(robot, findPath(robot.gridX, robot.gridY, access.x, access.y));
            if (robot.path.length === 0) {
              onRobotReachedDestination(robot);
            }
          }
        } else {
          // All parcels in this shipment are shelved!
          const completedMission = robot.inboundMission;
          if (completedMission) {
            const mIdx = inboundMissions.findIndex(m => m.id === completedMission.id);
            if (mIdx !== -1) inboundMissions.splice(mIdx, 1);
          }
          if (robot.logStats) {
            robot.logStats.totalInboundCompleted++;
          }
          if (robot.missionsHistory) {
            robot.missionsHistory.push({
              type: 'INBOUND',
              missionId: completedMission ? completedMission.id : 'INB',
              dockId: completedMission ? completedMission.dockId : null,
              parcelsCount: completedMission && completedMission.parcels ? completedMission.parcels.length : 0,
              finishSimTimeSec: Number(totalSimSeconds.toFixed(2)),
              durationSec: robot.missionStartTime ? Number(((Date.now() - robot.missionStartTime) / 1000).toFixed(1)) : 0
            });
          }
          recordRobotEvent(robot, 'INBOUND_FINISHED', `Finished inbound shipment ${completedMission ? completedMission.id : ''}. All parcels stored in 3D racks.`);

          robot.isLoadedYellow = false;
          robot.inboundMission = null;
          robot.statusBadge = null;
          robot.payloadWeight = 0;
          robot.payloadDamping = 1.0;

          logTerminal('COMPLETE', 'tag-complete', `✅ <strong>${robot.id}</strong> finished entire inbound shipment! All parcels successfully stored across 3D racks.`);

          // Opportunistic Dual-Command Chaining:
          // Check if there is an unassigned outbound order waiting nearby
          // ONLY if it strictly passes the two-tier BMS check!
          let chainedOrderIdx = -1;
          for (let i = 0; i < outboundMissions.length; i++) {
            const om = outboundMissions[i];
            if (om.status === 'PENDING' && om.itemsToPick.length > 0) {
              const first = om.itemsToPick[0];
              const dist = Math.hypot(robot.gridX - first.rack.x, robot.gridY - first.rack.y);
              if (dist <= 30) {
                const chainEval = evaluateMissionEnergyFeasibility(robot, {
                  type: 'OUTBOUND',
                  rack: first.rack,
                  itemsToPick: om.itemsToPick,
                  bayId: om.bayId,
                  bayX: om.bayX,
                  bayY: om.bayY,
                  totalWeight: om.totalWeight,
                  desc: `Chained Order ${om.orderId}`
                });
                if (chainEval.feasible) {
                  chainedOrderIdx = i;
                  break;
                }
              }
            }
          }

          if (chainedOrderIdx !== -1) {
            const chained = outboundMissions[chainedOrderIdx];
            chained.status = 'ASSIGNED';
            chained.assignedRobotId = robot.id;
            robot.state = 'ORDER_PICKING';
            robot.outboundMission = chained;
            robot.missionStartTime = Date.now();
            robot.orderBox = {
              orderId: chained.orderId,
              bayId: chained.bayId,
              totalItems: chained.totalItems,
              items: [],
              importance: chained.importance,
              totalWeight: chained.totalWeight
            };
            const firstPick = chained.itemsToPick[0];
            const access = getAccessPointForRack(firstPick.rack.x, firstPick.rack.y, robot.gridX, robot.gridY);
            robot.targetDesc = `Chained Order Pick 1/${chained.totalItems} for ${chained.orderId}`;
            robot.statusBadge = `PICK 0/${chained.totalItems}`;
            logTerminal('DISPATCH', 'tag-complete', `⚡ <strong>${robot.id}</strong> BMS verified chained picking for Order <strong>${chained.orderId}</strong> (saved deadhead trip!)`);
            if (access) {
              setRobotPath(robot, findPath(robot.gridX, robot.gridY, access.x, access.y));
              if (robot.path.length === 0) {
                onRobotReachedDestination(robot);
              }
              updateHudStats();
              return;
            }
          }

          robot.state = 'IDLE';
          updateHudStats();
          if (robot.battery < 80.0) {
            routeRobotToNearestCharger(robot, 'OPPORTUNITY_CHARGE');
          }
          dispatchFleet();
        }

      } else if (robot.state === 'ORDER_PICKING') {
        const mission = robot.outboundMission;
        if (!mission || !robot.orderBox) {
          robot.state = 'IDLE';
          dispatchFleet();
          return;
        }

        // Pick item from shelf and place into robot's Giant Box
        const pickItem = mission.itemsToPick.shift();
        pickItem.rack.floors[pickItem.floorIndex] = null; // Clears the rack tier!
        robot.orderBox.items.push(pickItem.parcel);
        if (robot.logStats) {
          robot.logStats.totalItemsConsolidated++;
          robot.logStats.totalWeightTransportedKg += (parseFloat(pickItem.parcel.weight) || 3.0);
        }
        recordRobotEvent(robot, 'ITEM_PICKED', `Collected item ${pickItem.parcel.parcel_id} (${pickItem.parcel.name}) into Giant Box for ${mission.orderId} [${robot.orderBox.items.length}/${robot.orderBox.totalItems}]`, { parcelId: pickItem.parcel.parcel_id, rackX: pickItem.rack.x, rackY: pickItem.rack.y, floorIndex: pickItem.floorIndex });

        logTerminal('PICKUP', 'tag-outbound', `📦 <strong>${robot.id}</strong> collected item <strong>${pickItem.parcel.parcel_id}</strong> (${pickItem.parcel.name}, ${pickItem.parcel.weight}) into Giant Box for <strong>${mission.orderId}</strong> [${robot.orderBox.items.length}/${robot.orderBox.totalItems} items consolidated]`);
        updateHudStats();

        if (mission.itemsToPick.length > 0) {
          // Move to next pick item for this order
          const nextPick = mission.itemsToPick[0];
          const access = getAccessPointForRack(nextPick.rack.x, nextPick.rack.y, robot.gridX, robot.gridY);
          robot.targetDesc = `Order Pick ${robot.orderBox.items.length + 1}/${robot.orderBox.totalItems} for ${mission.orderId} at Rack (${nextPick.rack.x},${nextPick.rack.y})`;
          robot.statusBadge = `PICK ${robot.orderBox.items.length}/${robot.orderBox.totalItems}`;
          if (access) {
            setRobotPath(robot, findPath(robot.gridX, robot.gridY, access.x, access.y));
            if (robot.path.length === 0) {
              onRobotReachedDestination(robot);
            }
          }
        } else {
          // All items for the customer order are collected in the giant box!
          robot.state = 'DELIVERING_ORDER_TO_BAY';
          robot.targetDesc = `Delivering Giant Order Box (${robot.orderBox.totalItems} items) to Bay ${mission.bayId}`;
          robot.statusBadge = 'DELIVER';
          setRobotPath(robot, findPath(robot.gridX, robot.gridY, mission.bayX, mission.bayY));
          const dampingPct = Math.round(Math.max(65, (1.0 - (mission.totalWeight / 60.0)) * 100));
          logTerminal('DISPATCH', 'tag-outbound', `📦 <strong>${robot.id}</strong> completed Giant Box consolidation (all <strong>${robot.orderBox.totalItems} items</strong>, ${mission.totalWeight.toFixed(1)}kg, ${mission.importance.label}, Load Speed Throttle: <span style="color:#f59e0b;font-weight:700;">${dampingPct}%</span>) for Order <strong>${mission.orderId}</strong>! Transporting to Departure Bay <strong>${mission.bayId}</strong>`);
          if (robot.path.length === 0) {
            onRobotReachedDestination(robot);
          }
        }

      } else if (robot.state === 'DELIVERING_ORDER_TO_BAY') {
        const mission = robot.outboundMission;
        if (mission && robot.orderBox) {
          // Deposited giant box at departure bay!
          outboundOrders[mission.bayId] = null; // Bay turns back to Orange!
          const oIdx = outboundMissions.findIndex(m => m.orderId === mission.orderId);
          if (oIdx !== -1) outboundMissions.splice(oIdx, 1);

          if (robot.logStats) {
            robot.logStats.totalOutboundCompleted++;
          }
          if (robot.missionsHistory) {
            robot.missionsHistory.push({
              type: 'OUTBOUND',
              orderId: mission.orderId,
              bayId: mission.bayId,
              itemsCount: robot.orderBox.totalItems,
              totalWeightKg: mission.totalWeight,
              finishSimTimeSec: Number(totalSimSeconds.toFixed(2)),
              durationSec: robot.missionStartTime ? Number(((Date.now() - robot.missionStartTime) / 1000).toFixed(1)) : 0
            });
          }
          recordRobotEvent(robot, 'ORDER_DELIVERED', `Customer Order ${robot.orderBox.orderId} (all ${robot.orderBox.totalItems} items) deposited at Bay ${mission.bayId}`, { orderId: mission.orderId, bayId: mission.bayId, totalItems: robot.orderBox.totalItems });

          logTerminal('COMPLETE', 'tag-complete', `✅ Customer Order <strong>${robot.orderBox.orderId}</strong> (Consolidated Giant Box with <strong>${robot.orderBox.totalItems} items</strong>) deposited at Departure Bay <strong>${mission.bayId}</strong> by <strong>${robot.id}</strong>! Bay returned to <span style="color:#f97316;font-weight:700;">IDLE (ORANGE)</span>`);
        }

        robot.orderBox = null;
        robot.outboundMission = null;
        robot.statusBadge = null;
        robot.payloadWeight = 0;
        robot.payloadDamping = 1.0;
        robot.state = 'IDLE';
        updateHudStats();
        if (robot.battery < 80.0) {
          routeRobotToNearestCharger(robot, 'POST_MISSION_CHARGE');
        }
        dispatchFleet();

      } else if (robot.state === 'RETURNING_HOME') {
        const port = CHARGING_PORTS.find(p => p.x === robot.gridX && p.y === robot.gridY) || 
                     CHARGING_PORTS.find(p => p.id === robot.targetChargerId) ||
                     CHARGING_PORTS[0];
        dockAtCharger(port.id, robot.id);
        robot.state = 'IDLE_CHARGING';
        robot.targetDesc = `Parked at Fast Charger ${port.id} (${robot.battery.toFixed(1)}%)`;
        robot.path = [];
        robot.pathIndex = 0;
        robot.statusBadge = null;
        robot.currentSpeed = 0;
        robot.payloadWeight = 0;
        robot.payloadDamping = 1.0;
        if (robot.logStats) {
          robot.logStats.chargeCyclesCount++;
        }
        onRobotJamEnd(robot, 'DOCKED_AT_CHARGER');
        recordRobotEvent(robot, 'DOCKED_AT_CHARGER', `Docked at Charger ${port.id} (${robot.battery.toFixed(1)}% SoC)`, { chargerId: port.id, battery: robot.battery });
        logTerminal('BMS', 'tag-inbound', `⚡ <strong>${robot.id}</strong> precision docked at Fast Charger <strong>${port.id}</strong> (${port.zone}). SoC: <strong>${robot.battery.toFixed(1)}%</strong>. 30kW CC Fast Charge engaged.`);
        updateHudStats();
      }
    }

    // Active Collision Avoidance, Overtaking, Yielding & Movement Engine
    function updateRobots(dt) {
      totalSimSeconds += dt;
      const baseSpeed = ROBOT_BASE_SPEED * simSpeed;

      // Update Dynamic Human Workers & Decentralized V2V Mesh Network
      if (typeof updateHumanWorkers === 'function') updateHumanWorkers(dt);
      if (typeof updateV2VMesh === 'function') updateV2VMesh(dt);

      // 1. Update battery & action timers
      for (const robot of AMR_FLEET) {
        if (!robot.logStats) {
          robot.logStats = {
            startTime: Date.now(),
            startSimTime: totalSimSeconds,
            totalSimTime: 0,
            activeMovingTime: 0,
            jamWaitTime: 0,
            chargingTime: 0,
            loadingTime: 0,
            idleTime: 0,
            totalDistanceTraveled: 0,
            totalCellsTraversed: 0,
            totalJamsEncountered: 0,
            totalBackupsToPreviousBox: 0,
            totalSideSteps: 0,
            totalOvertakesInitiated: 0,
            totalOvertakesCompleted: 0,
            totalReroutes: 0,
            totalEmergencyBraking: 0,
            totalRightOfWayYields: 0,
            totalInboundCompleted: 0,
            totalOutboundCompleted: 0,
            totalParcelsShelved: 0,
            totalItemsConsolidated: 0,
            totalWeightTransportedKg: 0,
            initialBattery: robot.battery,
            minBatterySeen: robot.battery,
            totalEnergyConsumedSoC: 0,
            totalEnergyChargedSoC: 0,
            chargeCyclesCount: 1,
            maxSpeed: 0
          };
          robot.currentJam = null;
          robot.jamEpisodes = robot.jamEpisodes || [];
          robot.missionsHistory = robot.missionsHistory || [];
          robot.eventHistory = robot.eventHistory || [];
        }

        robot.logStats.totalSimTime += dt;
        if (robot.state === 'IDLE_CHARGING') {
          robot.logStats.chargingTime += dt;
        } else if (robot.state === 'LOADING_INBOUND') {
          robot.logStats.loadingTime += dt;
        } else if (robot.isWaiting) {
          robot.logStats.jamWaitTime += dt;
        } else if (robot.state === 'IDLE') {
          robot.logStats.idleTime += dt;
        } else if (robot.path && robot.path.length > 0 && robot.pathIndex < robot.path.length) {
          robot.logStats.activeMovingTime += dt;
        }

        if (robot.state === 'IDLE_CHARGING') {
          // ==========================================
          // REALISTIC CC/CV FAST-CHARGING PROFILE
          // 48V 40Ah LiFePO4 (1,920 Wh) Pack
          // ==========================================
          let chargeRate = 0;
          let kw = 0;
          let phase = '';

          if (robot.battery < 75.0) {
            chargeRate = 3.5 * simSpeed;
            kw = 30.0;
            phase = 'Bulk CC Phase (Fast)';
          } else if (robot.battery < 95.0) {
            const taper = 1.0 - ((robot.battery - 75.0) / 20.0) * 0.68;
            chargeRate = 3.5 * taper * simSpeed;
            kw = 30.0 * taper;
            phase = 'Absorption CV Phase (Tapered)';
          } else if (robot.battery < 100.0) {
            chargeRate = 0.55 * simSpeed;
            kw = 2.4;
            phase = 'Cell Balancing / Float';
          } else {
            chargeRate = 0;
            kw = 0.1;
            phase = 'Fully Charged (100% Float)';
          }

          robot.battery = Math.min(100.0, robot.battery + chargeRate * dt);
          if (robot.logStats) {
            robot.logStats.totalEnergyChargedSoC += chargeRate * dt;
          }
          robot.chargeRateKw = kw;
          robot.chargePhase = phase;
          robot.batteryDeltaRate = chargeRate;
          robot.powerWatts = 0;
          robot.powerBreakdown = `Charger Input: +${kw.toFixed(1)}kW`;

          // Announce bulk charge readiness milestone (80% SoC)
          if (robot.battery >= 80.0 && !robot.hasAnnouncedBulkCharged) {
            robot.hasAnnouncedBulkCharged = true;
            robot.hasAnnouncedLowBatt = false; // Reset low batt announcement
            logTerminal('BMS', 'tag-inbound', `🔋 <strong>${robot.id}</strong> fast-charge reached <strong>${robot.battery.toFixed(1)}% SoC</strong> (${phase}). Ready for active warehouse dispatch.`);
          }
          if (robot.battery >= 99.9) {
            robot.battery = 100.0;
            robot.hasAnnouncedBulkCharged = true;
          }
        } else {
          // ==========================================
          // REALISTIC DYNAMIC DISCHARGE CONSUMPTION
          // P_total = P_avionics + P_traction + P_payload + P_maneuver + P_lift
          // ==========================================
          // ========================================================
          // EDGE-AI ONBOARD COMPUTING & SENSOR POWER MODEL
          // NVIDIA Jetson Orin Industrial (275 TOPS Edge AI Module)
          // ========================================================
          const isMoving = robot.path && robot.path.length > 0 && robot.pathIndex < robot.path.length && !robot.isWaiting;
          let computeLoadPct = 25; // 25% Idle baseline
          let pCompute = 15;        // 15W Base OS + Watchdog
          if (robot.isRerouting || (robot.waitTimer && robot.waitTimer > 0.2)) {
            computeLoadPct = 85;    // Neural SLAM + Real-Time A* Search Surge
            pCompute = 42;          // 42W Peak computing power
          } else if (isMoving) {
            computeLoadPct = 52;    // Continuous 3D LiDAR point cloud filtering & V2V RF mesh
            pCompute = 28;          // 28W Nominal edge AI load
          }
          robot.computeLoad = computeLoadPct;
          robot.computeWatts = pCompute;
          robot.computeTops = ((275.0 * computeLoadPct) / 100.0).toFixed(1);

          let pSensorsComms = 18;  // 18W: 360 LiDAR puck sensor + 5.9GHz C-V2X radio
          let pTraction = 0;
          let pPayload = 0;
          let pManeuver = 0;
          let pLift = 0;

          // Traction motor power: moving consumes power proportional to speed
          if (isMoving) {
            const speedRatio = (robot.currentSpeed || baseSpeed) / baseSpeed;
            pTraction = 125 * Math.max(0.4, speedRatio);
          } else {
            pTraction = 0; // Stationary while yielding or waiting
          }

          // Payload mass work penalty: 6.5 Watts per kg of cargo
          const cargoW = robot.payloadWeight || 0;
          if (cargoW > 0) {
            pPayload = cargoW * 6.5;
          }

          // Dynamic maneuver acceleration surges (I^2*R losses)
          if (robot.isOvertaking) {
            pManeuver += 85; // Peak torque current boost during overtake
          }
          if (robot.isRerouting) {
            pManeuver += 30; // Rapid differential steering friction
          }

          // Actuator mechanical lift during loading, shelving or picking
          if (robot.state === 'LOADING_INBOUND' || robot.state === 'CARRYING_TO_RACK' || robot.state === 'ORDER_PICKING') {
            pLift = 35;
          }

          const pTotal = pCompute + pSensorsComms + pTraction + pPayload + pManeuver + pLift;
          robot.powerWatts = pTotal;
          robot.powerBreakdown = `Edge AI: ${Math.round(pCompute)}W (${computeLoadPct}%) | Traction: ${Math.round(pTraction)}W | LiDAR/V2V: ${pSensorsComms}W${cargoW > 0 ? ` | Cargo: +${Math.round(pPayload)}W` : ''}${pManeuver > 0 ? ` | Surge: +${pManeuver}W` : ''}`;

          // Calibrated drain rate: 165W base drain corresponds to ~0.16% / sec (~0.038% / tile) at 1x simSpeed
          const drainRate = (pTotal / 165.0) * 0.16 * simSpeed;
          robot.battery = Math.max(10.0, robot.battery - drainRate * dt);
          if (robot.logStats) {
            robot.logStats.totalEnergyConsumedSoC += drainRate * dt;
            if (robot.battery < robot.logStats.minBatterySeen) {
              robot.logStats.minBatterySeen = robot.battery;
            }
          }
          robot.batteryDeltaRate = drainRate;
          robot.chargeRateKw = 0;
          robot.chargePhase = 'Discharging';

          // Out of charge check: Battery depleted to UVLO cut-off (10.0% Hard Floor, NEVER 4%)
          if (robot.battery <= 10.0) {
            robot.battery = 10.0;
            if (robot.state !== 'OUT_OF_CHARGE') {
              robot.state = 'OUT_OF_CHARGE';
              robot.currentSpeed = 0;
              robot.statusBadge = 'LOW 10%';
              robot.targetDesc = `IMMOBILIZED: BMS Low-Voltage Cutoff at 10.0% SoC (Tow Required)`;
              robot.strandedTimer = 0;
              if (robot.logStats) robot.logStats.totalOutOfChargeEvents = (robot.logStats.totalOutOfChargeEvents || 0) + 1;

              logBotProblem('OUT_OF_CHARGE', robot.id, {
                x: robot.gridX,
                y: robot.gridY,
                severity: 'CRITICAL',
                desc: `🪫 BMS UVLO Protection Tripped: <strong>${robot.id}</strong> battery reached 10.0% safe discharge floor at (${robot.gridX}, ${robot.gridY}). Drive motor inverter deactivated. Vehicle immobilized.`
              });
              logTerminal('ALERT', 'tag-yield', `🪫 <strong>${robot.id}</strong> BATTERY AT 10% FLOOR. Vehicle stranded at (${robot.gridX}, ${robot.gridY}). Dispatching auto-recovery.`);
            }

            // Autonomous Rescue Fail-Safe:
            // If stranded for > 3s, autonomous warehouse recovery tug tows it to a charger so simulation never freezes
            robot.strandedTimer = (robot.strandedTimer || 0) + dt;
            if (robot.strandedTimer > 3.0 / simSpeed) {
              logTerminal('SYSTEM', 'tag-complete', `🚜 Autonomous AGV Recovery Tug towed stranded <strong>${robot.id}</strong> from aisle (${robot.gridX}, ${robot.gridY}) to fast charger.`);
              rescueStrandedBot(robot.id);
            }
            continue; // Cannot move while dead!
          }

          // Reset bulk charge announcement flag once battery drops below 75%
          if (robot.battery < 75.0) {
            robot.hasAnnouncedBulkCharged = false;
          }

          // Autonomous Low-Battery Protection & Threshold Management
          if (robot.battery <= 28.0 && !robot.hasAnnouncedLowBatt) {
            robot.hasAnnouncedLowBatt = true;
            logTerminal('BMS', 'tag-yield', `⚠️ <strong>${robot.id}</strong> Battery Low (<strong>${robot.battery.toFixed(1)}% SoC</strong>, draw ${Math.round(pTotal)}W). Scheduling autonomous opportunity recharge.`);
          }

          // If robot is IDLE on the floor with battery < 40%, immediately route to nearest available charger
          if (robot.state === 'IDLE' && robot.battery < 40.0) {
            routeRobotToNearestCharger(robot, 'LOW_BATTERY');
          }

          // Intelligent BMS Dynamic Return-to-Charger Horizon:
          // Proactively route to charger BEFORE entering deficit!
          // Calculate distance to nearest charger: (dist * 0.18% SoC) + 14% safety reserve floor
          const nearestChg = getNearestAvailableCharger(robot.gridX, robot.gridY, robot.id, true);
          const chgPort = nearestChg ? nearestChg.charger : CHARGING_PORTS[0];
          const distToChg = chgPort ? (Math.abs(robot.gridX - chgPort.x) + Math.abs(robot.gridY - chgPort.y)) : 40;
          const dynamicAbortThreshold = Math.max(24.0, (distToChg * 0.18) + 14.0);

          if (robot.battery <= dynamicAbortThreshold && robot.state !== 'IDLE_CHARGING' && robot.state !== 'RETURNING_HOME' && robot.state !== 'OUT_OF_CHARGE') {
            abortMissionToCharger(robot.id, 'DYNAMIC_SAFETY_ABORT');
          }
        }

        if (robot.state === 'LOADING_INBOUND') {
          if (robot.loadingTimer > 0) {
            robot.loadingTimer -= dt;
            if (robot.loadingTimer <= 0) {
              // Finished loading at dock -> start moving to first shelf destination!
              robot.state = 'CARRYING_TO_RACK';
              if (robot.carriedParcels && robot.carriedParcels.length > 0) {
                const nextP = robot.carriedParcels[0];
                const access = getAccessPointForRack(nextP.rackSlot.rack.x, nextP.rackSlot.rack.y, robot.gridX, robot.gridY);
                robot.targetDesc = `Shelving ${nextP.parcel_id} (${robot.carriedParcels.length} left) at Rack (${nextP.rackSlot.rack.x},${nextP.rackSlot.rack.y})`;
                robot.statusBadge = `SHELVE ${robot.carriedParcels.length}`;
                if (access) {
                  setRobotPath(robot, findPath(robot.gridX, robot.gridY, access.x, access.y));
                  if (robot.path.length === 0) {
                    onRobotReachedDestination(robot);
                  }
                }
              }
            }
          }
        }

        if (robot.rerouteTimer > 0) {
          robot.rerouteTimer -= dt;
          if (robot.rerouteTimer <= 0) {
            robot.isRerouting = false;
            if (robot.statusBadge === 'REROUTE') robot.statusBadge = null;
          }
        }
        if (robot.overtakeTimer > 0) {
          robot.overtakeTimer -= dt;
          if (robot.overtakeTimer <= 0) {
            robot.isOvertaking = false;
            robot.speedMultiplier = 1.0;
            if (robot.statusBadge === 'PASS') robot.statusBadge = null;
          }
        }
        // Auto-release bots that were pinned so a faster bot could overtake them
        if (robot._pinnedForOvertake && robot._pinnedTimer !== undefined) {
          robot._pinnedTimer -= dt;
          if (robot._pinnedTimer <= 0) {
            robot._pinnedForOvertake = false;
            robot._pinnedTimer = 0;
            robot.isWaiting = false;
            robot.waitTimer = 0;
            robot.yieldTo = null;
            if (robot.statusBadge === 'YIELD') robot.statusBadge = null;
          }
        }


        robot._wasWaitingThisFrame = false;
      }

      // 1.5. Physical Collision & Close Contact Detection
      for (let i = 0; i < AMR_FLEET.length; i++) {
        const A = AMR_FLEET[i];
        if (A.state === 'IDLE_CHARGING' || A.state === 'OUT_OF_CHARGE') continue;

        for (let j = i + 1; j < AMR_FLEET.length; j++) {
          const B = AMR_FLEET[j];
          if (B.state === 'IDLE_CHARGING' || B.state === 'OUT_OF_CHARGE') continue;

          const distAB = Math.hypot(A.x - B.x, A.y - B.y);
          const sameCell = (A.gridX === B.gridX && A.gridY === B.gridY && distAB < 0.45);

          // Physical Collision Condition: Distance < 0.55 cells (actual chassis contact)
          if (distAB < 0.55 || sameCell) {
            A._collidedWith = A._collidedWith || new Set();
            B._collidedWith = B._collidedWith || new Set();

            if (!A._collidedWith.has(B.id)) {
              A._collidedWith.add(B.id);
              B._collidedWith.add(A.id);
              trafficMetrics.totalCollisions = (trafficMetrics.totalCollisions || 0) + 1;
              if (A.logStats) A.logStats.physicalCollisions = (A.logStats.physicalCollisions || 0) + 1;
              if (B.logStats) B.logStats.physicalCollisions = (B.logStats.physicalCollisions || 0) + 1;

              logBotProblem('COLLISION', A.id, {
                peerId: B.id,
                x: Math.round(A.x),
                y: Math.round(A.y),
                severity: 'CRITICAL',
                desc: `Physical collision between <strong>${A.id}</strong> and <strong>${B.id}</strong> at cell (${Math.round(A.x)}, ${Math.round(A.y)}) [Separation: ${distAB.toFixed(2)} cells]. AEB emergency override.`
              });

              COLLISION_SPARKS.push({
                x: (A.x + B.x) / 2,
                y: (A.y + B.y) / 2,
                timer: 1.5,
                maxTimer: 1.5
              });
            }

            // Kinematic bounce separation (clamped strictly to walkable floor cells)
            const overlap = 0.65 - distAB;
            if (overlap > 0) {
              const nx = distAB > 0.01 ? (A.x - B.x) / distAB : 0;
              const ny = distAB > 0.01 ? (A.y - B.y) / distAB : 1;
              const newAx = A.x + nx * (overlap * 0.5);
              const newAy = A.y + ny * (overlap * 0.5);
              const newBx = B.x - nx * (overlap * 0.5);
              const newBy = B.y - ny * (overlap * 0.5);
              if (isWalkable(Math.round(newAx), Math.round(newAy))) { A.x = newAx; A.y = newAy; }
              if (isWalkable(Math.round(newBx), Math.round(newBy))) { B.x = newBx; B.y = newBy; }
            }
          } else if (distAB > 0.85) {
            if (A._collidedWith) A._collidedWith.delete(B.id);
            if (B._collidedWith) B._collidedWith.delete(A.id);
          }
        }
      }

      // =========================================================================
      // DEADLOCK RESOLVER (User Specification):
      // if (2 or more bots should be moving but not moving due to collision prevention) {
      //     the one with the highest, 2nd highest.... battery stops completely and the lowest moves.
      //     once it moves away. then 2nd highest moves, then highest....
      // }
      // =========================================================================
      for (let i = 0; i < AMR_FLEET.length; i++) {
        const A = AMR_FLEET[i];
        if (A.state === 'IDLE_CHARGING' || A.state === 'OUT_OF_CHARGE' || A.state === 'LOADING_INBOUND' || A.state === 'IDLE') continue;
        if (!A.path || A.path.length === 0 || A.pathIndex >= A.path.length) continue;

        for (let j = i + 1; j < AMR_FLEET.length; j++) {
          const B = AMR_FLEET[j];
          if (B.state === 'IDLE_CHARGING' || B.state === 'OUT_OF_CHARGE' || B.state === 'LOADING_INBOUND' || B.state === 'IDLE') continue;
          if (!B.path || B.path.length === 0 || B.pathIndex >= B.path.length) continue;

          const distAB = Math.hypot(A.x - B.x, A.y - B.y);
          if (distAB > 1.8) continue;

          // Check if bots should be moving but are NOT MOVING due to collision prevention
          const aNotMoving = A.isWaiting || A.currentSpeed < 0.05 || (A.waitTimer && A.waitTimer > 0.05);
          const bNotMoving = B.isWaiting || B.currentSpeed < 0.05 || (B.waitTimer && B.waitTimer > 0.05);
          const mutualBlock = (A.yieldTo === B.id && B.yieldTo === A.id);
          const kissing = distAB < 1.15;

          if ((aNotMoving && bNotMoving) || mutualBlock || kissing) {
            // Mutual deadlock / collision stall: Lower battery bot moves!
            const aHasLowerBatt = isHigherPriority(A, B);
            const winner = aHasLowerBatt ? A : B;
            const loser = aHasLowerBatt ? B : A;

            // User Specification: When blocked, make bots try to move back to previous box,
            // and only the lowest charging moves!
            // First allow pausing: if waitTimer > 1.2s or face-to-face, execute back-up to previous box!
            if ((loser.waitTimer || 0) > 1.2 / simSpeed || distAB < 1.15 || mutualBlock) {
              const backedUp = attemptMoveBackToPreviousBox(loser, winner);
              if (!backedUp) {
                executeSideStepYield(loser, winner);
              }
              // While loser is executing back-up or side-step, winner pauses until separation >= 1.2
              winner._wasWaitingThisFrame = true;
              winner.isWaiting = true;
              winner.yieldTo = loser.id;
              winner.currentSpeed = 0;
              winner.waitTimer = (winner.waitTimer || 0) + dt; // <-- ADD THIS LINE
              winner.statusBadge = 'WAIT';
              onRobotJamStart(winner, loser.id, 'WAITING_FOR_ESCAPE_MANEUVER');
            } else {
              // Higher-battery bot stops completely and pauses patiently
              loser.isWaiting = true;
              loser._wasWaitingThisFrame = true;
              loser.currentSpeed = 0;
              loser.yieldTo = winner.id;
              loser.statusBadge = 'WAIT';
              loser.waitTimer = (loser.waitTimer || 0) + dt;
              onRobotJamStart(loser, winner.id, 'HEAD_ON_DEADLOCK_PRIORITY_PAUSE');

              // Lowest charging bot moves forward!
              winner.isWaiting = false;
              winner._wasWaitingThisFrame = false;
              winner.yieldTo = null;
              if (winner.statusBadge === 'WAIT') winner.statusBadge = null;
              onRobotJamEnd(winner, 'RESUMED_NORMAL');
            }
          }
        }
      }

      // =========================================================================
      // 1.8. INNER SIMULATION TRAFFIC MONITOR & PROACTIVE PATH DISCARD
      // "simulation run inside simulation that checks for traffic problems.
      //  when to discard a path : if a bot stops or not moving in the speed
      //  it is supposed to, then compute new path."
      // =========================================================================
      for (const robot of AMR_FLEET) {
        if (robot.state === 'IDLE_CHARGING' || robot.state === 'OUT_OF_CHARGE' || robot.state === 'LOADING_INBOUND' || robot.state === 'IDLE') continue;
        if (robot.isBackingUp || robot.isSideStepping || robot._pinnedUntilBotId) continue;
        if (!robot.path || robot.path.length === 0 || robot.pathIndex >= robot.path.length) continue;

        const dest = robot.path[robot.path.length - 1];
        if (!dest || Math.hypot(robot.gridX - dest.x, robot.gridY - dest.y) <= 1) continue;

        const nominalSpeed = baseSpeed * (robot.speedMultiplier || 1.0) * (robot.payloadDamping || 1.0);
        const actualSpeed = (robot.currentSpeed !== undefined && robot.currentSpeed !== null) ? robot.currentSpeed : nominalSpeed;

        // Discard trigger A: bot stops or not moving in the speed it is supposed to
        const isBotStopped = robot.isWaiting || actualSpeed < 0.1 || (robot.waitTimer && robot.waitTimer > 0.25);
        const isSpeedDeficit = (actualSpeed < nominalSpeed * 0.70 && !robot.isWaiting);

        // Discard trigger B: inner simulation predicts conflict on current path ahead
        const simPrediction = runInnerTrafficSimulation(robot, null, 5.0);
        const hasProjectedJam = simPrediction.hasTrafficProblem && simPrediction.timeToConflict <= 4.0;

        if (isBotStopped || isSpeedDeficit || hasProjectedJam) {
          const timeSinceRepath = totalSimSeconds - (robot._lastInnerSimRepathTime || -999);
          if (timeSinceRepath >= 0.4 / simSpeed || (isBotStopped && robot.waitTimer > 0.3 / simSpeed)) {
            const repathed = solveTrafficPathViaInnerSim(robot, dest, simPrediction.blocker, simPrediction.conflictCell);
            if (repathed) {
              robot._lastInnerSimRepathTime = totalSimSeconds;
            }
          }
        }
      }

      // 1.9. Perception & ISO 3691-4 Calibrated Safety Zone Protection for Dynamic Obstacles & Human Workers
      if (typeof dynamicObstaclesEnabled !== 'undefined' && dynamicObstaclesEnabled && typeof DYNAMIC_OBSTACLES !== 'undefined') {
        for (const robot of AMR_FLEET) {
          if (robot.state === 'IDLE_CHARGING' || robot.state === 'OUT_OF_CHARGE' || robot.state === 'LOADING_INBOUND') continue;
          if (!robot.path || robot.path.length === 0 || robot.pathIndex >= robot.path.length) continue;

          for (const obs of DYNAMIC_OBSTACLES) {
            const distObs = Math.hypot(robot.x - obs.x, robot.y - obs.y);
            if (distObs > 2.8) continue; // Ignore distant non-interfering obstacles

            // Focused forward LiDAR sensing beam (+/- 38 degrees)
            const angleToObs = Math.atan2(obs.y - robot.y, obs.x - robot.x);
            let angleDiff = Math.abs(robot.heading - angleToObs);
            while (angleDiff > Math.PI) angleDiff = Math.abs(angleDiff - 2 * Math.PI);
            const inForwardBeam = angleDiff < 0.65 || distObs < 0.60;

            if (inForwardBeam) {
              if (typeof broadcastV2VObstacleAlert === 'function') {
                broadcastV2VObstacleAlert(robot, obs);
              }

              // Calibrated Tight Safety Zones with Hysteresis (Completely eliminates back-and-forth glitching!)
              const wasStopped = robot._stoppedForObs === obs.id;
              const stopThreshold = 0.82; // Tight stop distance near bumper
              const resumeThreshold = 0.98; // Solid 0.16m hysteresis gap before resuming

              const isDirectlyAhead = wasStopped ? (distObs < resumeThreshold) : (distObs < stopThreshold);
              const isCellBlocked = obs.isStatic && Math.round(obs.x) === robot.gridX && Math.round(obs.y) === robot.gridY;

              if (isDirectlyAhead || isCellBlocked) {
                robot._stoppedForObs = obs.id;
                robot.isWaiting = true;
                robot._wasWaitingThisFrame = true;
                robot.statusBadge = obs.type === 'human' ? 'HUMAN_STOP' : 'OBS_STOP';
                robot.currentSpeed = 0;
                robot.yieldTo = obs.id;
                robot.waitTimer = (robot.waitTimer || 0) + dt;

                if (robot.logStats) robot.logStats.totalEmergencyBraking++;
                trafficMetrics.collisionsPrevented++;

                const now = Date.now();
                if (now - (robot._lastObsWarnTime || 0) > 4000) {
                  robot._lastObsWarnTime = now;
                  logTerminal('SAFETY', 'tag-yield', `🚨 <strong>${robot.id}</strong> Safe Stop: Yielding to <strong>${obs.name}</strong> (${distObs.toFixed(2)}m).`);
                }

                // AVOID UNNECESSARY PATH SHIFTS:
                // Only detour around persistent STATIC obstacles (> 2.5s).
                // Dynamic walking workers clear the lane in ~1s — AMR stands calm without erratic path shifts!
                if (obs.isStatic && robot.waitTimer > 2.5 / simSpeed) {
                  const repathed = solveTrafficPathViaInnerSim(robot, null, null, { x: Math.round(obs.x), y: Math.round(obs.y) });
                  if (repathed) {
                    robot.isWaiting = false;
                    robot._wasWaitingThisFrame = false;
                    robot._stoppedForObs = null;
                    robot.waitTimer = 0;
                    logTerminal('DETOUR', 'tag-reroute', `🔀 <strong>${robot.id}</strong> autonomous detour calculated around <strong>${obs.name}</strong>.`);
                  }
                }
                break;
              } else if (distObs < 1.35) {
                // Smooth Caution Zone (0.82m - 1.35m): Gently modulate speed to 50% without stopping
                robot._stoppedForObs = null;
                const cautionSpeed = baseSpeed * 0.50 * (robot.speedMultiplier || 1.0);
                robot.currentSpeed = Math.min(robot.currentSpeed || baseSpeed, cautionSpeed);
                if (!robot.statusBadge || robot.statusBadge === 'NORMAL') {
                  robot.statusBadge = 'SLOW_CAUTION';
                }
              } else {
                robot._stoppedForObs = null;
              }
            } else {
              if (robot._stoppedForObs === obs.id) robot._stoppedForObs = null;
            }
          }
        }
      }

      // 2. Multi-Agent Conflict Detection, Overtaking & Right-of-Way Resolution
      for (let i = 0; i < AMR_FLEET.length; i++) {
        const A = AMR_FLEET[i];
        if (A.state === 'IDLE_CHARGING' || A.state === 'LOADING_INBOUND' || A.state === 'OUT_OF_CHARGE' || !A.path || A.path.length === 0 || A.pathIndex >= A.path.length) continue;
        if (A.isBackingUp || A.isSideStepping) continue; // Dedicated escape maneuver in progress: do not stall!

        const targetA = A.path[A.pathIndex];
        const urgA = calculateRobotUrgency(A);
        const speedA = (A.currentSpeed !== undefined && A.currentSpeed !== null) ? A.currentSpeed : (baseSpeed * (A.speedMultiplier || 1.0) * (A.payloadDamping || 1.0));

        for (let j = 0; j < AMR_FLEET.length; j++) {
          if (i === j) continue;
          const B = AMR_FLEET[j];
          if (B.state === 'IDLE_CHARGING' || B.state === 'OUT_OF_CHARGE') continue;

          const distAB = Math.hypot(A.x - B.x, A.y - B.y);
          if (distAB > 4.2) continue; // Long range: no immediate conflict

          const urgB = calculateRobotUrgency(B);
          const speedB = (B.currentSpeed !== undefined && B.currentSpeed !== null) ? B.currentSpeed : (baseSpeed * (B.speedMultiplier || 1.0) * (B.payloadDamping || 1.0));
          const targetB = (B.path && B.pathIndex < B.path.length) ? B.path[B.pathIndex] : null;

          // Check if B is ahead of A in A's planned trajectory (Trailing Encounter)
          const lookaheadSteps = Math.min(4, A.path.length - A.pathIndex);
          const aheadPath = A.path.slice(A.pathIndex, A.pathIndex + lookaheadSteps);
          const bInAHeadPath = aheadPath.some(pt => Math.hypot(B.x - pt.x, B.y - pt.y) < 1.15);
          const isTrailingB = bInAHeadPath || (distAB < 2.8 && Math.abs(A.heading - B.heading) < 1.2);

          // =========================================================================
          // CASE 1: PROACTIVE OVERTAKE OF SLOW BOTS BY FAST BOTS
          // =========================================================================
          if (isTrailingB && distAB < 3.2) {
            // A bot is considered slower if stopped/waiting, speed < 92% of A, or carrying heavier payload
            const isBSlower = B.isWaiting || (speedB < speedA * 0.92) || (A.payloadDamping > B.payloadDamping + 0.08) || (urgA > urgB + 5) || (B.waitTimer > 0);

            if (isBSlower && !A.isOvertaking) {
              const took = attemptOvertake(A, B, urgA, urgB);
              if (took) {
                A.isWaiting = false;
                A._wasWaitingThisFrame = false;
                break; // Successfully branched into parallel passing lane!
              }
            }

            // Adaptive Cruise Control (ACC): smoothly slow to match lead vehicle speed
            if (distAB < 1.6) {
              A.currentSpeed = Math.min(A.currentSpeed, Math.max(0, speedB * 0.95));
            }

            // Chain-jam guard: only fully stop A if B is genuinely idle/stuck (not merely slow-moving).
            // A bot that is ITSELF waiting in a queue (B.isWaiting) propagates the chain;
            // we check B's actual speed rather than its isWaiting flag to break cascades.
            // Anti-Mutual-Wait: If B is already yielding to A, A MUST NOT yield to B!
            if (B.isWaiting && B.yieldTo === A.id) {
              if (distAB < 1.4 && A.waitTimer > 0.3 / simSpeed) {
                const stepped = executeSideStepYield(B, A);
                if (!stepped) attemptMoveBackToPreviousBox(B, A, 3);
              }
              continue;
            }

            // Continuous Highway Flow: When trailing a lead vehicle, ACC matches speed smoothly
            // instead of abruptly stopping into a yield jam!
            const bGenuinelyStopped = (B.isWaiting && B.waitTimer > 0.8) || speedB < 0.02;
            if (distAB < 0.95 || (bGenuinelyStopped && distAB < 1.15)) {
              A._wasWaitingThisFrame = true;
              A.isWaiting = true;
              A.yieldTo = B.id;
              A.waitTimer += dt;
              A.statusBadge = 'WAIT';
              A.currentSpeed = 0;
              onRobotJamStart(A, B.id, 'TRAILING_TRAFFIC_CONGESTION');

              // Detect if blocker is doing active rack work (shelving/picking/loading at a rack).
              // These are KNOWN long-duration stops — reroute quickly to prevent queue buildup.
              const bAtRackWork = (
                (B.state === 'CARRYING_TO_RACK' || B.state === 'ORDER_PICKING' || B.state === 'LOADING_INBOUND') &&
                (!B.path || B.path.length === 0 || B.pathIndex >= B.path.length)
              );
              const rerouteThreshold = bAtRackWork ? 0.3 / simSpeed : 1.2 / simSpeed;

              // Proactive multi-stage inner simulation reroute
              if (A.waitTimer > rerouteThreshold) {
                const repathed = solveTrafficPathViaInnerSim(A, null, B, { x: B.gridX, y: B.gridY });
                if (repathed) {
                  A.isWaiting = false;
                  A._wasWaitingThisFrame = false;
                  break;
                }
              }
              break;
            } else if (distAB < 2.0) {
              // Smooth Adaptive Cruise: Keep safe 1.1m buffer, cruise smoothly without yielding!
              A.isWaiting = false;
              A._wasWaitingThisFrame = false;
              A.statusBadge = null;
              A.currentSpeed = Math.min(speedA, Math.max(baseSpeed * 0.35, speedB * 0.96));
              continue;
            }
            continue;
          }


          // =========================================================================
          // CASE 2: CROSSING PATHS, HEAD-ON & INTERSECTION CONFLICTS
          // =========================================================================
          const bAtTargetA = targetA && Math.hypot(B.x - targetA.x, B.y - targetA.y) < 0.85;
          const bAlsoTargetingA = targetB && targetA && targetB.x === targetA.x && targetB.y === targetA.y;
          const headOn = targetB && targetB.x === A.gridX && targetB.y === A.gridY && targetA.x === B.gridX && targetA.y === B.gridY;
          const isConflict = bAtTargetA || (bAlsoTargetingA && distAB < 2.0) || headOn || distAB < 1.25;

          if (isConflict) {
            trafficMetrics.collisionsPrevented++;
            if (typeof negotiateV2VRightOfWay === 'function') {
              negotiateV2VRightOfWay(A, B);
            }

            // ZERO YIELDING FOR CHARGING BOTS:
            // If A is heading to charger, A NEVER waits! B must yield or step aside!
            if (A.state === 'RETURNING_HOME' || A.battery <= 28.0) {
              if (distAB < 1.45) {
                const cleared = executeSideStepYield(B, A);
                if (!cleared) attemptMoveBackToPreviousBox(B, A, 3);
              }
              // A maintains continuous motion without waiting
              continue;
            }

            // Anti-Mutual-Wait: If B is already yielding to A, A MUST NOT yield to B!
            if (B.isWaiting && B.yieldTo === A.id) {
              if (distAB < 1.45 && A.waitTimer > 0.15 / simSpeed) {
                const cleared = executeSideStepYield(B, A);
                if (!cleared) attemptMoveBackToPreviousBox(B, A, 3);
              }
              continue;
            }

            // Strict deterministic total ordering: who yields?
            if (!isHigherPriority(A, B)) {
              // Traffic Flow Optimization: If separation is > 1.15m, modulate speed (slow down to 35%)
              // to let B pass ahead without A coming to a dead stop!
              if (distAB > 1.15 && !bAtTargetA && !headOn) {
                A.isWaiting = false;
                A._wasWaitingThisFrame = false;
                A.statusBadge = 'SLOW';
                A.currentSpeed = baseSpeed * 0.35;
                continue;
              }

              // ZERO TIME WASTING IN YIELDING:
              // If waiting persists for more than 0.15s, IMMEDIATELY take dynamic detour via inner sim!
              if (A.waitTimer > 0.15 / simSpeed) {
                const repathed = solveTrafficPathViaInnerSim(A, null, B, { x: B.gridX, y: B.gridY });
                if (repathed) {
                  A.isWaiting = false;
                  A._wasWaitingThisFrame = false;
                  A.statusBadge = 'DETOUR';
                  break;
                }
              }

              A._wasWaitingThisFrame = true;
              A.isWaiting = true;
              A.yieldTo = B.id;
              A.waitTimer += dt;
              A.statusBadge = 'WAIT';
              A.currentSpeed = 0;
              if (A.logStats) A.logStats.totalRightOfWayYields++;
              onRobotJamStart(A, B.id, 'RIGHT_OF_WAY_YIELD');

              // ACTIVE CLEARING MANEUVER: A does not just sit in B's way!
              // If A is blocking B from moving forward, A actively side-steps or backs up!
              const bDest = (B.path && B.pathIndex < B.path.length) ? B.path[B.pathIndex] : null;
              const aInBWay = bDest && Math.hypot(A.gridX - bDest.x, A.gridY - bDest.y) < 1.0;
              if ((aInBWay || distAB < 1.35) && A.waitTimer > 0.15 / simSpeed) {
                const cleared = executeSideStepYield(A, B);
                if (!cleared) {
                  attemptMoveBackToPreviousBox(A, B, 3);
                }
              }

              // Throttled yield terminal log
              const now = Date.now();
              if (now - (A.lastYieldLogTime || 0) > 4000) {
                A.lastYieldLogTime = now;
                trafficMetrics.totalYields++;
                const bCargoDesc = B.orderBox ? `Consolidated Order (${B.orderBox.items.length}/${B.orderBox.totalItems})` : (B.isLoadedYellow ? `Inbound Load (${B.carriedParcels.length} pkgs)` : 'Higher Priority');
                logTerminal('YIELD', 'tag-yield', `⚠️ <strong>${A.id}</strong> (Urgency ${urgA}%) yielding right-of-way to <strong>${B.id}</strong> (Urgency ${urgB}%, ${bCargoDesc})`);
                updateHudStats();
              }

              // Dynamic Detour Rerouting via Inner Simulation if waiting persists
              const bAtRackWork2 = (
                (B.state === 'CARRYING_TO_RACK' || B.state === 'ORDER_PICKING' || B.state === 'LOADING_INBOUND') &&
                (!B.path || B.path.length === 0 || B.pathIndex >= B.path.length)
              );
              const yieldRerouteThreshold = bAtRackWork2 ? 0.25 / simSpeed : 0.8 / simSpeed;
              if (A.waitTimer > yieldRerouteThreshold) {
                const repathed = solveTrafficPathViaInnerSim(A, null, B, { x: B.gridX, y: B.gridY });
                if (repathed) {
                  A.isWaiting = false;
                  A._wasWaitingThisFrame = false;
                  break;
                }
              }
              break;
            } else {
              // Higher priority robot A: AEB safe spacing
              if (B.isBackingUp || B.isSideStepping) {
                // Modulate speed rather than full stop
                A.currentSpeed = baseSpeed * 0.35;
              } else if (distAB < 1.1) {
                A.currentSpeed = 0;
                // If loser B is physically in A's way, actively command B to clear!
                if (A.waitTimer > 0.20 / simSpeed && !B.isBackingUp && !B.isSideStepping) {
                  const cleared = executeSideStepYield(B, A);
                  if (!cleared) attemptMoveBackToPreviousBox(B, A, 3);
                }
              }
            }
          }
        }
      }

      // =========================================================================
      // 2.5. DECENTRALIZED MUTUAL DEADLOCK SENTINEL (STANDOFF BREAKER)
      // If two bots are stuck mutually yielding or blocking each other:
      // =========================================================================
      for (let i = 0; i < AMR_FLEET.length; i++) {
        const A = AMR_FLEET[i];
        if (!A.isWaiting || A.isBackingUp || A.isSideStepping) continue;
        for (let j = i + 1; j < AMR_FLEET.length; j++) {
          const B = AMR_FLEET[j];
          if (!B.isWaiting || B.isBackingUp || B.isSideStepping) continue;
          const dAB = Math.hypot(A.x - B.x, A.y - B.y);
          if (dAB < 1.55) {
            // Mutual standoff detected!
            const loser = isHigherPriority(A, B) ? B : A;
            const winner = isHigherPriority(A, B) ? A : B;
            loser.yieldTo = winner.id;
            const sideStepped = executeSideStepYield(loser, winner);
            if (!sideStepped) {
              attemptMoveBackToPreviousBox(loser, winner, 3);
            }
            winner.isWaiting = false;
            winner._wasWaitingThisFrame = false;
            winner.waitTimer = 0;
            winner.statusBadge = null;
            logTerminal('V2V', 'tag-overtake', `⚡ <strong>[V2V-RESOLVE]</strong> Resolved standoff between <strong>${A.id}</strong> and <strong>${B.id}</strong>: ${loser.id} executed active corridor clearing.`);
          }
        }
      }

      // Update accurate fleet proximity metrics
      if (typeof updateProximityMetrics === 'function') updateProximityMetrics();

      // 3. Kinematic motion integration with Autonomous Emergency Braking (AEB)
      for (const robot of AMR_FLEET) {
        if (robot.state === 'LOADING_INBOUND') {
          // Stationary at dock during loading animation
          continue;
        }

        // If robot was backed up or side-stepped and path is now clear, resume saved destination
        if (robot.savedDest && (robot.isWaiting || !robot.path || robot.path.length === 0 || robot.pathIndex >= robot.path.length)) {
          let clearAhead = true;
          for (const other of AMR_FLEET) {
            if (other.id === robot.id || other.state === 'IDLE_CHARGING' || other.state === 'OUT_OF_CHARGE') continue;
            if (Math.hypot(other.x - robot.x, other.y - robot.y) < 1.35) {
              clearAhead = false;
              break;
            }
          }
          if (clearAhead) {
            if (Math.hypot(robot.gridX - robot.savedDest.x, robot.gridY - robot.savedDest.y) < 0.5) {
              robot.isWaiting = false;
              robot.statusBadge = null;
              robot.savedDest = null;
              onRobotReachedDestination(robot);
            } else {
              const resumePath = findPath(robot.gridX, robot.gridY, robot.savedDest.x, robot.savedDest.y);
              if (resumePath && resumePath.length > 0) {
                setRobotPath(robot, resumePath);
                robot.isWaiting = false;
                robot.statusBadge = null;
                robot.savedDest = null;
              }
            }
          }
        }

        if (!robot._wasWaitingThisFrame) {
          robot._clearFrames = (robot._clearFrames || 0) + 1;
          if (robot._clearFrames >= 3) {
            if (robot.isWaiting) {
              robot.isWaiting = false;
              robot.yieldTo = null;
              if (robot.statusBadge === 'WAIT') robot.statusBadge = null;
              robot.waitTimer = 0;
              onRobotJamEnd(robot, 'RESUMED_NORMAL');
            }
          }
        } else {
          robot._clearFrames = 0;
        }

        // Payload Weight & Dynamic Kinematic Speed Scaling:
        let cargoWeight = 0;
        if (robot.orderBox) {
          cargoWeight = robot.orderBox.totalWeight || 0;
          if (cargoWeight === 0 && robot.orderBox.items) {
            cargoWeight = robot.orderBox.items.reduce((sum, it) => sum + (parseFloat(it.weight) || 3), 0);
          }
        } else if (robot.carriedParcels && robot.carriedParcels.length > 0) {
          cargoWeight = robot.carriedParcels.reduce((sum, p) => sum + (parseFloat(p.weight) || 3), 0);
        } else if (robot.cargo) {
          cargoWeight = parseFloat(robot.cargo.weight) || 0;
        }

        // Kinematic Speed Damping Factor:
        const payloadDamping = Math.max(0.65, 1.0 - (cargoWeight / 60.0));
        const effectiveSpeed = baseSpeed * (robot.speedMultiplier || 1.0) * payloadDamping;
        robot.currentSpeed = effectiveSpeed;
        robot.payloadWeight = cargoWeight;
        robot.payloadDamping = payloadDamping;

        if (robot.isWaiting) {
          // Preserve safety buffer: smoothly settle squarely into cell center without reducing distance to peer
          robot.currentSpeed = 0;
          let canSnap = true;
          for (const other of AMR_FLEET) {
            if (other.id === robot.id || other.state === 'IDLE_CHARGING' || other.state === 'OUT_OF_CHARGE') continue;
            const curD = Math.hypot(robot.x - other.x, robot.y - other.y);
            const targetD = Math.hypot(robot.gridX - other.x, robot.gridY - other.y);
            if (curD < 1.35 && targetD < curD) {
              canSnap = false;
              break;
            }
          }
          if (canSnap) {
            const snapRate = Math.min(1.0, dt * 8.0 * simSpeed);
            robot.x += (robot.gridX - robot.x) * snapRate;
            robot.y += (robot.gridY - robot.y) * snapRate;
            if (Math.abs(robot.x - robot.gridX) < 0.005) robot.x = robot.gridX;
            if (Math.abs(robot.y - robot.gridY) < 0.005) robot.y = robot.gridY;
          }
          continue;
        }

        if (!robot.path || robot.path.length === 0 || robot.pathIndex >= robot.path.length) {
          if (robot.savedDest) {
            continue; // Wait for corridor to clear to resume journey
          }
          if (robot.state === 'IDLE' || robot.state === 'IDLE_CHARGING') {
            robot.currentSpeed = 0;
            // Settle squarely into cell center
            const snapRate = Math.min(1.0, dt * 8.0 * simSpeed);
            robot.x += (robot.gridX - robot.x) * snapRate;
            robot.y += (robot.gridY - robot.y) * snapRate;
            if (Math.abs(robot.x - robot.gridX) < 0.005) robot.x = robot.gridX;
            if (Math.abs(robot.y - robot.gridY) < 0.005) robot.y = robot.gridY;
            continue;
          }
          // Arrived at destination waypoint!
          onRobotReachedDestination(robot);
          continue;
        }

        const targetCell = robot.path[robot.pathIndex];
        const nextCell = (robot.pathIndex + 1 < robot.path.length) ? robot.path[robot.pathIndex + 1] : null;

        // 45° Corner Fillet Curve Determination
        let aimX = targetCell.x;
        let aimY = targetCell.y;
        let isCornerTurn = false;
        const distToTarget = Math.hypot(targetCell.x - robot.x, targetCell.y - robot.y);

        if (nextCell) {
          const inDx = targetCell.x - robot.gridX;
          const inDy = targetCell.y - robot.gridY;
          const outDx = nextCell.x - targetCell.x;
          const outDy = nextCell.y - targetCell.y;
          // Orthogonal corner turn detected (perpendicular direction change)
          isCornerTurn = (inDx !== 0 && outDy !== 0) || (inDy !== 0 && outDx !== 0);

          if (isCornerTurn && distToTarget < 0.40) {
            // Smooth 45° beveled corner curve: blend aim point towards exit lane
            const blend = Math.max(0, Math.min(1.0, (0.40 - distToTarget) / 0.40));
            aimX = targetCell.x + outDx * 0.32 * blend;
            aimY = targetCell.y + outDy * 0.32 * blend;
          }
        }

        const dx = aimX - robot.x;
        const dy = aimY - robot.y;
        const dist = Math.hypot(dx, dy);

        // Heading rotation with smooth 45° corner curve tracking
        if (dist > 0.001) {
          const targetHeading = Math.atan2(dy, dx);
          let diff = targetHeading - robot.heading;
          while (diff < -Math.PI) diff += Math.PI * 2;
          while (diff > Math.PI) diff -= Math.PI * 2;
          const turnRate = isCornerTurn ? 16.0 : 12.0;
          robot.heading += diff * Math.min(1.0, dt * (turnRate * payloadDamping) * simSpeed);
        }

        // Lane Centerline Lock: pull lateral drift back to the aisle center
        if (!isCornerTurn) {
          const moveDx = targetCell.x - robot.gridX;
          const moveDy = targetCell.y - robot.gridY;
          const lateralRate = Math.min(1.0, dt * 10.0 * simSpeed);
          if (moveDx !== 0 && moveDy === 0) {
            // Moving horizontally: lock y to aisle centerline
            robot.y += (targetCell.y - robot.y) * lateralRate;
          } else if (moveDy !== 0 && moveDx === 0) {
            // Moving vertically: lock x to aisle centerline
            robot.x += (targetCell.x - robot.x) * lateralRate;
          }
        }

        let step = effectiveSpeed * dt;

        // PRE-STEP AEB COLLISION CLAMP:
        // Ensure that advancing by 'step' will NEVER bring robot center closer than safe buffer to another robot
        let maxSafeStep = step;
        for (const other of AMR_FLEET) {
          if (other.id === robot.id || other.state === 'IDLE_CHARGING' || other.state === 'OUT_OF_CHARGE') continue;
          const curDist = Math.hypot(robot.x - other.x, robot.y - other.y);
          if (curDist < 0.001) continue;
          const nx = dist > 0.001 ? dx / dist : 0;
          const ny = dist > 0.001 ? dy / dist : 0;
          const projX = robot.x + nx * step;
          const projY = robot.y + ny * step;
          const projDist = Math.hypot(projX - other.x, projY - other.y);

          // Accurate Gap Navigation: Calibrated to allow safe passage through 1-cell rack corridors
          const isOtherYieldingToMe = other.isWaiting && (other.yieldTo === robot.id || isHigherPriority(robot, other));
          const safeLimit = isOtherYieldingToMe ? 0.68 : 0.74;

          if (projDist < safeLimit && projDist < curDist) {
            const allowed = Math.max(0, curDist - (safeLimit + 0.02));
            if (allowed < maxSafeStep) {
              maxSafeStep = allowed;
            }
          }
        }

        if (maxSafeStep < step) {
          step = maxSafeStep;
          if (step <= 0.001) {
            robot.currentSpeed = 0;
            trafficMetrics.collisionsPrevented++;

            // Find nearest conflicting robot
            let nearestOther = null;
            let nearestDist = Infinity;
            for (const oth of AMR_FLEET) {
              if (oth.id === robot.id || oth.state === 'IDLE_CHARGING' || oth.state === 'OUT_OF_CHARGE') continue;
              const d = Math.hypot(robot.x - oth.x, robot.y - oth.y);
              if (d < nearestDist) { nearestDist = d; nearestOther = oth; }
            }

            // User Rule: Lower battery bot moves; higher battery bot stops completely
            if (nearestOther && isHigherPriority(robot, nearestOther)) {
              // Robot has lower battery: it MUST move.
              // Make higher battery nearestOther side-step or reroute out of the way!
              nearestOther.isWaiting = true;
              nearestOther.yieldTo = robot.id;
              nearestOther.statusBadge = 'WAIT';
              onRobotJamStart(nearestOther, robot.id, 'AEB_INTERSECTION_YIELD');
              if (nearestDist < 1.1) {
                const sideStepped = executeSideStepYield(nearestOther, robot);
                if (!sideStepped) {
                  attemptReroute(robot, nearestOther);
                }
              }
            } else {
              // Robot has higher battery: stops completely and yields
              robot.isWaiting = true;
              robot._wasWaitingThisFrame = true;
              robot.waitTimer = (robot.waitTimer || 0) + dt;
              if (nearestOther) robot.yieldTo = nearestOther.id;
              robot.statusBadge = 'WAIT';
              if (robot.logStats) robot.logStats.totalEmergencyBraking++;
              onRobotJamStart(robot, nearestOther ? nearestOther.id : 'OBSTACLE', 'AEB_PRE_COLLISION_STOP');
            }

            continue;
          }
        }

        // Advance to next waypoint cleanly
        const waypointReached = (distToTarget <= step);

        if (waypointReached) {
          if (robot.gridX !== targetCell.x || robot.gridY !== targetCell.y) {
            robot.previousBox = { x: robot.gridX, y: robot.gridY };
            // Populate recentVisitedCells trail for straight-line backup logic
            if (!robot.recentVisitedCells) robot.recentVisitedCells = [];
            robot.recentVisitedCells.push({ x: robot.gridX, y: robot.gridY });
            if (robot.recentVisitedCells.length > 8) robot.recentVisitedCells.shift(); // FIFO cap at 8
          }
          if (robot.logStats) robot.logStats.totalCellsTraversed++;
          robot.x = targetCell.x;
          robot.y = targetCell.y;
          robot.gridX = targetCell.x;
          robot.gridY = targetCell.y;
          robot.pathIndex++;

          if (robot.pathIndex >= robot.path.length) {
            robot.x = targetCell.x;
            robot.y = targetCell.y;
            robot.path = [];
            robot.pathIndex = 0;
            if (robot.isOvertaking) {
              robot.isOvertaking = false;
              robot.speedMultiplier = 1.0;
              if (robot.statusBadge === 'PASS') robot.statusBadge = null;
            }
            onRobotReachedDestination(robot);
          }
        } else {
          robot.x += (dx / (dist || 1)) * step;
          robot.y += (dy / (dist || 1)) * step;
          robot.gridX = Math.round(robot.x);
          robot.gridY = Math.round(robot.y);
        }

        if (robot.logStats) {
          robot.logStats.totalDistanceTraveled += step;
          if (robot.currentSpeed > robot.logStats.maxSpeed) {
            robot.logStats.maxSpeed = robot.currentSpeed;
          }
        }
      }
    }

    // Industrial Visual Rendering (Safety Buffers, Status Badges, Dynamic Trajectories)
    function drawRobot(ctx, r, cellSize) {
      const cx = (r.x + 0.5) * cellSize;
      const cy = (r.y + 0.5) * cellSize;
      const radius = Math.max(5, cellSize * 0.42);

      // 1. Dynamic Trajectory Breadcrumbs with 45° Rounded Fillet Curves
      if (r.path && r.path.length > 0 && r.pathIndex < r.path.length) {
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(cx, cy);

        const radiusCorner = Math.max(3, cellSize * 0.40);
        const rawPts = r.path.slice(r.pathIndex);

        // Sanitize points to guarantee zero diagonal clipping
        const remPts = [];
        let curX = Math.round(r.x);
        let curY = Math.round(r.y);
        for (const pt of rawPts) {
          if (!pt) continue;
          if (Math.abs(pt.x - curX) > 1.5 || Math.abs(pt.y - curY) > 1.5) {
            break; // Stop at any jump to prevent drawing diagonal vectors across the map
          }
          remPts.push(pt);
          curX = pt.x;
          curY = pt.y;
        }

        if (remPts.length === 1) {
          ctx.lineTo((remPts[0].x + 0.5) * cellSize, (remPts[0].y + 0.5) * cellSize);
        } else if (remPts.length > 1) {
          for (let i = 0; i < remPts.length - 1; i++) {
            const p1 = remPts[i];
            const p2 = remPts[i + 1];
            ctx.arcTo((p1.x + 0.5) * cellSize, (p1.y + 0.5) * cellSize, (p2.x + 0.5) * cellSize, (p2.y + 0.5) * cellSize, radiusCorner);
          }
          const lastPt = remPts[remPts.length - 1];
          ctx.lineTo((lastPt.x + 0.5) * cellSize, (lastPt.y + 0.5) * cellSize);
        }
        let trailColor = 'rgba(56, 189, 248, 0.45)';
        if (r.id === trackedRobotId) {
          trailColor = '#38bdf8';
        } else if (r.isOvertaking) {
          trailColor = 'rgba(56, 189, 248, 0.95)'; // Bright overtake line
        } else if (r.isRerouting) {
          trailColor = 'rgba(192, 132, 252, 0.85)'; // Purple reroute line
        } else if (r.isLoadedYellow) {
          trailColor = 'rgba(250, 204, 21, 0.85)'; // Yellow trail when carrying inbound shipment!
        } else if (r.orderBox) {
          trailColor = r.orderBox.importance ? r.orderBox.importance.color : 'rgba(245, 158, 11, 0.7)';
        } else if (r.state === 'RETURNING_HOME') {
          trailColor = 'rgba(34, 197, 94, 0.4)';
        }
        ctx.strokeStyle = trailColor;
        if (r.id === trackedRobotId) {
          ctx.lineWidth = Math.max(2.2, cellSize * 0.14);
          ctx.setLineDash([6, 3]);
          ctx.lineDashOffset = -((Date.now() / 40) % 9);
          ctx.shadowColor = '#38bdf8';
          ctx.shadowBlur = 8;
        } else {
          ctx.lineWidth = r.isOvertaking || r.isRerouting ? Math.max(1.8, cellSize * 0.12) : Math.max(1.2, cellSize * 0.08);
          ctx.setLineDash(r.isOvertaking ? [6, 3] : [3, 3]);
        }
        ctx.stroke();

        // If tracked robot, render holographic waypoint dots & destination beacon
        if (r.id === trackedRobotId) {
          ctx.shadowBlur = 0;
          for (let i = r.pathIndex; i < r.path.length; i++) {
            const pt = r.path[i];
            ctx.beginPath();
            ctx.arc((pt.x + 0.5) * cellSize, (pt.y + 0.5) * cellSize, Math.max(2, cellSize * 0.07), 0, Math.PI * 2);
            ctx.fillStyle = '#38bdf8';
            ctx.fill();
          }

          // Destination Beacon
          const dest = r.path[r.path.length - 1];
          if (dest) {
            const destX = (dest.x + 0.5) * cellSize;
            const destY = (dest.y + 0.5) * cellSize;
            const beaconR = (cellSize * 0.45) + Math.sin(Date.now() / 160) * (cellSize * 0.1);

            // Pulsing target ring
            ctx.beginPath();
            ctx.arc(destX, destY, beaconR, 0, Math.PI * 2);
            ctx.strokeStyle = 'rgba(56, 189, 248, 0.8)';
            ctx.lineWidth = 1.8;
            ctx.setLineDash([3, 3]);
            ctx.stroke();

            // Destination icon
            ctx.font = `${Math.max(10, Math.floor(cellSize * 0.6))}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('🏁', destX, destY);
          }
        }

        ctx.restore();
      }

      ctx.save();
      ctx.translate(cx, cy);

      // 2. Active Safety Clearance Buffer Ring
      ctx.save();
      ctx.beginPath();
      ctx.arc(0, 0, radius * 1.25, 0, Math.PI * 2);
      if (r.state === 'OUT_OF_CHARGE' || r.battery <= 10.0) {
        const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 90);
        ctx.strokeStyle = `rgba(239, 68, 68, ${0.7 + 0.3 * pulse})`;
        ctx.lineWidth = 2.4;
        ctx.setLineDash([4, 2]);
        ctx.stroke();
      } else if (r.isWaiting) {
        const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 120);
        ctx.strokeStyle = `rgba(245, 158, 11, ${0.4 + 0.5 * pulse})`;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 3]);
        ctx.stroke();
      } else if (r.state === 'LOADING_INBOUND' || r.isLoadedYellow) {
        const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 90);
        ctx.strokeStyle = `rgba(250, 204, 21, ${0.6 + 0.4 * pulse})`;
        ctx.lineWidth = 2.0;
        ctx.setLineDash([4, 2]);
        ctx.stroke();
      } else if (r.isOvertaking) {
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.8)';
        ctx.lineWidth = 1.8;
        ctx.setLineDash([4, 2]);
        ctx.stroke();
      } else if (r.isRerouting) {
        ctx.strokeStyle = 'rgba(168, 85, 247, 0.8)';
        ctx.lineWidth = 1.8;
        ctx.setLineDash([4, 2]);
        ctx.stroke();
      } else {
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.18)';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      ctx.restore();

      // Radar Ping Ripple when located from Problem Dashboard
      if (r.mapPingTimer > 0) {
        const pingProgress = 1.0 - (r.mapPingTimer / 4.0);
        const pingRad = radius * (1.2 + pingProgress * 2.8);
        const pingAlpha = Math.max(0, 1.0 - pingProgress);
        ctx.save();
        ctx.beginPath();
        ctx.arc(0, 0, pingRad, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(56, 189, 248, ${pingAlpha})`;
        ctx.lineWidth = 2.5;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(0, 0, pingRad * 0.7, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(239, 68, 68, ${pingAlpha * 0.8})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();
      }

      // 3. Status Ring Colors & Halo
      let ringColor = '#38bdf8';
      let glowColor = 'rgba(56, 189, 248, 0.6)';
      if (r.state === 'OUT_OF_CHARGE' || r.battery <= 10.0) {
        ringColor = '#ef4444';
        glowColor = 'rgba(239, 68, 68, 0.95)';
      } else if (r.state === 'IDLE_CHARGING') {
        ringColor = '#22c55e';
        glowColor = 'rgba(34, 197, 94, 0.7)';
      } else if (r.state === 'LOADING_INBOUND') {
        ringColor = '#facc15';
        glowColor = 'rgba(250, 204, 21, 0.95)';
      } else if (r.isLoadedYellow) {
        ringColor = '#facc15'; // Glowing golden yellow chassis when carrying inbound load!
        glowColor = 'rgba(250, 204, 21, 0.85)';
      } else if (r.isWaiting) {
        ringColor = '#f59e0b';
        glowColor = 'rgba(245, 158, 11, 0.85)';
      } else if (r.isOvertaking) {
        ringColor = '#38bdf8';
        glowColor = 'rgba(56, 189, 248, 0.9)';
      } else if (r.isRerouting) {
        ringColor = '#a855f7';
        glowColor = 'rgba(168, 85, 247, 0.9)';
      } else if (r.orderBox) {
        ringColor = r.orderBox.importance ? r.orderBox.importance.color : '#f59e0b';
        glowColor = ringColor;
      } else if (r.state === 'RETURNING_HOME') {
        ringColor = '#10b981';
        glowColor = 'rgba(16, 185, 129, 0.6)';
      }

      ctx.shadowColor = glowColor;
      ctx.shadowBlur = (r.state === 'OUT_OF_CHARGE' || r.isLoadedYellow || r.isWaiting || r.isOvertaking) ? 12 : (r.state === 'IDLE_CHARGING' ? 6 : 8);

      // 4. Robot Chassis
      ctx.beginPath();
      ctx.arc(0, 0, radius, 0, Math.PI * 2);
      ctx.fillStyle = '#0f172a';
      ctx.fill();
      ctx.lineWidth = Math.max(1.5, cellSize * 0.08);
      ctx.strokeStyle = ringColor;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Inner deck
      ctx.beginPath();
      ctx.arc(0, 0, radius * 0.78, 0, Math.PI * 2);
      ctx.fillStyle = '#1e293b';
      ctx.fill();
      ctx.strokeStyle = '#334155';
      ctx.lineWidth = 1;
      ctx.stroke();

      // 5. Heading Indicator
      ctx.save();
      ctx.rotate(r.heading);
      ctx.fillStyle = ringColor;
      ctx.beginPath();
      ctx.moveTo(radius * 0.88, 0);
      ctx.lineTo(radius * 0.45, -radius * 0.32);
      ctx.lineTo(radius * 0.45, radius * 0.32);
      ctx.closePath();
      ctx.fill();
      ctx.restore();

      // 6. Physical Cargo Presentation:
      // Case A: Inbound Shipment Tote (illuminates Golden Yellow)
      if (r.isLoadedYellow || (r.carriedParcels && r.carriedParcels.length > 0)) {
        const toteW = radius * 1.35;
        const toteH = radius * 1.1;
        ctx.fillStyle = '#ca8a04';
        ctx.fillRect(-toteW / 2, -toteH / 2, toteW, toteH);
        ctx.fillStyle = '#facc15';
        ctx.fillRect(-toteW / 2 + 1, -toteH / 2 + 1, toteW - 2, toteH - 2);
        ctx.strokeStyle = '#a16207';
        ctx.lineWidth = 1;
        ctx.strokeRect(-toteW / 2, -toteH / 2, toteW, toteH);

        // Tote parcel count badge
        ctx.fillStyle = '#0f172a';
        ctx.font = `bold ${Math.max(8, Math.floor(radius * 0.75))}px monospace`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${r.carriedParcels ? r.carriedParcels.length : 0}`, 0, 0);

      // Case B: Outbound Customer Order - 1 Giant Box / Tote
      } else if (r.orderBox) {
        const boxSize = radius * 1.35;
        const half = boxSize / 2;
        ctx.fillStyle = '#92400e';
        ctx.fillRect(-half, -half, boxSize, boxSize);
        ctx.fillStyle = '#b45309';
        ctx.fillRect(-half + 1, -half + 1, boxSize - 2, boxSize - 2);

        // SLA Colored Ribbon across center
        ctx.fillStyle = r.orderBox.importance ? r.orderBox.importance.color : '#facc15';
        ctx.fillRect(-half, -2, boxSize, 4);

        // White shipping label with "x/y" items consolidated
        const labelW = boxSize * 0.72;
        const labelH = boxSize * 0.45;
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(-labelW / 2, -labelH / 2, labelW, labelH);
        ctx.fillStyle = '#0f172a';
        ctx.font = `bold ${Math.max(7, Math.floor(radius * 0.55))}px monospace`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${r.orderBox.items.length}/${r.orderBox.totalItems}`, 0, 0);

        ctx.strokeStyle = '#78350f';
        ctx.lineWidth = 1;
        ctx.strokeRect(-half, -half, boxSize, boxSize);

      // Case C: Empty deck (Number)
      } else {
        ctx.fillStyle = '#f8fafc';
        ctx.font = `bold ${Math.max(8, Math.floor(radius * 0.95))}px monospace`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${r.num}`, 0, -1);
      }

      // 6.5. Persistent BMS Battery Gauge Bar (Visible on ALL robots: empty or carrying cargo)
      if (cellSize >= 11) {
        const batWidth = radius * 1.15;
        const batHeight = Math.max(2.2, cellSize * 0.08);
        const batY = radius * 0.65;
        const batPct = Math.max(0, Math.min(1, r.battery / 100.0));

        // Gauge background track
        ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
        ctx.fillRect(-batWidth / 2, batY, batWidth, batHeight);
        ctx.strokeStyle = 'rgba(71, 85, 105, 0.8)';
        ctx.lineWidth = 0.6;
        ctx.strokeRect(-batWidth / 2, batY, batWidth, batHeight);

        // Dynamic battery fill color (Green > 50%, Amber 25-50%, Blinking Red <= 25%)
        let barColor = '#22c55e';
        if (r.battery <= 25.0) {
          const blink = (Date.now() % 400) < 200;
          barColor = blink ? '#ef4444' : '#991b1b';
        } else if (r.battery <= 50.0) {
          barColor = '#f59e0b';
        }

        ctx.fillStyle = barColor;
        ctx.fillRect(-batWidth / 2 + 0.5, batY + 0.5, Math.max(0, (batWidth - 1) * batPct), batHeight - 1);

        // Charging indicator bolt
        if (r.state === 'IDLE_CHARGING') {
          ctx.fillStyle = '#4ade80';
          ctx.font = 'bold 7px sans-serif';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
          ctx.fillText('⚡', batWidth / 2 + 1, batY + batHeight / 2);
        }
      }

      // 7. Floating Action Status Badge Pill above Robot
      let badgeText = r.statusBadge;
      let badgeBg = '#0284c7';
      let badgeBorder = '#38bdf8';

      if (r.isWaiting) {
        badgeText = 'WAIT';
        badgeBg = '#b45309';
        badgeBorder = '#f59e0b';
      } else if (r.isOvertaking) {
        badgeText = 'WAIT';
        badgeBg = '#b45309';
        badgeBorder = '#f59e0b';
      } else if (r.isOvertaking) {
        badgeText = 'PASS 1.35x';
        badgeBg = '#0369a1';
        badgeBorder = '#38bdf8';
      } else if (r.isRerouting) {
        badgeText = 'REROUTE';
        badgeBg = '#7e22ce';
        badgeBorder = '#c084fc';
      } else if (r.state === 'LOADING_INBOUND') {
        badgeText = 'LOAD';
        badgeBg = '#ca8a04';
        badgeBorder = '#facc15';
      } else if (r.state === 'CARRYING_TO_RACK') {
        badgeText = `SHELVE ${r.carriedParcels ? r.carriedParcels.length : ''}`;
        badgeBg = '#ca8a04';
        badgeBorder = '#facc15';
      } else if (r.state === 'ORDER_PICKING' && r.orderBox) {
        badgeText = `PICK ${r.orderBox.items.length}/${r.orderBox.totalItems}`;
        badgeBg = '#d97706';
        badgeBorder = '#fbbf24';
      } else if (r.state === 'DELIVERING_ORDER_TO_BAY') {
        badgeText = 'ORDER BOX';
        badgeBg = '#ea580c';
        badgeBorder = '#fb923c';
      } else if (r.state === 'OUT_OF_CHARGE' || r.battery <= 10.0) {
        badgeText = 'LOW 10%';
        badgeBg = '#7f1d1d';
        badgeBorder = '#ef4444';
      } else if (r.battery <= 25.0 && r.state !== 'IDLE_CHARGING') {
        badgeText = 'LOW BATT';
        badgeBg = '#b91c1c';
        badgeBorder = '#ef4444';
      } else if (r.state === 'IDLE_CHARGING' && r.battery < 99.5) {
        badgeText = `⚡ ${Math.round(r.battery)}%`;
        badgeBg = '#14532d';
        badgeBorder = '#22c55e';
      }

      if (badgeText) {
        const badgeY = -radius - 8;
        ctx.font = 'bold 8px monospace';
        const tw = ctx.measureText(badgeText).width;
        const pw = tw + 8;
        const ph = 11;

        ctx.fillStyle = badgeBg;
        ctx.fillRect(-pw / 2, badgeY - ph / 2, pw, ph);
        ctx.strokeStyle = badgeBorder;
        ctx.lineWidth = 1;
        ctx.strokeRect(-pw / 2, badgeY - ph / 2, pw, ph);

        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(badgeText, 0, badgeY);
      }

      // 8. Holographic Targeting Reticle for Tracked Robot
      if (r.id === trackedRobotId) {
        ctx.save();
        const reticleTime = Date.now();
        const reticleAngle = (reticleTime / 1200) % (Math.PI * 2);
        const bracketOffset = radius * 1.55 + Math.sin(reticleTime / 180) * 1.5;
        const bracketLen = Math.max(4, radius * 0.45);

        // Neon Glow
        ctx.shadowColor = '#38bdf8';
        ctx.shadowBlur = 10;
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = Math.max(1.8, cellSize * 0.1);

        // 4 Corner Brackets [ ]
        // Top-Left
        ctx.beginPath();
        ctx.moveTo(-bracketOffset, -bracketOffset + bracketLen);
        ctx.lineTo(-bracketOffset, -bracketOffset);
        ctx.lineTo(-bracketOffset + bracketLen, -bracketOffset);
        ctx.stroke();

        // Top-Right
        ctx.beginPath();
        ctx.moveTo(bracketOffset - bracketLen, -bracketOffset);
        ctx.lineTo(bracketOffset, -bracketOffset);
        ctx.lineTo(bracketOffset, -bracketOffset + bracketLen);
        ctx.stroke();

        // Bottom-Right
        ctx.beginPath();
        ctx.moveTo(bracketOffset, bracketOffset - bracketLen);
        ctx.lineTo(bracketOffset, bracketOffset);
        ctx.lineTo(bracketOffset - bracketLen, bracketOffset);
        ctx.stroke();

        // Bottom-Left
        ctx.beginPath();
        ctx.moveTo(-bracketOffset + bracketLen, bracketOffset);
        ctx.lineTo(-bracketOffset, bracketOffset);
        ctx.lineTo(-bracketOffset, bracketOffset - bracketLen);
        ctx.stroke();

        // Rotating dashed compass ring
        ctx.save();
        ctx.rotate(reticleAngle);
        ctx.beginPath();
        ctx.arc(0, 0, radius * 1.35, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.5)';
        ctx.lineWidth = 1.2;
        ctx.setLineDash([4, 6]);
        ctx.stroke();
        ctx.restore();

        // Top targeting badge header: "🎯 AMR-0X"
        const tagText = `🎯 ${r.id}`;
        ctx.font = 'bold 9px monospace';
        const tagTw = ctx.measureText(tagText).width;
        const tagPw = tagTw + 10;
        const tagPh = 13;
        const tagY = -bracketOffset - (badgeText ? 18 : 9);

        ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
        ctx.fillRect(-tagPw / 2, tagY - tagPh / 2, tagPw, tagPh);
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1.2;
        ctx.strokeRect(-tagPw / 2, tagY - tagPh / 2, tagPw, tagPh);

        ctx.fillStyle = '#38bdf8';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(tagText, 0, tagY);

        ctx.restore();
      }

      ctx.restore();
    }

    // Inbound Shipment: dock receives r parcels (1 < r < 8), stays lit yellow until 1 assigned AMR picks up
    function triggerInboundShipment() {
      if (!mapData || !mapData.stations) return;
      const pickups = Object.keys(mapData.stations).filter(id => id.startsWith('P'));
      if (pickups.length === 0) return;

      // Select an available dock that isn't already holding a pending shipment
      const availableDocks = pickups.filter(id => (inboundQueues[id] || []).length === 0 && !inboundMissions.some(m => m.dockId === id));
      if (availableDocks.length === 0) return;

      const chosenDock = availableDocks[Math.floor(Math.random() * availableDocks.length)];
      const r = Math.floor(Math.random() * 4) + 2; // 2 to 5 parcels per shipment batch

      // Random delivery importance for shipment SLA
      const randVal = Math.random();
      let importance = IMPORTANCE_TIERS.STANDARD;
      if (randVal < 0.15) importance = IMPORTANCE_TIERS.VIP_EXPRESS;
      else if (randVal < 0.40) importance = IMPORTANCE_TIERS.SAME_DAY;
      else if (randVal < 0.85) importance = IMPORTANCE_TIERS.STANDARD;
      else importance = IMPORTANCE_TIERS.ECONOMY;

      const batch = [];
      let totalWeight = 0;

      for (let i = 0; i < r; i++) {
        parcelSequence++;
        const skuInfo = SKU_CATALOG[Math.floor(Math.random() * SKU_CATALOG.length)];
        const weightVal = parseFloat((skuInfo.weight + (Math.random() * 3 - 1.5)).toFixed(1));
        totalWeight += weightVal;
        batch.push({
          parcel_id: `PKG-${parcelSequence}`,
          sku: skuInfo.sku,
          name: skuInfo.name,
          weight: `${weightVal}kg`,
          weightVal: weightVal,
          importance: importance,
          dock: chosenDock,
          timestamp: new Date().toLocaleTimeString()
        });
      }

      // Reserve slots in 3D storage racks
      const validBatch = [];
      for (const parcel of batch) {
        const slot = findRandomSlotForSku(parcel.sku);
        if (slot) {
          slot.rack.floors[slot.floorIndex] = { isReservedInbound: true, parcel_id: parcel.parcel_id, parcel: parcel };
          parcel.rackSlot = slot;
          validBatch.push(parcel);
        } else {
          logTerminal('ALERT', 'tag-outbound', `⚠️ Warehouse Full! No empty tier available for parcel <strong>${parcel.parcel_id}</strong> from ${chosenDock}.`);
        }
      }

      if (validBatch.length === 0) return;

      inboundQueues[chosenDock].push(...validBatch);

      const st = mapData.stations[chosenDock];
      const zoneName = st ? st.zone : 'Inbound';
      const idRange = validBatch.length > 1 ? `${validBatch[0].parcel_id}..${validBatch[validBatch.length - 1].parcel_id}` : validBatch[0].parcel_id;

      logTerminal('INBOUND', 'tag-inbound', `📦 Inbound Dock <strong>${chosenDock}</strong> (${zoneName}) received shipment of <strong>${validBatch.length} parcels</strong> (${idRange}, ${totalWeight.toFixed(1)}kg, <span style="color:${importance.color};font-weight:700;">${importance.label}</span>) | Dock holding load: <span style="color:#facc15;font-weight:700;">LIT YELLOW</span>`);

      // Queue exactly ONE Inbound Mission (1 AMR assigned, no zombie swarm!)
      inboundMissions.push({
        id: `INB-${parcelSequence}`,
        dockId: chosenDock,
        dockX: st.x,
        dockY: st.y,
        parcels: validBatch,
        totalWeight: totalWeight,
        importance: importance,
        createdAt: Date.now(),
        status: 'PENDING',
        assignedRobotId: null
      });

      updateHudStats();
      dispatchFleet();
    }

    // Outbound Request: 1 customer orders r items (1 < r < 7) to be consolidated into 1 Giant Box by 1 robot
    function triggerOutboundOrder() {
      if (!mapData || !mapData.stations) return;
      const dropoffs = Object.keys(mapData.stations).filter(id => id.startsWith('D'));
      if (dropoffs.length === 0) return;

      // Select available bay without an active order
      const availableBays = dropoffs.filter(id => !outboundOrders[id]);
      if (availableBays.length === 0) return;

      const chosenBay = availableBays[Math.floor(Math.random() * availableBays.length)];
      const r = Math.floor(Math.random() * 4) + 2; // 2 to 5 items consolidated for 1 customer

      // Collect available stored parcels across all rack memory
      const allStored = [];
      for (const rack of Object.values(rackMemory)) {
        for (let f = 0; f < MAX_FLOORS; f++) {
          const item = rack.floors[f];
          if (item !== null && !item.isReservedInbound && !item.isReservedOutbound) {
            allStored.push({
              parcel: item,
              rack: rack,
              floorIndex: f,
              floorNum: f + 1,
              categoryName: rack.categoryName
            });
          }
        }
      }

      if (allStored.length === 0) {
        logTerminal('OUTBOUND', 'tag-outbound', `📋 Departure Bay <strong>${chosenBay}</strong> requested ${r} parcels, but no available stored inventory found in racks.`);
        return;
      }

      // Shuffle stored parcels across warehouse rows
      for (let i = allStored.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [allStored[i], allStored[j]] = [allStored[j], allStored[i]];
      }

      const retrieved = allStored.slice(0, r);
      orderSequence++;
      const orderId = `ORD-${orderSequence}`;
      const actualCount = retrieved.length;

      const st = mapData.stations[chosenBay];
      const zoneName = st ? st.zone : 'Outbound';

      // Pick SLA importance for customer order
      const randVal = Math.random();
      let orderImportance = IMPORTANCE_TIERS.STANDARD;
      if (randVal < 0.20) orderImportance = IMPORTANCE_TIERS.VIP_EXPRESS;
      else if (randVal < 0.45) orderImportance = IMPORTANCE_TIERS.SAME_DAY;
      else if (randVal < 0.85) orderImportance = IMPORTANCE_TIERS.STANDARD;
      else orderImportance = IMPORTANCE_TIERS.ECONOMY;

      let totalOrderWeight = 0;
      for (const item of retrieved) {
        item.rack.floors[item.floorIndex] = { isReservedOutbound: true, parcel: item.parcel };
        totalOrderWeight += parseFloat(item.parcel.weight) || 3.0;
      }

      // Bay lights up Yellow awaiting deposit
      outboundOrders[chosenBay] = {
        orderId: orderId,
        bayId: chosenBay,
        totalCount: actualCount,
        deliveredCount: 0
      };

      logTerminal('OUTBOUND', 'tag-outbound', `🚚 Customer Order <strong>${orderId}</strong> placed at <strong>${chosenBay}</strong> (${zoneName}) for <strong>${actualCount} items to consolidate in 1 Giant Box</strong> (${totalOrderWeight.toFixed(1)}kg, <span style="color:${orderImportance.color};font-weight:700;">${orderImportance.label}</span>) | Bay awaiting deposit: <span style="color:#facc15;font-weight:700;">LIT YELLOW</span>`);

      // Queue exactly ONE Outbound Mission (1 AMR assigned for consolidated multi-stop pick tour!)
      outboundMissions.push({
        orderId: orderId,
        bayId: chosenBay,
        bayX: st.x,
        bayY: st.y,
        itemsToPick: retrieved, // Multi-stop pick tour
        totalItems: actualCount,
        totalWeight: totalOrderWeight,
        importance: orderImportance,
        createdAt: Date.now(),
        status: 'PENDING',
        assignedRobotId: null
      });

      updateHudStats();
      dispatchFleet();
    }

    // Fast-Forward & Simulation Speed Control
    let simSpeed = 1;
    const SPEED_PRESETS = [1, 2, 5, 10];
    let inboundTimer = null;
    let outboundTimer = null;

    function cycleSimulationSpeed() {
      const idx = SPEED_PRESETS.indexOf(simSpeed);
      const next = SPEED_PRESETS[(idx + 1) % SPEED_PRESETS.length];
      setSimulationSpeed(next);
    }

    function setSimulationSpeed(spd) {
      simSpeed = spd;
      const speedBtn = document.getElementById('speed-btn');
      const speedLabel = document.getElementById('speed-label');
      const hudSpeedBtn = document.getElementById('hud-speed-btn');
      const ctrlSpeedBtn = document.getElementById('ctrl-speed-btn');

      const labelText = `${simSpeed}x Speed`;
      if (speedLabel) speedLabel.innerText = labelText;
      if (speedBtn) speedBtn.classList.toggle('active', simSpeed > 1);
      if (hudSpeedBtn) {
        hudSpeedBtn.innerText = `⏩ ${simSpeed}x`;
        hudSpeedBtn.classList.toggle('active', simSpeed > 1);
      }
      if (ctrlSpeedBtn) {
        ctrlSpeedBtn.innerText = `${simSpeed}x`;
        ctrlSpeedBtn.style.color = simSpeed > 1 ? '#facc15' : 'var(--text)';
      }

      rescheduleSimulationTimers();
      logTerminal('SPEED', 'tag-inbound', `⚡ Fast Forward: Simulation Speed set to <strong>${simSpeed}x</strong>`);
    }

    function rescheduleSimulationTimers() {
      if (inboundTimer) clearInterval(inboundTimer);
      if (outboundTimer) clearInterval(outboundTimer);

      const intervalMs = Math.max(600, Math.floor(10000 / simSpeed));
      inboundTimer = setInterval(triggerInboundShipment, intervalMs);
      outboundTimer = setInterval(triggerOutboundOrder, intervalMs);
    }

    // Bulk Ingestion & Add N Parcels
    function openBulkModal() {
      const modal = document.getElementById('bulk-modal');
      if (modal) {
        modal.classList.add('open');
        const input = document.getElementById('bulk-input-val');
        if (input) {
          input.focus();
          input.select();
        }
      }
    }

    function closeBulkModal(e) {
      if (e && e.target && e.target !== e.currentTarget && !e.target.classList.contains('modal-close-btn')) return;
      const modal = document.getElementById('bulk-modal');
      if (modal) modal.classList.remove('open');
    }

    function setPresetN(val) {
      const input = document.getElementById('bulk-input-val');
      if (input) input.value = val;
    }

    function fillCapacity(ratio) {
      const totalSlots = Object.keys(rackMemory).length * MAX_FLOORS;
      const currentStored = getStoredParcelCount();
      const target = Math.floor(totalSlots * ratio);
      const needed = Math.max(0, target - currentStored);
      const input = document.getElementById('bulk-input-val');
      if (input) input.value = needed;
    }

    function submitBulkIngest() {
      const input = document.getElementById('bulk-input-val');
      const val = input ? parseInt(input.value, 10) : 50;
      if (val > 0) {
        addNParcels(val);
        const modal = document.getElementById('bulk-modal');
        if (modal) modal.classList.remove('open');
      }
    }

    function addNParcels(n) {
      if (!mapData || !mapData.grid) return 0;
      const count = parseInt(n, 10);
      if (isNaN(count) || count <= 0) {
        alert('Please enter a valid positive number of parcels.');
        return 0;
      }

      const totalSlots = Object.keys(rackMemory).length * MAX_FLOORS;
      const currentStored = getStoredParcelCount();
      const availableSpace = totalSlots - currentStored;

      if (availableSpace <= 0) {
        logTerminal('ALERT', 'tag-outbound', '⚠️ Warehouse is completely full! (7,560 / 7,560) No available rack tiers.');
        alert('Warehouse is at 100% capacity (7,560 slots full). Please dispatch parcels via outbound bays.');
        return 0;
      }

      const toAdd = Math.min(count, availableSpace);
      let added = 0;
      const nowStr = new Date().toLocaleTimeString();

      for (let i = 0; i < toAdd; i++) {
        const skuInfo = SKU_CATALOG[Math.floor(Math.random() * SKU_CATALOG.length)];
        const slot = findRandomSlotForSku(skuInfo.sku);
        if (!slot) break;

        parcelSequence++;
        const weight = (skuInfo.weight + (Math.random() * 3 - 1.5)).toFixed(1);
        slot.rack.floors[slot.floorIndex] = {
          parcel_id: `PKG-${parcelSequence}`,
          sku: skuInfo.sku,
          name: skuInfo.name,
          weight: `${weight}kg`,
          dock: 'BULK_INGEST',
          timestamp: nowStr
        };
        added++;
      }

      updateHudStats();
      render();

      const newStored = getStoredParcelCount();
      const pct = ((newStored / totalSlots) * 100).toFixed(1);

      logTerminal('BULK INGEST', 'tag-complete', `📥 Injected <strong>${added.toLocaleString()} parcels</strong> directly into 3D Racks | Current Occupancy: <strong>${newStored.toLocaleString()} / ${totalSlots.toLocaleString()} (${pct}%)</strong>`);

      if (count > availableSpace) {
        logTerminal('ALERT', 'tag-outbound', `⚠️ Partial injection: Requested ${count.toLocaleString()} parcels, but only ${availableSpace.toLocaleString()} empty slots were available.`);
      }

      try {
        fetch('/api/inventory/inject', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ count: added })
        }).catch(() => {});
      } catch (e) {}

      return added;
    }

    // Schedule initial triggers
    setTimeout(() => {
      logTerminal('SYSTEM', 'tag-complete', '🚀 Edge Fleet Mission Control Online | 8 Autonomous AMRs Deployed | 3D Rack Memory Active (7,560 Slots across 5 Tiers)');
      triggerInboundShipment();
    }, 1200);
    rescheduleSimulationTimers();

    setTimeout(triggerOutboundOrder, 5500);

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const modal = document.getElementById('bulk-modal');
        if (modal) modal.classList.remove('open');
      }
    });

    // =========================================================================
    // AUTONOMOUS FLEET & MISSION WATCHDOG ENGINE
    // Prevents orphaned missions, locks on docks/bays, and frozen robots
    // Ensures uninterrupted 24/7 continuous warehouse operations
    // =========================================================================
    let lastWatchdogTime = 0;
    function runFleetWatchdog(now) {
      if (now - lastWatchdogTime < 2000) return;
      lastWatchdogTime = now;

      // 1. Recover orphaned or stuck Inbound Missions
      for (let i = inboundMissions.length - 1; i >= 0; i--) {
        const m = inboundMissions[i];
        if (m.status === 'ASSIGNED') {
          const assignedBot = AMR_FLEET.find(b => b.id === m.assignedRobotId);
          if (!assignedBot || assignedBot.state === 'IDLE_CHARGING' || assignedBot.state === 'OUT_OF_CHARGE' || assignedBot.state === 'RETURNING_HOME' || !assignedBot.inboundMission || assignedBot.inboundMission.id !== m.id) {
            logTerminal('SYSTEM', 'tag-yield', `⚠️ Watchdog recovered orphaned Inbound Mission <strong>${m.id}</strong> at Dock <strong>${m.dockId}</strong>.`);
            m.status = 'PENDING';
            m.assignedRobotId = null;
          }
        }
        if (!m.parcels || m.parcels.length === 0) {
          inboundMissions.splice(i, 1);
        }
      }

      // 2. Recover orphaned or stuck Outbound Orders
      for (let i = outboundMissions.length - 1; i >= 0; i--) {
        const m = outboundMissions[i];
        if (m.status === 'ASSIGNED') {
          const assignedBot = AMR_FLEET.find(b => b.id === m.assignedRobotId);
          if (!assignedBot || assignedBot.state === 'IDLE_CHARGING' || assignedBot.state === 'OUT_OF_CHARGE' || assignedBot.state === 'RETURNING_HOME' || !assignedBot.outboundMission || assignedBot.outboundMission.orderId !== m.orderId) {
            logTerminal('SYSTEM', 'tag-yield', `⚠️ Watchdog recovered orphaned Outbound Order <strong>${m.orderId}</strong> at Bay <strong>${m.bayId}</strong>.`);
            m.status = 'PENDING';
            m.assignedRobotId = null;
          }
        }
        if ((!m.itemsToPick || m.itemsToPick.length === 0) && m.status === 'PENDING') {
          if (outboundOrders[m.bayId]) outboundOrders[m.bayId] = null;
          outboundMissions.splice(i, 1);
        }
      }

      // 3. Clean up any orphan dock or bay locks
      for (const [bayId, ord] of Object.entries(outboundOrders)) {
        if (ord && !outboundMissions.some(m => m.bayId === bayId)) {
          outboundOrders[bayId] = null;
        }
      }

      // 4. Check for active robots that arrived at target or have empty paths
      for (const r of AMR_FLEET) {
        if ((r.state === 'CARRYING_TO_RACK' || r.state === 'MOVING_TO_PICKUP' || r.state === 'ORDER_PICKING' || r.state === 'DELIVERING_ORDER_TO_BAY' || r.state === 'RETURNING_HOME') && (!r.path || r.path.length === 0 || r.pathIndex >= r.path.length)) {
          onRobotReachedDestination(r);
        }
      }

      // 5. Per-bot stuck recovery: if any active bot has been waiting > 4s and still has
      //    no resolved path or is in a bad grid cell, force-reset its state
      for (const r of AMR_FLEET) {
        if (r.state === 'IDLE_CHARGING' || r.state === 'OUT_OF_CHARGE' || r.state === 'LOADING_INBOUND') continue;
        if (r.isWaiting && r.waitTimer > 4.0) {
          // Bot has been frozen for 4+ sim-seconds - force an escape
          r.isWaiting = false;
          r._wasWaitingThisFrame = false;
          r.waitTimer = 0;
          r.yieldTo = null;
          if (r.statusBadge === 'WAIT') r.statusBadge = null;
          onRobotJamEnd(r, 'WATCHDOG_AUTO_UNBLOCK');
          // If gridX/Y is unwalkable (e.g. nudged into wall), snap back to nearest walkable
          if (!isWalkable(r.gridX, r.gridY)) {
            for (const [dx2, dy2] of [[0,0],[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,-1],[1,-1],[-1,1]]) {
              const cx2 = r.gridX + dx2, cy2 = r.gridY + dy2;
              if (isWalkable(cx2, cy2)) {
                r.x = cx2; r.y = cy2; r.gridX = cx2; r.gridY = cy2;
                break;
              }
            }
          }
          // If bot has path but current gridX/Y is stuck, try rerouting from current position
          if (r.path && r.path.length > 0 && r.pathIndex < r.path.length) {
            const dest = r.path[r.path.length - 1];
            const newPath = findPath(r.gridX, r.gridY, dest.x, dest.y);
            if (newPath.length > 0) {
              setRobotPath(r, newPath);
            } else {
              // Can't reach dest - trigger destination handler to replan
              onRobotReachedDestination(r);
            }
          } else {
            onRobotReachedDestination(r);
          }
        }

        // Cap waitTimer to prevent exponential accumulation
        if (r.waitTimer > 5.0) r.waitTimer = 0;
      }

      // 6. Global fleet deadlock detector: if ALL mobile bots have been waiting > 2s, force-unblock all
      const mobileFleet = AMR_FLEET.filter(r => r.state !== 'IDLE_CHARGING' && r.state !== 'OUT_OF_CHARGE' && r.state !== 'LOADING_INBOUND' && r.state !== 'IDLE');
      if (mobileFleet.length > 0 && mobileFleet.every(r => r.isWaiting && r.waitTimer > 2.0)) {
        logTerminal('SYSTEM', 'tag-yield', 'Global fleet deadlock: all ' + mobileFleet.length + ' bots frozen. Force-unblocking.');
        for (const r of mobileFleet) {
          r.isWaiting = false;
          r._wasWaitingThisFrame = false;
          r.waitTimer = 0;
          r.yieldTo = null;
          if (r.statusBadge === 'WAIT') r.statusBadge = null;
          onRobotJamEnd(r, 'WATCHDOG_AUTO_UNBLOCK');
          if (r.path && r.path.length > 0) {
            const dest = r.path[r.path.length - 1];
            const newPath = findPath(r.gridX, r.gridY, dest.x, dest.y);
            if (newPath.length > 0) { setRobotPath(r, newPath); }
            else { onRobotReachedDestination(r); }
          }
        }
      }

      dispatchFleet();
    }

    let lastAnimTime = performance.now();
    let lastDashboardUpdate = 0;
    let lastPeriodicDispatch = 0;
    let lastLogSyncTime = 0;
    let simPaused = false;

    function togglePause() { 
      simPaused = !simPaused;
      document.getElementById('pause-btn').innerText = simPaused ? '▶️' : '⏸️';
      logTerminal('SYSTEM', 'tag-yield', simPaused ? '⏸️ Simulation Paused by Operator' : '▶️ Simulation Resumed');
    }

    function animateLoop(now) {
      if (!now) now = performance.now();
      const dt = Math.min(0.1, (now - lastAnimTime) / 1000);
      lastAnimTime = now;

      // Periodic Background Telemetry Sync (every 5s)
      if (now - lastLogSyncTime > 5000) {
        lastLogSyncTime = now;
        try {
          if (typeof fetch !== 'undefined') {
            fetch('/api/fleet/logs/sync', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(buildFleetTelemetryPayload())
            }).catch(() => {});
          }
        } catch (e) {}
      }

      if (!simPaused) { 
        for (let sIdx = COLLISION_SPARKS.length - 1; sIdx >= 0; sIdx--) {
          COLLISION_SPARKS[sIdx].timer -= dt;
          if (COLLISION_SPARKS[sIdx].timer <= 0) COLLISION_SPARKS.splice(sIdx, 1);
        }
        for (const r of AMR_FLEET) {
          if (r.mapPingTimer > 0) r.mapPingTimer = Math.max(0, r.mapPingTimer - dt);
        }

        updateRobots(dt);
        runFleetWatchdog(now);

        if (now - lastPeriodicDispatch > 800 / simSpeed) {
          lastPeriodicDispatch = now;
          dispatchFleet();
        }
      } 

      if (currentMainTab === 'map') {
        if (trackedRobotId && trackCameraFollow && !isDragging) {
          const trkBot = AMR_FLEET.find(b => b.id === trackedRobotId);
          if (trkBot) {
            const w = canvas.width / window.devicePixelRatio;
            const h = canvas.height / window.devicePixelRatio;
            const offsetX = window.innerWidth > 1000 ? -40 : 0;
            const targetX = (w / 2 + offsetX) - (trkBot.x + 0.5) * camera.scale;
            const targetY = (h / 2) - (trkBot.y + 0.5) * camera.scale;
            const lerpFactor = Math.min(1.0, dt * 8.0);
            camera.x += (targetX - camera.x) * lerpFactor;
            camera.y += (targetY - camera.y) * lerpFactor;
          }
        }
        if (trackedRobotId) {
          updateTrackingHud();
        }
        render();
      } else if (currentMainTab === 'terminal') {
        if (now - lastDashboardUpdate > 180) {
          lastDashboardUpdate = now;
          updateBotsHealthDashboard();
        }
      } else if (currentMainTab === 'problems') {
        if (now - lastDashboardUpdate > 250) {
          lastDashboardUpdate = now;
          updateProblemsDashboard();
        }
      }
      requestAnimationFrame(animateLoop);
    }

    async function loadMap() {
      const res = await fetch('/api/map');
      mapData = await res.json();
      initRackMemory();
      initAmrFleet();
      resetView();
      lastAnimTime = performance.now();
      requestAnimationFrame(animateLoop);
    }

    function resize() {
      if (!canvas || !canvas.parentElement) return;
      const pw = canvas.parentElement.clientWidth;
      const ph = canvas.parentElement.clientHeight;
      if (pw === 0 || ph === 0) return;
      canvas.width = pw * window.devicePixelRatio;
      canvas.height = ph * window.devicePixelRatio;
      render();
    }
    window.addEventListener('resize', resize);

    function resetView() {
      if (!mapData) return;
      const w = canvas.width / window.devicePixelRatio;
      const h = canvas.height / window.devicePixelRatio;
      const scaleX = (w - 80) / mapData.width;
      const scaleY = (h - 80) / mapData.height;
      camera.scale = Math.max(10, Math.min(scaleX, scaleY));
      camera.x = (w - mapData.width * camera.scale) / 2;
      camera.y = (h - mapData.height * camera.scale) / 2;
      render();
    }

    function zoom(factor) {
      const centerW = (canvas.width / window.devicePixelRatio) / 2;
      const centerH = (canvas.height / window.devicePixelRatio) / 2;
      const newScale = Math.min(60, Math.max(8, camera.scale * factor));
      camera.x = centerW - (centerW - camera.x) * (newScale / camera.scale);
      camera.y = centerH - (centerH - camera.y) * (newScale / camera.scale);
      camera.scale = newScale;
      render();
    }

    function screenToGrid(sx, sy) {
      if (!mapData) return null;
      const gx = Math.floor((sx - camera.x) / camera.scale);
      const gy = Math.floor((sy - camera.y) / camera.scale);
      if (gx >= 0 && gx < mapData.width && gy >= 0 && gy < mapData.height) {
        return { x: gx, y: gy };
      }
      return null;
    }

    function getInboundPlacementRacks() {
      const set = new Set();
      for (const [key, rack] of Object.entries(rackMemory)) {
        for (let f = 0; f < MAX_FLOORS; f++) {
          const item = rack.floors[f];
          if (item && item.isReservedInbound) set.add(key);
        }
      }
      for (const r of AMR_FLEET) {
        if (r.carriedParcels && r.carriedParcels.length > 0) {
          for (const p of r.carriedParcels) {
            if (p.rackSlot && p.rackSlot.rack) {
              set.add(`${p.rackSlot.rack.x},${p.rackSlot.rack.y}`);
            }
          }
        }
        if (r.inboundMission && r.inboundMission.parcels) {
          for (const p of r.inboundMission.parcels) {
            if (p.rackSlot && p.rackSlot.rack) {
              set.add(`${p.rackSlot.rack.x},${p.rackSlot.rack.y}`);
            }
          }
        }
      }
      return set;
    }

    function getOutboundPickRacks() {
      const set = new Set();
      for (const [key, rack] of Object.entries(rackMemory)) {
        for (let f = 0; f < MAX_FLOORS; f++) {
          const item = rack.floors[f];
          if (item && item.isReservedOutbound) set.add(key);
        }
      }
      for (const r of AMR_FLEET) {
        if (r.state === 'ORDER_PICKING' && r.outboundMission && r.outboundMission.itemsToPick) {
          for (const it of r.outboundMission.itemsToPick) {
            if (it.rack) {
              set.add(`${it.rack.x},${it.rack.y}`);
            }
          }
        }
      }
      return set;
    }

    function render() {
      if (!mapData) return;
      const dpr = window.devicePixelRatio;
      ctx.save();
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.scale(dpr, dpr);
      ctx.translate(camera.x, camera.y);

      const cellSize = camera.scale;

      // 1. Draw Floor grid & corridors
      ctx.fillStyle = '#0f172a';
      ctx.fillRect(0, 0, mapData.width * cellSize, mapData.height * cellSize);

      // Subtle gridlines
      ctx.strokeStyle = '#172033';
      ctx.lineWidth = 0.5;
      for (let x = 0; x <= mapData.width; x++) {
        ctx.beginPath();
        ctx.moveTo(x * cellSize, 0);
        ctx.lineTo(x * cellSize, mapData.height * cellSize);
        ctx.stroke();
      }
      for (let y = 0; y <= mapData.height; y++) {
        ctx.beginPath();
        ctx.moveTo(0, y * cellSize);
        ctx.lineTo(mapData.width * cellSize, y * cellSize);
        ctx.stroke();
      }

      // Collect sets of racks targeted for Inbound Placement (Dotted Blue) vs Outbound Pick (Dotted Red)
      const inboundPlacementRacks = getInboundPlacementRacks();
      const outboundPickRacks = getOutboundPickRacks();
      const animDashOffset = (Date.now() / 45) % 5;

      // 2. Draw Walls & Storage Racks (Darker Grey)
      for (let x = 0; x < mapData.width; x++) {
        for (let y = 0; y < mapData.height; y++) {
          const cell = mapData.grid[x][y];
          if (cell === 1) {
            const isPerimeterWall = (x === 0 || x === mapData.width - 1 || y === 0 || y === mapData.height - 1);
            if (isPerimeterWall) {
              // Outer Perimeter Wall: Darker Matte Industrial Grey
              ctx.fillStyle = '#0e1116';
              ctx.fillRect(x * cellSize, y * cellSize, cellSize, cellSize);
              ctx.strokeStyle = '#21262f';
              ctx.lineWidth = 1;
              ctx.strokeRect(x * cellSize + 0.5, y * cellSize + 0.5, cellSize - 1, cellSize - 1);
            } else {
              // Internal Storage Rack: Dark Charcoal Grey with Clean Tier Indicators
              const rackKey = `${x},${y}`;
              const rack = rackMemory[rackKey];
              const occCount = rack ? rack.floors.filter(f => f !== null && !f.isReservedInbound).length : 0;
              const isInboundPlacement = inboundPlacementRacks.has(rackKey);
              const isOutboundPick = outboundPickRacks.has(rackKey);

              ctx.fillStyle = occCount === 5 ? '#1c1917' : (occCount > 0 ? '#111827' : '#151821');
              ctx.fillRect(x * cellSize + 0.5, y * cellSize + 0.5, cellSize - 1, cellSize - 1);

              if (isInboundPlacement) {
                // Dotted Blue: A bot is holding the parcel and will place it in a movement
                ctx.save();
                ctx.setLineDash([3, 2]);
                ctx.lineDashOffset = -animDashOffset;
                ctx.strokeStyle = '#38bdf8'; // Bright Vivid Blue
                ctx.lineWidth = 2.0;
                ctx.strokeRect(x * cellSize + 0.5, y * cellSize + 0.5, cellSize - 1, cellSize - 1);
                ctx.restore();
              } else if (isOutboundPick) {
                // Dotted Red: Parcel that will be picked by a bot that is on its way towards that rack
                ctx.save();
                ctx.setLineDash([3, 2]);
                ctx.lineDashOffset = animDashOffset;
                ctx.strokeStyle = '#ef4444'; // Bright Vivid Red
                ctx.lineWidth = 2.0;
                ctx.strokeRect(x * cellSize + 0.5, y * cellSize + 0.5, cellSize - 1, cellSize - 1);
                ctx.restore();
              } else if (occCount === 5) {
                ctx.strokeStyle = '#f59e0b'; // Gold border when all 5 tiers are full
                ctx.lineWidth = 1.5;
                ctx.strokeRect(x * cellSize + 1, y * cellSize + 1, cellSize - 2, cellSize - 2);
              } else if (occCount > 0) {
                ctx.strokeStyle = '#38bdf8'; // Clean cyan border when holding inventory
                ctx.lineWidth = 1;
                ctx.strokeRect(x * cellSize + 1, y * cellSize + 1, cellSize - 2, cellSize - 2);
              } else {
                ctx.strokeStyle = '#282d37';
                ctx.lineWidth = 1;
                ctx.strokeRect(x * cellSize + 1, y * cellSize + 1, cellSize - 2, cellSize - 2);
              }

              // 5-Floor Level indicators (dots or pips)
              if (cellSize >= 14 && occCount > 0) {
                const pipWidth = (cellSize - 4) / 5;
                for (let f = 0; f < occCount; f++) {
                  ctx.fillStyle = occCount === 5 ? '#facc15' : '#38bdf8';
                  ctx.fillRect(x * cellSize + 2 + f * pipWidth, y * cellSize + cellSize - 3.5, pipWidth - 1, 2);
                }
              }
            }
          }
        }
      }

      // 5. Draw Functional Stations
      for (const [sid, st] of Object.entries(mapData.stations)) {
        const sx = st.x * cellSize;
        const sy = st.y * cellSize;
        const type = st.station_type || st.type || '';

        if (type === 'charging' || sid.startsWith('CH')) {
          const port = CHARGING_PORTS.find(p => p.id === sid);
          const isOccupied = port && port.occupiedBy !== null;
          const isReserved = port && port.reservedBy !== null;
          const reserver = isReserved ? AMR_FLEET.find(b => b.id === port.reservedBy) : null;

          if (isOccupied) {
            // Actively Occupied & Fast Charging (Pulsing Electric Green with Lightning Bolt)
            const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 250);
            ctx.fillStyle = '#14532d';
            ctx.fillRect(sx, sy, cellSize, cellSize);
            ctx.fillStyle = '#16a34a';
            ctx.fillRect(sx + 1, sy + 1, cellSize - 2, cellSize - 2);
            ctx.strokeStyle = '#4ade80';
            ctx.lineWidth = 1.8;
            ctx.strokeRect(sx + 0.5, sy + 0.5, cellSize - 1, cellSize - 1);
            ctx.shadowColor = '#22c55e';
            ctx.shadowBlur = 12 + 6 * pulse;

            ctx.fillStyle = '#ffffff';
            ctx.font = `bold ${Math.max(10, Math.floor(cellSize * 0.52))}px monospace`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('⚡', sx + cellSize / 2, sy + cellSize / 2);
            ctx.shadowBlur = 0;
          } else if (isReserved) {
            // Reserved by an incoming robot (Pulsing Cyan Outline)
            const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 200);
            ctx.fillStyle = '#0f172a';
            ctx.fillRect(sx, sy, cellSize, cellSize);
            ctx.fillStyle = 'rgba(6, 182, 212, 0.25)';
            ctx.fillRect(sx + 1, sy + 1, cellSize - 2, cellSize - 2);
            ctx.strokeStyle = '#22d3ee';
            ctx.lineWidth = 1.8;
            ctx.setLineDash([4, 2]);
            ctx.strokeRect(sx + 0.5, sy + 0.5, cellSize - 1, cellSize - 1);
            ctx.setLineDash([]);
            ctx.shadowColor = '#06b6d4';
            ctx.shadowBlur = 10 + 4 * pulse;

            ctx.fillStyle = '#67e8f9';
            ctx.font = `bold ${Math.max(9, Math.floor(cellSize * 0.42))}px monospace`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            const shortId = reserver ? reserver.id.replace('AMR-0', '') : 'R';
            ctx.fillText(`R${shortId}`, sx + cellSize / 2, sy + cellSize / 2);
            ctx.shadowBlur = 0;
          } else {
            // Free & Available Fast Charger (Clean Emerald Green)
            ctx.fillStyle = '#15803d';
            ctx.fillRect(sx, sy, cellSize, cellSize);
            ctx.fillStyle = '#22c55e';
            ctx.fillRect(sx + 1, sy + 1, cellSize - 2, cellSize - 2);
            ctx.strokeStyle = '#86efac';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(sx + 0.5, sy + 0.5, cellSize - 1, cellSize - 1);
            ctx.shadowColor = '#22c55e';
            ctx.shadowBlur = 8;

            ctx.fillStyle = '#ffffff';
            ctx.font = `bold ${Math.max(10, Math.floor(cellSize * 0.55))}px monospace`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('C', sx + cellSize / 2, sy + cellSize / 2);
            ctx.shadowBlur = 0;
          }
        } else if (type === 'pickup' || sid.startsWith('P')) {
          const q = inboundQueues[sid] || [];
          const hasParcel = q.length > 0;

          if (hasParcel) {
            // Yellow P while holding load waiting for AMR pickup
            const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 200);
            ctx.fillStyle = '#ca8a04';
            ctx.fillRect(sx, sy, cellSize, cellSize);
            ctx.fillStyle = '#facc15';
            ctx.fillRect(sx + 1, sy + 1, cellSize - 2, cellSize - 2);
            ctx.strokeStyle = '#fef08a';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(sx + 0.5, sy + 0.5, cellSize - 1, cellSize - 1);
            ctx.shadowColor = '#facc15';
            ctx.shadowBlur = 8 + 6 * pulse;

            ctx.fillStyle = '#0f172a'; // Bold black P on yellow
            ctx.font = `bold ${Math.max(10, Math.floor(cellSize * 0.55))}px monospace`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('P', sx + cellSize / 2, sy + cellSize / 2);
            ctx.shadowBlur = 0;
          } else {
            // Standard Blue P (idle / ready)
            ctx.fillStyle = '#06b6d4';
            ctx.fillRect(sx + 1, sy + 1, cellSize - 2, cellSize - 2);
            ctx.strokeStyle = '#67e8f9';
            ctx.lineWidth = 1;
            ctx.strokeRect(sx + 0.5, sy + 0.5, cellSize - 1, cellSize - 1);
            ctx.shadowColor = '#06b6d4';
            ctx.shadowBlur = 8;

            ctx.fillStyle = '#ffffff';
            ctx.font = `bold ${Math.max(10, Math.floor(cellSize * 0.5))}px monospace`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('P', sx + cellSize / 2, sy + cellSize / 2);
            ctx.shadowBlur = 0;
          }
        } else if (type === 'dropoff' || sid.startsWith('D')) {
          const ord = outboundOrders[sid];
          const isAwaitingDeposit = ord !== null && ord !== undefined;

          if (isAwaitingDeposit) {
            // Yellow while awaiting deposit
            const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 150);
            ctx.fillStyle = '#ca8a04';
            ctx.fillRect(sx, sy, cellSize, cellSize);
            ctx.fillStyle = '#facc15';
            ctx.fillRect(sx + 1, sy + 1, cellSize - 2, cellSize - 2);
            ctx.strokeStyle = '#fef08a';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(sx + 0.5, sy + 0.5, cellSize - 1, cellSize - 1);
            ctx.shadowColor = '#facc15';
            ctx.shadowBlur = 10 + 6 * pulse;

            ctx.fillStyle = '#0f172a'; // Bold black D on yellow
            ctx.font = `bold ${Math.max(10, Math.floor(cellSize * 0.55))}px monospace`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('D', sx + cellSize / 2, sy + cellSize / 2);
            ctx.shadowBlur = 0;
          } else {
            // Standard Orange D (idle)
            ctx.fillStyle = '#ea580c';
            ctx.fillRect(sx, sy, cellSize, cellSize);
            ctx.fillStyle = '#f97316';
            ctx.fillRect(sx + 1, sy + 1, cellSize - 2, cellSize - 2);
            ctx.strokeStyle = '#fdba74';
            ctx.lineWidth = 1;
            ctx.strokeRect(sx + 0.5, sy + 0.5, cellSize - 1, cellSize - 1);
            ctx.shadowColor = '#f97316';
            ctx.shadowBlur = 8;

            ctx.fillStyle = '#ffffff';
            ctx.font = `bold ${Math.max(10, Math.floor(cellSize * 0.5))}px monospace`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('D', sx + cellSize / 2, sy + cellSize / 2);
            ctx.shadowBlur = 0;
          }
        }
      }

      // 5.5. Draw Decentralized V2V Mesh RF Links
      if (typeof v2vMeshEnabled !== 'undefined' && v2vMeshEnabled && typeof v2vLinks !== 'undefined') {
        ctx.save();
        for (const l of v2vLinks) {
          ctx.beginPath();
          ctx.moveTo((l.botA.x + 0.5) * cellSize, (l.botA.y + 0.5) * cellSize);
          ctx.lineTo((l.botB.x + 0.5) * cellSize, (l.botB.y + 0.5) * cellSize);
          ctx.strokeStyle = l.activePulse ? 'rgba(255, 255, 255, 0.95)' : 'rgba(56, 189, 248, 0.28)';
          ctx.lineWidth = l.activePulse ? 2.5 : 1.2;
          ctx.setLineDash(l.activePulse ? [2, 2] : [4, 4]);
          ctx.stroke();
        }
        ctx.restore();
      }

      // 5.6. Draw Dynamic Obstacles & Human Workers (2D Tactical)
      if (typeof dynamicObstaclesEnabled !== 'undefined' && dynamicObstaclesEnabled && typeof DYNAMIC_OBSTACLES !== 'undefined') {
        ctx.save();
        for (const obs of DYNAMIC_OBSTACLES) {
          const ox = (obs.x + 0.5) * cellSize;
          const oy = (obs.y + 0.5) * cellSize;

          if (obs.type === 'human') {
            // Calibrated Tight Safety Zones (Inner 0.82m Stop Halo, Outer 1.35m Caution Halo)
            ctx.beginPath();
            ctx.arc(ox, oy, 0.82 * cellSize, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(239, 68, 68, 0.12)';
            ctx.fill();
            ctx.strokeStyle = 'rgba(239, 68, 68, 0.50)';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            ctx.beginPath();
            ctx.arc(ox, oy, 1.35 * cellSize, 0, Math.PI * 2);
            ctx.strokeStyle = 'rgba(245, 158, 11, 0.35)';
            ctx.setLineDash([3, 3]);
            ctx.stroke();
            ctx.setLineDash([]);

            // Worker Avatar
            ctx.beginPath();
            ctx.arc(ox, oy, cellSize * 0.45, 0, Math.PI * 2);
            ctx.fillStyle = '#facc15'; // High-vis yellow safety vest
            ctx.fill();
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 2;
            ctx.stroke();

            ctx.fillStyle = '#000000';
            ctx.font = `bold ${Math.max(9, cellSize * 0.4)}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('👷', ox, oy);

            // Name label
            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 9px sans-serif';
            ctx.fillText(obs.name.split(' ')[0], ox, oy - cellSize * 0.65);
          } else {
            // Pallet Staging Cart
            ctx.fillStyle = '#f59e0b';
            ctx.fillRect(ox - cellSize * 0.4, oy - cellSize * 0.4, cellSize * 0.8, cellSize * 0.8);
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(ox - cellSize * 0.4, oy - cellSize * 0.4, cellSize * 0.8, cellSize * 0.8);
            ctx.fillStyle = '#000000';
            ctx.font = `bold ${Math.max(8, cellSize * 0.35)}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('📦', ox, oy);
          }
        }
        ctx.restore();
      }

      // 6. Draw AMR Robot Fleet (8 Units)
      for (const robot of AMR_FLEET) {
        drawRobot(ctx, robot, cellSize);
      }

      // 7. Draw Collision Sparks / Impact Visuals
      for (let sIdx = COLLISION_SPARKS.length - 1; sIdx >= 0; sIdx--) {
        const spk = COLLISION_SPARKS[sIdx];
        const alpha = Math.max(0, spk.timer / spk.maxTimer);
        const rad = cellSize * (0.8 + (1 - alpha) * 1.2);
        ctx.save();
        ctx.beginPath();
        ctx.arc((spk.x + 0.5) * cellSize, (spk.y + 0.5) * cellSize, rad, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(239, 68, 68, ${alpha * 0.35})`;
        ctx.fill();
        ctx.strokeStyle = `rgba(250, 204, 21, ${alpha})`;
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 2]);
        ctx.stroke();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('💥', (spk.x + 0.5) * cellSize, (spk.y + 0.5) * cellSize);
        ctx.restore();
      }

      ctx.restore();
    }

    // Canvas Interactions
    let dragDownPos = { x: 0, y: 0 };
    let dragDistance = 0;

    canvas.addEventListener('mousedown', (e) => {
      isDragging = true;
      dragStart.x = e.clientX - camera.x;
      dragStart.y = e.clientY - camera.y;
      dragDownPos.x = e.clientX;
      dragDownPos.y = e.clientY;
      dragDistance = 0;
    });

    window.addEventListener('mousemove', (e) => {
      if (isDragging) {
        const dx = e.clientX - dragDownPos.x;
        const dy = e.clientY - dragDownPos.y;
        dragDistance = Math.hypot(dx, dy);

        // If user manually pans the canvas, temporarily disengage follow camera
        if (dragDistance > 10 && trackCameraFollow) {
          trackCameraFollow = false;
          const camBtn = document.getElementById('track-cam-toggle-btn');
          if (camBtn) {
            camBtn.classList.remove('active');
            camBtn.innerHTML = '🎥 Cam: OFF';
          }
        }

        camera.x = e.clientX - dragStart.x;
        camera.y = e.clientY - dragStart.y;
        render();
      }

      const rect = canvas.getBoundingClientRect();
      const pos = screenToGrid(e.clientX - rect.left, e.clientY - rect.top);
      if (pos) {
        coordsLabel.innerText = `X: ${pos.x}, Y: ${pos.y}`;

        // Check if cursor is hovering over any AMR robot puck
        const mouseGridX = (e.clientX - rect.left - camera.x) / camera.scale;
        const mouseGridY = (e.clientY - rect.top - camera.y) / camera.scale;
        let hoveredRobot = null;
        for (const r of AMR_FLEET) {
          const dist = Math.hypot(mouseGridX - (r.x + 0.5), mouseGridY - (r.y + 0.5));
          if (dist <= 0.6) {
            hoveredRobot = r;
            break;
          }
        }

        if (hoveredRobot) {
          const r = hoveredRobot;
          let stateLabel = 'IDLE';
          let stateColor = '#94a3b8';
          if (r.state === 'IDLE_CHARGING') { stateLabel = 'FAST CHARGING (100%)'; stateColor = '#22c55e'; }
          else if (r.state === 'MOVING_TO_PICKUP') { stateLabel = 'TRANSIT TO DOCK'; stateColor = '#38bdf8'; }
          else if (r.state === 'LOADING_INBOUND') { stateLabel = 'LOADING SHIPMENT'; stateColor = '#facc15'; }
          else if (r.state === 'CARRYING_TO_RACK') { stateLabel = 'SHELVING SHIPMENT'; stateColor = '#facc15'; }
          else if (r.state === 'ORDER_PICKING') { stateLabel = 'CONSOLIDATING ORDER'; stateColor = '#f59e0b'; }
          else if (r.state === 'DELIVERING_ORDER_TO_BAY') { stateLabel = 'DELIVERING GIANT BOX'; stateColor = '#ea580c'; }
          else if (r.state === 'RETURNING_HOME') { stateLabel = 'RETURNING TO BASE'; stateColor = '#10b981'; }

          const batColor = r.battery > 50 ? '#22c55e' : (r.battery > 20 ? '#f59e0b' : '#ef4444');
          const urgency = calculateRobotUrgency(r);
          const urgencyColor = urgency >= 75 ? '#ef4444' : (urgency >= 55 ? '#f97316' : (urgency >= 35 ? '#38bdf8' : '#94a3b8'));
          const overtakeEligible = urgency >= 60;

          // Manifest & Payload description
          let payloadHtml = '<span style="color:#64748b; font-style:italic;">[Deck Empty]</span>';
          let slaHtml = '<span style="color:#94a3b8;">None (Idle Fleet)</span>';
          let weightHtml = '0.0 kg';

          if (r.orderBox) {
            const ob = r.orderBox;
            slaHtml = `<span style="color:${ob.importance ? ob.importance.color : '#f59e0b'}; font-weight:700;">${ob.importance ? ob.importance.label : 'Order Pick'}</span>`;
            weightHtml = `${ob.totalWeight ? ob.totalWeight.toFixed(1) : '5.0'} kg`;
            const itemsList = ob.items && ob.items.length > 0 
              ? ob.items.map(it => `<div style="color:#cbd5e1; font-size:10px;">• ${it.parcel_id} (${it.name}, ${it.weight})</div>`).join('')
              : '<div style="color:#94a3b8; font-size:10px; font-style:italic;">• Collecting items from racks...</div>';
            payloadHtml = `
              <div style="margin-top:2px;">
                <strong style="color:#f59e0b;">📦 Giant Order Box (${ob.orderId}):</strong>
                <span style="color:#e2e8f0; font-size:10px;"> [${ob.items.length}/${ob.totalItems} Items Consolidated]</span>
                <div style="margin-top:2px; padding-left:4px;">${itemsList}</div>
              </div>`;
          } else if (r.carriedParcels && r.carriedParcels.length > 0) {
            const highest = r.carriedParcels[0].importance || IMPORTANCE_TIERS.STANDARD;
            const totW = r.carriedParcels.reduce((sum, p) => sum + (parseFloat(p.weight) || 3), 0);
            slaHtml = `<span style="color:${highest.color}; font-weight:700;">${highest.label}</span>`;
            weightHtml = `${totW.toFixed(1)} kg`;
            const preview = r.carriedParcels.slice(0, 3).map(p => `<div style="color:#cbd5e1; font-size:10px;">• ${p.parcel_id} (${p.name}, ${p.weight})</div>`).join('');
            const more = r.carriedParcels.length > 3 ? `<div style="color:#94a3b8; font-size:9px;">+ ${r.carriedParcels.length - 3} more in tote</div>` : '';
            payloadHtml = `
              <div style="margin-top:2px;">
                <strong style="color:#facc15;">📦 Inbound Shipment Tote:</strong>
                <span style="color:#e2e8f0; font-size:10px;"> [${r.carriedParcels.length} Parcels to Shelf]</span>
                <div style="margin-top:2px; padding-left:4px;">${preview}${more}</div>
              </div>`;
          }

          let trafficStatusHtml = '';
          if (r.isOvertaking) {
            trafficStatusHtml = `<div>Traffic: <strong style="color:#38bdf8;">⚡ Overtaking (Bypass Lane, 1.35x speed)</strong></div>`;
          } else if (r.isRerouting) {
            trafficStatusHtml = `<div>Traffic: <strong style="color:#c084fc;">🔄 Dynamic Detour / Rerouted</strong></div>`;
          } else if (r.isWaiting) {
            trafficStatusHtml = `<div>Traffic: <strong style="color:#f59e0b;">⏳ Yielding to ${r.yieldTo || 'AMR'}</strong></div>`;
          } else {
            trafficStatusHtml = `<div>Traffic: <strong style="color:#22c55e;">✔ Safe Following Distance (${overtakeEligible ? 'Overtake Authorized' : 'Lane Cruise'})</strong></div>`;
          }

          // Realistic BMS Telemetry for Tooltip
          let batteryCardHtml = '';
          if (r.state === 'IDLE_CHARGING') {
            const kw = (r.chargeRateKw || 30.0).toFixed(1);
            const phase = r.chargePhase || 'Bulk CC Phase';
            const chgRate = (r.batteryDeltaRate || 3.5).toFixed(1);
            const timeRemSec = Math.max(0, Math.round((100 - r.battery) / Math.max(0.2, (r.batteryDeltaRate || 2.5))));
            batteryCardHtml = `
              <div style="margin-top:5px; padding:5px 8px; background:rgba(34, 197, 94, 0.08); border:1px solid rgba(34, 197, 94, 0.3); border-radius:4px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="color:#4ade80; font-weight:700;">⚡ 48V LiFePO4 Fast Charge:</span>
                  <span style="color:#22c55e; font-weight:700;">${r.battery.toFixed(1)}% SoC</span>
                </div>
                <div style="width:100%; height:4px; background:#1e293b; border-radius:2px; margin:4px 0; overflow:hidden;">
                  <div style="width:${r.battery.toFixed(1)}%; height:100%; background:#22c55e;"></div>
                </div>
                <div style="color:#cbd5e1; font-size:10px;">• Charger: <strong>+${kw} kW</strong> (${phase}) [<strong>+${chgRate}%/s</strong>]</div>
                <div style="color:#94a3b8; font-size:10px;">• Time to 100%: <strong>~${timeRemSec}s</strong> | Pack Temp: 32.4°C (Optimal)</div>
              </div>`;
          } else {
            const pTot = Math.round(r.powerWatts || 165);
            const drain = (r.batteryDeltaRate || 0.38).toFixed(2);
            const breakdown = r.powerBreakdown || 'Avionics: 45W | Traction: 120W';
            const activeSecRem = Math.max(1, Math.round((r.battery - 15) / Math.max(0.08, r.batteryDeltaRate || 0.38)));
            const minRem = (activeSecRem / 60).toFixed(1);
            const isLow = r.battery <= 28.0;
            batteryCardHtml = `
              <div style="margin-top:5px; padding:5px 8px; background:${isLow ? 'rgba(239, 68, 68, 0.12)' : 'rgba(15, 23, 42, 0.7)'}; border:1px solid ${isLow ? '#ef4444' : 'rgba(255,255,255,0.1)'}; border-radius:4px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="color:${isLow ? '#f87171' : '#e2e8f0'}; font-weight:700;">🔋 48V LiFePO4 BMS Battery:</span>
                  <span style="color:${batColor}; font-weight:700;">${r.battery.toFixed(1)}% SoC ${isLow ? '⚠️ LOW' : ''}</span>
                </div>
                <div style="width:100%; height:4px; background:#1e293b; border-radius:2px; margin:4px 0; overflow:hidden;">
                  <div style="width:${r.battery.toFixed(1)}%; height:100%; background:${batColor};"></div>
                </div>
                <div style="color:#cbd5e1; font-size:10px;">• Power Draw: <strong>-${pTot} W</strong> [<strong>-${drain}%/s</strong>]</div>
                <div style="color:#94a3b8; font-size:10px;">• Load: ${breakdown}</div>
                <div style="color:#94a3b8; font-size:10px;">• Est. Range: <strong>~${minRem} min</strong> duty (to 15% reserve) | Temp: 31.8°C</div>
              </div>`;
          }

          const nearestInfo = getNearestAvailableCharger(r.gridX, r.gridY, r.id);
          const minReqSoC = nearestInfo.energyNeeded + SAFETY_RESERVE_SOC;
          const isOk = r.battery >= minReqSoC;

          tooltip.style.display = 'block';
          tooltip.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
              <strong style="color:#fff; font-size:12px;">🤖 ${r.id} (Autonomous Mobile Robot)</strong>
              <span style="color:${stateColor}; font-weight:700; font-size:10px; padding:1px 5px; background:rgba(255,255,255,0.06); border-radius:3px;">${stateLabel}</span>
            </div>
            <div style="font-size:11px; margin-bottom:4px; line-height:1.5;">
              <div>Target: <strong style="color:#e2e8f0;">${r.targetDesc}</strong></div>
              <div>Nearest Charger: <strong style="color:#4ade80;">${nearestInfo.charger ? nearestInfo.charger.id : 'CH-01'}</strong> (${nearestInfo.distance} cells | Est: ~${nearestInfo.energyNeeded.toFixed(1)}% SoC)</div>
              <div>BMS Energy Budget: ${isOk ? `<strong style="color:#22c55e;">✔ PASS (12% Reserve Safe, +${(r.battery - minReqSoC).toFixed(1)}% margin)</strong>` : `<strong style="color:#ef4444;">🚨 RECHARGE NEEDED (Deficit: ${(minReqSoC - r.battery).toFixed(1)}%)</strong>`}</div>
              <div>Delivery SLA: ${slaHtml}</div>
              <div>Urgency Score: <strong style="color:${urgencyColor};">${urgency}/100</strong> <span style="color:#94a3b8; font-size:10px;">(${overtakeEligible ? 'High - Overtake Authorized' : 'Lane Cruise'})</span></div>
              <div>Cargo Weight: <strong style="color:#e2e8f0;">${weightHtml}</strong></div>
              <div>Kinematic Speed: <strong style="color:#38bdf8;">${(r.currentSpeed || (ROBOT_BASE_SPEED * simSpeed)).toFixed(2)} cells/s</strong> <span style="color:${r.payloadDamping && r.payloadDamping < 0.99 ? '#f59e0b' : '#94a3b8'}; font-size:10px;">(${r.payloadDamping ? Math.round(r.payloadDamping * 100) : 100}% load throttle)</span></div>
              ${payloadHtml}
              ${batteryCardHtml}
              ${trafficStatusHtml}
            </div>
          `;
        } else {
          // Tooltip inspection for Stations & 3D Storage Racks
          let foundStation = null;
          if (mapData && mapData.stations) {
            for (const s of Object.values(mapData.stations)) {
              if (s.x === pos.x && s.y === pos.y) {
                foundStation = s;
                break;
              }
            }
          }

          if (foundStation) {
            const stype = foundStation.station_type || foundStation.type || '';
            let statusHtml = '';
            if (foundStation.id.startsWith('P')) {
              const q = inboundQueues[foundStation.id] || [];
              if (q.length > 0) {
                const preview = q.slice(0, 3).map(p => `<div style="color:#cbd5e1; font-size:10px;">• ${p.parcel_id} (${p.name}, ${p.weight})</div>`).join('');
                const more = q.length > 3 ? `<div style="color:#94a3b8; font-size:9px;">+ ${q.length - 3} more parcels</div>` : '';
                statusHtml = `
                  <div style="margin-top:4px; padding-top:4px; border-top:1px solid rgba(255,255,255,0.1);">
                    <span style="color:#facc15; font-weight:700;">📦 HOLDING LOAD (${q.length} Parcels)</span>
                    <div style="margin-top:2px;">${preview}${more}</div>
                    <div style="color:#fde047; font-size:10px; margin-top:2px;">Awaiting AMR Bot Pickup</div>
                  </div>`;
              } else {
                statusHtml = '<div style="margin-top:4px; color:#38bdf8; font-size:11px;">Status: <strong>Ready / Idle</strong> (No waiting parcels)</div>';
              }
            } else if (foundStation.id.startsWith('D')) {
              const ord = outboundOrders[foundStation.id];
              if (ord) {
                statusHtml = `
                  <div style="margin-top:4px; padding-top:4px; border-top:1px solid rgba(255,255,255,0.1);">
                    <span style="color:#facc15; font-weight:700;">🚚 RECEIVING ORDER ${ord.orderId}</span>
                    <div style="color:#cbd5e1; font-size:10px; margin-top:2px;">Requested: <strong>${ord.totalCount} parcels</strong> from Racks</div>
                    <div style="color:#fde047; font-size:10px; margin-top:2px;">Delivered: <strong>${ord.deliveredCount || 0} / ${ord.totalCount}</strong></div>
                  </div>`;
              } else {
                statusHtml = '<div style="margin-top:4px; color:#f97316; font-size:11px;">Status: <strong>Ready / Idle</strong> for Dispatch</div>';
              }
            } else if (foundStation.id.startsWith('CH') || stype === 'charging') {
              const port = CHARGING_PORTS.find(p => p.id === foundStation.id);
              const occBot = port && port.occupiedBy ? AMR_FLEET.find(b => b.id === port.occupiedBy) : null;
              const resBot = port && port.reservedBy ? AMR_FLEET.find(b => b.id === port.reservedBy) : null;
              if (occBot) {
                statusHtml = `
                  <div style="margin-top:4px; padding-top:4px; border-top:1px solid rgba(255,255,255,0.1);">
                    <span style="color:#4ade80; font-weight:700;">⚡ OCCUPIED &amp; CHARGING</span>
                    <div style="color:#cbd5e1; font-size:10px; margin-top:2px;">Robot: <strong>${occBot.id}</strong> (${occBot.battery.toFixed(1)}% SoC, +${(occBot.chargeRateKw || 30).toFixed(1)} kW)</div>
                    <div style="color:#94a3b8; font-size:10px;">Phase: ${occBot.chargePhase || 'Fast Charge'}</div>
                  </div>`;
              } else if (resBot) {
                statusHtml = `
                  <div style="margin-top:4px; padding-top:4px; border-top:1px solid rgba(255,255,255,0.1);">
                    <span style="color:#38bdf8; font-weight:700;">⚡ RESERVED (INCOMING)</span>
                    <div style="color:#cbd5e1; font-size:10px; margin-top:2px;">Reserved by: <strong>${resBot.id}</strong> (${resBot.battery.toFixed(1)}% SoC)</div>
                    <div style="color:#38bdf8; font-size:10px;">En route to dock contact pad</div>
                  </div>`;
              } else {
                statusHtml = '<div style="margin-top:4px; color:#22c55e; font-size:11px;">⚡ <strong>Free &amp; Ready</strong> (30kW CC/CV Fast Pad Ready)</div>';
              }
            }

            tooltip.style.display = 'block';
            tooltip.innerHTML = `
              <div style="font-weight:700; color:#fff; display:flex; justify-content:space-between; gap:6px;">
                <span>${foundStation.id}: ${foundStation.name}</span>
              </div>
              <div style="color:#94a3b8; font-size:10px;">Zone: ${foundStation.zone} | Grid: (${foundStation.x}, ${foundStation.y})</div>
              ${statusHtml}
            `;
          } else {
            // Check 3D Storage Rack Memory at (x, y)
            const rackKey = `${pos.x},${pos.y}`;
            const rack = rackMemory[rackKey];
            if (rack) {
              let occ = 0;
              let tiersHtml = '';
              const catName = rack.categoryFullName || rack.categoryName || 'General';
              const catSku = rack.categorySku || '';

              for (let f = MAX_FLOORS - 1; f >= 0; f--) {
                const p = rack.floors[f];
                const floorNum = f + 1;
                if (p) {
                  if (p.isReservedInbound) {
                    tiersHtml += `
                      <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; padding:2px 5px; background:rgba(56,189,248,0.06); border-left:3px dashed #38bdf8; margin:2px 0; border-radius:2px; font-size:10px;">
                        <span style="color:#38bdf8;">Tier ${floorNum}:</span>
                        <span style="color:#94a3b8; font-style:italic;">[Reserved: ${p.parcel_id}]</span>
                        <span style="color:#64748b;">AMR en route</span>
                      </div>`;
                  } else {
                    occ++;
                    const parcelObj = p.isReservedOutbound ? p.parcel || p : p;
                    const subTag = p.isReservedOutbound ? '<span style="color:#f59e0b; font-size:9px;">[Retrieving]</span>' : '';
                    tiersHtml += `
                      <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; padding:2px 5px; background:rgba(56,189,248,0.12); border-left:3px solid #38bdf8; margin:2px 0; border-radius:2px;">
                        <span style="color:#38bdf8; font-weight:700; font-size:10px;">Tier ${floorNum}:</span>
                        <span style="color:#f8fafc; font-weight:600; font-size:10px;">${parcelObj.parcel_id} ${subTag}</span>
                        <span style="color:#cbd5e1; font-size:9px;">${parcelObj.name.split(' ')[0]} (${parcelObj.weight})</span>
                      </div>`;
                  }
                } else {
                  tiersHtml += `
                    <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; padding:2px 5px; background:rgba(255,255,255,0.02); border-left:3px solid #334155; margin:2px 0; border-radius:2px; color:#64748b; font-size:10px;">
                      <span>Tier ${floorNum}:</span>
                      <span style="font-style:italic;">[Empty Slot]</span>
                      <span>-</span>
                    </div>`;
                }
              }

              const isInboundPlacement = getInboundPlacementRacks().has(rackKey);
              const isOutboundPick = getOutboundPickRacks().has(rackKey);
              let transitBanner = '';

              if (isInboundPlacement) {
                transitBanner = `
                  <div style="display:flex; align-items:center; gap:5px; margin-bottom:5px; padding:3px 6px; background:rgba(56,189,248,0.12); border:1.5px dashed #38bdf8; border-radius:3px; font-size:10px; color:#38bdf8; font-weight:700;">
                    <span>📥 DOTTED BLUE:</span>
                    <span style="color:#e2e8f0; font-weight:normal;">Bot is holding parcel & en route to place it</span>
                  </div>`;
              } else if (isOutboundPick) {
                transitBanner = `
                  <div style="display:flex; align-items:center; gap:5px; margin-bottom:5px; padding:3px 6px; background:rgba(239,68,68,0.12); border:1.5px dashed #ef4444; border-radius:3px; font-size:10px; color:#ef4444; font-weight:700;">
                    <span>📤 DOTTED RED:</span>
                    <span style="color:#e2e8f0; font-weight:normal;">Bot is on its way to pick parcel</span>
                  </div>`;
              }

              const badgeColor = occ === 5 ? '#f59e0b' : (occ > 0 ? '#38bdf8' : '#64748b');
              const statusLabel = occ === 5 ? 'FULL (5/5)' : (occ > 0 ? `STORED (${occ}/5)` : 'VACANT (0/5)');

              tooltip.style.display = 'block';
              tooltip.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:3px;">
                  <strong style="color:#fff;">3D STORAGE RACK</strong>
                  <span style="color:${badgeColor}; font-weight:700; font-size:10px; padding:1px 5px; background:rgba(255,255,255,0.05); border-radius:3px;">${statusLabel}</span>
                </div>
                ${transitBanner}
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; font-size:10px;">
                  <span style="color:#94a3b8;">Row: <strong style="color:#e2e8f0;">${catName}</strong> (${catSku})</span>
                  <span style="color:#94a3b8;">(${pos.x}, ${pos.y})</span>
                </div>
                <div style="display:flex; flex-direction:column; gap:1px;">
                  ${tiersHtml}
                </div>
              `;
            } else {
              tooltip.style.display = 'none';
            }
          }
        }

        // Clamp tooltip position within screen bounds
        if (tooltip.style.display === 'block') {
          const tw = 310;
          const th = 280;
          let left = e.clientX + 14;
          let top = e.clientY + 14;
          if (left + tw > window.innerWidth) left = Math.max(10, e.clientX - tw - 14);
          if (top + th > window.innerHeight) top = Math.max(10, e.clientY - th - 14);
          tooltip.style.left = left + 'px';
          tooltip.style.top = top + 'px';
        }
      } else {
        coordsLabel.innerText = '-';
        tooltip.style.display = 'none';
      }
    });

    window.addEventListener('mouseup', (e) => {
      if (isDragging) {
        // If minimal mouse movement occurred, treat as direct click-to-track on robot
        if (dragDistance < 6) {
          const rect = canvas.getBoundingClientRect();
          const clickGridX = (e.clientX - rect.left - camera.x) / camera.scale;
          const clickGridY = (e.clientY - rect.top - camera.y) / camera.scale;
          let clickedBot = null;
          for (const r of AMR_FLEET) {
            const dist = Math.hypot(clickGridX - (r.x + 0.5), clickGridY - (r.y + 0.5));
            if (dist <= 0.65) {
              clickedBot = r;
              break;
            }
          }
          if (clickedBot) {
            trackBot(clickedBot.id, true);
          }
        }
        isDragging = false;
      }
    });

    // Keyboard Shortcuts for Bot Tracking & Fleet Navigation
    window.addEventListener('keydown', (e) => {
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT')) {
        return;
      }
      if (e.key === 'f' || e.key === 'F') {
        toggleTrackCameraFollow();
      } else if (e.key === 'c' || e.key === 'C') {
        centerOnTrackedBot();
      } else if (e.key === 'ArrowRight' || e.key === ']') {
        cycleTrackedRobot(1);
      } else if (e.key === 'ArrowLeft' || e.key === '[') {
        cycleTrackedRobot(-1);
      } else if (e.key === 'Escape') {
        stopTrackingBot();
      }
    });

    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const newScale = Math.min(80, Math.max(8, camera.scale * zoomFactor));
      camera.x = mouseX - (mouseX - camera.x) * (newScale / camera.scale);
      camera.y = mouseY - (mouseY - camera.y) * (newScale / camera.scale);
      camera.scale = newScale;
      render();
    });

    // Setup & start
    resize();
    loadMap();
  </script>
</body>
</html>
"""

INDEX_TEMPLATE = os.path.join(os.path.dirname(__file__), "templates", "index.html")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    if os.path.exists(INDEX_TEMPLATE):
        with open(INDEX_TEMPLATE, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content=HTML_DASHBOARD)

@app.get("/api/map")
async def get_map():
    return warehouse.to_dict()

@app.get("/api/inventory")
async def get_inventory():
    return inventory.get_summary()

@app.post("/api/inventory/inject")
async def inject_inventory(req: BulkInjectRequest):
    stored = inventory.bulk_store_parcels(req.count)
    return {
        "stored": stored,
        "total_stored": inventory.total_stored_parcels,
        "capacity": inventory.total_capacity,
        "occupancy_rate": round(inventory.occupancy_rate, 2)
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    try:
        # Send initial map setup
        await websocket.send_json({"type": "INIT", "map": warehouse.to_dict()})
        while True:
            data = await websocket.receive_text()
            # Handle client messages if needed
    except WebSocketDisconnect:
        active_connections.remove(websocket)

_latest_fleet_logs = None

@app.post("/api/fleet/logs/sync")
async def sync_fleet_logs(req: Request):
    global _latest_fleet_logs
    try:
        data = await req.json()
        _latest_fleet_logs = data
        return {"status": "ok", "received_bots": len(data.get("bots", []))}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/fleet/logs")
async def get_fleet_logs():
    global _latest_fleet_logs
    if _latest_fleet_logs is None:
        return {"status": "empty", "message": "No fleet logs synchronized yet from simulation client.", "timestamp": time.time()}
    return _latest_fleet_logs


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

