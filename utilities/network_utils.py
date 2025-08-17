# Network Utilities
# Suite of network utilities for remote SSH control and port checking

import paramiko
import socket
import time
from utilities.config import RASPBERRY_PI_IP, SSH_USERNAME, SSH_PASSWORD

def get_ssh_client(ip, username, password, retries=2):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for attempt in range(retries):
        try:
            client.connect(ip, username=username, password=password, timeout=5)
            return client
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(1)

def run_ssh_command(client, command):
    stdin, stdout, stderr = client.exec_command(command)
    return {
        "stdout": stdout.read().decode().strip(),
        "stderr": stderr.read().decode().strip(),
        "returncode": stdout.channel.recv_exit_status()
    }

def stream_ssh_output(client, command, callback):
    """Stream stdout/stderr lines via callback from a long-running command."""
    channel = client.get_transport().open_session()
    channel.exec_command(command)

    while True:
        if channel.recv_ready():
            for line in channel.recv(1024).decode().splitlines():
                callback(line.strip())
        if channel.recv_stderr_ready():
            for line in channel.recv_stderr(1024).decode().splitlines():
                callback(f"ERR: {line.strip()}")
        if channel.exit_status_ready():
            break

def check_remote_port(ip, port, timeout=2):
    """Check if a remote port is open (e.g., INDIGO on 7624)."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except:
        return False
    
def run_ssh_command_with_log(client, command, log_callback):
    stdin, stdout, stderr = client.exec_command(command)

    seen = set()
    for line in stdout:
        line = line.strip()
        if line and line not in seen:
            log_callback(f"[SSH] {line}")
            seen.add(line)

    for line in stderr:
        log_callback(f"[SSH:ERR] {line.strip()}")

    return stdout.channel.recv_exit_status()

def run_pi_ssh_command(command):
    """Run a one-off SSH command on the Pi using stored config credentials."""
    client = get_ssh_client(RASPBERRY_PI_IP, SSH_USERNAME, SSH_PASSWORD)
    result = run_ssh_command(client, command)
    client.close()
    return result