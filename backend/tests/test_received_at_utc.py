from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.email.gmail import normalize_gmail_message
from app.timeutil import UtcDateTime, as_utc


class Base(DeclarativeBase):
    pass


class Sample(Base):
    __tablename__ = "sample_times"
    id = Column(Integer, primary_key=True)
    received_at = Column(UtcDateTime())


def test_as_utc_converts_offset():
    edt = parsedate_to_datetime("Mon, 21 Sep 2026 09:15:05 -0400")
    utc = as_utc(edt)
    assert utc == datetime(2026, 9, 21, 13, 15, 5, tzinfo=timezone.utc)


def test_sqlite_stores_utc_wall_clock_not_local():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    edt = datetime(2026, 9, 21, 9, 15, 5, tzinfo=timezone(timedelta(hours=-4)))
    db.add(Sample(received_at=edt))
    db.commit()

    raw = db.execute(__import__("sqlalchemy").text("SELECT received_at FROM sample_times")).scalar()
    assert raw.startswith("2026-09-21 13:15:05")

    back = db.query(Sample).one().received_at
    assert back == datetime(2026, 9, 21, 13, 15, 5, tzinfo=timezone.utc)
    db.close()


def test_gmail_prefers_internal_date_utc():
    # Date header is Eastern; internalDate is the UTC instant Gmail shows.
    edt = parsedate_to_datetime("Mon, 21 Sep 2026 09:15:05 -0400")
    ms = int(edt.timestamp() * 1000)
    raw = {
        "id": "msg1",
        "threadId": "t1",
        "snippet": "hi",
        "internalDate": str(ms),
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Hello"},
                {"name": "From", "value": "a@b.com"},
                {"name": "Date", "value": "Mon, 21 Sep 2026 09:15:05 -0400"},
            ],
            "body": {"data": ""},
        },
        "labelIds": ["INBOX"],
    }
    norm = normalize_gmail_message(raw)
    assert norm["received_at"] == datetime(2026, 9, 21, 13, 15, 5, tzinfo=timezone.utc)
