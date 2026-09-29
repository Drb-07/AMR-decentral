"""
Industrial Mega-Warehouse Map & Topology (80 x 50 Grid)
Designed for Edge-AI Distributed Fleet Coordination for AMRs

Key Features:
- 80 columns x 50 rows = 4,000 cells
- Solid, continuous rectangular shelf pods
- 100% natural warehouse floor: no artificial yield points or choke point markers
- Dedicated Green Charging Bay Rows:
    * Left-Top Row (y=1, x=1..4): CH-01 to CH-04 in a clean horizontal row
    * Left-Bottom Row (y=48, x=1..4): CH-05 to CH-08 in a clean horizontal row
- 50-50 Balanced Dock Layout:
    * Left Side (x=1): Top Half = Inbound Pickups (P-01 to P-05), Bottom Half = Outbound Dropoffs (D-01 to D-05)
    * Right Side (x=78): Top Half = Outbound Dropoffs (D-06 to D-10), Bottom Half = Inbound Pickups (P-06 to P-10)
- Single-lane narrow aisles (1.5x robot base width)
"""

from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass, asdict
import json


# Cell Type Constants
CELL_EMPTY = 0           # Open floor / corridor / highway
CELL_RACK = 1            # Solid static storage rack
CELL_CHARGING = 3        # Fast charging station (Green)
CELL_PICKUP = 4          # Inbound pickup dock (Cyan)
CELL_DROPOFF = 5         # Outbound sorting / dispatch bay (Amber)
CELL_HAZARD = 9          # Dynamic obstacle / human / blocked aisle


@dataclass
class Station:
    id: str
    name: str
    station_type: str  # 'pickup', 'dropoff', 'charging'
    x: int
    y: int
    zone: str = "General"


class WarehouseMap:
    def __init__(self, width: int = 80, height: int = 50):
        self.width = width
        self.height = height

        # 2D Grid: grid[x][y]
        self.grid: List[List[int]] = [[CELL_EMPTY for _ in range(height)] for _ in range(width)]

        # Dynamic obstacles injected at runtime
        self.dynamic_obstacles: Set[Tuple[int, int]] = set()

        # Topological sets
        self.stations: Dict[str, Station] = {}
        self.narrow_aisles: Set[Tuple[int, int]] = set()
        self.rack_cells: Set[Tuple[int, int]] = set()

        self._build_layout()

    def _build_layout(self):
        # 1. Outer perimeter walls
        for x in range(self.width):
            self.grid[x][0] = CELL_RACK
            self.grid[x][self.height - 1] = CELL_RACK
            self.rack_cells.add((x, 0))
            self.rack_cells.add((x, self.height - 1))

        for y in range(self.height):
            self.grid[0][y] = CELL_RACK
            self.grid[self.width - 1][y] = CELL_RACK
            self.rack_cells.add((0, y))
            self.rack_cells.add((self.width - 1, y))

        # 2. Storage Sectors (Solid continuous rack pods):
        west_col_pairs = [(5, 6), (8, 9), (11, 12), (14, 15), (17, 18), (20, 21), (23, 24)]
        central_col_pairs = [(30, 31), (33, 34), (36, 37), (39, 40), (42, 43), (45, 46), (48, 49)]
        east_col_pairs = [(56, 57), (59, 60), (62, 63), (65, 66), (68, 69), (71, 72), (74, 75)]

        all_rack_col_pairs = west_col_pairs + central_col_pairs + east_col_pairs

        # North Sector Solid Racks: y in [5..22]
        for col_start, col_end in all_rack_col_pairs:
            for x in range(col_start, col_end + 1):
                for y in range(5, 23):
                    self.grid[x][y] = CELL_RACK
                    self.rack_cells.add((x, y))

        # South Sector Solid Racks: y in [27..44]
        for col_start, col_end in all_rack_col_pairs:
            for x in range(col_start, col_end + 1):
                for y in range(27, 45):
                    self.grid[x][y] = CELL_RACK
                    self.rack_cells.add((x, y))

        # 3. Narrow Single-Lane Aisles (1.5x robot base width):
        west_aisles = [7, 10, 13, 16, 19, 22]
        central_aisles = [32, 35, 38, 41, 44, 47]
        east_aisles = [58, 61, 64, 67, 70, 73]
        all_vertical_aisles = west_aisles + central_aisles + east_aisles

        for ax in all_vertical_aisles:
            for y in range(4, 24):
                self.narrow_aisles.add((ax, y))
            for y in range(26, 46):
                self.narrow_aisles.add((ax, y))

        # Horizontal perimeter transition aisles
        for y in (4, 23, 26, 45):
            for x in range(4, 26):
                self.narrow_aisles.add((x, y))
            for x in range(28, 52):
                self.narrow_aisles.add((x, y))
            for x in range(54, 76):
                self.narrow_aisles.add((x, y))

        # 4. Dedicated Charging Depots at Top Center and Bottom Center:
        # A. Top Center Charging Row (y=1, x from 38 to 41)
        for i, cx in enumerate([38, 39, 40, 41]):
            cid = f"CH-{i+1:02d}"
            cname = f"Top Center Fast Charge {i+1}"
            self.stations[cid] = Station(cid, cname, "charging", cx, 1, "Charging-Top-Center")
            self.grid[cx][1] = CELL_CHARGING

        # B. Bottom Center Charging Row (y=48, x from 38 to 41)
        for i, cx in enumerate([38, 39, 40, 41]):
            cid = f"CH-{i+5:02d}"
            cname = f"Bottom Center Fast Charge {i+1}"
            self.stations[cid] = Station(cid, cname, "charging", cx, 48, "Charging-Bottom-Center")
            self.grid[cx][48] = CELL_CHARGING

        # 5. Balanced 50-50 Inbound & Outbound Docks:
        # LEFT SIDE (x=1):
        left_pickups = [
            ("P-01", "West Inbound Dock 1", 1, 5, "West-North-Inbound"),
            ("P-02", "West Inbound Dock 2", 1, 9, "West-North-Inbound"),
            ("P-03", "West Inbound Dock 3", 1, 13, "West-North-Inbound"),
            ("P-04", "West Inbound Dock 4", 1, 17, "West-North-Inbound"),
            ("P-05", "West Inbound Dock 5", 1, 21, "West-North-Inbound"),
        ]
        for sid, sname, sx, sy, szone in left_pickups:
            self.stations[sid] = Station(sid, sname, "pickup", sx, sy, szone)
            self.grid[sx][sy] = CELL_PICKUP

        left_dropoffs = [
            ("D-01", "West Sort Bay 1", 1, 27, "West-South-Outbound"),
            ("D-02", "West Sort Bay 2", 1, 31, "West-South-Outbound"),
            ("D-03", "West Packing Station 1", 1, 35, "West-South-Outbound"),
            ("D-04", "West Packing Station 2", 1, 39, "West-South-Outbound"),
            ("D-05", "West Dispatch Bay", 1, 43, "West-South-Outbound"),
        ]
        for sid, sname, sx, sy, szone in left_dropoffs:
            self.stations[sid] = Station(sid, sname, "dropoff", sx, sy, szone)
            self.grid[sx][sy] = CELL_DROPOFF

        # RIGHT SIDE (x=78):
        right_dropoffs = [
            ("D-06", "East Sort Bay 1", 78, 5, "East-North-Outbound"),
            ("D-07", "East Sort Bay 2", 78, 9, "East-North-Outbound"),
            ("D-08", "East Packing Station 1", 78, 13, "East-North-Outbound"),
            ("D-09", "East Packing Station 2", 78, 17, "East-North-Outbound"),
            ("D-10", "East Dispatch Bay", 78, 21, "East-North-Outbound"),
        ]
        for sid, sname, sx, sy, szone in right_dropoffs:
            self.stations[sid] = Station(sid, sname, "dropoff", sx, sy, szone)
            self.grid[sx][sy] = CELL_DROPOFF

        right_pickups = [
            ("P-06", "East Inbound Dock 1", 78, 27, "East-South-Inbound"),
            ("P-07", "East Inbound Dock 2", 78, 31, "East-South-Inbound"),
            ("P-08", "East Inbound Dock 3", 78, 35, "East-South-Inbound"),
            ("P-09", "East Inbound Dock 4", 78, 39, "East-South-Inbound"),
            ("P-10", "East Inbound Dock 5", 78, 43, "East-South-Inbound"),
        ]
        for sid, sname, sx, sy, szone in right_pickups:
            self.stations[sid] = Station(sid, sname, "pickup", sx, sy, szone)
            self.grid[sx][sy] = CELL_PICKUP

    def is_walkable(self, x: int, y: int, ignore_dynamic: bool = False) -> bool:
        """Check if coordinates are within bounds and not occupied by racks or dynamic obstacles."""
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return False
        if self.grid[x][y] == CELL_RACK:
            return False
        if not ignore_dynamic and (x, y) in self.dynamic_obstacles:
            return False
        return True

    def get_neighbors(self, x: int, y: int, allow_diagonal: bool = False) -> List[Tuple[int, int]]:
        """Return valid walkable neighboring coordinates."""
        neighbors = []
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        if allow_diagonal:
            directions += [(1, 1), (1, -1), (-1, 1), (-1, -1)]

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if self.is_walkable(nx, ny):
                neighbors.append((nx, ny))
        return neighbors

    def get_stations_by_type(self, station_type: str) -> List[Station]:
        """Filter stations by type ('pickup', 'dropoff', 'charging')."""
        return [s for s in self.stations.values() if s.station_type == station_type]

    def add_dynamic_obstacle(self, x: int, y: int):
        """Inject a dynamic obstacle (e.g. human worker or blocked aisle)."""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.dynamic_obstacles.add((x, y))

    def remove_dynamic_obstacle(self, x: int, y: int):
        """Clear a specific dynamic obstacle."""
        self.dynamic_obstacles.discard((x, y))

    def clear_dynamic_obstacles(self):
        """Clear all active dynamic obstacles."""
        self.dynamic_obstacles.clear()

    def to_dict(self) -> dict:
        """Serialize map structure for WebSocket / React Three.js / Canvas frontend."""
        return {
            "width": self.width,
            "height": self.height,
            "grid": self.grid,
            "dynamic_obstacles": list(self.dynamic_obstacles),
            "narrow_aisles": list(self.narrow_aisles),
            "stations": {
                k: {
                    "id": v.id,
                    "name": v.name,
                    "type": v.station_type,
                    "station_type": v.station_type,
                    "x": v.x,
                    "y": v.y,
                    "zone": v.zone,
                }
                for k, v in self.stations.items()
            },
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


if __name__ == "__main__":
    wm = WarehouseMap()
    print("Warehouse Map Updated (Charging Bays in Rows, Green):")
    print(f"- Dimensions: {wm.width} x {wm.height} ({wm.width * wm.height} total cells)")
    print(f"- Stations ({len(wm.stations)}): {len(wm.get_stations_by_type('pickup'))} Pickups, "
          f"{len(wm.get_stations_by_type('dropoff'))} Dropoffs, {len(wm.get_stations_by_type('charging'))} Charging Bays")
    print(f"- Left-Top Charging Row (y=1): {[s.id for s in wm.get_stations_by_type('charging') if 'Top' in s.zone]}")
    print(f"- Left-Bottom Charging Row (y=48): {[s.id for s in wm.get_stations_by_type('charging') if 'Bottom' in s.zone]}")

    # Connectivity Check
    from collections import deque
    start = (wm.stations["P-01"].x, wm.stations["P-01"].y)
    visited = {start}
    q = deque([start])
    while q:
        curr = q.popleft()
        for nbr in wm.get_neighbors(curr[0], curr[1]):
            if nbr not in visited:
                visited.add(nbr)
                q.append(nbr)

    all_stations_reachable = all((s.x, s.y) in visited for s in wm.stations.values())
    print(f"- Graph Connectivity Verified: Stations Reachable={all_stations_reachable}")
