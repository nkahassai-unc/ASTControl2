# Tracking Module
# Logic for relaying solar tracking coordinates to mount

import threading
import time

from modules.solar_module import SolarPosition
from modules.mount_module import MountControl
from utilities.config import GEO_LAT, GEO_LON, GEO_ELEV
from utilities.logger import emit_log
from utilities.logger import get_logger

logger = get_logger(__name__)


class SolarTracker:
    def __init__(self, mount: MountControl, interval_sec: int = 5):
        self.mount = mount
        self.interval = interval_sec
        self.active = False
        self.solar = SolarPosition()
        self.thread = None

    def start(self):
        if self.active:
            logger.warning("Tracking already active.")
            return

        self.active = True
        self._emit_status("✅ Solar tracking started.")
        logger.info("Started solar tracking thread.")

        def loop():
            while self.active:
                try:
                    self.solar.update_solar_position()
                    data = self.solar.get_data()
                    alt = data.get("solar_alt")
                    az = data.get("solar_az")

                    if alt == "Below":
                        self._emit_status("☁️ Sun is below the horizon.")
                    else:
                        ra, dec = self._altaz_to_equatorial(alt, az)
                        self.mount._slew_to_coords(ra, dec)
                        logger.debug(f"Slewed to RA={ra:.3f}, DEC={dec:.3f}")

                except Exception as e:
                    logger.error(f"Tracking error: {e}")

                time.sleep(self.interval)

            logger.info("Stopped solar tracking loop.")
            self._emit_status("🛑 Solar tracking stopped.")

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.active = False
        logger.info("Stopping solar tracking...")

    def _altaz_to_equatorial(self, alt, az):
        # TODO: Replace with true conversion later
        return float(az), float(alt)

    def _emit_status(self, msg):
        if hasattr(self.mount, "emit_status"):
            self.mount.emit_status(msg)