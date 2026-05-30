import os
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

SENDER = "matthewli2000@gmail.com"
RECIPIENTS = [
    "matthewli2000@gmail.com",
    "blu5959@gmail.com",
    "alexkberger@gmail.com",
    "oronorocks@gmail.com",
]

# Rotation order, switching one step each week.
NAMES = ["Li", "Ben", "Baran", "Berger"]

# Known anchor: the week of Mon 04/20/2026 is Ben (index 1 in NAMES).
# Every other week's person is derived by counting weeks from here.
ANCHOR_MONDAY = date(2026, 4, 20)
ANCHOR_INDEX = 1


def rotation_for(this_monday):
    """Return (this_name, last_name, next_name) for the given Monday."""
    weeks = (this_monday - ANCHOR_MONDAY).days // 7
    idx = (ANCHOR_INDEX + weeks) % len(NAMES)
    this_name = NAMES[idx]
    last_name = NAMES[(idx - 1) % len(NAMES)]
    next_name = NAMES[(idx + 1) % len(NAMES)]
    return this_name, last_name, next_name


def build_body(this_monday):
    this_name, last_name, next_name = rotation_for(this_monday)
    start = this_monday.strftime("%m/%d/%Y")
    end = (this_monday + timedelta(days=7)).strftime("%m/%d/%Y")
    return (
        f"This weeks trashman from {start} to {end} will be {this_name}. "
        f"Last week was {last_name} and next week will be {next_name}."
    )


def current_monday():
    # GitHub cron fires in UTC; anchor the rotation to the ET calendar week
    # so the "current week" matches your local Monday.
    today = datetime.now(ZoneInfo("America/New_York")).date()
    return today - timedelta(days=today.weekday())  # Monday == weekday 0


def send_email(body):
    msg = EmailMessage()
    msg["Subject"] = "Trashman of the week"
    msg["From"] = SENDER
    msg["To"] = ", ".join(RECIPIENTS)
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(SENDER, os.environ["GMAIL_APP_PASSWORD"])
        s.send_message(msg)


if __name__ == "__main__":
    send_email(build_body(current_monday()))
