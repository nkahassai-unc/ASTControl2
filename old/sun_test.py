from pysolar.solar import get_altitude, get_azimuth
from datetime import datetime, timezone

lat, lon = 35.9132, -79.0558
now = datetime.now(timezone.utc)
alt = get_altitude(lat, lon, now)
az = get_azimuth(lat, lon, now)

print(f"Altitude: {alt}, Azimuth: {az}")
