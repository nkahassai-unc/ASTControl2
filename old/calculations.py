# Cross reference calculations for telescope coordinates

from astropy.time import Time
from astropy.coordinates import EarthLocation, AltAz, ICRS, SkyCoord, get_sun
import astropy.units as u

# Observer's location (Chapel Hill, NC)
location = EarthLocation(lat=35.9132*u.deg, lon=-79.0558*u.deg, height=80*u.m)

# Current time
now = Time.now()

# Define the AltAz frame
altaz_frame = AltAz(obstime=now, location=location)

"""
# Polaris calculations
# RA and Dec of Polaris
ra = 1.554 * u.deg
dec = 90 * u.deg

# Create SkyCoord object for the given RA and Dec
icrs_coord = SkyCoord(ra=ra, dec=dec, frame='icrs')
# Convert to AltAz coordinates
altaz_coord = icrs_coord.transform_to(altaz_frame)

# Extract Altitude and Azimuth
altitude = altaz_coord.alt
azimuth = altaz_coord.az

print("Polaris Alt Az:")
print(f"Altitude: {altitude.deg} degrees, Azimuth: {azimuth.deg} degrees")
print("--------------------")
"""

# Testing home positions
"""Calculate home equatorial coordinates."""
# Due west azimuth is 270 degrees, and horizon altitude is 0 degrees
az = 270 * u.deg
alt = 0 * u.deg
# Create a SkyCoord object for the given alt/az
horizontal_coord = SkyCoord(alt=alt, az=az, frame=altaz_frame)

# Convert horizontal coordinates to equatorial coordinates (ICRS frame)
# 0 - 360 Degrees Format
equatorial_coord = horizontal_coord.transform_to(ICRS) 
home_ra = equatorial_coord.ra.deg
home_dec = equatorial_coord.dec.deg
print("-*-*-*-*-*-*-*-*-*-*")
print(f"New Calculations @ {now}")
print("--------------------")
print("Home West Alt & Az (Degrees):")
print(f"Alt: {alt}, Az: {az}")
print("--------------------")
print("Home West RA & Dec (Degrees):")
print(f"RA: {home_ra} degrees, Dec: {home_dec} degrees")
print("--------------------")

# Convert RA and Dec
dec = home_dec * u.deg

# Convert RA Format to hours:minutes:seconds
ra_convert = home_ra/15.0
ra_hours = int(ra_convert) // 1 
ra_minutes = (ra_convert - ra_hours) * 60
ra_seconds = (ra_minutes - int(ra_minutes)) * 60
ra_format = f"{ra_hours}h {int(ra_minutes)}m {int(ra_seconds)}s"


# Calculate local sidereal time & format
lst = now.sidereal_time('apparent', longitude = location.lon)
lst_convert = lst.hourangle
lst_hours = int(lst.hourangle) // 1
lst_minutes = (lst_convert - lst_hours) * 60
lst_seconds = (lst_minutes - int(lst_minutes)) * 60
lst_format = f"{lst_hours}h {int(lst_minutes)}m {int(lst_seconds)}s"
print(f"Local Sidereal Time: {lst}, or {lst_format}")
print("--------------------")


#Calculate hour angle & format
ha = int(lst.hourangle) - ra_convert
print("Home West (Hour Angle)")
ha_hours = int(ha) // 1
ha_minutes = (ha - ha_hours) * 60
ha_seconds = (ha_minutes - int(ha_minutes)) * 60
ha_format = f"{ha_hours}h {int(ha_minutes)}m {int(ha_seconds)}s"
print(f"HA: {ha}, Dec: {dec}, or {ha_format}")
print("--------------------")


# Calculate RA to hours:minutes:seconds format
print("Home West (RA Format conversion)")
print(f"RA: {ra_format} , Dec: {dec}")
print("-*-*-*-*-*-*-*-*-*-*")

# Solar Position Calculation
sun_gcrs = get_sun(now)
sun_altaz = sun_gcrs.transform_to(altaz_frame)
# Convert horizontal coordinates to equatorial coordinates (ICRS frame)
equatorial_coord = sun_altaz.transform_to(ICRS) 
sun_ra = equatorial_coord.ra.deg
sun_dec = equatorial_coord.dec.deg
print("Sun Position")
print(f"RA: {sun_ra} degrees, Dec: {sun_dec} degrees")
print("--------------------")
print(sun_altaz.alt.deg, sun_altaz.az.deg)