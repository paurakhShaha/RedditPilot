"""SQLAlchemy models for RedditPilot."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.enums import (
    DraftStatus,
    PublishedStatus,
    ScheduleStatus,
    SubredditApproval,
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class UserSettings(Base, TimestampMixin):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    gemini_model: Mapped[str] = mapped_column(String(120), default="gemini-2.5-flash")
    gemini_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    weekly_frequency: Mapped[int] = mapped_column(Integer, default=1)
    publishing_day: Mapped[int] = mapped_column(Integer, default=0)  # Monday=0
    publishing_time: Mapped[str] = mapped_column(String(5), default="10:00")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kathmandu")
    scheduling_paused: Mapped[bool] = mapped_column(Boolean, default=False)

    publishing_mode: Mapped[str] = mapped_column(String(16), default="manual")
    api_publishing_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    generation_temperature: Mapped[float] = mapped_column(Float, default=0.75)
    max_promo_score: Mapped[int] = mapped_column(Integer, default=3)
    avoid_emojis: Mapped[bool] = mapped_column(Boolean, default=True)
    default_include_link: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_generation_notes: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        CheckConstraint("weekly_frequency BETWEEN 1 AND 3", name="ck_weekly_frequency"),
        CheckConstraint("publishing_day BETWEEN 0 AND 6", name="ck_publishing_day"),
        CheckConstraint("max_promo_score BETWEEN 1 AND 5", name="ck_max_promo_score"),
        CheckConstraint(
            "publishing_mode IN ('manual','api')", name="ck_publishing_mode"
        ),
    )

    default_project: Mapped["Project | None"] = relationship(
        foreign_keys=[default_project_id]
    )


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    website_url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    product_category: Mapped[str] = mapped_column(String(160), default="")
    unique_selling_proposition: Mapped[str] = mapped_column(Text, default="")
    features: Mapped[str] = mapped_column(Text, default="")
    pricing_info: Mapped[str] = mapped_column(Text, default="")
    brand_voice: Mapped[str] = mapped_column(Text, default="")
    marketing_objectives: Mapped[str] = mapped_column(Text, default="")
    disclosure_statement: Mapped[str] = mapped_column(Text, default="")
    restricted_claims: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    subreddits: Mapped[list["Subreddit"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    drafts: Mapped[list["Draft"]] = relationship(back_populates="project")
    schedule_plan: Mapped["SchedulePlan | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )


class Subreddit(Base, TimestampMixin):
    __tablename__ = "subreddits"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_subreddit_project_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    self_promotion_policy: Mapped[str] = mapped_column(
        String(40), default="unknown", nullable=False
    )
    links_policy: Mapped[str] = mapped_column(String(30), default="unknown")
    allowed_post_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    min_account_age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_karma: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_rules_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    approval_status: Mapped[str] = mapped_column(
        String(30), default=SubredditApproval.REVIEW.value, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="subreddits")
    rules: Mapped[list["SubredditRule"]] = relationship(
        back_populates="subreddit",
        cascade="all, delete-orphan",
        order_by="SubredditRule.position",
    )
    drafts: Mapped[list["Draft"]] = relationship(back_populates="subreddit")


class SubredditRule(Base):
    __tablename__ = "subreddit_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subreddit_id: Mapped[int] = mapped_column(
        ForeignKey("subreddits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    subreddit: Mapped["Subreddit"] = relationship(back_populates="rules")


class SchedulePlan(Base, TimestampMixin):
    __tablename__ = "schedule_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    subreddit_id: Mapped[int] = mapped_column(
        ForeignKey("subreddits.id", ondelete="CASCADE"), nullable=False
    )
    objective: Mapped[str] = mapped_column(String(120), default="Share a development story")
    post_type: Mapped[str] = mapped_column(String(60), default="Text post")
    topic_hint: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    project: Mapped["Project"] = relationship(back_populates="schedule_plan")
    subreddit: Mapped["Subreddit"] = relationship()


class Draft(Base, TimestampMixin):
    __tablename__ = "drafts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Pending Review','Approved','Rejected','Scheduled','Published','Failed','Archived')",
            name="ck_draft_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    subreddit_id: Mapped[int] = mapped_column(
        ForeignKey("subreddits.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    disclosure: Mapped[str] = mapped_column(Text, default="")
    link_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    objective: Mapped[str] = mapped_column(String(120), default="")
    post_type: Mapped[str] = mapped_column(String(60), default="Text post")
    topic: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(
        String(30), default=DraftStatus.PENDING_REVIEW.value, nullable=False, index=True
    )
    promotional_intensity: Mapped[int] = mapped_column(Integer, default=0)
    relevance: Mapped[str] = mapped_column(Text, default="")
    rule_violations: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    compliance_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(String(120), default="")
    source: Mapped[str] = mapped_column(String(40), default="studio")
    parent_draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("drafts.id", ondelete="SET NULL"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")

    project: Mapped["Project"] = relationship(back_populates="drafts")
    subreddit: Mapped["Subreddit"] = relationship(back_populates="drafts")
    revisions: Mapped[list["DraftRevision"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="DraftRevision.version.desc()",
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="Approval.approved_at.desc()",
    )
    published_post: Mapped["PublishedPost | None"] = relationship(
        back_populates="draft", uselist=False, cascade="all, delete-orphan"
    )
    scheduled_slot: Mapped["ScheduledPost | None"] = relationship(
        back_populates="draft", uselist=False, foreign_keys="ScheduledPost.draft_id"
    )
    parent_draft: Mapped["Draft | None"] = relationship(remote_side=[id])

    @property
    def current_approval(self) -> "Approval | None":
        for approval in self.approvals:
            if approval.is_valid and approval.invalidated_at is None:
                return approval
        return None

    @property
    def is_approved(self) -> bool:
        approval = self.current_approval
        return (
            self.status in (DraftStatus.APPROVED.value, DraftStatus.SCHEDULED.value)
            and approval is not None
            and approval.content_hash == self.content_hash
        )


class DraftRevision(Base):
    __tablename__ = "draft_revisions"
    __table_args__ = (
        UniqueConstraint("draft_id", "version", name="uq_revision_draft_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    disclosure: Mapped[str] = mapped_column(Text, default="")
    link_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    change_note: Mapped[str] = mapped_column(String(300), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    draft: Mapped["Draft"] = relationship(back_populates="revisions")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(120), default="local-user")
    note: Mapped[str] = mapped_column(Text, default="")
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    invalidation_reason: Mapped[str] = mapped_column(String(300), default="")

    draft: Mapped["Draft"] = relationship(back_populates="approvals")


class ScheduledPost(Base, TimestampMixin):
    __tablename__ = "scheduled_posts"
    __table_args__ = (
        UniqueConstraint("project_id", "slot_start", name="uq_schedule_project_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subreddit_id: Mapped[int] = mapped_column(
        ForeignKey("subreddits.id", ondelete="CASCADE"), nullable=False
    )
    slot_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), default=ScheduleStatus.PLANNED.value, nullable=False, index=True
    )
    objective: Mapped[str] = mapped_column(String(120), default="")
    post_type: Mapped[str] = mapped_column(String(60), default="Text post")
    topic_hint: Mapped[str] = mapped_column(Text, default="")
    draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("drafts.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    error: Mapped[str] = mapped_column(Text, default="")

    project: Mapped["Project"] = relationship()
    subreddit: Mapped["Subreddit"] = relationship()
    draft: Mapped["Draft | None"] = relationship(
        back_populates="scheduled_slot", foreign_keys=[draft_id]
    )


class PublishedPost(Base, TimestampMixin):
    __tablename__ = "published_posts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('published','uncertain')", name="ck_published_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    subreddit_id: Mapped[int] = mapped_column(
        ForeignKey("subreddits.id", ondelete="RESTRICT"), nullable=False
    )
    reddit_post_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    subreddit_name: Mapped[str] = mapped_column(String(100), default="")
    published_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="manual")
    status: Mapped[str] = mapped_column(
        String(20), default=PublishedStatus.PUBLISHED.value, nullable=False
    )
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    website_visits: Mapped[int] = mapped_column(Integer, default=0)
    referral_visits: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    metrics_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    draft: Mapped["Draft"] = relationship(back_populates="published_post")
    project: Mapped["Project"] = relationship()
    subreddit: Mapped["Subreddit"] = relationship()
    metric_history: Mapped[list["AnalyticsRecord"]] = relationship(
        back_populates="published_post",
        cascade="all, delete-orphan",
        order_by="AnalyticsRecord.recorded_at.desc()",
    )


class AnalyticsRecord(Base):
    __tablename__ = "analytics_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    published_post_id: Mapped[int] = mapped_column(
        ForeignKey("published_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    website_visits: Mapped[int] = mapped_column(Integer, default=0)
    referral_visits: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(300), default="")

    published_post: Mapped["PublishedPost"] = relationship(back_populates="metric_history")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), default="local-user")
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(20), default="info")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class APIConnection(Base, TimestampMixin):
    __tablename__ = "api_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), default="reddit", unique=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    client_id_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    username_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="disconnected")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
