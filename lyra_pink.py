from datetime import datetime
from pathlib import Path
import os
import sys

from flask import Flask, render_template
from flask_apscheduler import APScheduler
import requests

app = Flask(__name__)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Store data from the APIs with defaults in case nothing is returned.
class ApiData:
    # Moonrise, etc. will be None if the moon does not rise during that
    # 24-hour period (theoretically the same for sunrise).
    # Extra space is added for alignment.
    sunrise: str = " None"
    sunset: str = " None"
    moonrise: str = " None"
    moonset: str = " None"
    phase: str = "Unknown"
    fracillum: str = "??%"
    apod_title: str = "Untitled"
    apod_image: str = 'No image supplied (check the <a href="https://apod.nasa.gov/">APOD website</a>)'
    apod_copyright: str = "Unknown"
    apod_explanation: str = "No explanation provided"
    apod_date: str = "????-??-??"

def get_api_data() -> ApiData:
    data = ApiData()

    # Make request to USNO
    today = datetime.today().strftime("%Y-%m-%d")
    usno_payload = {
        "date": today,
        "coords": "39.90,-75.35", # Coordinates of Swarthmore
        "tz": "-4", # Eastern time (UTC-4:00)
        "id": os.environ.get("USNO_ID"),
    }

    try:
        usno = requests.get("https://aa.usno.navy.mil/api/rstt/oneday",
                            params=usno_payload,
                            timeout=10)
        usno_data = usno.json()["properties"]["data"]
        data.phase = usno_data.get("curphase")
        data.fracillum = usno_data.get("fracillum")
        for sundata in usno_data.get("sundata", []):
            if sundata.get("phen") == "Rise":
                data.sunrise = sundata.get("time")
            elif sundata.get("phen") == "Set":
                data.sunset = sundata.get("time")
        for moondata in usno_data.get("moondata"):
            if moondata.get("phen") == "Rise":
                data.moonrise = moondata.get("time")
            elif moondata.get("phen") == "Set":
                data.moonset = moondata.get("time")
    except requests.exceptions.ReadTimeout:
        app.logger.warning("Timed out accessing USNO API")
    except requests.exceptions.JSONDecodeError:
        app.logger.warning("Error decoding USNO JSON response")
    except KeyError:
        app.logger.warning("USNO JSON response missing data")

    # Make request to NASA
    try:
        apod = requests.get("https://api.nasa.gov/planetary/apod",
                            params={"api_key": os.environ.get("NASA_API_KEY")},
                            timeout=10)
        apod_data = apod.json()
        data.apod_title = apod_data.get("title")
        data.apod_copyright = apod_data.get("copyright")
        data.apod_explanation = apod_data.get("explanation")
        data.apod_date = apod_data.get("date")
        apod_url = apod_data.get("url")
        if apod_url:
            data.apod_image = f"<img src={apod_url}>"
    except requests.exceptions.ReadTimeout:
        app.logger.warning("Timed out accessing APOD API")
    except requests.exceptions.JSONDecodeError:
        app.logger.warning("Error deciding APOD JSON response")

    return data

# Store data from the APIs globally and periodically update it to avoid
# delays in loading the website.
data = get_api_data()

@scheduler.task("cron", id="update_api_data", day="*")
def update_api_data():
    data = get_api_data()

@app.route("/")
def index():
    return render_template("index.html", page="/", data=data)

@app.route("/photos")
def photos():
    shoots_dir = Path("static/photos")
    shoots = {}
    for s in shoots_dir.iterdir():
        thumbs = s / "thumbs"
        fullsize = s / "fullsize"
        if s.is_dir() and thumbs.is_dir() and fullsize.is_dir():
            shoots[s.name] = '<div class="photo-gallery">'
            for p in thumbs.iterdir():
                fspath = str(fullsize / p.name)
                tpath = str(p)
                shoots[s.name] += f'<a href="{fspath}"><img src="{tpath}"></a>'
            shoots[s.name] += '</div>'
            
    return render_template("photos.html", page="photos", shoots=shoots)

@app.route("/<page>")
def page(page=None):
    return render_template(f"{page}.html", page=page)
