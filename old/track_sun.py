# Tracking script for mount control based on Sun position.

import time as pytime  # Renamed to avoid conflict with astropy's Time class
import subprocess
from astropy.coordinates import get_sun, EarthLocation, AltAz, SkyCoord, ICRS
from astropy.time import Time
import astropy.units as u

class MountControl:
    def __init__(self):
        """Initialize Mount & Location."""
        #self.indigo_server = 'localhost'
        self.mount_device = 'Mount PMC Eight'
        self.location = EarthLocation(lat=35.9132*u.deg, lon=-79.0558*u.deg, height=80*u.m)  # Chapel Hill, NC coordinates

    def run_command(self, command):
        """Execute a shell command and return the output."""
        try:
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return result.stdout.decode('utf-8')
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e.stderr.decode('utf-8')}")
            return None

    def get_sun_coordinates(self):
        """Fetch the current equatorial coordinates of the Sun."""
        
        now = Time.now()  # Current UTC time
        print("Current time:", now)
        sun_gcrs = get_sun(now)
        altaz_frame = AltAz(obstime=now, location=self.location)
        sun_altaz = sun_gcrs.transform_to(altaz_frame)

        # Convert horizontal coordinates to equatorial coordinates (ICRS frame)
        equatorial_coord = sun_altaz.transform_to(ICRS) 
        sun_ra = equatorial_coord.ra.deg
        sun_dec = equatorial_coord.dec.deg

        """
        # Convert RA Format to hours:minutes:seconds
        ra_convert = home_ra/15.0
        ra_hours = int(ra_convert) // 1 
        ra_minutes = (ra_convert - ra_hours) * 60
        ra_seconds = (ra_minutes - int(ra_minutes)) * 60
        ra_format = f"{ra_hours}h {int(ra_minutes)}m {int(ra_seconds)}s"
        """
        return sun_ra, sun_dec

    def initial_slew(self):
        """Initial slew to the Sun's position."""
        # Retrieve the current RA and DEC from the mount
        current_ra = self.run_command(f"indigo_prop_tool get \"{self.mount_device}.MOUNT_EQUATORIAL_COORDINATES.RA\"")
        current_dec = self.run_command(f"indigo_prop_tool get \"{self.mount_device}.MOUNT_EQUATORIAL_COORDINATES.DEC\"")

        # Log the raw values for debugging
        self.log(f"Raw values from mount - RA: {current_ra}, DEC: {current_dec}")

        # Convert the retrieved RA and DEC values to float if they are not None
        try:
            current_ra = float(current_ra) if current_ra else 0.0
            current_dec = float(current_dec) if current_dec else 0.0
        except ValueError:
            self.log(f"Error converting RA/DEC values to float: RA={current_ra}, DEC={current_dec}")
            return

        # Calculate the Sun's position
        solar_ra, solar_dec = self.get_sun_coordinates()
        self.log(f"Sun coordinates at RA: {solar_ra}, DEC: {solar_dec}")

        # Check if the mount is already pointing at the Sun
        if abs(current_ra - solar_ra) < 10.0 and abs(current_dec - solar_dec) < 10.0:
            self.log("Mount is already pointing at the Sun.")
            return

        # If not, proceed with slewing
        self.log("Slewing to the Sun...")
        self.run_command(f"indigo_prop_tool set \"{self.mount_device}.MOUNT_EQUATORIAL_COORDINATES.RA={solar_ra};DEC={solar_dec}\"")


    def update_sun(self):
        """Track the Sun by updating mount coordinates periodically."""

        # Update the Solar coordinates
        solar_ra, solar_dec = self.get_sun_coordinates()
        print(f"Updating target coordinates to RA: {solar_ra}, Dec: {solar_dec}")

        # Slew to the updated coordinates
        self.run_command(f"indigo_prop_tool set \"{self.mount_device}.MOUNT_EQUATORIAL_COORDINATES.RA={solar_ra};DEC={solar_dec}\"")

        # Get the current azimuth and altitude
        current_ra = self.run_command(f"indigo_prop_tool get \"{self.mount_device}.MOUNT_EQUATORIAL_COORDINATES.RA\"")
        current_dec = self.run_command(f"indigo_prop_tool get \"{self.mount_device}.MOUNT_EQUATORIAL_COORDINATES.DEC\"")

        # Assuming a small tolerance, check if the mount is on target
        if abs(current_ra - solar_ra) < 0.5 and abs(current_ra - solar_dec) < 0.5:
            print("Mount is on target.")
        else:
            print(f"Current RA: {current_ra}, Current Dec: {current_dec}. Waiting for mount to finish slewing...")
            print("Mount is not on target. Waiting for mount to finish slewing...")
            pytime.sleep(1)  # Wait for 1 seconds before checking again

        print("Mount position updated. Waiting for next update...")

def main():
    mount_control = MountControl()

    # Run initial_slew once to position the telescope towards the Sun initially
    mount_control.initial_slew()

    # After initial positioning, continuously update the Sun's position
    while True:
        mount_control.update_sun()
        pytime.sleep(5)  # Update every 5 seconds

if __name__ == "__main__":
    main()
