from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI

from app.classify.prompt_store import get_active_system_prompt
from app.config import get_settings
from app.models import EmailLabel
from app.schemas import ClassificationResult

logger = logging.getLogger(__name__)

VALID_LABELS = {label.value for label in EmailLabel}

LEGACY_LABEL_MAP = {
    "tech": EmailLabel.ASSESSMENT.value,
    "available": EmailLabel.SCREENING.value,
    "alert": EmailLabel.JOB_ALERT.value,
    "application_submitted": EmailLabel.APPLIED.value,
    "new_opportunity": EmailLabel.JOB_ALERT.value,
    "recruiter_outreach": EmailLabel.JOB_ALERT.value,
    "talent_pool": EmailLabel.OTHERS.value,
    "company_news": EmailLabel.OTHERS.value,
    "career_event": EmailLabel.OTHERS.value,
    "profile_update_request": EmailLabel.OTHERS.value,
    "withdrawn": EmailLabel.REJECTED.value,
    "hired": EmailLabel.OFFER.value,
}


def normalize_label(raw: str) -> str:
    label = raw.lower().strip().replace(" ", "_")
    label = LEGACY_LABEL_MAP.get(label, label)
    if label not in VALID_LABELS:
        return EmailLabel.UNKNOWN.value
    return label


def _parse_label(content: str) -> tuple[str, float | None]:
    content = content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return EmailLabel.UNKNOWN.value, None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return EmailLabel.UNKNOWN.value, None

    label = normalize_label(str(data.get("label", EmailLabel.UNKNOWN.value)))
    confidence = data.get("confidence")
    try:
        confidence_f = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_f = None
    return label, confidence_f


def _combined_text(subject: str, sender: str, body_text: str, snippet: str) -> str:
    raw = f"{subject}\n{sender}\n{snippet}\n{body_text}".lower()
    return raw.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")


def _is_pre_interview_screen(text: str) -> bool:
    """Written screening for a named role — interview is not booked yet."""
    before_booking = any(
        re.search(p, text)
        for p in [
            r"\bbefore\s+(scheduling|we\s+schedule|setting\s+up|i\s+schedule)\s+"
            r"(a\s+)?(recruiter\s+|phone\s+|screening\s+)?interview\b",
            r"\bprior\s+to\s+(scheduling|an)\s+interview\b",
            r"\bbefore\s+(we\s+)?(move\s+forward\s+to|set\s+up)\s+(an\s+)?interview\b",
        ]
    )
    asks_written = any(
        s in text
        for s in [
            "reply with brief answers",
            "reply with answers",
            "answers to the questions",
            "answer the questions",
            "a few sentences per question",
            "could you reply with",
            "please answer the",
            "questions below",
        ]
    )
    thanks_interest = bool(re.search(r"\bthanks for your interest in\b", text))
    named_role = bool(re.search(r"\b(the\s+)?[\w /+-]+ (role|position) at\b", text))
    if before_booking and (asks_written or thanks_interest):
        return True
    return thanks_interest and named_role and asks_written


def _is_application_received(text: str) -> bool:
    """Post-apply receipt / 'we'll interview later if we want' — not a live invite."""
    if _looks_like_cold_jd_blast(text) or _is_true_rejection(text):
        return False
    receipts = [
        r"\bthank you for (taking the time to )?apply(ing)?\b",
        r"\bthanks for (taking the time to )?apply(ing)?\b",
        r"\bthank(s| you) for submitting your application\b",
        r"\bwe have received (your application|several applications|all of your materials)\b",
        r"\breceived (all of )?your (application|materials)\b",
        r"\byour application\b.{0,160}\bhas been received\b",
        r"\bapplication has been received\b",
        r"\bnow that we have your application\b",
        r"\bwe('ll| will) be in touch\b.*\bschedule an interview\b",
        r"\bif (we('d| would) like to|your qualifications meet)\b",
        r"\bone of our team members will get in touch\b",
        r"\bin the coming weeks to schedule an interview\b",
        r"\breview (them|applications) as quickly as possible\b",
    ]
    return any(re.search(p, text) for p in receipts)


def _is_hypothetical_interview(text: str) -> bool:
    return any(
        re.search(p, text)
        for p in [
            r"\bif we('d| would) like to schedule\b",
            r"\bif your qualifications meet\b",
            r"\bin the coming weeks to schedule an interview\b",
            r"\bmode of interview\b",
            r"\bjob description\b",
        ]
    )


def _is_true_interview_invite(text: str) -> bool:
    """Candidate-directed interview scheduling — not JD wording or screening Qs."""
    if _is_pre_interview_screen(text):
        return False
    if _is_application_received(text):
        return False
    if _looks_like_cold_jd_blast(text):
        return False
    if _is_hypothetical_interview(text) and not re.search(
        r"\b(confirmed for your interview|your interview (is|has been)|i('ll| will) call you)\b",
        text,
    ):
        return False
    patterns = [
        r"\byou are confirmed for your interview\b",
        r"\bconfirmed for your interview\b",
        r"\binvite[d]?\s+you\s+to\s+(an\s+)?interview\b",
        r"\bplease\s+(book|schedule)\s+(a|your)\s+(time|slot|interview)\b",
        r"\byour\s+interview\s+(is|has been|will be)\b",
        r"\binterview\s+(invitation|invite)\b",
        r"\bplease\s+(join|attend)\s+(the|your)\s+interview\b",
        r"\bcalendar\s+invite\b.*\binterview\b",
        r"\bi('ll| will) call you\b.*\binterview\b",
        r"\binterview\b.*\bi('ll| will) call you\b",
        r"\bbook\s+(a|your)\s+(time|slot)\b.*\binterview\b",
    ]
    return any(re.search(p, text) for p in patterns)


def _is_true_rejection(text: str) -> bool:
    patterns = [
        r"\bnot (?:be )?(?:able to )?mov(?:e|ing) forward\b",
        r"\bcannot move forward with your\b",
        r"\bregret to inform you\b",
        r"\byou have reached that limit\b",
        r"\breached (the|that|our) (application )?limit\b",
        r"\bwe have decided to move forward with other candidates?\b",
        r"\bunfortunately\b.*\b(your application|this role|this position|your candidacy)\b",
        r"\bwe\s+have\s+decided\s+to\s+move\s+forward\b",
        r"\bwill\s+not\s+be\s+progressing\b",
        r"\bnot been selected\b",
        r"\byou have not been selected to move forward\b",
        r"\bwe(?:['’]ve|\s+have) decided to move forward\b",
        r"\b(?:have\s+)?made the decision to move forward\b",
        r"\bmov(?:e|ing)\s+forward\s+with\s+(?:other\s+)?candidates\b",
        r"\bexperience aligns more directly\b",
        r"\bexperience more closely aligns\b",
        r"\baligns more directly to what this (?:specific )?role needs\b",
        r"\bunfortunately\b.{0,240}\bmove forward\b",
        r"\b(?:this )?(?:position|role|job) is not available in your (?:current )?location\b",
        r"\bnot available in your (?:current )?location\b",
        r"\bonly registered to hire\b",
        r"\b(?:we are|are only) registered to hire employees in specific locations\b",
        r"\bcannot hire (?:you )?in your (?:current )?location\b",
        r"\bnot (?:able|eligible) to hire (?:you )?(?:in|from) your (?:current )?location\b",
        r"\bproceed with (?:other\s+)?candidates\b",
        r"\bdecided to proceed with (?:other\s+)?candidates\b",
        r"\bbetter align with our current hiring needs\b",
    ]
    return any(re.search(p, text) for p in patterns)


def _is_true_screening(text: str) -> bool:
    """Booked recruiter/phone screen — not a technical/behavioral interview."""
    if _is_application_received(text) or _looks_like_cold_jd_blast(text):
        return False
    if _is_true_rejection(text):
        return False
    return any(
        re.search(p, text)
        for p in [
            r"\bphone\s+screen\b",
            r"\brecruiter\s+screen\b",
            r"\bscreening\s+call\b",
            r"\bschedule\s+a\s+(quick\s+)?(intro|introductory|recruiter)\s+call\b",
            r"\blet'?s\s+schedule\s+a\s+(quick\s+)?call\b",
        ]
    )


def _is_true_assessment(text: str) -> bool:
    patterns = [
        r"\bhackerrank\b",
        r"\bcodility\b",
        r"\btake[- ]home\b",
        r"\bcoding\s+test\b",
        r"\bonline\s+assessment\b",
        r"\bcomplete\s+(this|the)\s+assessment\b",
        r"\btechnical\s+assessment\b",
    ]
    return any(re.search(p, text) for p in patterns)


def _looks_like_cold_jd_blast(text: str) -> bool:
    """Cold recruiter JD pitch: role dump, even without 'send resume'."""
    jd_markers = [
        "job description",
        "job details",
        "job summary",
        "must have technical",
        "preferred skills",
        "preferred skills and knowledge",
        "mode of interview",
        "role:-",
        "experience required",
        "job type",
        "long term contract",
        "duration-",
        "duration -",
        "duration:",
    ]
    structure_markers = [
        "job description",
        "preferred skills",
        "mode of interview",
        "location",
        "duration",
        "summary:",
        "job –",
        "job-",
    ]
    ask_markers = [
        "send me a copy of your resume",
        "send your resume",
        "please send me a copy of your resume",
        "should you be interested",
        "if you are interested",
        "if interested",
        "share your resume",
        "forward your resume",
        "updated resume",
        "reply with your updated resume",
        "reply with your resume",
        "please reply with your",
        "find the requirement",
        "please find the requirement",
        "if you find yourself comfortable",
        "asap",
    ]
    sourcing_markers = [
        "unsubscribe",
        "posted your resume",
        "jobs portals",
        "job portals",
        "wish to be contacted",
        "email preferences",
        "technical it recruiter",
        "staffing",
    ]
    has_jd = sum(1 for m in jd_markers if m in text) >= 2
    has_structure = sum(1 for m in structure_markers if m in text) >= 3
    has_mode = "mode of interview" in text and ("job description" in text or "location" in text)
    has_ask = any(m in text for m in ask_markers)
    has_sourcing = any(m in text for m in sourcing_markers)
    has_req_fields = bool(
        re.search(r"\btitle\s*[-:]", text)
        and re.search(r"\blocation\s*[-:]", text)
        and re.search(r"\bduration\s*[-:]", text)
    )
    has_openings = bool(re.search(r"\b\d+\s+openings?\b", text))
    return (
        has_mode
        or has_structure
        or has_req_fields
        or (has_jd and (has_ask or has_sourcing or has_openings))
        or (has_ask and has_req_fields)
    )


def _heuristic_label(subject: str, sender: str, body_text: str, snippet: str) -> str | None:
    text = _combined_text(subject, sender, body_text, snippet)

    if _is_true_rejection(text):
        return EmailLabel.REJECTED.value
    if _is_application_received(text):
        return EmailLabel.APPLIED.value
    if _looks_like_cold_jd_blast(text):
        return EmailLabel.JOB_ALERT.value

    alert_signals = [
        "jobs that might interest you",
        "new jobs that might interest",
        "job alert",
        "job notification",
        "see all opportunities",
        "view all the jobs",
        "unsubscribe",
        "you have an interesting background",
        "fast track your application",
        "virtual agent",
        "click here to start a quick conversation",
        "we are currently working with one of our top clients",
        "surely you may know someone",
        "browse our open positions",
        "find more opportunities",
        "posted your resume on jobs portals",
        "posted your resume on job portals",
        "wish to be contacted for job opportunities",
    ]
    if any(s in text for s in alert_signals):
        return EmailLabel.JOB_ALERT.value

    if _is_true_assessment(text):
        return EmailLabel.ASSESSMENT.value
    if _is_pre_interview_screen(text) or _is_true_screening(text):
        return EmailLabel.SCREENING.value
    if _is_true_interview_invite(text):
        return EmailLabel.INTERVIEW.value
    return None


def apply_label_guards(
    label: str,
    *,
    subject: str,
    sender: str,
    body_text: str,
    snippet: str,
) -> str:
    """Force known heuristic outcomes over a mistaken model label."""
    heuristic = _heuristic_label(subject, sender, body_text, snippet)
    text = _combined_text(subject, sender, body_text, snippet)
    if heuristic == EmailLabel.REJECTED.value:
        return EmailLabel.REJECTED.value
    if heuristic == EmailLabel.APPLIED.value:
        return EmailLabel.APPLIED.value
    if heuristic == EmailLabel.JOB_ALERT.value:
        return EmailLabel.JOB_ALERT.value
    if heuristic == EmailLabel.INTERVIEW.value:
        return EmailLabel.INTERVIEW.value
    if heuristic == EmailLabel.SCREENING.value:
        return EmailLabel.SCREENING.value
    if label == EmailLabel.INTERVIEW.value and (
        _is_pre_interview_screen(text) or _is_true_screening(text)
    ):
        return EmailLabel.SCREENING.value
    return label


async def classify_email(
    *,
    subject: str,
    sender: str,
    body_text: str,
    snippet: str,
    force_openai: bool = False,
    use_openai: bool = True,
) -> ClassificationResult:
    heuristic = _heuristic_label(subject, sender, body_text, snippet)
    settings = get_settings()

    # Heuristic-only path (fallback or tests). Live/Sync use OpenAI + guards.
    if not force_openai and not use_openai:
        return ClassificationResult(
            label=(heuristic or EmailLabel.UNKNOWN.value),  # type: ignore[arg-type]
            confidence=0.55 if heuristic else 0.35,
            response_id=None,
        )
    if not settings.openai_api_key:
        return ClassificationResult(
            label=(heuristic or EmailLabel.UNKNOWN.value),  # type: ignore[arg-type]
            confidence=0.45 if heuristic else None,
            response_id=None,
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_content = (
        f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}\n\nBody:\n{body_text[:6000]}"
    )
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": get_active_system_prompt()},
                {"role": "user", "content": user_content},
            ],
        )
    except Exception:
        logger.exception("OpenAI classification failed; using heuristic")
        return ClassificationResult(
            label=(heuristic or EmailLabel.UNKNOWN.value),  # type: ignore[arg-type]
            confidence=0.45 if heuristic else None,
            response_id=None,
        )
    content = response.choices[0].message.content or "{}"
    label, confidence = _parse_label(content)
    label = apply_label_guards(
        label,
        subject=subject,
        sender=sender,
        body_text=body_text,
        snippet=snippet,
    )

    return ClassificationResult(
        label=label,  # type: ignore[arg-type]
        confidence=confidence,
        response_id=response.id,
    )
