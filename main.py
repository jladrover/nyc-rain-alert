# Checks the NYC morning (7-9am) rain forecast and emails an umbrella alert. Weekdays only

import os
from datetime import datetime
from zoneinfo import ZoneInfo
import smtplib
from email.mime.text import MIMEText
import requests

LAT, LON = 40.7128, -74.0060
TZ = ZoneInfo("America/New_York")

EMAIL = os.environ["EMAIL_ADDRESS"]
PASSWORD = os.environ["EMAIL_PASSWORD"]
RECIPIENT = os.environ["RECIPIENT_EMAIL"]


def get_forecast():
    data = requests.get(
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&hourly=precipitation_probability,precipitation"
        "&timezone=America%2FNew_York"
        "&forecast_days=1",
        timeout=15,
    ).json()

    morning = [
        (p, a)
        for t, p, a in zip(
            data["hourly"]["time"],
            data["hourly"]["precipitation_probability"],
            data["hourly"]["precipitation"],
        )
        if 7 <= int(t[11:13]) < 9
    ]

    return max(morning, default=(0, 0))


def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"], msg["From"], msg["To"] = subject, EMAIL, RECIPIENT

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL, PASSWORD)
        smtp.sendmail(EMAIL, RECIPIENT, msg.as_string())


def main():
    if datetime.now(TZ).weekday() > 4:
        return

    prob, amount = get_forecast()

    if prob >= 60 or amount >= 2.5:
        size = "LARGE "
    elif prob >= 30:
        size = ""
    else:
        return

    send_email(
        f"☔{'☔' if size else ''} Bring a {size}umbrella today",
        f"Rain expected in NYC this morning ({prob}% chance, {amount} mm/hr).",
    )


if __name__ == "__main__":
    main()