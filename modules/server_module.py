# Server Module
# Remote INDIGO server controller for Flask GUI or CLI

import threading
import time
from utilities.config import RASPBERRY_PI_IP
from utilities.indigo_json_client import IndigoJSONClient
from utilities.network_utils import (
    get_ssh_client,
    stream_ssh_output,
    run_ssh_command,
    check_remote_port
)

indigo_client = IndigoJSONClient(RASPBERRY_PI_IP)

def start_indigo_client():
    import threading
    threading.Thread(target=indigo_client.connect, daemon=True).start()

class IndigoRemoteServer:
    def __init__(self, server_ip, username, password, port=7624):
        self.ip = server_ip
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.running = False
        self.thread = None

    def connect(self):
        if not self.client:
            self.client = get_ssh_client(self.ip, self.username, self.password)

    def start(self, callback):
        """Start INDIGO server remotely and stream output via callback."""
        self.connect()
        self.running = True

        def runner():
            try:
                # Kill existing INDIGO instances
                run_ssh_command(self.client, "pkill -f indigo_server")

                # Start server in background
                stream_ssh_output(self.client, "indigo_server", callback)

            except Exception as e:
                callback(f"[ERROR] INDIGO server stream failed: {e}")
                self.running = False
                return

            # Wait for port to be available (max 10s)
            for i in range(20):  # Try every 0.5s for 10 seconds
                if check_remote_port(self.ip, self.port):
                    callback(f"[INDIGO] Server online at {self.ip}:{self.port}")
                    start_indigo_client()
                    break
                else:
                    callback(f"[INDIGO] Waiting for server port {self.port}... ({i+1}/20)")
                    time.sleep(0.5)
            else:
                callback(f"[INDIGO] Failed to detect server after 10s.")

            self.running = False

        self.thread = threading.Thread(target=runner, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop INDIGO server process remotely."""
        self.connect()
        self.running = False
        return run_ssh_command(self.client, "pkill -f indigo_server")

    def check_status(self):
        """Check if INDIGO server is active on port 7624."""
        return check_remote_port(self.ip, self.port)

    def get_status(self):
        """Return current status as a simple dict."""
        return {
            "running": self.check_status()
        }
    
