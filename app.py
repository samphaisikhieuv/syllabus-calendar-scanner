from datetime import datetime, timedelta
import re

import pandas as pd
import streamlit as st
from pdf2image import convert_from_bytes

from manual_mode import render_manual_mode
from ocr_utils import extract_date_bounded_schedule


st.set_page_config(page_title="Syllabus Calendar Scanner", layout="wide")
st.title("Syllabus Calendar Scanner")
st.write(
    "Scan a syllabus PDF automatically or enter calendar events manually. "
    "Review the events and download them as CSV or an .ics calendar file."
)

mode = st.radio("Entry mode", ["Automatic scan", "Manual entry"], horizontal=True)


def _year_from_filename(filename):
    matches = re.findall(r"\b(?:19|20)\d{2}\b", filename or "")
    return int(matches[-1]) if matches else None


def _ics_escape(value):
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics(entries):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Syllabus Calendar Scanner//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for index, entry in enumerate(entries, start=1):
        if not entry.get("start_date"):
            continue
        start = datetime.strptime(entry["start_date"], "%Y-%m-%d")
        end = datetime.strptime(entry.get("end_date") or entry["start_date"], "%Y-%m-%d")
        uid = f"syllabus-{start.date().isoformat()}-{index}@local"
        lines.extend(["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{timestamp}"])

        if entry.get("start_time"):
            start_dt = datetime.strptime(
                f"{entry['start_date']} {entry['start_time']}", "%Y-%m-%d %H:%M"
            )
            if entry.get("end_time"):
                end_dt = datetime.strptime(
                    f"{entry.get('end_date') or entry['start_date']} {entry['end_time']}",
                    "%Y-%m-%d %H:%M",
                )
            else:
                end_dt = start_dt + timedelta(hours=1)
            lines.extend([
                f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            ])
        else:
            lines.extend([
                f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{(end + timedelta(days=1)).strftime('%Y%m%d')}",
            ])

        description = (
            f"Type: {entry.get('event_type', '')}\n"
            f"Week: {entry.get('week', '')}\n"
            f"Date range: {entry.get('date_range', '')}\n"
            f"Notes: {entry.get('notes', '')}"
        )
        lines.extend([
            f"SUMMARY:{_ics_escape(entry.get('title'))}",
            f"DESCRIPTION:{_ics_escape(description)}",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


all_results = []
show_source = False

if mode == "Manual entry":
    all_results = render_manual_mode()
else:
    uploaded_file = st.file_uploader("Upload a syllabus PDF", type=["pdf"])
    col_a, col_b = st.columns(2)
    with col_a:
        show_pages = st.checkbox("Show scanned pages", value=False)
    with col_b:
        show_source = st.checkbox("Show OCR source text", value=False)

    keyword_text = st.text_input(
        "Additional search keywords",
        placeholder="e.g. Zybook, presentation, paper",
        help=(
            "Separate terms with commas. Built-in event terms like homework, "
            "assignment, test, quiz, exam, project, and lab are always checked."
        ),
    )
    custom_keywords = list(dict.fromkeys(
        keyword.strip() for keyword in keyword_text.split(",") if keyword.strip()
    ))

    if uploaded_file is not None:
        pdf_bytes = uploaded_file.read()
        detected_year = _year_from_filename(uploaded_file.name)
        year_value = st.number_input(
            "Schedule year",
            min_value=1900,
            max_value=2100,
            value=detected_year or datetime.now().year,
            step=1,
            help="Used when the syllabus lists dates without a year. A year in the filename is used as the default when present.",
        )

        try:
            pages = convert_from_bytes(pdf_bytes)
        except Exception as exc:
            st.error("Could not convert the PDF. Make sure Poppler is installed and available on PATH.")
            st.exception(exc)
            st.stop()

        for page_number, page_image in enumerate(pages, start=1):
            if show_pages:
                st.subheader(f"Page {page_number}")
                st.image(page_image, caption=f"Page {page_number}", use_container_width=True)
            try:
                entries = extract_date_bounded_schedule(
                    page_image,
                    year_hint=int(year_value),
                    custom_keywords=custom_keywords,
                )
            except Exception as exc:
                st.error(f"OCR failed on page {page_number}.")
                st.exception(exc)
                continue
            all_results.extend({"page": page_number, **entry} for entry in entries)

        st.divider()
        st.subheader("Add entries to this scan")
        manual_results = render_manual_mode()
        all_results.extend(manual_results)

if not all_results:
    if mode == "Automatic scan" and 'uploaded_file' in locals() and uploaded_file is not None:
        st.warning("No calendar events were detected. Turn on the debugging options above and try again.")
    elif mode == "Automatic scan":
        st.info("Upload a syllabus PDF to scan, or switch to Manual entry.")
    st.stop()

st.subheader("Calendar-ready entries")
df = pd.DataFrame(all_results)
display_columns = [
    "start_date", "end_date", "start_time", "end_time", "week",
    "event_type", "title", "notes", "page",
]
for column in display_columns:
    if column not in df.columns:
        df[column] = ""
st.dataframe(df[display_columns], use_container_width=True, hide_index=True)
st.caption(f"{len(all_results)} calendar-ready event(s).")

st.subheader("Events")
for entry in all_results:
    start = entry.get("start_date") or entry.get("date_range") or "Date not set"
    end = entry.get("end_date")
    date_label = f"{start} → {end}" if end and end != start else start
    if entry.get("start_time"):
        date_label += f" @ {entry['start_time']}"
        if entry.get("end_time"):
            date_label += f"–{entry['end_time']}"
    with st.expander(f"{date_label} · {entry.get('title', 'Untitled event')}"):
        st.write(f"**Week:** {entry.get('week') or 'Not detected'}")
        st.write(f"**Type:** {entry.get('event_type', '')}")
        st.write(f"**Date range:** {entry.get('date_range', '')}")
        st.write(f"**Notes:** {entry.get('notes', '')}")
        if show_source:
            st.code(entry.get("source_text", ""), language="text")

csv_columns = [
    "page", "start_date", "end_date", "start_time", "end_time",
    "week", "event_type", "title", "notes",
]
for column in csv_columns:
    if column not in df.columns:
        df[column] = ""
csv_bytes = df[csv_columns].to_csv(index=False).encode("utf-8")
ics_bytes = build_ics(all_results).encode("utf-8")
left, right = st.columns(2)
with left:
    st.download_button(
        "Download CSV", data=csv_bytes, file_name="syllabus_calendar_events.csv",
        mime="text/csv", use_container_width=True,
    )
with right:
    st.download_button(
        "Download Calendar (.ics)", data=ics_bytes,
        file_name="syllabus_calendar_events.ics", mime="text/calendar",
        use_container_width=True,
    )
