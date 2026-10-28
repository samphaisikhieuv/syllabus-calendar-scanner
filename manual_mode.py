from datetime import date

import streamlit as st


EVENT_TYPES = [
    "assignment",
    "class",
    "exam",
    "holiday",
    "lab",
    "project",
    "quiz",
    "reading",
    "test",
    "other",
]


def render_manual_mode():
    """Render the manual event editor and return its saved calendar entries."""
    st.subheader("Add calendar events")
    st.caption("Enter events directly, one at a time. Your entries stay in this session.")

    if "manual_events" not in st.session_state:
        st.session_state.manual_events = []

    with st.form("manual_event_form", clear_on_submit=True):
        title = st.text_input("Event title", placeholder="e.g. Quiz 1")
        event_type = st.selectbox("Event type", EVENT_TYPES)
        start_date = st.date_input("Date", value=date.today())
        has_end_date = st.checkbox("This event spans multiple days")
        end_date = st.date_input("Last day", value=start_date) if has_end_date else start_date
        has_time = st.checkbox("Add a time")
        if has_time:
            start_time = st.time_input("Start time")
            has_end_time = st.checkbox("Add an end time")
            end_time = st.time_input("End time") if has_end_time else None
        else:
            start_time = None
            end_time = None
        week = st.text_input("Week (optional)", placeholder="Week 4")
        notes = st.text_area("Notes (optional)")
        submitted = st.form_submit_button("Add event", type="primary")

    if submitted:
        if not title.strip():
            st.error("Enter an event title before adding it.")
        elif end_date < start_date:
            st.error("The last day must be on or after the event date.")
        elif start_time and end_time and end_time <= start_time and end_date == start_date:
            st.error("The end time must be after the start time.")
        else:
            st.session_state.manual_events.append({
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "start_time": start_time.strftime("%H:%M") if start_time else None,
                "end_time": end_time.strftime("%H:%M") if end_time else None,
                "week": week.strip() or None,
                "event_type": event_type,
                "title": title.strip(),
                "notes": notes.strip(),
                "date_range": start_date.isoformat() if end_date == start_date else f"{start_date.isoformat()} - {end_date.isoformat()}",
                "source_text": "Manually entered",
                "page": "",
            })
            st.success(f"Added “{title.strip()}”.")

    entries = st.session_state.manual_events
    if entries:
        st.markdown("**Saved events**")
        for index, entry in enumerate(entries):
            left, right = st.columns([8, 1])
            event_time = f" · {entry['start_time']}" if entry.get("start_time") else ""
            left.write(f"**{entry['start_date']}{event_time} · {entry['title']}**  \n{entry['event_type'].title()} · {entry.get('week') or 'No week'}")
            if right.button("Remove", key=f"remove_manual_event_{index}"):
                entries.pop(index)
                st.rerun()
        if st.button("Clear all manual events", key="clear_manual_events"):
            st.session_state.manual_events = []
            st.rerun()

    return list(st.session_state.manual_events)
