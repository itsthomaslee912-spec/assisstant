from __future__ import annotations

import json
import re

from openai import AsyncOpenAI

from app.config import get_settings
from app.models import EmailLabel
from app.schemas import ClassificationResult

VALID_LABELS = {label.value for label in EmailLabel}

LEGACY_LABEL_MAP = {
    "tech": EmailLabel.ASSESSMENT.value,
}

SYSTEM_PROMPT = """You classify recruiting / job-search emails into exactly ONE label.

Labels:

1) rejected
   - Explicit rejection of THIS candidate / not moving forward / another candidate selected.
   - Also: application cap / “we will not be able to move forward with your most recent
     application” / “you have reached that limit” — even if they thank you for applying.

2) interview
   - ONLY when THIS candidate already has (or is being asked to book) an interview NOW.
   - Examples: "you are confirmed for your interview on Wednesday", "please book a time",
     "I'll call you at … for your interview", calendar/Zoom link for THEIR interview.
   - Confirmations and reminders of a booked interview still count as interview.
   - Do NOT use interview for:
     * "if we'd like to schedule an interview" / "if your qualifications meet, we will
       get in touch to schedule an interview" (that is applied).
     * Job descriptions that list "Mode of Interview: MS Teams" or F2F rounds (that is alert).
     * Screening questionnaires sent BEFORE any interview is booked (that is available).

3) assessment
   - Coding test / HackerRank / Codility / take-home / online assessment for THIS candidate.

4) applied
   - Confirmation that THIS candidate's application was received / is under review
     AFTER they applied. Not cold outreach.
   - Examples: "thank you for your interest in joining … we have received several applications",
     "thanks for taking the time to apply … we'll be in touch if we'd like to schedule an interview".

5) alert  ← default for most job-related marketing / cold mail
   - Job alerts, digests, newsletters, unsubscribe footers from job portals.
   - Cold recruiter / staffing outreach that pastes a Job Description.
   - Role dump with Location / Duration / Mode of Interview / Preferred Skills.
   - "Should you be interested, please send your resume".

6) available
   - Personalized outreach about a specific role for THIS candidate, still in screening —
     not yet an interview on the calendar.
   - Recruiter asks screening / experience questions ("thanks for your interest in the
     X role", "before scheduling a recruiter interview, reply with answers").
   - When it is a cold JD blast / job-portal sourcing → alert, not available.

7) others
   - Non-recruiting mail.

Critical rules:
- Word "interview" inside a Job Description ≠ label interview.
- "Before scheduling an interview, answer these questions" ≠ interview → available.
- "Thanks for applying / we received your application / we may schedule later" → applied.
- "Will not be able to move forward with your application" / application-limit cap → rejected.
- Cold JD + location/duration/"mode of interview" → alert.
- Prefer alert over interview / available whenever the email is pitching a role to apply.
- Respond JSON only: {"label":"<one label>","confidence":0.0-1.0}
"""


def normalize_label(raw: str) -> str:
    label = raw.lower().strip()
    label = LEGACY_LABEL_MAP.get(label, label)
    if label not in VALID_LABELS:
        return EmailLabel.OTHERS.value
    return label


def _parse_label(content: str) -> tuple[str, float | None]:
    content = content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return EmailLabel.OTHERS.value, None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return EmailLabel.OTHERS.value, None

    label = normalize_label(str(data.get("label", EmailLabel.OTHERS.value)))
    confidence = data.get("confidence")
    try:
        confidence_f = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_f = None
    return label, confidence_f


def _combined_text(subject: str, sender: str, body_text: str, snippet: str) -> str:
    return f"{subject}\n{sender}\n{snippet}\n{body_text}".lower()


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
        r"\bthank you for (taking the time to )?apply\b",
        r"\bthanks for (taking the time to )?apply\b",
        r"\bwe have received (your application|several applications)\b",
        r"\breceived your application\b",
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
        r"\bphone\s+screen\s+(with|on|tomorrow|today|at)\b",
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
    ]
    return any(re.search(p, text) for p in patterns)


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
    return has_mode or has_structure or (has_jd and (has_ask or has_sourcing))


def _heuristic_label(subject: str, sender: str, body_text: str, snippet: str) -> str | None:
    text = _combined_text(subject, sender, body_text, snippet)

    if _is_true_rejection(text):
        return EmailLabel.REJECTED.value
    if _is_application_received(text):
        return EmailLabel.APPLIED.value
    if _looks_like_cold_jd_blast(text):
        return EmailLabel.ALERT.value

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
        return EmailLabel.ALERT.value

    if _is_true_assessment(text):
        return EmailLabel.ASSESSMENT.value
    if _is_pre_interview_screen(text):
        return EmailLabel.AVAILABLE.value
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
    if heuristic == EmailLabel.ALERT.value:
        return EmailLabel.ALERT.value
    if heuristic == EmailLabel.INTERVIEW.value:
        return EmailLabel.INTERVIEW.value
    if _is_pre_interview_screen(text) and label == EmailLabel.INTERVIEW.value:
        return EmailLabel.AVAILABLE.value
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

    # Historical bulk Sync may skip the model; still use heuristics, not "others".
    if not force_openai and not use_openai:
        return ClassificationResult(
            label=(heuristic or EmailLabel.OTHERS.value),  # type: ignore[arg-type]
            confidence=0.55 if heuristic else 0.35,
            response_id=None,
        )
    if not settings.openai_api_key:
        return ClassificationResult(
            label=(heuristic or EmailLabel.OTHERS.value),  # type: ignore[arg-type]
            confidence=0.45 if heuristic else None,
            response_id=None,
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_content = (
        f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}\n\nBody:\n{body_text[:6000]}"
    )
    response = await client.chat.completions.create(
        model=settings.openai_model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
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
