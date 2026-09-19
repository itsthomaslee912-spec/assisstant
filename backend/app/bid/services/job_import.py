from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass


@dataclass
class ParsedJob:
    company: str
    title: str
    url: str


_URL_RE = re.compile(r"https?://\S+", re.I)


def parse_job_text(text: str) -> list[ParsedJob]:
    raw = (text or "").strip()
    if not raw:
        return []
    rows: list[ParsedJob] = []
    sample = raw.splitlines()[0] if raw else ""
    if "," in sample or "\t" in sample:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
        reader = csv.reader(io.StringIO(raw), dialect)
        for parts in reader:
            job = _from_parts([p.strip() for p in parts if p is not None])
            if job:
                rows.append(job)
        return _dedupe(rows)
    for line in raw.splitlines():
        job = _from_line(line.strip())
        if job:
            rows.append(job)
    return _dedupe(rows)


def _from_line(line: str) -> ParsedJob | None:
    if not line:
        return None
    lower = line.lower()
    if lower.startswith("company") and "title" in lower and "http" not in lower:
        return None
    if "|" in line:
        parts = [p.strip() for p in line.split("|")]
        return _from_parts(parts)
    if "\t" in line:
        return _from_parts([p.strip() for p in line.split("\t")])
    url_match = _URL_RE.search(line)
    if not url_match:
        return None
    url = url_match.group(0).rstrip(".,;")
    rest = (line[: url_match.start()] + " " + line[url_match.end() :]).strip()
    if "\t" in rest or "," in rest:
        left = [p.strip() for p in re.split(r"[\t,]", rest) if p.strip()]
        return _from_parts([*left, url])
    tokens = rest.split()
    company = tokens[0] if tokens else ""
    title = " ".join(tokens[1:]) if len(tokens) > 1 else ""
    return ParsedJob(company=company, title=title, url=url)


def _from_parts(parts: list[str]) -> ParsedJob | None:
    cleaned = [p.strip().strip('"') for p in parts if p and p.strip()]
    if not cleaned:
        return None
    header = [p.lower() for p in cleaned]
    if header[:3] == ["company", "title", "url"] or (
        len(header) >= 1 and header[0] in {"company", "title", "url"} and "http" not in header[0]
    ):
        if "http" not in " ".join(header):
            return None
    url = ""
    others: list[str] = []
    for item in cleaned:
        if item.lower().startswith("http://") or item.lower().startswith("https://"):
            url = item.rstrip(".,;")
        else:
            others.append(item)
    if not url:
        match = _URL_RE.search(" ".join(cleaned))
        if match:
            url = match.group(0).rstrip(".,;")
    if not url:
        return None
    company = others[0] if others else ""
    title = " ".join(others[1:]) if len(others) > 1 else (others[0] if others else "")
    if len(others) == 1:
        title = others[0]
        # keep company if it looks like a brand token
        company = others[0]
    if len(others) >= 2:
        company, title = others[0], " ".join(others[1:])
    return ParsedJob(company=company, title=title, url=url)


def _dedupe(rows: list[ParsedJob]) -> list[ParsedJob]:
    seen: set[str] = set()
    out: list[ParsedJob] = []
    for row in rows:
        key = row.url.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
