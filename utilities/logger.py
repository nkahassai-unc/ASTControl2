# Logger Module
# Centralized logging with SocketIO support
from datetime import datetime

log_buffer = []
socketio_instance = None

def set_socketio(sock):
    global socketio_instance
    socketio_instance = sock

def emit_log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    log_buffer.append(full_msg)
    if len(log_buffer) > 300:
        log_buffer.pop(0)
    if socketio_instance:
        try:
            socketio_instance.emit("server_log", full_msg)
        except Exception as e:
            print(f"[emit_log error] {e}")
    else:
        print(f"[emit_log fallback] {full_msg}")

def get_log_history():
    return log_buffer