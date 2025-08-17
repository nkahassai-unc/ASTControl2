# Arduino Module
# Central Arduino controller for UI interaction using TCP client

import threading
import time
import socket
from utilities import config
from utilities.config import RASPBERRY_PI_IP
from utilities.logger import emit_log

# === Arduino State (from config) ===
state = config.ARDUINO_STATE

_socketio = None

def set_socketio(sio):
    global _socketio
    _socketio = sio

# === TCP Client ===
class ArduinoTCPClient:
    def __init__(self, host=RASPBERRY_PI_IP, port=5555):
        self.host = host
        self.port = port
        self.sock = None
        self.lock = threading.Lock()
        self.last_used = time.time()
        self.idle_timeout = 20
        self.last_fail_time = 0
        self.fail_count = 0
        self.max_log_interval = 15  # seconds
        self.max_warns = 3
        self.warn_sent = False
        self.watcher_thread = threading.Thread(target=self._idle_watcher, daemon=True)
        self.watcher_thread.start()

    def _connect(self):
        if self.fail_count >= self.max_warns:
            return  # Stop retrying after max_warns

        try:
            if self.sock:
                self.sock.close()
            self.sock = socket.create_connection((self.host, self.port), timeout=3)
            state["connected"] = True
            self.fail_count = 0
            self.warn_sent = False
            emit_log("[ARDUINO-TCP] ✅ Connected to servo_daemon.")
        except Exception as e:
            state["connected"] = False
            self.fail_count += 1
            now = time.time()

            if now - self.last_fail_time > self.max_log_interval:
                emit_log(f"[ARDUINO-TCP] ❌ Connection attempt {self.fail_count}: {e}")
                self.last_fail_time = now

            if _socketio and not self.warn_sent and self.fail_count == self.max_warns:
                try:
                    _socketio.emit("server_log", "⚠️ Arduino unreachable after 5 retries.")
                    self.warn_sent = True
                except Exception as emit_err:
                    emit_log(f"[ARDUINO-TCP] Emit fail: {emit_err}")

            self.sock = None

    def send(self, message: str) -> str:
        with self.lock:
            try:
                if not self.sock:
                    self._connect()
                    if not self.sock:
                        return ""
                self.sock.sendall((message + '\n').encode())

                buffer = ""
                while True:
                    data = self.sock.recv(1024).decode()
                    if not data:
                        raise ConnectionError("Connection closed by server")
                    buffer += data
                    if '\n' in buffer:
                        break
                self.last_used = time.time()
                state["connected"] = True
                return buffer.strip()

            except Exception as e:
                state["connected"] = False
                emit_log(f"[ARDUINO-TCP] Send failed: {e}")
                self.sock = None
                return ""

    def _idle_watcher(self):
        while True:
            time.sleep(5)
            with self.lock:
                if self.sock and (time.time() - self.last_used > self.idle_timeout):
                    try:
                        self.sock.close()
                        emit_log("[ARDUINO-TCP] Closed idle socket.")
                    except:
                        pass
                    self.sock = None

# Persistent client instance
_client = ArduinoTCPClient()

# === Public UI API ===

def set_dome(state_cmd: str) -> bool:
    if state_cmd not in ("open", "close"):
        return False
    res = _send(f"dome {'180' if state_cmd == 'open' else '0'}")
    if res.startswith("dome:"):
        state["dome"] = state_cmd.upper()
        _update()
        return True
    return False

def set_etalon(index: int, value: int) -> bool:
    if index not in (1, 2) or not (0 <= value <= 180):
        return False
    res = _send(f"et{index} {value}")
    if res.startswith(f"et{index}:"):
        state[f"etalon{index}"] = value
        _update()
        return True
    return False

def get_state() -> dict:
    return state

def get_dome() -> str:
    return state.get("dome", "UNKNOWN")

def get_etalon(index: int) -> int:
    return state.get(f"etalon{index}", 90)

# === Background Polling Thread ===
_poll_thread = None
_running = False

def start_monitor(interval=5):
    global _poll_thread, _running
    if _poll_thread and _poll_thread.is_alive():
        return
    _running = True
    _poll_thread = threading.Thread(target=_poll_loop, args=(interval,), daemon=True)
    _poll_thread.start()

def stop_monitor():
    global _running
    _running = False

# === Internals ===

def _poll_loop(interval):
    retry_delay = 10  # seconds between retry attempts

    while _running:
        if not state.get("connected"):
            if _client.fail_count < _client.max_warns:
                _client._connect()
            else:
                time.sleep(retry_delay)
                continue

        try:
            dome = _send("status").strip()
            for line in dome.split("\n"):
                if line.startswith("dome:"):
                    dome_pos = int(line.split(":")[1])
                    state["dome_raw"] = dome_pos
                    if dome_pos >= 170:
                        state["dome"] = "OPEN"
                    elif dome_pos <= 10:
                        state["dome"] = "CLOSED"
                    else:
                        state["dome"] = f"Moving ({dome_pos}°)"
                elif line.startswith("et1:"):
                    state["etalon1"] = int(line.split(":")[1])
                elif line.startswith("et2:"):
                    state["etalon2"] = int(line.split(":")[1])
            _update()
        except Exception as e:
            emit_log(f"[Arduino Monitor Error] {e}")
            state["connected"] = False
        time.sleep(interval)

def _send(cmd: str) -> str:
    return _client.send(cmd)

def _update():
    state['last_updated'] = time.strftime("%Y-%m-%d %H:%M:%S")
    if _socketio:
        try:
            _socketio.emit("arduino_state", state)
        except Exception as e:
            emit_log(f"[Emit Error] Failed to emit Arduino state: {e}")