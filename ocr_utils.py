import re
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


DATE_TOKEN_RE = re.compile(
    r"^\d{1,2}\s*[/\-]\s*\d{1,2}"
    r"(?:\s*[-–]\s*(?:(?:\d{1,2}\s*[/\-]\s*)?\d{1,2}))?$"
)
DATE_RANGE_RE = re.compile(
    r"(?<![\d/])"
    r"(?P<sm>\d{1,2})\s*[/\-]\s*(?P<sd>\d{1,2})"
    r"\s*[-–]\s*"
    r"(?:(?P<em>\d{1,2})\s*[/\-]\s*)?"
    r"(?P<ed>\d{1,2})"
    r"(?!\s*/\s*\d{2,4})"
)
SINGLE_DATE_RE = re.compile(
    r"(?<![\d/])(?P<m>\d{1,2})\s*[-/]\s*(?P<d>\d{1,2})(?!\s*[-/]\s*\d{1,4})"
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
WEEK_RE = re.compile(r"\bWeek\s*(\d+)\b", re.I)

SOURCE_ASSIGNMENT_RE = re.compile(
    r"\b(?P<source>zybook|handout)\s+assignment\s*#?\s*(?P<number>\d+)\b",
    re.I,
)
LAB_RE = re.compile(r"\bZybook\s+Lab\s*#?\s*(\d+)\b", re.I)
PROJECT_RE = re.compile(r"\bProject\s*#?\s*(\d+)\b", re.I)
QUIZ_RE = re.compile(r"\bQuiz\s*#?\s*(\d+)\b", re.I)
TEST_RE = re.compile(r"\bTest\s*#?\s*(\d+)\b", re.I)
FINAL_EXAM_RE = re.compile(r"\bFinal\s+Exam\b", re.I)
MIDTERM_RE = re.compile(r"\bMidterm\s+Exam\b", re.I)
EXAM_RE = re.compile(r"\bExam\b", re.I)
FINAL_RE = re.compile(r"\bFinal\b", re.I)

HOLIDAYS = [
    ("Thanksgiving", re.compile(r"\bThanksgiving\b", re.I)),
    ("Veterans Day", re.compile(r"\bVeterans\s+Day\b", re.I)),
    ("Memorial Day", re.compile(r"\bMemorial\s+Day\b", re.I)),
    ("Labor Day", re.compile(r"\bLabor\s+Day\b", re.I)),
    ("Independence Day", re.compile(r"\bIndependence\s+Day\b", re.I)),
]


def preprocess_image(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    gray = gray.resize((gray.width * 2, gray.height * 2))
    gray = ImageEnhance.Contrast(gray).enhance(2.2)
    return gray.filter(ImageFilter.SHARPEN)


def _ocr_data(image: Image.Image, psm: int = 4) -> List[Dict]:
    data = pytesseract.image_to_data(
        preprocess_image(image),
        config=f"--psm {psm}",
        output_type=pytesseract.Output.DICT,
    )

    result = []
    scale = 2.0

    for i, raw in enumerate(data["text"]):
        text = raw.strip()
        if not text:
            continue

        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1

        if conf < 0:
            continue

        left = int(data["left"][i] / scale)
        top = int(data["top"][i] / scale)
        width = int(data["width"][i] / scale)
        height = int(data["height"][i] / scale)

        result.append({
            "text": text,
            "x1": left,
            "y1": top,
            "x2": left + width,
            "y2": top + height,
            "cx": left + width / 2,
            "cy": top + height / 2,
            "conf": conf,
        })

    return result


def _group_lines(words: List[Dict], y_tolerance: int = 10) -> List[Dict]:
    lines = []

    for word in sorted(words, key=lambda w: (w["cy"], w["x1"])):
        target = None

        for line in lines:
            if abs(word["cy"] - line["cy"]) <= y_tolerance:
                target = line
                break

        if target is None:
            target = {
                "words": [],
                "x1": word["x1"],
                "x2": word["x2"],
                "y1": word["y1"],
                "y2": word["y2"],
                "cy": word["cy"],
            }
            lines.append(target)

        target["words"].append(word)
        target["x1"] = min(target["x1"], word["x1"])
        target["x2"] = max(target["x2"], word["x2"])
        target["y1"] = min(target["y1"], word["y1"])
        target["y2"] = max(target["y2"], word["y2"])
        target["cy"] = sum(w["cy"] for w in target["words"]) / len(target["words"])

    for line in lines:
        line["words"].sort(key=lambda w: w["x1"])
        line["text"] = _clean_text(" ".join(w["text"] for w in line["words"]))

    return sorted(lines, key=lambda x: x["y1"])


def _clean_text(text: str) -> str:
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.replace("|", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_dates(text: str) -> List[Dict]:
    text = _clean_text(text)
    results = []
    occupied = []

    for match in DATE_RANGE_RE.finditer(text):
        sm = int(match.group("sm"))
        sd = int(match.group("sd"))
        em = int(match.group("em")) if match.group("em") else sm
        ed = int(match.group("ed"))

        if not (1 <= sm <= 12 and 1 <= em <= 12 and 1 <= sd <= 31 and 1 <= ed <= 31):
            continue

        results.append({
            "start_month": sm,
            "start_day": sd,
            "end_month": em,
            "end_day": ed,
            "text": _clean_text(match.group(0)),
            "start": match.start(),
            "end": match.end(),
        })
        occupied.append((match.start(), match.end()))

    for match in SINGLE_DATE_RE.finditer(text):
        if any(a <= match.start() < b for a, b in occupied):
            continue

        month = int(match.group("m"))
        day = int(match.group("d"))

        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue

        results.append({
            "start_month": month,
            "start_day": day,
            "end_month": month,
            "end_day": day,
            "text": _clean_text(match.group(0)),
            "start": match.start(),
            "end": match.end(),
        })

    return sorted(results, key=lambda x: x["start"])


def _find_year(lines: List[Dict]) -> Optional[int]:
    text = "\n".join(line["text"] for line in lines)
    years = YEAR_RE.findall(text)
    return int(years[0]) if years else None


def _find_date_column_cluster(words: List[Dict]) -> Optional[Tuple[float, float]]:
    centers = []

    for word in words:
        text = word["text"].strip()
        if DATE_TOKEN_RE.fullmatch(text):
            centers.append((word["cx"], word["x1"], word["x2"]))

    if len(centers) < 2:
        return None

    values = sorted(x[0] for x in centers)
    clusters = [[values[0]]]

    for value in values[1:]:
        if value - clusters[-1][-1] <= 140:
            clusters[-1].append(value)
        else:
            clusters.append([value])

    clusters = [c for c in clusters if len(c) >= 2]
    if not clusters:
        return None

    cluster = max(clusters, key=len)
    return min(cluster) - 110, max(cluster) + 110


def _find_schedule_start(lines: List[Dict]) -> int:
    # Find the first actual schedule row. This is especially important on
    # continuation pages where later policy text can contain the word
    # "schedule".
    first_week = next(
        (line for line in lines if WEEK_RE.search(line["text"])),
        None,
    )

    if first_week is not None:
        # If a schedule title is immediately above the first Week row, use it.
        for line in lines:
            if line["y1"] >= first_week["y1"]:
                break
            t = line["text"].lower()
            if "class scheduling" in t or (
                "schedule" in t and len(t) < 120
            ):
                return max(0, line["y2"] - 5)

        return max(0, first_week["y1"] - 10)

    # Last fallback: a compact line containing several schedule headers.
    schedule_terms = (
        "week", "activity", "date", "remarks",
        "comments", "lectures", "topics", "chapter",
    )

    for line in lines:
        hits = sum(term in line["text"].lower() for term in schedule_terms)
        if hits >= 3:
            return max(0, line["y2"] - 5)

    return 0


def _looks_like_schedule_page(lines: List[Dict]) -> bool:
    text = " ".join(line["text"] for line in lines).lower()

    date_count = 0
    for line in lines:
        date_count += len(_parse_dates(line["text"]))

    indicators = [
        "schedule",
        "class scheduling",
        "week",
        "activity",
        "remarks",
        "chapter",
        "assignment",
        "quiz",
        "project",
        "test",
        "final",
    ]

    hits = sum(1 for item in indicators if item in text)

    return date_count >= 2 and hits >= 1


def _schedule_date_candidates(
    image: Image.Image,
    words: List[Dict],
    lines: List[Dict],
) -> List[Dict]:
    schedule_start = _find_schedule_start(lines)
    cluster = _find_date_column_cluster(words)

    if cluster:
        x1, x2 = cluster
        y1 = max(0, schedule_start - 60)
        y2 = int(image.height * 0.92)

        crop = image.crop((int(x1), y1, int(x2), y2))
        crop_words = _ocr_data(crop, psm=4)
        crop_lines = _group_lines(crop_words, y_tolerance=10)

        found = []
        for line in crop_lines:
            dates = _parse_dates(line["text"])
            for parsed in dates:
                found.append({
                    **parsed,
                    "y": y1 + line["cy"],
                })

        if found:
            return sorted(found, key=lambda x: (x["y"], x["start"]))

    # Last-resort scan of whole schedule text.
    found = []
    for line in lines:
        if line["y1"] < schedule_start:
            continue

        for parsed in _parse_dates(line["text"]):
            found.append({
                **parsed,
                "y": line["cy"],
            })

    return sorted(found, key=lambda x: (x["y"], x["start"]))


def _find_week_column_x(
    words: List[Dict],
    schedule_start: int,
) -> Optional[float]:
    # Prefer an actual Week header.
    for word in words:
        if word["y1"] >= schedule_start and word["text"].lower().strip(":") == "week":
            return word["cx"]

    # Fallback: find the leftmost strong cluster of small integers.
    max_x = max((w["x2"] for w in words), default=0)
    nums = [
        w["cx"]
        for w in words
        if w["y1"] >= schedule_start
        and w["cx"] < 0.75 * max_x
        and re.fullmatch(r"\d{1,2}", w["text"])
    ]

    if not nums:
        return None

    nums.sort()
    clusters = [[nums[0]]]
    for value in nums[1:]:
        if value - clusters[-1][-1] <= 80:
            clusters[-1].append(value)
        else:
            clusters.append([value])

    strong = [c for c in clusters if len(c) >= 3]
    if strong:
        return float(np.median(strong[0]))

    return float(np.median(nums[:min(8, len(nums))]))


def _week_for_date(
    date_y: float,
    words: List[Dict],
    week_column_x: Optional[float],
    previous_week: Optional[int],
) -> Optional[int]:
    if week_column_x is not None:
        nearby = [
            w for w in words
            if abs(w["cx"] - week_column_x) < 65
            and (date_y - 80) <= w["cy"] <= (date_y + 15)
            and re.fullmatch(r"\d{1,2}", w["text"])
        ]
        if nearby:
            nearby.sort(key=lambda w: abs(w["cy"] - date_y))
            return int(nearby[0]["text"])

    # Direct "Week N" fallback.
    for word in words:
        if abs(word["cy"] - date_y) > 80:
            continue
        if word["text"].lower().strip(":") != "week":
            continue

        adjacent = [
            w for w in words
            if abs(w["cy"] - word["cy"]) < 30
            and 0 < w["x1"] - word["x2"] < 90
            and re.fullmatch(r"\d{1,2}", w["text"])
        ]
        if adjacent:
            return int(adjacent[0]["text"])

    return previous_week


def _extract_events(text: str) -> List[Dict]:
    text = _clean_text(text)
    events = []

    source_matches = list(SOURCE_ASSIGNMENT_RE.finditer(text))
    if source_matches:
        for match in source_matches:
            source = match.group("source").title()
            number = match.group("number")
            events.append({
                "event_type": "assignment",
                "title": f"{source} Assignment {number}",
                "notes": text[max(0, match.start()):].strip(" -:;"),
                "_pos": match.start(),
            })
    else:
        for match in re.finditer(r"\bAssignment\s*#?\s*(\d+)\b", text, re.I):
            events.append({
                "event_type": "assignment",
                "title": f"Assignment {match.group(1)}",
                "notes": text[max(0, match.start()):].strip(" -:;"),
                "_pos": match.start(),
            })

    for match in LAB_RE.finditer(text):
        events.append({
            "event_type": "lab",
            "title": f"Zybook Lab {match.group(1)}",
            "notes": text[max(0, match.start()):].strip(" -:;"),
            "_pos": match.start(),
        })

    for pattern, kind, label in [
        (PROJECT_RE, "project", "Project"),
        (QUIZ_RE, "quiz", "Quiz"),
        (TEST_RE, "test", "Test"),
    ]:
        for match in pattern.finditer(text):
            events.append({
                "event_type": kind,
                "title": f"{label} {match.group(1)}",
                "notes": text[max(0, match.start()):].strip(" -:;"),
                "_pos": match.start(),
            })

    for pattern, kind, label in [
        (FINAL_EXAM_RE, "exam", "Final Exam"),
        (MIDTERM_RE, "exam", "Midterm Exam"),
    ]:
        for match in pattern.finditer(text):
            events.append({
                "event_type": kind,
                "title": label,
                "notes": text[max(0, match.start()):].strip(" -:;"),
                "_pos": match.start(),
            })

    if not any(event["event_type"] == "exam" for event in events):
        for match in EXAM_RE.finditer(text):
            events.append({
                "event_type": "exam",
                "title": "Exam",
                "notes": text[max(0, match.start()):].strip(" -:;"),
                "_pos": match.start(),
            })

    # A standalone "Final" is useful for table schedules like the reference
    # syllabus, but is suppressed when "Final Exam" already matched.
    if not any(event["title"] == "Final Exam" for event in events):
        for match in FINAL_RE.finditer(text):
            events.append({
                "event_type": "final",
                "title": "Final",
                "notes": text[max(0, match.start()):].strip(" -:;"),
                "_pos": match.start(),
            })

    for title, pattern in HOLIDAYS:
        for match in pattern.finditer(text):
            events.append({
                "event_type": "holiday",
                "title": title,
                "notes": text[max(0, match.start()):].strip(" -:;"),
                "_pos": match.start(),
            })

    # One calendar event per title/type/date band.
    seen = set()
    cleaned = []
    for event in sorted(events, key=lambda e: e["_pos"]):
        key = (event["event_type"], event["title"])
        if key in seen:
            continue
        seen.add(key)
        event.pop("_pos", None)
        cleaned.append(event)

    return cleaned


def _iso_dates(parsed: Dict, year: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    if year is None:
        return None, None

    try:
        start = date(year, parsed["start_month"], parsed["start_day"])
        end_year = year + 1 if parsed["end_month"] < parsed["start_month"] else year
        end = date(end_year, parsed["end_month"], parsed["end_day"])
        return start.isoformat(), end.isoformat()
    except ValueError:
        return None, None


def _extract_time_info(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    matches = re.findall(r"\b(\d{1,2}):(\d{2})\b", text)

    def fmt(pair):
        return f"{int(pair[0]):02d}:{int(pair[1]):02d}"

    start = fmt(matches[0]) if matches else None
    end = fmt(matches[1]) if len(matches) > 1 else None

    room_match = re.search(r"\bRoom\s+([A-Za-z0-9 -]+)", text, re.I)
    room = room_match.group(1).strip() if room_match else None

    return start, end, room


def extract_date_bounded_schedule(image: Image.Image) -> List[Dict]:
    words = _ocr_data(image, psm=4)
    lines = _group_lines(words, y_tolerance=10)

    if not _looks_like_schedule_page(lines):
        return []

    year = _find_year(lines)
    candidates = _schedule_date_candidates(image, words, lines)

    if not candidates:
        return []

    date_cluster = _find_date_column_cluster(words)
    date_x = None
    if date_cluster:
        date_x = (date_cluster[0] + date_cluster[1]) / 2

    week_x = _find_week_column_x(
        words,
        _find_schedule_start(lines),
    )

    results = []
    previous_week = None

    # Group date candidates that are on the same visual line. This allows
    # schedules such as Week 12 with "11/23" and "11/24-27" on one row.
    groups = []
    for candidate in candidates:
        if not groups or abs(candidate["y"] - groups[-1]["y"]) > 12:
            groups.append({"y": candidate["y"], "dates": [candidate]})
        else:
            groups[-1]["dates"].append(candidate)

    for group_index, group in enumerate(groups):
        y = group["y"]

        if group_index == 0:
            top = max(0, int(y - 55))
        else:
            top = int((groups[group_index - 1]["y"] + y) / 2)

        if group_index + 1 < len(groups):
            bottom = int((y + groups[group_index + 1]["y"]) / 2)
        else:
            bottom = int(image.height * 0.92)

        band_words = [
            word for word in words
            if top <= word["cy"] < bottom
        ]
        band_lines = _group_lines(band_words, y_tolerance=10)
        band_text = "\n".join(line["text"] for line in band_lines)

        week = _week_for_date(
            y,
            words,
            week_x,
            previous_week,
        )
        if week is not None:
            previous_week = week

        events = _extract_events(band_text)
        if not events:
            continue

        start_time, end_time, room = _extract_time_info(band_text)

        for parsed in group["dates"]:
            start_date, end_date = _iso_dates(parsed, year)

            for event in events:
                notes = event["notes"]

                if room and f"Room {room}" not in notes:
                    notes = f"{notes} Room {room}".strip()

                results.append({
                    "week": f"Week {week}" if week is not None else None,
                    "date_range": parsed["text"],
                    "start_date": start_date,
                    "end_date": end_date,
                    "start_time": start_time,
                    "end_time": end_time,
                    "event_type": event["event_type"],
                    "title": event["title"],
                    "notes": notes,
                    "source_text": band_text,
                })

    # Exact duplicates only.
    final = []
    seen = set()

    for entry in results:
        key = (
            entry["start_date"],
            entry["end_date"],
            entry["event_type"],
            entry["title"],
        )
        if key in seen:
            continue
        seen.add(key)
        final.append(entry)

    final.sort(
        key=lambda e: (
            e["start_date"] or "9999-99-99",
            e["title"],
        )
    )

    return final


# Backwards-compatible helpers used by earlier versions of the app.
def get_ocr_words(image: Image.Image) -> List[Dict]:
    return _ocr_data(image, psm=4)


def merge_words_into_lines(words: List[Dict], y_tolerance: int = 10) -> List[Dict]:
    return _group_lines(words, y_tolerance)


def find_date_lines(lines: List[Dict]) -> List[Dict]:
    return [line for line in lines if _parse_dates(line["text"])]
