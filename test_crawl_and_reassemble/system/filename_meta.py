from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path


SUBJECT_ALIASES: dict[str, str] = {
    "생활과윤리": "생활과윤리",
    "생활과 윤리": "생활과윤리",
    "생윤": "생활과윤리",
    "윤리와사상": "윤리와사상",
    "윤리와 사상": "윤리와사상",
    "윤사": "윤리와사상",
    "통합사회": "통합사회",
    "사회문화": "사회문화",
    "사회·문화": "사회문화",
    "사회 문화": "사회문화",
    "정치와법": "정치와법",
    "정치와 법": "정치와법",
    "경제": "경제",
    "한국지리": "한국지리",
    "세계지리": "세계지리",
    "동아시아사": "동아시아사",
    "세계사": "세계사",
    "물리학Ⅰ": "물리학1",
    "물리학I": "물리학1",
    "물리1": "물리학1",
    "화학Ⅰ": "화학1",
    "화학I": "화학1",
    "화학1": "화학1",
    "생명과학Ⅰ": "생명과학1",
    "생명과학I": "생명과학1",
    "생명1": "생명과학1",
    "지구과학Ⅰ": "지구과학1",
    "지구과학I": "지구과학1",
    "지구1": "지구과학1",
    "국어": "국어",
    "수학": "수학",
    "영어": "영어",
    "한국사": "한국사",
}

KIND_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("answer_explanation", ("정답및해설", "정답 및 해설", "정답해설", "해설지")),
    ("answer", ("정답", "답지", "답안")),
    ("script", ("듣기대본", "듣기 대본", "대본")),
    ("audio", ("음원", "듣기파일", "mp3")),
    ("problem", ("문제지", "문제", "문항")),
]


@dataclass
class ExamMeta:
    path: str
    filename: str
    stem: str
    year: int | None = None
    school_year: int | None = None
    grade: int | None = None
    month: int | None = None
    exam_label: str | None = None
    exam_family: str | None = None
    subject: str | None = None
    subject_canonical: str | None = None
    document_kind: str = "unknown"
    source: str = "unknown"
    source_detail: str | None = None
    is_problem: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def compact_text(value: str) -> str:
    value = value.replace("_", "-")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_for_match(value: str) -> str:
    value = compact_text(value)
    value = value.replace("-", " ")
    value = value.replace("_", " ")
    return re.sub(r"\s+", " ", value)


def detect_document_kind(text: str, suffix: str = "") -> str:
    haystack = normalize_for_match(text).replace(" ", "")
    suffix_l = suffix.lower().lstrip(".")
    if suffix_l in {"mp3", "wav", "m4a"}:
        return "audio"
    for kind, needles in KIND_PATTERNS:
        for needle in needles:
            if needle.replace(" ", "") in haystack:
                return kind
    return "unknown"


def detect_subject(text: str) -> tuple[str | None, str | None]:
    normalized = normalize_for_match(text)
    compact = normalized.replace(" ", "")
    ordered = sorted(SUBJECT_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
    for alias, canonical in ordered:
        alias_compact = alias.replace(" ", "")
        if alias in normalized or alias_compact in compact:
            return alias, canonical
    return None, None


def detect_source(text: str) -> tuple[str, str | None]:
    compact = normalize_for_match(text).replace(" ", "").lower()
    if "ebsi" in compact or "ebs" in compact:
        return "ebsi", "EBSi"
    if "교육청" in compact or "학평" in compact or "전국연합" in compact:
        return "education_office", "교육청 학력평가"
    if "kice" in compact or "평가원" in compact or "수능" in compact:
        return "kice", "한국교육과정평가원"
    return "unknown", None


def detect_exam_label(text: str, source: str, month: int | None) -> tuple[str | None, str | None]:
    compact = normalize_for_match(text).replace(" ", "")
    if "전국연합학력평가" in compact:
        return "전국연합학력평가", "education_office"
    if "학력평가" in compact or "학평" in compact:
        return "학력평가", "education_office"
    if "모의평가" in compact:
        return "모의평가", "kice"
    if "모의고사" in compact:
        family = "education_office" if source == "education_office" else None
        return "모의고사", family
    if "수능" in compact and "수능특강" not in compact:
        return "수능", "kice"
    if source == "education_office":
        return "학력평가", "education_office"
    if source == "kice" and month in {6, 9}:
        return "모의평가", "kice"
    if source == "kice":
        return "수능", "kice"
    return None, None


def parse_exam_metadata(path: str | Path, input_root: str | Path | None = None) -> ExamMeta:
    pdf_path = Path(path)
    try:
        display_path = str(pdf_path.resolve())
    except OSError:
        display_path = str(pdf_path)

    if input_root:
        try:
            context = str(pdf_path.relative_to(Path(input_root))) + " " + pdf_path.name
        except ValueError:
            context = str(pdf_path)
    else:
        context = str(pdf_path)

    name_text = compact_text(pdf_path.stem)
    context_text = compact_text(context)
    all_text = f"{context_text} {name_text}"

    year = None
    school_year = None
    m = re.search(r"(?<!\d)((?:19|20)\d{2})\s*년", name_text)
    if m:
        year = int(m.group(1))
    m = re.search(r"(?<!\d)((?:19|20)\d{2})\s*학년도", name_text)
    if m:
        school_year = int(m.group(1))

    grade = None
    m = re.search(r"고\s*([123])", all_text)
    if m:
        grade = int(m.group(1))

    month = None
    m = re.search(r"(?<!\d)(1[0-2]|[1-9])\s*월", name_text)
    if m:
        month = int(m.group(1))

    subject, subject_canonical = detect_subject(all_text)
    source, source_detail = detect_source(all_text)
    exam_label, exam_family = detect_exam_label(name_text, source, month)
    if not exam_label:
        exam_label, exam_family = detect_exam_label(all_text, source, month)
    document_kind = detect_document_kind(name_text, pdf_path.suffix)

    return ExamMeta(
        path=display_path,
        filename=pdf_path.name,
        stem=pdf_path.stem,
        year=year,
        school_year=school_year,
        grade=grade,
        month=month,
        exam_label=exam_label,
        exam_family=exam_family,
        subject=subject,
        subject_canonical=subject_canonical,
        document_kind=document_kind,
        source=source,
        source_detail=source_detail,
        is_problem=document_kind == "problem",
    )


def normalized_output_stem(meta: ExamMeta) -> str:
    parts: list[str] = []
    if meta.year:
        parts.append(f"{meta.year}년")
    elif meta.school_year:
        parts.append(f"{meta.school_year}학년도")
    else:
        parts.append("연도미상")
    if meta.grade:
        parts.append(f"고{meta.grade}")
    if meta.month:
        parts.append(f"{meta.month}월")
    if meta.exam_label:
        parts.append(meta.exam_label)
    if meta.subject_canonical:
        parts.append(meta.subject_canonical)
    kind_label = {
        "problem": "문제",
        "answer": "정답",
        "answer_explanation": "정답및해설",
        "script": "듣기대본",
        "audio": "음원",
        "unknown": "자료",
    }.get(meta.document_kind, meta.document_kind)
    parts.append(kind_label)
    return "-".join(safe_path_part(p) for p in parts if p)


def safe_path_part(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]', "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value.rstrip(". ")
