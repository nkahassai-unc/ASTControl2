# Flask App for Automated Solar Telescope Control

import warnings

from modules import solar_module
warnings.filterwarnings("ignore", category=DeprecationWarning)

import logging
logging.getLogger("paramiko").setLevel(logging.WARNING)

import requests
from flask import Flask, render_template, Response, jsonify
from flask_socketio import SocketIO

from utilities.config import RASPBERRY_PI_IP, SSH_USERNAME, SSH_PASSWORD, FILE_STATUS
from utilities.network_utils import run_pi_ssh_command

from modules.weather_module import WeatherForecast
from modules.solar_module import SolarPosition
from modules import file_module

from modules.server_module import IndigoRemoteServer
from modules.server_module import indigo_client, start_indigo_client
from utilities.logger import emit_log, set_socketio as set_log_socketio, get_log_history


from modules.nstep_module import NStepFocuser, set_socketio as set_nstep_socketio
from modules.mount_module import MountControl, set_socketio as set_mount_socketio
from modules import arduino_module


# === App Init ===
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
set_log_socketio(socketio)

# === Module Instances ===
weather_forecast = WeatherForecast()
solar_calculator = SolarPosition()
solar_module.set_socketio(socketio)

indigo = IndigoRemoteServer(RASPBERRY_PI_IP, SSH_USERNAME, SSH_PASSWORD)

mount = MountControl(indigo_client=indigo_client)
nstep = NStepFocuser(indigo_client=indigo_client)

file_module.set_socketio_instance(socketio)

try:
    start_indigo_client()
except Exception as e:
    print(f"[APP] Warning: INDIGO client failed to start — {e}")


# Attach shared socket
set_nstep_socketio(socketio)
set_mount_socketio(socketio)
arduino_module.set_socketio(socketio)

# === Routes ===
# Main Web Page
@app.route('/')
def index():
    return render_template('index.html', pi_ip=RASPBERRY_PI_IP)

@socketio.on("connect")
def send_log_history():
    for msg in get_log_history():
        socketio.emit("server_log", msg)

# File Handlers
@app.route("/get_file_list")
def get_file_list_route():
    files = file_module.get_file_list()

    # Inject live status for frontend coloring (optional if already included)
    for f in files:
        f["status"] = FILE_STATUS.get(f["name"], "Copied")
    return jsonify(files)


# === WebSocket Handlers ===

# === Weather Handlers ===
@socketio.on('get_weather')
def send_weather_now():
    socketio.emit("update_weather", weather_forecast.get_data())


# === Solar Handlers ===
@socketio.on('get_solar')
def send_solar_now():
    # Sends current solar az/alt
    socketio.emit("update_solar", solar_calculator.get_data())

@socketio.on("get_mount_solar_state")
def handle_get_mount_solar_state():
    solar_coords = solar_calculator.get_solar_equatorial()
    mount_coords = mount.get_coordinates()  # assumes mount module supports this
    socketio.emit("mount_solar_state", {
        **solar_coords,
        **mount_coords
    })

@socketio.on("get_solar_path")
def handle_get_solar_path():
    path = solar_calculator.get_full_day_path()  # internally cached now
    socketio.emit("solar_path_data", path)

@app.route("/get_solar_path")
def get_solar_path():
    path = solar_calculator.get_full_day_path()  # internally cached now
    return jsonify(path)


# === INDIGO Server Handlers ===
@socketio.on('start_indigo')
def handle_start_indigo():
    indigo.start(lambda msg: socketio.emit("server_log", msg))

@socketio.on('stop_indigo')
def handle_stop_indigo():
    result = indigo.stop()
    emit_log(result.get("stdout", ""))

@socketio.on('check_indigo_status')
def handle_check_indigo_status():
    is_up = indigo.check_status()
    socketio.emit("indigo_status", {
        "running": is_up,
        "ip": RASPBERRY_PI_IP if is_up else None
    })


# === Mount Handlers ===
@socketio.on("get_mount_coordinates")
def handle_get_mount_coordinates():
    coords = mount.get_coordinates()
    socketio.emit("mount_coordinates", coords)

@socketio.on("get_mount_solar_state")
def handle_get_mount_solar_state():
    solar_coords = solar_calculator.get_solar_equatorial()  # ra_solar / dec_solar (strings)
    mount_coords = mount.get_coordinates()                  # ra/dec/alt/az + ra_str/dec_str
    socketio.emit("mount_solar_state", {**solar_coords, **mount_coords})


@socketio.on("get_mount_status")
def handle_get_mount_status():
    # push latest coords
    mount.get_coordinates(emit=True)
    # push status (public API)
    socketio.emit("mount_status", mount.get_status())

@socketio.on("slew_mount")
def handle_slew_mount(data):
    mount.slew(data["direction"], data.get("rate", "solar"))

@socketio.on("nudge_mount")
def handle_nudge_mount(data):
    mount.nudge(
        data.get("direction"),
        int(data.get("ms", 200)),
        data.get("rate", "solar"),
    )

@socketio.on("stop_mount")
def handle_stop_mount():
    mount.stop()

@socketio.on("track_sun")
def handle_track_sun():
    mount.track_sun()

@socketio.on("park_mount")
def handle_park_mount():
    mount.park()

@socketio.on("unpark_mount")
def handle_unpark_mount():
    mount.unpark()

# === nSTEP Focuser Handlers ===
@socketio.on("nstep_move")
def handle_nstep_move(data):
    direction = data.get("direction")
    nstep.move(direction)
    nstep.get_position()  # Optionally request update right after move

@socketio.on("get_nstep_position")
def handle_get_nstep_position():
    nstep.get_position()

# === Arduino Handlers ===
@socketio.on('set_dome')
def handle_set_dome(data):
    state_cmd = data.get("state")  # should be "open" or "close"
    if state_cmd and arduino_module.set_dome(state_cmd):
        emit_log("dome_state", arduino_module.get_dome())
    else:
        emit_log(f"⚠️ Failed to set dome state: {state_cmd}")

@socketio.on('set_etalon')
def handle_set_etalon(data):
    index = int(data.get("index", 0))
    value = int(data.get("value", 90))
    if arduino_module.set_etalon(index, value):
        socketio.emit("etalon_position", {
            "index": index,
            "value": arduino_module.get_etalon(index)
        })
    else:
        emit_log(f"⚠️ Failed to set etalon {index} to {value}")

@socketio.on('get_arduino_state')
def handle_get_arduino_state():
    state = arduino_module.get_state()
    socketio.emit("arduino_state", state)

# === Science Camera Handlers ===
preview_running = False  # Global state

@socketio.on("start_fc_preview")
def handle_start_fc_preview():
    global preview_running
    emit_log("[FireCapture] ✅ Preview and HTTP server started.")
    try:
        run_pi_ssh_command("/home/pi/fc_stream/start_fc_http_server.sh")
        run_pi_ssh_command("/home/pi/fc_stream/fc_preview_stream.sh &")
        preview_running = True
    except Exception as e:
        emit_log(f"[FireCapture] ❌ Preview failed: {e}")

@socketio.on("stop_fc_preview")
def handle_stop_fc_preview():
    global preview_running
    emit_log("[FireCapture] 🛑 Stopping preview and HTTP server...")
    if not preview_running:
        return
    try:
        run_pi_ssh_command("pkill -f fc_preview_stream.sh")
        run_pi_ssh_command("pkill -f 'http.server 8082'")
        preview_running = False
    except Exception as e:
        emit_log(f"[FireCapture] ❌ Failed to stop preview: {e}")

@socketio.on("trigger_fc_capture")
def handle_fc_capture():
    try:
        run_pi_ssh_command("cd /home/pi/fc_capture && DISPLAY=:0 ./trigger_fc_script.sh")
        emit_log("📸 [FireCapture] Capture triggered.")
    except Exception as e:
        emit_log(f"❌ [FireCapture] Capture failed: {e}")

@socketio.on("get_fc_status")
def handle_get_fc_status():
    socketio.emit("fc_preview_status", preview_running)

# === Dome Camera Handler ===
@app.route("/ping_dome_status")
def ping_dome_status():
    try:
        ip = RASPBERRY_PI_IP
        url = f"http://{ip}:8080/"
        resp = requests.get(url, timeout=2)
        if resp.status_code == 200:
            return Response("OK", status=200)
        return Response("Unavailable", status=503)
    except Exception as e:
        return Response(f"Error: {e}", status=502)
    
# === Start App ===
if __name__ == '__main__':
    weather_forecast.start_monitor(socketio, interval=600)
    solar_calculator.start_monitor(socketio, interval=5)
    arduino_module.start_monitor(interval=1)

    # Launch file monitor in background via SocketIO
    socketio.start_background_task(file_module.start_file_monitoring, 5)
    emit_log("[APP] Background tasks started.")

    werkzeug_log = logging.getLogger('werkzeug')
    werkzeug_log.setLevel(logging.ERROR)

    print("Starting Flask app on http://localhost:5001...")
    socketio.run(app, host='0.0.0.0', port=5001, debug=False, use_reloader=False)