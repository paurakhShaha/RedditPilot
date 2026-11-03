"""Test configuration.

All tests use a throwaway SQLite database, a test encryption key, no real
Gemini calls and no real Reddit calls. The background scheduler is disabled.
"""

from __future__ import annotations

import os
import tempfile
from datetime import timedelta
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="redditpilot-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_DIR / 'test.db').as_posix()}"
os.environ["DISABLE_SCHEDULER"] = "1"
from cryptography.fernet import Fernet  # noqa: E402

os.environ["APP_SECRET_KEY"] = Fernet.generate_key().decode()
# config.py calls load_dotenv(), which does not override existing variables.
# An empty value keeps a developer's real .env key out of the test process.
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine, utcnow  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Draft, DraftRevision, Project, Subreddit, SubredditRule, UserSettings  # noqa: E402
from app.services.serialize import content_hash  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def settings_row(db):
    row = UserSettings(id=1, gemini_api_key_enc=None, gemini_model="gemini-2.5-flash")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def project(db):
    row = Project(
        name="Time Traveler Receipt",
        website_url="https://timetravelerreceipt.app/",
        description="An interactive site where people guess historical grocery prices.",
        target_audience="History enthusiasts and curious web users",
        product_category="Interactive web app",
        unique_selling_proposition="Compare your guesses with real historical prices",
        features="Price guessing game, historical data, sharing",
        pricing_info="Free",
        brand_voice="Curious, honest, plain-spoken",
        marketing_objectives="Find early users who enjoy history",
        disclosure_statement="I built Time Traveler Receipt, the site mentioned in this post.",
        restricted_claims="No financial advice",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def subreddit(db, project):
    row = Subreddit(
        project_id=project.id,
        name="webdev",
        description="A community for web developers",
        self_promotion_policy="allowed_with_disclosure",
        links_policy="restricted",
        allowed_post_types=["Text post", "Discussion", "Question", "Feedback request", "Tutorial", "Project showcase"],
        approval_status="suitable",
        last_rules_verified_at=utcnow(),
        notes="Showcase posts only on Saturdays.",
    )
    row.rules.append(SubredditRule(title="Show off Saturday", detail="Showcase posts only on Saturday", position=0))
    row.rules.append(SubredditRule(title="Be kind", detail="No harassment", position=1))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


SAFE_BODY = (
    "Last month I rebuilt the way a small history project handles guessed grocery prices. "
    "The first version compared formatted strings, which broke on currency symbols and "
    "regional number formats. I moved to integer cents, added a narrow parser, and wrote "
    "tests for prices from the 1970s through today. The hard part was not the parser. It was "
    "deciding how much precision to show when the historical source is itself an estimate. "
    "I now show a range and label the source. If you have worked with messy historical data, "
    "I would like to hear how you communicate uncertainty without making the interface noisy."
)


def make_draft(
    db,
    project,
    subreddit,
    *,
    title="How I handled uncertain historical price data",
    body=SAFE_BODY,
    disclosure="Disclosure: I built Time Traveler Receipt, the site mentioned here.",
    link_url=None,
    status="Pending Review",
    objective="Share a development story",
    post_type="Text post",
    promotional_intensity=1,
    relevance="A concrete data-modeling story relevant to web developers.",
) -> Draft:
    draft = Draft(
        project_id=project.id,
        subreddit_id=subreddit.id,
        title=title,
        body=body,
        disclosure=disclosure,
        link_url=link_url,
        objective=objective,
        post_type=post_type,
        topic="Historical price data",
        status=status,
        promotional_intensity=promotional_intensity,
        relevance=relevance,
        model="gemini-2.5-flash",
        version=1,
    )
    draft.content_hash = content_hash(title, body, disclosure, link_url)
    draft.project = project
    draft.subreddit = subreddit
    db.add(draft)
    db.flush()
    db.add(
        DraftRevision(
            draft_id=draft.id,
            version=1,
            title=draft.title,
            body=draft.body,
            disclosure=draft.disclosure,
            link_url=draft.link_url,
            change_note="Initial draft",
            content_hash=draft.content_hash,
        )
    )
    db.commit()
    db.refresh(draft)
    return draft


def approve_direct(db, draft, note="Reviewed in test"):
    from app.models import Approval

    draft.status = "Approved"
    draft.approved_at = utcnow()
    db.add(
        Approval(
            draft_id=draft.id,
            content_hash=draft.content_hash,
            is_valid=True,
            approved_at=utcnow(),
            note=note,
        )
    )
    if draft.scheduled_slot:
        draft.scheduled_slot.status = "approved"
    db.commit()
    db.refresh(draft)
    return draft
