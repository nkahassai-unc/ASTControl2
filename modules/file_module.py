# File Handling Module
# Monitors and copies files from a watched directory to a destination directory

import os
import time
import threading
from datetime import datetime

import smbclient
from utilities.config import FILE_WATCH_DIR, FILE_DEST_DIR, FILE_STATUS, RASPBERRY_PI_IP, SSH_USERNAME, SSH_PASSWORD
from utilities.logger import emit_log

STABILITY_CHECK_TIME = 3  # Seconds

socketio = None
def set_socketio_instance(sio):
    global socketio
    socketio = sio

# Configure SMB (guest, no creds)
smbclient.ClientConfig(
    username=SSH_USERNAME,
    password=SSH_PASSWORD,
    domain="",             # blank domain for workgroup
)
class FileHandler:
    def __init__(self):
        self.file_count = 0
        self.current_day = datetime.now().date()

    def is_file_write_complete(self, filepath):
        try:
            with smbclient.open_file(filepath, mode='rb') as f:
                initial_size = f.seek(0, os.SEEK_END)
            time.sleep(STABILITY_CHECK_TIME)
            with smbclient.open_file(filepath, mode='rb') as f:
                final_size = f.seek(0, os.SEEK_END)
            return initial_size == final_size
        except Exception as e:
            emit_log(f"[FILES] File check error: {e}")
            return False

    def process_file(self, smb_path, filename):
        FILE_STATUS[filename] = "Detected"

        if not self.is_file_write_complete(smb_path):
            FILE_STATUS[filename] = "Failed"
            emit_log(f"[FILES] File still writing: {filename}")
            self._emit_update()
            return

        FILE_STATUS[filename] = "Copying"
        now = datetime.now()
        if now.date() != self.current_day:
            self.current_day = now.date()
            self.file_count = 0
        self.file_count += 1

        date_str = now.strftime('%m%d%y')
        time_str = now.strftime('%H%M%S')
        new_folder = f"{self.file_count}_{date_str}_{time_str}"
        new_path = os.path.join(FILE_DEST_DIR, new_folder)
        os.makedirs(new_path, exist_ok=True)

        dest_file = os.path.join(new_path, filename)
        try:
            with smbclient.open_file(smb_path, mode='rb') as remote, open(dest_file, 'wb') as local:
                local.write(remote.read())
            FILE_STATUS[filename] = "Copied"
            emit_log(f"[FILES] Copied: {filename} → {dest_file}")
            smbclient.remove(smb_path)
            emit_log(f"[FILES] Deleted original: {filename}")
        except Exception as e:
            FILE_STATUS[filename] = "Failed"
            emit_log(f"[FILES] Error copying {filename}: {e}")
        finally:
            self._emit_update()

    def _emit_update(self):
        if socketio:
            try:
                socketio.emit("file_list_update", FileHandler.get_file_list(), broadcast=True)
            except Exception as e:
                emit_log(f"[FILES] Emit error: {e}")

    def check_directory(self):
        base_share = FILE_WATCH_DIR
        base_path = f"\\\\{RASPBERRY_PI_IP}\\{base_share}"
        today_str = datetime.now().strftime('%m%d%y')
        smb_today = base_path + "\\" + today_str

        if not smbclient.path.exists(base_path):
            emit_log(f"[FILES] ❌ Base watch directory missing: {base_path}")
            if socketio:
                socketio.emit("file_watch_status", {"status": "disconnected"})
            return
        else:
            if socketio:
                socketio.emit("file_watch_status", {"status": "connected"})

        try:
            if not smbclient.path.exists(base_path):
                if not hasattr(self, "warned_base_missing") or not self.warned_base_missing:
                    emit_log(f"[FILES] ❌ Base watch directory missing: {base_path}")
                    self.warned_base_missing = True
                return
            else:
                if getattr(self, "warned_base_missing", False):
                    emit_log(f"[FILES] ✅ Base directory reconnected: {base_path}")
                self.warned_base_missing = False

            if not smbclient.path.exists(smb_today):
                if not hasattr(self, "warned_today_missing") or not self.warned_today_missing:
                    emit_log(f"[FILES] 📂 Today's folder not found: {smb_today}")
                    self.warned_today_missing = True
                return
            else:
                if getattr(self, "warned_today_missing", False):
                    emit_log(f"[FILES] 🗂️ Found today's folder: {smb_today}")
                self.warned_today_missing = False

            for f in smbclient.listdir(smb_today):
                if f.lower().endswith(".avi") and f not in FILE_STATUS:
                    full_path = os.path.join(smb_today, f)
                    self.process_file(full_path, f)

        except Exception as e:
            emit_log(f"[FILES] ⚠️ SMB access error: {e}")

    @staticmethod
    def get_file_list():
        file_data = []
        for folder in os.listdir(FILE_DEST_DIR):
            folder_path = os.path.join(FILE_DEST_DIR, folder)
            if os.path.isdir(folder_path):
                for f in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, f)
                    if os.path.isfile(file_path):
                        stats = os.stat(file_path)
                        file_data.append({
                            "name": f,
                            "size": f"{stats.st_size // 1024} KB",
                            "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "status": FILE_STATUS.get(f, "Copied")
                        })
        return file_data

def start_file_monitoring(interval=5, max_retries=5):
    handler = FileHandler()
    retries = 0

    def monitor_loop():
        nonlocal retries
        while True:
            try:
                handler.check_directory()
                retries = 0
            except Exception as e:
                emit_log(f"[FileHandler] Error during monitoring: {e}")
                retries += 1
                if retries >= max_retries:
                    emit_log("[FileHandler] Max retries reached. Stopping file monitor.")
                    break
            time.sleep(interval)

    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()

def get_file_list():
    return FileHandler.get_file_list()

def main():
    start_file_monitoring()
    try:
        while True:
            time.sleep(3)
    except KeyboardInterrupt:
        emit_log("[FileHandler] Stopped.")

if __name__ == "__main__":
    main()