# nSTEP Focuser Module
# Focuser control module using INDIGO JSON client

import threading
from utilities.indigo_json_client import IndigoJSONClient

_socketio = None  # Module-level SocketIO reference

def set_socketio(instance):
    global _socketio
    _socketio = instance

class NStepFocuser:
    def __init__(self, indigo_client):
        self.client = indigo_client
        self.device = "nSTEP"
        self.current_position = 0  # Updated by feedback
        self.set_position = 0      # Target set by user

    def move(self, direction, speed=50):
        if direction not in ("in", "out", "stop"):
            return

        speed = max(1, min(int(speed), 100))  # Clamp to 1–100
        motion = {
            "IN": direction == "in",
            "OUT": direction == "out",
            "ABORT": direction == "stop"
        }

        self.set_position = speed  # Store set speed for feedback

        self.client.send({
            "setProperties": {
                "device": self.device,
                "name": "FOCUSER_MOTION",
                "elements": {
                    "FOCUSER_INWARD": motion["IN"],
                    "FOCUSER_OUTWARD": motion["OUT"],
                    "FOCUSER_ABORT_MOTION": motion["ABORT"]
                }
            }
        })

        self.client.send({
            "setProperties": {
                "device": self.device,
                "name": "FOCUSER_SPEED",
                "elements": {
                    "FOCUSER_SPEED_VALUE": speed
                }
            }
        })

        self._emit_position_feedback()

    def get_position(self):
        self.client.send({
            "getProperties": {
                "device": self.device,
                "name": "FOCUSER_POSITION"
            }
        })
        threading.Thread(target=self._poll_position, daemon=True).start()

    def _poll_position(self):
        try:
            state = self.client.get_property(self.device, "FOCUSER_POSITION")
            if state and "FOCUSER_POSITION" in state.get("elements", {}):
                self.current_position = state["elements"]["FOCUSER_POSITION"]["value"]
                self._emit_position_feedback()
        except Exception as e:
            self._emit_log(f"Poll error: {e}")

    def _emit_position_feedback(self):
        if _socketio:
            _socketio.emit("nstep_feedback", {
                "current": self.current_position,
                "set": self.set_position
            })

    def _emit_log(self, message):
        if _socketio:
            _socketio.emit("server_log", f"[nSTEP] {message}")
