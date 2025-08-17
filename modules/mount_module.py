# Mount Module
# Mount control module using INDIGO JSON client (Mount Agent native)

import threading
import time
from typing import Optional

from utilities.indigo_json_client import IndigoJSONClient
from utilities.config import GEO_LAT, GEO_LON, GEO_ELEV
from utilities.logger import emit_log

_socketio = None  # Module-level SocketIO reference


def set_socketio(instance):
    """Attach global socketio instance for emitting from MountControl."""
    global _socketio
    _socketio = instance


class MountControl:
    """
    Public API (stable for app.py):
      - set_location(lat, lon, elev)
      - slew(direction, rate="solar")         # press-and-hold style start
      - stop()                                # stop any continuous motion
      - nudge(direction, ms=200, rate="solar")# single-click micro move
      - park()
      - unpark()
      - get_coordinates(emit=False)
      - shutdown()

    Notes:
      * Tracking enable/disable is intentionally OUT of this module now.
        `track_sun()` remains as a harmless no-op to avoid breaking app.py.
      * Emits:
        - "mount_coordinates": {
              ra, dec, ra_str, dec_str, alt, az
          }
        - "mount_status": "IDLE|SLEWING|PARKED"
    """

    def __init__(self, indigo_client: IndigoJSONClient):
        self.client = indigo_client
        self.device = "Mount Agent"  # from your property dump

        self.set_location(GEO_LAT, GEO_LON, GEO_ELEV)

        # Cached state (RA in hours, DEC in degrees)
        self._state = {
            "ra_h": None,       # float hours
            "dec_deg": None,    # float degrees
            "alt_deg": None,    # float degrees
            "az_deg": None,     # float degrees
            "slew_rate": "GUIDE",
            "parked": False,
            "moving_ra": False,
            "moving_dec": False,
        }

        # Pulse (nudge) control
        self._pulse_lock = threading.Lock()
        self._pulse_thread: Optional[threading.Thread] = None
        self._pulse_active = False

        # Subscribe to INDIGO updates
        self.client.on("setNumberVector", self._handle_number_vector)
        self.client.on("setSwitchVector", self._handle_switch_vector)

        # Poll key properties (1 Hz) to stay fresh even if no events arrive
        self._mon_running = False
        self._start_monitor()

    # ---------------- Formatting helpers ----------------

    @staticmethod
    def format_ra(ra_h):
        """Decimal hours -> HH:MM:SS.ss"""
        if ra_h is None:
            return "--:--:--"
        hours = int(ra_h)
        minutes_f = (ra_h - hours) * 60.0
        minutes = int(minutes_f)
        seconds = (minutes_f - minutes) * 60.0
        return f"{hours:02}:{minutes:02}:{seconds:05.2f}"

    @staticmethod
    def format_dec(dec_deg):
        """Decimal degrees -> ±DD:MM:SS.ss"""
        if dec_deg is None:
            return "--:--:--"
        sign = "-" if dec_deg < 0 else "+"
        d = abs(dec_deg)
        degrees = int(d)
        minutes_f = (d - degrees) * 60.0
        minutes = int(minutes_f)
        seconds = (minutes_f - minutes) * 60.0
        return f"{sign}{degrees:02}:{minutes:02}:{seconds:05.2f}"

    # ---------------- Emitting ----------------

    def _emit_status(self):
        status = "PARKED" if self._state["parked"] else (
            "SLEWING" if (self._state["moving_ra"] or self._state["moving_dec"]) else "IDLE"
        )
        if _socketio:
            _socketio.emit("mount_status", status)
        emit_log(f"[MOUNT] Status: {status}")

    def _emit_coordinates(self):
        ra = self._state["ra_h"]
        dec = self._state["dec_deg"]
        alt = self._state["alt_deg"]
        az = self._state["az_deg"]
        payload = {
            "ra": ra,
            "dec": dec,
            "alt": alt,
            "az": az,
            "ra_str": self.format_ra(ra) if ra is not None else "--:--:--",
            "dec_str": self.format_dec(dec) if dec is not None else "--:--:--",
        }
        if _socketio:
            _socketio.emit("mount_coordinates", payload)

    # ---------------- INDIGO handlers ----------------

    def _handle_number_vector(self, msg: dict):
        """Capture RA/DEC, ALT/AZ, etc."""
        if msg.get("device") != self.device:
            return

        name = msg.get("name")
        items = {it["name"]: it.get("value") for it in msg.get("items", [])}

        changed = False

        # Prefer Agent coordinates for display but accept mount native too
        if name in ("AGENT_MOUNT_EQUATORIAL_COORDINATES", "MOUNT_EQUATORIAL_COORDINATES"):
            ra = items.get("RA")
            dec = items.get("DEC")
            if ra is not None:
                ra_f = float(ra)
                if ra_f != self._state["ra_h"]:
                    self._state["ra_h"] = ra_f
                    changed = True
            if dec is not None:
                dec_f = float(dec)
                if dec_f != self._state["dec_deg"]:
                    self._state["dec_deg"] = dec_f
                    changed = True

        elif name == "MOUNT_HORIZONTAL_COORDINATES":
            alt = items.get("ALT")
            az = items.get("AZ")
            if alt is not None:
                alt_f = float(alt)
                if alt_f != self._state["alt_deg"]:
                    self._state["alt_deg"] = alt_f
                    changed = True
            if az is not None:
                az_f = float(az)
                if az_f != self._state["az_deg"]:
                    self._state["az_deg"] = az_f
                    changed = True

        if changed:
            self._emit_coordinates()

        # status after any numeric change (e.g., motion may have stopped)
        self._emit_status()

    def _handle_switch_vector(self, msg: dict):
        """Capture motion, park, slew rate switches."""
        if msg.get("device") != self.device:
            return

        name = msg.get("name")
        items = {it["name"]: it.get("value") for it in msg.get("items", [])}

        if name == "MOUNT_SLEW_RATE":
            for rate in ("GUIDE", "CENTERING", "FIND", "MAX"):
                if items.get(rate, False):
                    self._state["slew_rate"] = rate
                    break

        elif name == "MOUNT_MOTION_RA":
            self._state["moving_ra"] = bool(items.get("WEST", False) or items.get("EAST", False))

        elif name == "MOUNT_MOTION_DEC":
            self._state["moving_dec"] = bool(items.get("NORTH", False) or items.get("SOUTH", False))

        elif name == "MOUNT_PARK":
            self._state["parked"] = bool(items.get("PARKED", False))

        self._emit_status()

    # ---------------- Commands ----------------

    def set_location(self, latitude, longitude, elevation):
        """Write site to Agent (Mount Agent.GEOGRAPHIC_COORDINATES.*)"""
        try:
            self.client.send({
                "newNumberVector": {
                    "device": self.device,
                    "name": "GEOGRAPHIC_COORDINATES",
                    "items": [
                        {"name": "LAT", "value": float(latitude)},
                        {"name": "LONG", "value": float(longitude)},
                        {"name": "ELEVATION", "value": float(elevation)}
                    ]
                }
            }, quiet=True)
            emit_log(f"[MOUNT] Set site: lat={latitude}, lon={longitude}, elev={elevation}")
        except Exception as e:
            emit_log(f"[MOUNT] ERROR set_location: {e}")

    def _map_ui_rate(self, ui_rate: str) -> str:
        """Map UI rate tokens -> Agent slew rate group members."""
        ui = (ui_rate or "solar").lower()
        if ui == "slow":
            return "CENTERING"
        if ui == "fast":
            return "MAX"
        # default 'solar' button maps to a gentle nudge rate
        return "GUIDE"

    def _set_slew_rate_switch(self, ui_rate: str):
        want = self._map_ui_rate(ui_rate)
        items = [
            {"name": "GUIDE", "value": want == "GUIDE"},
            {"name": "CENTERING", "value": want == "CENTERING"},
            {"name": "FIND", "value": want == "FIND"},
            {"name": "MAX", "value": want == "MAX"},
        ]
        self.client.send({
            "newSwitchVector": {
                "device": self.device,
                "name": "MOUNT_SLEW_RATE",
                "items": items
            }
        }, quiet=True)

    def slew(self, direction, rate="solar"):
        """Begin continuous motion in a cardinal direction. Call stop() to end."""
        direction = (direction or "").lower()
        emit_log(f"[MOUNT] Slew start: {direction} ({rate})")

        self._set_slew_rate_switch(rate)

        if direction in ("east", "west"):
            self.client.send({
                "newSwitchVector": {
                    "device": self.device,
                    "name": "MOUNT_MOTION_RA",
                    "items": [
                        {"name": "WEST", "value": direction == "west"},
                        {"name": "EAST", "value": direction == "east"},
                    ]
                }
            }, quiet=True)

        elif direction in ("north", "south"):
            self.client.send({
                "newSwitchVector": {
                    "device": self.device,
                    "name": "MOUNT_MOTION_DEC",
                    "items": [
                        {"name": "NORTH", "value": direction == "north"},
                        {"name": "SOUTH", "value": direction == "south"},
                    ]
                }
            }, quiet=True)
        else:
            emit_log(f"[MOUNT] ERROR invalid slew direction: {direction}")

    def stop(self):
        """Stop both axes motion (and cancel any active pulse)."""
        emit_log("[MOUNT] Stop motion")
        # cancel pulse if active
        with self._pulse_lock:
            self._pulse_active = False

        try:
            self.client.send({
                "newSwitchVector": {
                    "device": self.device,
                    "name": "MOUNT_MOTION_DEC",
                    "items": [{"name": "NORTH", "value": False}, {"name": "SOUTH", "value": False}]
                }
            }, quiet=True)
            self.client.send({
                "newSwitchVector": {
                    "device": self.device,
                    "name": "MOUNT_MOTION_RA",
                    "items": [{"name": "WEST", "value": False}, {"name": "EAST", "value": False}]
                }
            }, quiet=True)
            # optional hard abort (safe no-op if ignored)
            self.client.send({
                "newSwitchVector": {
                    "device": self.device,
                    "name": "MOUNT_ABORT_MOTION",
                    "items": [{"name": "ABORT_MOTION", "value": True}]
                }
            }, quiet=True)
        except Exception as e:
            emit_log(f"[MOUNT] Stop failed: {e}")

    def nudge(self, direction: str, ms: int = 200, rate: str = "solar"):
        """
        Fire a short motion pulse in one direction, then stop automatically.
        Safe against double-click spam via a lightweight lock.
        """
        direction = (direction or "").lower()
        ms = max(20, min(int(ms), 5000))  # clamp 20ms..5s

        def _pulse():
            try:
                self._set_slew_rate_switch(rate)

                # start motion
                if direction in ("east", "west"):
                    self.client.send({
                        "newSwitchVector": {
                            "device": self.device,
                            "name": "MOUNT_MOTION_RA",
                            "items": [
                                {"name": "WEST", "value": direction == "west"},
                                {"name": "EAST", "value": direction == "east"},
                            ]
                        }
                    }, quiet=True)
                elif direction in ("north", "south"):
                    self.client.send({
                        "newSwitchVector": {
                            "device": self.device,
                            "name": "MOUNT_MOTION_DEC",
                            "items": [
                                {"name": "NORTH", "value": direction == "north"},
                                {"name": "SOUTH", "value": direction == "south"},
                            ]
                        }
                    }, quiet=True)
                else:
                    emit_log(f"[MOUNT] ERROR invalid nudge direction: {direction}")
                    return

                # hold for pulse duration unless cancelled
                start = time.time()
                while True:
                    with self._pulse_lock:
                        if not self._pulse_active:
                            break
                    if (time.time() - start) * 1000.0 >= ms:
                        break
                    time.sleep(0.01)

            finally:
                # stop axis used
                if direction in ("east", "west"):
                    self.client.send({
                        "newSwitchVector": {
                            "device": self.device,
                            "name": "MOUNT_MOTION_RA",
                            "items": [{"name": "WEST", "value": False}, {"name": "EAST", "value": False}]
                        }
                    }, quiet=True)
                elif direction in ("north", "south"):
                    self.client.send({
                        "newSwitchVector": {
                            "device": self.device,
                            "name": "MOUNT_MOTION_DEC",
                            "items": [{"name": "NORTH", "value": False}, {"name": "SOUTH", "value": False}]
                        }
                    }, quiet=True)
                with self._pulse_lock:
                    self._pulse_active = False

        # Start/replace a pulse
        with self._pulse_lock:
            # cancel any prior pulse loop and mark new active
            self._pulse_active = False
        # tiny pause to allow any prior loop to notice cancellation
        time.sleep(0.01)
        with self._pulse_lock:
            self._pulse_active = True
        self._pulse_thread = threading.Thread(target=_pulse, daemon=True)
        self._pulse_thread.start()

    def _slew_to_coords(self, ra_h, dec_deg):
        """Agent-friendly slew to target coordinates."""
        try:
            self.client.send({
                "newNumberVector": {
                    "device": self.device,
                    "name": "AGENT_MOUNT_EQUATORIAL_COORDINATES",
                    "items": [{"name": "RA", "value": float(ra_h)},
                              {"name": "DEC", "value": float(dec_deg)}]
                }
            }, quiet=True)
            self.client.send({
                "newSwitchVector": {
                    "device": self.device,
                    "name": "AGENT_START_PROCESS",
                    "items": [{"name": "SLEW", "value": True}]
                }
            }, quiet=True)
            emit_log(f"[MOUNT] SlewTo: RA={ra_h:.6f}h  DEC={dec_deg:.6f}°")
        except Exception as e:
            emit_log(f"[MOUNT] SlewTo failed: {e}")

    # ---- Tracking hooks (kept as no-ops to avoid breaking current app.py) ----

    def track_sun(self):
        """Deprecated here; tracking is handled by track_module.py. No-op."""
        emit_log("[MOUNT] track_sun() called — no-op (handled by track_module.py)")

    # ---------------- Park / Unpark ----------------

    def park(self):
        emit_log("[MOUNT] Park")
        try:
            self.client.send({
                "newSwitchVector": {
                    "device": self.device,
                    "name": "MOUNT_PARK",
                    "items": [{"name": "PARKED", "value": True}, {"name": "UNPARKED", "value": False}]
                }
            }, quiet=True)
        except Exception as e:
            emit_log(f"[MOUNT] Park failed: {e}")

    def unpark(self):
        emit_log("[MOUNT] Unpark")
        try:
            self.client.send({
                "newSwitchVector": {
                    "device": self.device,
                    "name": "MOUNT_PARK",
                    "items": [{"name": "PARKED", "value": False}, {"name": "UNPARKED", "value": True}]
                }
            }, quiet=True)
        except Exception as e:
            emit_log(f"[MOUNT] Unpark failed: {e}")

    def get_status(self):
        if self._state["parked"]:
            return "PARKED"
        if self._state["moving_ra"] or self._state["moving_dec"]:
            return "SLEWING"
        return "IDLE"

    # ---------------- Queries ----------------

    def get_coordinates(self, emit=False):
        """Return last cached coordinates (numeric + formatted)."""
        ra = self._state["ra_h"]
        dec = self._state["dec_deg"]
        alt = self._state["alt_deg"]
        az = self._state["az_deg"]
        result = {
            "ra": ra,
            "dec": dec,
            "alt": alt,
            "az": az,
            "ra_str": self.format_ra(ra) if ra is not None else "--:--:--",
            "dec_str": self.format_dec(dec) if dec is not None else "--:--:--",
        }
        if emit:
            self._emit_coordinates()
        return result

    # ---------------- Monitor ----------------

    def _start_monitor(self):
        if self._mon_running:
            return
        self._mon_running = True

        def monitor():
            names_to_poll = [
                # Coords
                "AGENT_MOUNT_EQUATORIAL_COORDINATES",
                "MOUNT_EQUATORIAL_COORDINATES",
                "MOUNT_HORIZONTAL_COORDINATES",
                # State
                "MOUNT_SLEW_RATE",
                "MOUNT_MOTION_RA",
                "MOUNT_MOTION_DEC",
                "MOUNT_PARK",
            ]
            while self._mon_running:
                try:
                    for nm in names_to_poll:
                        self.client.send({
                            "getProperties": {
                                "device": self.device,
                                "name": nm
                            }
                        }, quiet=True)
                except Exception as e:
                    emit_log(f"[MOUNT] Monitor poll error: {e}")
                time.sleep(1)

        threading.Thread(target=monitor, daemon=True).start()

    # ---------------- Shutdown ----------------

    def shutdown(self):
        self._mon_running = False
        try:
            self.stop()
        except Exception:
            pass
        try:
            self.client.close()
        except Exception:
            pass
        emit_log("[MOUNT] Module shutdown")
