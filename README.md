# Automated Solar Telescope Control (ASTControl) II

Automated Solar Telescope Control is a modular, browser-based control system for managing an automated solar telescope. It centralizes mount control, weather and solar tracking, dome and etalon servo management, file transfer automation, and real-time status monitoring into one web interface.

Originally developed for solar instrumentation at UNC-Chapel Hill, ASTControl now supports remote hardware coordination across multiple devices including INDIGO-compliant mounts, Arduino peripherals, and FireCapture imaging systems.

---

## Features

- Web-based control panel using Flask and Socket.IO
- Mount slewing, parking, and solar tracking via INDIGO JSON-over-TCP
- Solar position updates and altitude/azimuth calculation
- Weather monitoring with auto-shutdown triggers
- Real-time RA/DEC feedback and device state display
- Arduino-based servo control for dome and etalon positioning
- File handler for auto-transferring `.avi` videos from Raspberry Pi to PC
- Optional FireCapture preview integration and script support

---

## Architecture

**Backend (PC):**
- `app.py`: Flask server with WebSocket events
- `mount_module.py`, `solar_module.py`, `nstep_module.py`, etc.
- File handler monitors incoming files and organizes them
- Commands Raspberry Pi and Arduino via SSH and serial

**Frontend:**
- HTML + Tailwind CSS
- JavaScript + Socket.IO for event-based updates

**Remote Devices:**
- Raspberry Pi runs the INDIGO server and serial handler for Arduino
- Arduino controls servo logic for dome and etalon
- FireCapture runs on the Pi or a connected Windows box for imaging

---

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/nkahassai-unc/ASTControl.git
   cd ASTControl

2. Install required Python packages:
   ```bash
   pip install -r requirements.txt

3. Update configuration:

- Edit IPs, SSH credentials, and serial paths in config.py

- Flash the Arduino with appropriate dome/etalon firmware

- Ensure the Raspberry Pi is network-accessible and the INDIGO server can be launched remotely

4. Launch the server:
   ```bash
   python app.py

5. Open your browser at:
   ```bash
   http://localhost:5001

---
## Usage

The control panel provides:

- Live mount position and solar data

- Weather readout and forecast

- Slew, park, and sun-tracking buttons

- Dome open/close and etalon position control

- nSTEP focuser control

- File status and incoming AVI transfer tracker

All functionality is exposed through the main web interface. Optional features like FireCapture preview or scripting hooks can be added modularly.

## Notes
This system assumes a stable Ethernet or LAN connection between the PC and Raspberry Pi.

All device communication is event-driven for responsiveness.

Future updates intended to include automation routines and persistent data logging.

