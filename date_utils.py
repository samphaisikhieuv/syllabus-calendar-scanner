import re

HIGH_VALUE_KEYWORDS = [
    "assignment",
    "test",
    "quiz",
    "exam",
    "midterm",
    "final",
    "project",
    "lab",
    "homework",
    "assessment",
]

MEDIUM_VALUE_KEYWORDS = [
    "module",
    "week",
    "chapter",
    "lecture",
    "topic",
    "syllabus",
]

LOW_VALUE_KEYWORDS = [
    "zybook",
    "handout",
    "covers",
    "covers modules",
    "covers chapters",
]

NOISE_PATTERNS = [
    r"^Class Scheduling and Assignments:?$",
    r"^Page \d+$",
    r"^Brady Chen$",
    r"^9/5/2026$",
]

WEEK_RE = re.compile(r"\bWeek\s+(\d+)\b", re.IGNORECASE)
DATE_RANGE_RE = re.compile(r"\b\d{1,2}/\d{1,2}\s*-\s*\d{1,2}/\d{1,2}\b")
DATE_RANGE_RE_ALT = re.compile(r"\b\d{1,2}/\d{1,2}\s*–\s*\d{1,2}/\d{1,2}\b")

def clean_text(text):
    replacements = {
        "913-914": "9/3-9/4",
        "10/12- 10/16": "10/12-10/16",
        "11/16/20": "11/16-11/20",
        "Zsjbook": "Zybook",
        "Zjbook": "Zybook",
    }

    for bad, good in replacements.items():
        text = text.replace(bad, good)

    text = text.replace("9/5/2026", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def split_week_blocks(text):
    lines = [line.strip() for line in text.splitlines()]
    blocks = []
    current = []

    for line in lines:
        if not line:
            continue

        if any(re.fullmatch(pattern, line, re.IGNORECASE) for pattern in NOISE_PATTERNS):
            continue

        if WEEK_RE.search(line):
            if current:
                blocks.append(" ".join(current).strip())
                current = []
        current.append(line)

    if current:
        blocks.append(" ".join(current).strip())

    return blocks

def has_event_keyword(text):
    lower = text.lower()
    return any(word in lower for word in HIGH_VALUE_KEYWORDS)

def score_block(block):
    lower = block.lower()
    score = 0

    for word in HIGH_VALUE_KEYWORDS:
        if word in lower:
            score += 3

    for word in MEDIUM_VALUE_KEYWORDS:
        if word in lower:
            score += 1

    for word in LOW_VALUE_KEYWORDS:
        if word in lower:
            score += 1

    if WEEK_RE.search(block):
        score += 1

    if DATE_RANGE_RE.search(block) or DATE_RANGE_RE_ALT.search(block):
        score += 2

    return score

def split_by_keywords(text):
    pattern = re.compile(
        r"(?=\bWeek\s+\d+\b|\bModule\s+[0-9A-Za-z]+\b|\b(?:Assignment|Test|Quiz|Exam|Lab|Project|Handout)\b)",
        re.IGNORECASE
    )
    parts = [p.strip() for p in pattern.split(text) if p.strip()]
    return parts

def extract_schedule_entries(text, min_score=4):
    text = clean_text(text)

    # First split into rough blocks
    blocks = split_week_blocks(text)

    # Then split large noisy blocks into smaller keyword-based pieces
    refined_blocks = []
    for block in blocks:
        subparts = split_by_keywords(block)
        if subparts:
            refined_blocks.extend(subparts)
        else:
            refined_blocks.append(block)

    entries = []

    for block in refined_blocks:
        block = re.sub(r"\s+", " ", block).strip()
        score = score_block(block)

        week_match = WEEK_RE.search(block)
        has_week = week_match is not None
        has_event = has_event_keyword(block)

        # Require a week anchor and a real event keyword
        if not (has_week and has_event):
            continue

        if score < min_score:
            continue

        week = f"Week {week_match.group(1)}" if week_match else None

        date_match = DATE_RANGE_RE.search(block) or DATE_RANGE_RE_ALT.search(block)
        date_range = date_match.group(0) if date_match else None

        module_match = re.search(
            r"\bModule\s+[0-9A-Za-z]+\b(?:\s*\([^)]
