# Checks the NYC morning (7-9am) rain forecast and emails an umbrella alert. Weekdays only

import os
import sys
import time
import logging
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

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5  # doubles each retry: 5s, 10s, 20s


class NYFormatter(logging.Formatter):
    """Formats log timestamps in America/New_York time, regardless of the runner's local tz."""
    def converter(self, timestamp):
        return datetime.fromtimestamp(timestamp, TZ).timetuple()


handler = logging.StreamHandler()
handler.setFormatter(NYFormatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S %Z",
))

logger = logging.getLogger("nyc-rain-alert")
logger.setLevel(logging.INFO)
logger.addHandler(handler)


def get_forecast():
    """Fetch precipitation forecast, retrying on transient network/API errors."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&hourly=precipitation_probability,precipitation"
        "&timezone=America%2FNew_York"
        "&forecast_days=1"
    )

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Fetching forecast (attempt {attempt}/{MAX_RETRIES})...")
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()

            morning = [
                (p, a)
                for t, p, a in zip(
                    data["hourly"]["time"],
                    data["hourly"]["precipitation_probability"],
                    data["hourly"]["precipitation"],
                )
                if 7 <= int(t[11:13]) < 9
            ]

            result = max(morning, default=(0, 0))
            logger.info(f"Forecast fetched successfully: {result}")
            return result

        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"Forecast fetch failed on attempt {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

    # All retries exhausted
    raise RuntimeError(f"Forecast API failed after {MAX_RETRIES} attempts: {last_error}")


def send_email(subject, body):
    try:
        msg = MIMEText(body)
        msg["Subject"], msg["From"], msg["To"] = subject, EMAIL, RECIPIENT

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL, PASSWORD)
            smtp.sendmail(EMAIL, RECIPIENT, msg.as_string())

        logger.info("Email sent successfully.")
    except smtplib.SMTPException as e:
        logger.error(f"Failed to send email: {e}")
        raise  # email failures should still surface as a real failure


def main():
    now = datetime.now(TZ)
    logger.info(f"Run started at {now.isoformat()}")

    if now.weekday() > 4:
        logger.info("Weekend. Skipping.")
        return

    try:
        prob, amount = get_forecast()
    except RuntimeError as e:
        # Forecast couldn't be fetched after retries -- log it, but don't fail the run.
        logger.error(f"Could not get forecast, skipping this run: {e}")
        return

    logger.info(f"Forecast: {prob}% chance, {amount} mm/hr")

    if prob >= 60 or amount >= 2.5:
        size = "LARGE "
    elif prob >= 30:
        size = ""
    else:
        logger.info("No umbrella needed.")
        return

    logger.info(f"Sending {size.lower() or 'regular '}umbrella email.")

    send_email(
        f"☔{'☔' if size else ''} Bring a {size}umbrella today",
        f"Rain expected in NYC this morning ({prob}% chance, {amount} mm/hr).",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Unexpected error, run failing: {e}", exc_info=True)
        sys.exit(1)