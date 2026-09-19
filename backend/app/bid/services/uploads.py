from pathlib import Path

from app.bid.settings import get_bid_settings

RESUME_TYPES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
RESUME_EXTENSIONS = {".pdf", ".doc", ".docx"}


def uploads_root() -> Path:
    settings = get_bid_settings()
    if settings.upload_dir:
        root = Path(settings.upload_dir)
    else:
        root = Path(__file__).resolve().parents[3] / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    (root / "resumes").mkdir(parents=True, exist_ok=True)
    return root


def resume_dir(profile_id: int) -> Path:
    path = uploads_root() / "resumes" / str(profile_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def allowed_resume(filename: str, content_type: str | None) -> bool:
    suffix = Path(filename).suffix.lower()
    if suffix in RESUME_EXTENSIONS:
        return True
    return (content_type or "") in RESUME_TYPES
