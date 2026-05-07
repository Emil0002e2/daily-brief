#!/usr/bin/env python3
"""
Daily Brief Updater
Holt Google Kalender + Gmail Daten und aktualisiert die index.html
"""

import os
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# --- Config ---
TIMEZONE = "Europe/Vienna"
BRIEFING_LOCALE = "de_AT"

WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
WEEKDAYS_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONTHS_DE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
             "Juli", "August", "September", "Oktober", "November", "Dezember"]

def get_greeting(hour):
    if hour < 12:
        return "Guten Morgen, Emil."
    elif hour < 18:
        return "Guten Tag, Emil."
    else:
        return "Guten Abend, Emil."

def format_date_de(dt):
    return f"{dt.day}. {MONTHS_DE[dt.month]} {dt.year}"

def get_weekday_de(dt):
    return WEEKDAYS_DE[dt.weekday()]

def get_credentials():
    """Load Google credentials from environment variables."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    token_json = os.environ.get("GOOGLE_TOKEN_JSON")

    if not token_json:
        raise ValueError("GOOGLE_TOKEN_JSON secret not set")

    token_data = json.loads(token_json)

    if creds_json:
        creds_data = json.loads(creds_json)
        client_id = creds_data.get("installed", creds_data.get("web", {})).get("client_id")
        client_secret = creds_data.get("installed", creds_data.get("web", {})).get("client_secret")
    else:
        client_id = token_data.get("client_id")
        client_secret = token_data.get("client_secret")

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/gmail.readonly"
        ]
    )
    return creds

def fetch_calendar_events(creds, days_ahead=7):
    """Fetch calendar events for the next N days."""
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now()
    time_min = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
    time_max = (now + timedelta(days=days_ahead)).replace(hour=23, minute=59, second=59).isoformat() + "Z"

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        timeZone=TIMEZONE
    ).execute()

    events = []
    for event in events_result.get("items", []):
        start = event["start"]
        if "dateTime" in start:
            dt = datetime.fromisoformat(start["dateTime"])
            time_str = dt.strftime("%H:%M")
            is_allday = False
        else:
            dt = datetime.fromisoformat(start["date"])
            time_str = "Ganztägig"
            is_allday = True

        events.append({
            "title": event.get("summary", "Ohne Titel"),
            "date": dt,
            "time": time_str,
            "location": event.get("location", ""),
            "is_allday": is_allday,
            "weekday": get_weekday_de(dt),
            "date_formatted": f"{get_weekday_de(dt)}, {dt.day}. {MONTHS_DE[dt.month]}"
        })

    return events

def fetch_emails(creds, max_results=5):
    """Fetch recent important emails."""
    service = build("gmail", "v1", credentials=creds)

    results = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        q="is:unread OR is:important newer_than:1d"
    ).execute()

    emails = []
    for msg_meta in results.get("messages", []):
        msg = service.users().messages().get(
            userId="me",
            id=msg_meta["id"],
            format="metadata",
            metadataHeaders=["From", "Subject"]
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        sender = headers.get("From", "Unbekannt")
        # Clean sender name
        if "<" in sender:
            sender = sender.split("<")[0].strip().strip('"')

        snippet = msg.get("snippet", "")
        labels = msg.get("labelIds", [])
        is_important = "IMPORTANT" in labels or "STARRED" in labels

        emails.append({
            "sender": sender,
            "subject": headers.get("Subject", "Kein Betreff"),
            "snippet": snippet[:120],
            "important": is_important
        })

    return emails

def generate_briefing(events, emails, today):
    """Generate a short briefing text."""
    today_events = [e for e in events if e["date"].date() == today.date()]
    upcoming = [e for e in events if e["date"].date() > today.date()]

    lines = []

    if today_events:
        event_names = [e["title"] for e in today_events]
        if len(event_names) == 1:
            lines.append(f"<strong>Heute steht {event_names[0]} an</strong>.")
        else:
            lines.append(f"<strong>Heute: {', '.join(event_names)}</strong>.")
    else:
        lines.append("<strong>Heute keine Termine</strong> — freier Tag.")

    if upcoming:
        next_days = {}
        for e in upcoming[:5]:
            day_key = e["date_formatted"]
            if day_key not in next_days:
                next_days[day_key] = []
            next_days[day_key].append(e["title"])

        preview_parts = []
        for day, titles in list(next_days.items())[:3]:
            preview_parts.append(f"<strong>{day}</strong>: {', '.join(titles)}")
        lines.append("Vorschau: " + " | ".join(preview_parts) + ".")

    important_emails = [e for e in emails if e["important"]]
    if important_emails:
        lines.append(f"Du hast <strong>{len(important_emails)} wichtige E-Mail{'s' if len(important_emails) > 1 else ''}</strong> im Posteingang.")

    return "<br><br>".join(lines)

def generate_today_events_html(events, today):
    """Generate HTML for today's events."""
    today_events = [e for e in events if e["date"].date() == today.date()]

    if not today_events:
        return '<div class="event-card"><div class="event-time">Heute</div><div class="event-title">Keine Termine</div></div>'

    html = ""
    for e in today_events:
        html += f"""    <div class="event-card">
      <div class="event-time">{e['time']}</div>
      <div class="event-title"><span class="event-dot"></span>{e['title']}</div>
      {'<div class="event-location">' + e['location'] + '</div>' if e['location'] else ''}
    </div>\n"""
    return html

def generate_upcoming_events_html(events, today):
    """Generate HTML for upcoming events."""
    upcoming = [e for e in events if e["date"].date() > today.date()]

    if not upcoming:
        return ""

    html = ""
    for e in upcoming:
        html += f"""    <div class="event-card">
      <div class="event-time">{e['date_formatted']}</div>
      <div class="event-title"><span class="event-dot"></span>{e['title']}</div>
      {'<div class="event-location">' + e['location'] + '</div>' if e['location'] else ''}
    </div>\n"""
    return html

def generate_mail_html(emails):
    """Generate HTML for email cards."""
    if not emails:
        return '<div class="empty-state">Keine neuen E-Mails</div>'

    html = ""
    for e in emails:
        badge = '<div class="mail-badge">Wichtig</div>\n      ' if e["important"] else ""
        html += f"""    <div class="mail-card">
      {badge}<div class="mail-sender">{e['sender']}</div>
      <div class="mail-subject">{e['subject']}</div>
      <div class="mail-snippet">{e['snippet']}</div>
    </div>\n"""
    return html

def generate_week_grid(today, events):
    """Generate the week grid HTML."""
    # Find Monday of current week
    monday = today - timedelta(days=today.weekday())

    html = '    <div class="week-grid">\n'
    for i in range(7):
        day = monday + timedelta(days=i)
        classes = ["week-day"]
        if day.date() == today.date():
            classes.append("today")
        day_events = [e for e in events if e["date"].date() == day.date()]
        if day_events:
            classes.append("has-event")

        html += f"""      <div class="{' '.join(classes)}">
        <div class="week-day-label">{WEEKDAYS_SHORT[i]}</div>
        <div class="week-day-num">{day.day}</div>
      </div>\n"""
    html += "    </div>"
    return html

def generate_week_events_html(events, today):
    """Generate week events grouped by day."""
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    week_events = [e for e in events if monday.date() <= e["date"].date() <= sunday.date()]

    if not week_events:
        return '<div class="empty-state">Keine Termine diese Woche</div>'

    # Group by day
    days = {}
    for e in week_events:
        key = e["date_formatted"]
        if key not in days:
            days[key] = []
        days[key].append(e)

    html = ""
    for day_label, day_events in days.items():
        html += f'\n    <div class="section-label">{day_label}</div>\n'
        for e in day_events:
            html += f"""    <div class="event-card">
      <div class="event-time">{e['time']}</div>
      <div class="event-title"><span class="event-dot"></span>{e['title']}</div>
      {'<div class="event-location">' + e['location'] + '</div>' if e['location'] else ''}
    </div>\n"""
        html += '    <div class="spacer-sm"></div>\n'

    return html

def build_html(template_path, today, events, emails):
    """Read the template and replace dynamic sections."""
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    weekday = get_weekday_de(today)
    date_str = format_date_de(today)
    greeting = get_greeting(8)  # Always morning greeting since it runs at 8am
    kw = today.isocalendar()[1]

    briefing = generate_briefing(events, emails, today)
    today_events_html = generate_today_events_html(events, today)
    upcoming_html = generate_upcoming_events_html(events, today)
    mail_html = generate_mail_html(emails)
    week_grid = generate_week_grid(today, events)
    week_events = generate_week_events_html(events, today)
    num_week_events = len([e for e in events if True])
    week_subtitle = f"{num_week_events} Termine diese Woche."

    # --- Replace TODAY page ---
    # Replace greeting (weekday)
    html = re.sub(
        r'(<div class="greeting animate-in">).*?(</div>)',
        rf'\g<1>{weekday}\2',
        html, count=1
    )
    # Replace date
    html = re.sub(
        r'(<div class="date-display animate-in delay-1">).*?(</div>)',
        rf'\g<1>{date_str}\2',
        html, count=1
    )
    # Replace greeting text
    html = re.sub(
        r'(<div class="subtitle animate-in delay-2">).*?(</div>)',
        rf'\g<1>{greeting}\2',
        html, count=1
    )

    # Replace briefing card
    html = re.sub(
        r'(<div class="briefing-card animate-in delay-4">\s*<div class="briefing-text">).*?(</div>\s*</div>)',
        rf'\g<1>\n        {briefing}\n      \2',
        html, count=1, flags=re.DOTALL
    )

    # Replace mail section
    mail_section_pattern = r'(<div class="section-label">Posteingang</div>\n).*?(<div class="section-divider"></div>\s*\n\s*<div class="section-label">Heute</div>)'
    html = re.sub(
        mail_section_pattern,
        rf'\g<1>{mail_html}\n\n    <div class="section-divider"></div>\n\n    <div class="section-label">Heute</div>',
        html, count=1, flags=re.DOTALL
    )

    # Replace today events
    today_section = r'(<div class="section-label">Heute</div>\n).*?(\n\s*<div class="spacer"></div>)'
    html = re.sub(
        today_section,
        rf'\g<1>{today_events_html}\2',
        html, count=1, flags=re.DOTALL
    )

    # Replace upcoming events
    upcoming_section = r'(<div class="section-label">Nächste Termine</div>\n).*?(</div>\s*\n\s*<!-- WEEK PAGE -->)'
    html = re.sub(
        upcoming_section,
        rf'\g<1>{upcoming_html}  \2',
        html, count=1, flags=re.DOTALL
    )

    # --- Replace WEEK page ---
    html = re.sub(
        r'(<div class="greeting">)KW \d+(</div>)',
        rf'\g<1>KW {kw}\2',
        html, count=1
    )
    html = re.sub(
        r'(<div id="page-week"[^>]*>.*?<div class="subtitle">).*?(</div>)',
        rf'\g<1>{week_subtitle}\2',
        html, count=1, flags=re.DOTALL
    )

    # Replace week grid
    html = re.sub(
        r'<div class="week-grid">.*?</div>\s*</div>\s*</div>\s*</div>\s*</div>\s*</div>\s*</div>\s*</div>',
        week_grid,
        html, count=1, flags=re.DOTALL
    )

    # Replace week events (everything after week-grid until <!-- FOCUS PAGE -->)
    week_events_section = r'(</div>\n\s*</div>\n)(.*?)(    <!-- FOCUS PAGE -->)'
    # Simpler: replace between last week-grid closing and FOCUS PAGE
    after_grid = html.find("<!-- FOCUS PAGE -->")
    if after_grid > 0:
        # Find the week-grid end
        grid_end = html.find("</div>", html.find("week-grid"))
        # Find all section-labels in week page
        week_page_start = html.find('id="page-week"')
        week_page_section = html[week_page_start:after_grid]

        # Replace week event listings
        old_week_events = re.findall(
            r'(<div class="section-label">(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag).*?)(?=<div class="section-label">(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag)|</div>\s*\n\s*<!-- FOCUS)',
            week_page_section, flags=re.DOTALL
        )

    return html

def main():
    today = datetime.now()
    print(f"Updating Daily Brief for {format_date_de(today)}...")

    try:
        creds = get_credentials()
        events = fetch_calendar_events(creds)
        print(f"Found {len(events)} calendar events")

        emails = fetch_emails(creds)
        print(f"Found {len(emails)} emails")
    except Exception as e:
        print(f"Warning: Could not fetch data: {e}")
        print("Generating with empty data...")
        events = []
        emails = []

    script_dir = Path(__file__).parent
    index_path = script_dir.parent / "index.html"

    new_html = build_html(index_path, today, events, emails)

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"Updated {index_path}")

if __name__ == "__main__":
    main()
