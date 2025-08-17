# Solar Module
# Solar position module using PyEphem 
# Set for latitude and longitude of Chapel Hill, NC

from arrow import now
import ephem
from datetime import datetime, timezone, timedelta
from utilities.config import GEO_LAT, GEO_LON, GEO_ELEV, solar_cache
from utilities.logger import emit_log

_socketio = None

def set_socketio(sio):
    global _socketio
    _socketio = sio

class SolarPosition:
    def __init__(self, latitude=GEO_LAT, longitude=GEO_LON):
        self.latitude = str(latitude)
        self.longitude = str(longitude)
        self.observer = ephem.Observer()
        self.observer.lat = self.latitude
        self.observer.lon = self.longitude
        self.observer.elev = GEO_ELEV
        self.local_tz = timezone(timedelta(hours=-5))  # Adjust for your time zone

        self.last_sun_time = "--"


        self.sun_times = {
            "sunrise": "--",
            "sunset": "--",
            "solar_noon": "--"
        }

        self.solar_position = {
            "solar_alt": "--",
            "solar_az": "--",
            "sun_time": "--"
        }

        self.update_sun_times()

    def update_sun_times(self):
        try:
            self.observer.date = datetime.utcnow()
            sunrise = ephem.localtime(self.observer.next_rising(ephem.Sun()))
            sunset = ephem.localtime(self.observer.next_setting(ephem.Sun()))
            transit = ephem.localtime(self.observer.next_transit(ephem.Sun()))

            self.sun_times.update({
                "sunrise": sunrise.strftime("%H:%M"),
                "sunset": sunset.strftime("%H:%M"),
                "solar_noon": transit.strftime("%H:%M")
            })
        except Exception as e:
            emit_log(f"[Solar] Error fetching sun times: {e}")

    def update_solar_position(self):
        try:
            self.observer.date = datetime.utcnow()
            sun = ephem.Sun(self.observer)
            alt = float(sun.alt) * 180.0 / ephem.pi
            az = float(sun.az) * 180.0 / ephem.pi

            last_time = self.solar_position.get("sun_time", "--")
            now_str  = datetime.now().strftime("%H:%M:%S")

            self.solar_position.update({
                "solar_alt": round(alt, 2) if alt > 0 else "Below Horizon",
                "solar_az": round(az, 2) if alt > 0 else "Below Horizon",
                "sun_time": now_str,
                "last_sun_time": last_time,
            })

        except Exception as e:
            emit_log(f"[Solar] Error calculating solar position: {e}")

    def get_solar_equatorial(self):
        try:
            self.observer.date = datetime.utcnow()
            sun = ephem.Sun(self.observer)
            ra = sun.ra  # in radians internally, but str is formatted
            dec = sun.dec
            return {
                "ra_solar": str(ra),   # HH:MM:SS
                "dec_solar": str(dec)  # ±DD:MM:SS
            }
        except Exception as e:
            emit_log(f"[Solar] Error getting RA/DEC: {e}")
            return {
                "ra_solar": "--:--:--",
                "dec_solar": "--:--:--"
            }
        
    def get_data(self):
        return {**self.sun_times, **self.solar_position}
    
    def get_full_day_path(self, interval_minutes=5):
        try:
            now = datetime.now()
            today = now.date()
            cached_date = solar_cache.get("date")

            if cached_date == today and solar_cache.get("path"):
                return solar_cache["path"]

            # Compute new path
            self.observer.date = now
            sun = ephem.Sun()
            sunrise_utc = self.observer.previous_rising(sun) if now < ephem.localtime(self.observer.next_rising(sun)) else self.observer.next_rising(sun)
            sunset_utc = self.observer.next_setting(sun)

            times = []
            t = sunrise_utc
            while t < sunset_utc:
                times.append(t)
                t = ephem.Date(t + interval_minutes / (24 * 60))

            path = []
            for t in times:
                self.observer.date = t
                sun = ephem.Sun(self.observer)
                alt = float(sun.alt) * 180.0 / ephem.pi
                az = float(sun.az) * 180.0 / ephem.pi
                alt = max(0, min(alt, 90))
                az = az % 360
                timestamp = ephem.localtime(t).strftime("%H:%M")
                path.append({"az": round(az, 2), "alt": round(alt, 2), "time": timestamp})

            # Cache it
            solar_cache["date"] = now.date()
            solar_cache["path"] = path

            emit_log(f"[SOLAR] ☀️ Generated {len(path)} points from {ephem.localtime(sunrise_utc)} to {ephem.localtime(sunset_utc)}")
            return path

        except Exception as e:
            emit_log(f"[SOLAR] Error generating sun path: {e}")
            return []

    def start_monitor(self, socketio, interval=20):
        def loop():
            emit_log("[SOLAR] Monitor loop running")

            self.update_sun_times()
            self.update_solar_position()
            socketio.emit("solar_update", self.get_data())

            count = 0
            while True:
                socketio.sleep(interval)
                self.update_solar_position()

                if count % (6 * 60 * 60 // interval) == 0:
                    self.update_sun_times()

                socketio.emit("solar_update", self.get_data())
                count += 1

        socketio.start_background_task(loop)