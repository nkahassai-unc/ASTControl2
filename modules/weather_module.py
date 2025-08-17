# Weather Module
# Weather forecast module using Open Meteo API
# Set for latitude and longitude of Chapel Hill, NC

import requests
import time
from datetime import datetime

class WeatherForecast:
    def __init__(self, latitude=35.9132, longitude=-79.0558):
        self.latitude = latitude
        self.longitude = longitude
        self.api_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={self.latitude}&longitude={self.longitude}"
            f"&current_weather=true"
            f"&hourly=precipitation_probability"
            f"&forecast_days=1"
            f"&timezone=America/New_York"
        )
        self.weather_data = {
            'temperature': "--",
            'wind_speed': "--",
            'sky_conditions': "unknown",
            'precip_chance': "--",
            'last_checked': "--"
        }

    def check_weather(self):
        try:
            res = requests.get(self.api_url, timeout=5)
            res.raise_for_status()
            body = res.json()

            current = body.get("current_weather", {})
            hourly = body.get("hourly", {})
            precip_list = hourly.get("precipitation_probability", [])
            precip_chance = precip_list[0] if precip_list else "--"

            self.weather_data = {
                'temperature': round(current.get('temperature', 0), 2),
                'wind_speed': current.get('windspeed', "--"),
                'sky_conditions': "CLEAR" if current.get('weathercode', 0) in [0, 1] else "CLOUDY",
                'precip_chance': round(precip_chance) if isinstance(precip_chance, (int, float)) else "--",
                'last_checked': datetime.now().strftime('%m-%d %H:%M:%S')
            }

        except Exception as e:
            print(f"[Weatherman] Error fetching weather: {e}")

    def get_data(self):
        return self.weather_data

    def start_monitor(self, socketio, interval=600):
        def loop():
            self.check_weather()
            socketio.emit("update_weather", self.weather_data)
            while True:
                time.sleep(interval)
                self.check_weather()
                socketio.emit("update_weather", self.weather_data)

        socketio.start_background_task(loop)