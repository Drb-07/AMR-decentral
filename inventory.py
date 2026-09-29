"""
Live Warehouse Inventory & 3D Multi-Tier Rack Memory System
Part of Edge-AI Distributed Fleet Coordination for AMRs

Features:
- 3D Rack Storage: Each rack cell has 5 vertical floor levels (Level 1 to 5)
- Inbound memory: Docks stay lit yellow until AMR/bot picks up the batch
- Outbound memory: Departure bays light up yellow until order is deposited
- Dynamic slot allocation and inventory de-allocation
- Full parcel lifecycle tracking (ID, SKU, Weight, Dock, Rack (X, Y, Floor), Timestamp)
"""

import time
import random
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict

from warehouse_map import WarehouseMap, CELL_RACK


SKU_CATALOG = [
    {"sku": "SKU-ELEC", "name": "Consumer Electronics", "unit_weight": 4.5},
    {"sku": "SKU-AUTO", "name": "Automotive Components", "unit_weight": 14.2},
    {"sku": "SKU-PHRM", "name": "Cold-Chain Pharma Tote", "unit_weight": 3.8},
    {"sku": "SKU-FASH", "name": "Apparel & Footwear Box", "unit_weight": 2.2},
    {"sku": "SKU-INDM", "name": "Industrial Hardware Crate", "unit_weight": 21.0},
    {"sku": "SKU-FMCG", "name": "Retail Packaged Goods", "unit_weight": 7.6},
]


@dataclass
class Parcel:
    parcel_id: str
    sku: str
    sku_name: str
    weight: float
    origin_dock: str
    destination_bay: Optional[str] = None
    rack_x: Optional[int] = None
    rack_y: Optional[int] = None
    rack_floor: Optional[int] = None  # 1 to 5
    created_at: float = 0.0
    status: str = "INBOUND_QUEUED"  # INBOUND_QUEUED, STORED_IN_RACK, IN_TRANSIT, DELIVERED


def get_rack_category_info(y: int) -> dict:
    """Categorized horizontal rack row bands: 3 rows per SKU category."""
    idx = 0
    if 5 <= y <= 22:
        idx = (y - 5) // 3
    elif 27 <= y <= 44:
        idx = (y - 27) // 3
    idx = max(0, min(len(SKU_CATALOG) - 1, idx))
    return SKU_CATALOG[idx]


class RackCell:
    def __init__(self, x: int, y: int, max_floors: int = 5, category_sku: str = "", category_name: str = ""):
        self.x = x
        self.y = y
        self.max_floors = max_floors
        self.category_sku = category_sku
        self.category_name = category_name
        # Floor 1 to max_floors (1-indexed) -> Optional[Parcel]
        self.floors: Dict[int, Optional[Parcel]] = {f: None for f in range(1, max_floors + 1)}

    @property
    def occupied_count(self) -> int:
        return sum(1 for p in self.floors.values() if p is not None)

    @property
    def is_full(self) -> bool:
        return self.occupied_count >= self.max_floors

    @property
    def is_empty(self) -> bool:
        return self.occupied_count == 0

    def get_first_empty_floor(self) -> Optional[int]:
        for floor in range(1, self.max_floors + 1):
            if self.floors[floor] is None:
                return floor
        return None

    def store_parcel(self, parcel: Parcel, floor: Optional[int] = None) -> Optional[int]:
        if floor is None:
            floor = self.get_first_empty_floor()
        if floor is None or self.floors[floor] is not None:
            return None
        parcel.rack_x = self.x
        parcel.rack_y = self.y
        parcel.rack_floor = floor
        parcel.status = "STORED_IN_RACK"
        self.floors[floor] = parcel
        return floor

    def remove_parcel(self, floor: int) -> Optional[Parcel]:
        if floor in self.floors and self.floors[floor] is not None:
            parcel = self.floors[floor]
            self.floors[floor] = None
            return parcel
        return None

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "category_sku": self.category_sku,
            "category_name": self.category_name,
            "max_floors": self.max_floors,
            "occupied_count": self.occupied_count,
            "is_full": self.is_full,
            "floors": {
                f: (asdict(p) if p else None) for f, p in self.floors.items()
            }
        }


class InventoryManager:
    def __init__(self, warehouse: WarehouseMap, floors_per_rack: int = 5):
        self.warehouse = warehouse
        self.floors_per_rack = floors_per_rack
        self.racks: Dict[Tuple[int, int], RackCell] = {}

        # Inbound Queues: dock_id -> List[Parcel] waiting for pickup
        self.inbound_queues: Dict[str, List[Parcel]] = {
            s.id: [] for s in warehouse.get_stations_by_type("pickup")
        }

        # Outbound Orders: bay_id -> dict with order info & parcels being delivered
        self.outbound_orders: Dict[str, Optional[dict]] = {
            s.id: None for s in warehouse.get_stations_by_type("dropoff")
        }

        self.parcel_seq = 1000
        self.order_seq = 2000

        self._init_racks()

    def _init_racks(self):
        """Initialize 3D rack cells with category assignments for each row band."""
        for x in range(1, self.warehouse.width - 1):
            for y in range(1, self.warehouse.height - 1):
                if self.warehouse.grid[x][y] == CELL_RACK:
                    cat = get_rack_category_info(y)
                    self.racks[(x, y)] = RackCell(
                        x=x, y=y,
                        max_floors=self.floors_per_rack,
                        category_sku=cat["sku"],
                        category_name=cat["name"]
                    )

    @property
    def total_capacity(self) -> int:
        return len(self.racks) * self.floors_per_rack

    @property
    def total_stored_parcels(self) -> int:
        return sum(r.occupied_count for r in self.racks.values())

    @property
    def occupancy_rate(self) -> float:
        if self.total_capacity == 0:
            return 0.0
        return (self.total_stored_parcels / self.total_capacity) * 100.0

    def find_available_rack_slot_for_sku(self, sku: str) -> Optional[Tuple[int, int, int]]:
        """
        Find a random available rack slot in the designated category rows for the given SKU.
        If designated category rows are 100% full, falls back to any random empty slot in warehouse.
        """
        designated_slots = []
        any_slots = []
        for (rx, ry), rack in self.racks.items():
            if not rack.is_full:
                floor = rack.get_first_empty_floor()
                if floor is not None:
                    if rack.category_sku == sku:
                        designated_slots.append((rx, ry, floor))
                    any_slots.append((rx, ry, floor))

        if designated_slots:
            return random.choice(designated_slots)
        if any_slots:
            return random.choice(any_slots)
        return None

    def find_available_rack_slot(self) -> Optional[Tuple[int, int, int]]:
        """Default slot finder (random fallback)."""
        any_slots = []
        for (rx, ry), rack in self.racks.items():
            if not rack.is_full:
                floor = rack.get_first_empty_floor()
                if floor is not None:
                    any_slots.append((rx, ry, floor))
        return random.choice(any_slots) if any_slots else None

    def add_inbound_shipment(self, dock_id: str, count: Optional[int] = None) -> List[Parcel]:
        """
        Inbound dock receives a batch of r parcels (1 < r < 10, i.e., 2 to 9).
        Dock stays lit yellow while parcels are waiting in queue.
        """
        if count is None:
            count = random.randint(2, 9)

        new_parcels = []
        now = time.time()
        for _ in range(count):
            self.parcel_seq += 1
            cat = random.choice(SKU_CATALOG)
            weight = round(cat["unit_weight"] + random.uniform(-1.0, 3.0), 1)
            parcel = Parcel(
                parcel_id=f"PKG-{self.parcel_seq}",
                sku=cat["sku"],
                sku_name=cat["name"],
                weight=weight,
                origin_dock=dock_id,
                created_at=now,
                status="INBOUND_QUEUED"
            )
            new_parcels.append(parcel)

        self.inbound_queues[dock_id].extend(new_parcels)
        return new_parcels

    def pickup_and_shelf_inbound(self, dock_id: str) -> List[dict]:
        """
        Simulate bot collecting parcels from inbound dock and shelving them into designated category rows at random positions.
        Returns list of stored parcel allocations.
        """
        stored_records = []
        parcels_to_store = list(self.inbound_queues.get(dock_id, []))
        self.inbound_queues[dock_id].clear()

        for parcel in parcels_to_store:
            slot = self.find_available_rack_slot_for_sku(parcel.sku)
            if slot:
                rx, ry, floor = slot
                self.racks[(rx, ry)].store_parcel(parcel, floor=floor)
                stored_records.append({
                    "parcel_id": parcel.parcel_id,
                    "sku": parcel.sku,
                    "weight": parcel.weight,
                    "dock": dock_id,
                    "rack": (rx, ry),
                    "floor": floor
                })
            else:
                # Warehouse completely full: re-queue
                self.inbound_queues[dock_id].append(parcel)

        return stored_records

    def bulk_store_parcels(self, count: int) -> int:
        """Directly allocate and store N parcels into categorized 3D rack rows at random positions."""
        stored = 0
        now = time.time()
        for _ in range(count):
            cat = random.choice(SKU_CATALOG)
            slot = self.find_available_rack_slot_for_sku(cat["sku"])
            if not slot:
                break
            rx, ry, floor = slot
            self.parcel_seq += 1
            weight = round(cat["unit_weight"] + random.uniform(-1.0, 3.0), 1)
            parcel = Parcel(
                parcel_id=f"PKG-{self.parcel_seq}",
                sku=cat["sku"],
                sku_name=cat["name"],
                weight=weight,
                origin_dock="BULK_INGEST",
                created_at=now,
                status="STORED_IN_RACK"
            )
            self.racks[(rx, ry)].store_parcel(parcel, floor=floor)
            stored += 1
        return stored

    def clear_all_inventory(self):
        """Clears all stored parcels from 3D racks."""
        for rack in self.racks.values():
            for f in range(1, rack.max_floors + 1):
                rack.floors[f] = None

    def request_outbound_order(self, bay_id: str, count: Optional[int] = None) -> Optional[dict]:
        """
        Outbound departure bay asks for r parcels (1 < r < 10, i.e., 2 to 9).
        Bay lights up yellow until parcels are deposited.
        Retrieves random parcels across rows so future AMR bots travel across the warehouse.
        """
        if count is None:
            count = random.randint(2, 9)

        # Collect all available stored parcels from racks
        available_parcels: List[Tuple[Tuple[int, int], int, Parcel]] = []
        for (rx, ry), rack in self.racks.items():
            for floor, p in rack.floors.items():
                if p is not None:
                    available_parcels.append(((rx, ry), floor, p))

        if not available_parcels:
            return None  # No parcels available in racks to fulfill

        # Randomize selection so outbound pulls from across all rows in the warehouse
        random.shuffle(available_parcels)
        selected_parcels = available_parcels[:count]

        self.order_seq += 1
        order_id = f"ORD-{self.order_seq}"

        # Fetch and remove parcels from the racks (clearing rack space)
        retrieved_parcels = []
        for (rx, ry), floor, p in selected_parcels:
            removed = self.racks[(rx, ry)].remove_parcel(floor)
            if removed:
                removed.destination_bay = bay_id
                removed.status = "IN_TRANSIT"
                retrieved_parcels.append(removed)

        order_data = {
            "order_id": order_id,
            "bay_id": bay_id,
            "count": len(retrieved_parcels),
            "parcels": [asdict(p) for p in retrieved_parcels],
            "requested_at": time.time(),
            "status": "PROCESSING"
        }
        self.outbound_orders[bay_id] = order_data
        return order_data

    def deposit_outbound_order(self, bay_id: str) -> Optional[dict]:
        """
        Deposits parcels at outbound bay, completing the order.
        Departure bay then clears its yellow state.
        """
        order = self.outbound_orders.get(bay_id)
        if not order:
            return None

        order["status"] = "COMPLETED"
        order["completed_at"] = time.time()
        self.outbound_orders[bay_id] = None  # Cleared
        return order

    def is_inbound_active(self, dock_id: str) -> bool:
        """Returns True if inbound dock has waiting parcels (lit yellow)."""
        return len(self.inbound_queues.get(dock_id, [])) > 0

    def is_outbound_active(self, bay_id: str) -> bool:
        """Returns True if outbound bay is waiting for parcel deposit (lit yellow)."""
        return self.outbound_orders.get(bay_id) is not None

    def get_summary(self) -> dict:
        """Overview stats for dashboard HUD."""
        return {
            "total_racks": len(self.racks),
            "floors_per_rack": self.floors_per_rack,
            "total_capacity": self.total_capacity,
            "stored_parcels": self.total_stored_parcels,
            "occupancy_rate": round(self.occupancy_rate, 2),
            "inbound_status": {
                dock_id: len(queue) for dock_id, queue in self.inbound_queues.items()
            },
            "outbound_status": {
                bay_id: (order["count"] if order else 0) for bay_id, order in self.outbound_orders.items()
            }
        }
