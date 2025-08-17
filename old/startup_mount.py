# Startup script to initialize the mount with location and home coordinates.

import subprocess
import time as pytime  # Renamed to avoid conflict with astropy's Time class
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, ICRS, get_sun
from astropy.time import Time
import astropy.units as u

class MountControl:
    def __init__(self, output_callback):
        """Mount & location settings."""
        self.mount_device = 'Mount PMC Eight'
        self.latitude = 35.913200  # N - INDIGO format
        self.longitude = 280.944153  # E - INDIGO format
        self.altitude = 80  # meters - INDIGO format
        self.location = EarthLocation(lat=35.9132 * u.deg, lon=-79.0558 * u.deg, height=80 * u.m) # Chapel Hill, NC coordinates
        self.output_callback = output_callback  # Assign the external output callback

    def log(self, message):
        """Log output through the callback to app.py."""
        self.output_callback(f"{message}")

    def run_command(self, command):
        """Execute a shell command and return the output."""
        try:
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return result.stdout.decode('utf-8')
        except subprocess.CalledProcessError as e:
            self.log(f"Error executing command: {e.stderr.decode('utf-8')}")
            return None

    def get_home_coordinates(self):
        """Calculate home equatorial coordinates."""
        # Current UTC time
        now = Time.now()
        # Define the AltAz frame for the given time and location
        altaz_frame = AltAz(obstime=now, location=self.location)
        # Mount home position: Due west, horizon altitude
        # Due west azimuth is 270 degrees, and horizon altitude is 0 degrees
        az = 270 * u.deg
        alt = 0 * u.deg
        # Create a SkyCoord object for the given alt/az
        horizontal_coord = SkyCoord(alt=alt, az=az, frame=altaz_frame)
        # Convert horizontal coordinates to equatorial coordinates (ICRS frame)
        equatorial_coord = horizontal_coord.transform_to(ICRS)
        home_ra = equatorial_coord.ra.deg
        home_dec = equatorial_coord.dec.deg
        return home_ra, home_dec
    
    def horizon_check(self):
        """Check if the Sun is below the horizon."""
        # Current UTC time
        now = Time.now()
        # Define the AltAz frame for the given time and location
        altaz_frame = AltAz(obstime=now, location=self.location)
        # Get the Sun's position in the AltAz frame
        sun_altaz = get_sun(now).transform_to(altaz_frame)
        # Check if the Sun's altitude is below the horizon
        if sun_altaz.alt.deg < 0 :
            self.log(f"The Sun is below the horizon at altitude {sun_altaz.alt:.2f}. Cannot initialize the mount.")
            return True
        return False


    def initialize_mount(self):
        """Initalize mount."""

        # Connect the mount
        self.log("Connecting to the mount...")
        self.run_command(f"indigo_prop_tool set \"{self.mount_device}.CONNECTION.CONNECTED=ON\"")

        # Initialize the mount with geographic coordinates
        self.log("Setting the location...")
        self.run_command(f"indigo_prop_tool set \"{self.mount_device}.GEOGRAPHIC_COORDINATES.LATITUDE={self.latitude};LONGITUDE={self.longitude};ELEVATION={self.altitude}\"")

        # On coordinate set sync
        self.log("Setting on coordinate set sync...")
        self.run_command(f"indigo_prop_tool set \"{self.mount_device}.MOUNT_ON_COORDINATES_SET.SYNC=ON\"")

        # Set tracking to solar rate
        self.log("Setting tracking to solar rate...")
        self.run_command(f"indigo_prop_tool set \"{self.mount_device}.MOUNT_TRACK_RATE.SOLAR=ON\"")

        # Turning tracking on
        self.log("Turning tracking on...")
        self.run_command(f"indigo_prop_tool set \"{self.mount_device}.MOUNT_TRACKING.ON=ON\"")
        self.run_command(f'indigo_prop_tool set "{self.mount_device}.MOUNT_TRACKING.OFF=OFF\"')

        # Calculate home coordinates
        home_ra, home_dec = self.get_home_coordinates()
        self.log(f"Home coordinates at RA: {home_ra}, DEC: {home_dec}")

        # Sync the telescope with home equatorial coordinates
        self.log("Syncing the telescope with home coordinates...")
        self.run_command(f"indigo_prop_tool set \"{self.mount_device}.MOUNT_EQUATORIAL_COORDINATES.RA={home_ra};DEC={home_dec}\"")

        self.log("Mount initialization complete.")

def main(output_callback):
    mount_control = MountControl(output_callback)
    
    if mount_control.horizon_check():
        mount_control.log("The Sun is below the horizon. Cannot initialize the mount.")
    else:
        mount_control.initialize_mount()

# Run the script independently with a basic output callback
if __name__ == "__main__":
    main(output_callback=print)  # Use print for standalone testing