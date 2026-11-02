"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import (
    OBJECTIVES,
    POST_TYPES,
    LinksPolicy,
    SelfPromotionPolicy,
    SubredditApproval,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _clean_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    return value


# --------------------------------------------------------------------------- projects


class ProjectBase(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    website_url: str
    description: str = ""
    target_audience: str = ""
    product_category: str = ""
    unique_selling_proposition: str = ""
    features: str = ""
    pricing_info: str = ""
    brand_voice: str = ""
    marketing_objectives: str = ""
    disclosure_statement: str = ""
    restricted_claims: str = ""

    @field_validator("website_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        cleaned = _clean_url(value)
        if not cleaned:
            raise ValueError("Website URL is required")
        return cleaned

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Project name is too short")
        return value


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    website_url: str | None = None
    description: str | None = None
    target_audience: str | None = None
    product_category: str | None = None
    unique_selling_proposition: str | None = None
    features: str | None = None
    pricing_info: str | None = None
    brand_voice: str | None = None
    marketing_objectives: str | None = None
    disclosure_statement: str | None = None
    restricted_claims: str | None = None
    is_archived: bool | None = None

    @field_validator("website_url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        return _clean_url(value)


class ProjectOut(ProjectBase, ORMModel):
    id: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    draft_count: int = 0
    published_count: int = 0
    subreddit_count: int = 0


# ------------------------------------------------------------------------- subreddits


class SubredditRuleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str = ""
    position: int = 0


class SubredditRuleOut(SubredditRuleIn, ORMModel):
    id: int


class SubredditBase(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = ""
    self_promotion_policy: SelfPromotionPolicy = SelfPromotionPolicy.UNKNOWN
    links_policy: LinksPolicy = LinksPolicy.UNKNOWN
    allowed_post_types: list[str] = Field(default_factory=list)
    min_account_age_days: int | None = Field(default=None, ge=0, le=36500)
    min_karma: int | None = Field(default=None, ge=0, le=10_000_000)
    last_rules_verified_at: datetime | None = None
    notes: str = ""
    approval_status: SubredditApproval = SubredditApproval.REVIEW
    rules: list[SubredditRuleIn] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        for prefix in ("https://reddit.com/", "https://www.reddit.com/"):
            if value.lower().startswith(prefix):
                value = value[len(prefix):]
        value = value.strip("/")
        if value.lower().startswith("r/"):
            value = value[2:]
        value = value.strip()
        if not value or not all(c.isalnum() or c == "_" for c in value):
            raise ValueError("Use a subreddit name such as 'webdev' (letters, numbers, underscore)")
        if len(value) > 100:
            raise ValueError("Subreddit name is too long")
        return value

    @field_validator("allowed_post_types")
    @classmethod
    def valid_post_types(cls, value: list[str]) -> list[str]:
        cleaned = []
        for item in value:
            if item not in POST_TYPES:
                raise ValueError(f"Unknown post type: {item}")
            if item not in cleaned:
                cleaned.append(item)
        return cleaned


class SubredditCreate(SubredditBase):
    project_id: int


class SubredditUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = None
    self_promotion_policy: SelfPromotionPolicy | None = None
    links_policy: LinksPolicy | None = None
    allowed_post_types: list[str] | None = None
    min_account_age_days: int | None = Field(default=None, ge=0, le=36500)
    min_karma: int | None = Field(default=None, ge=0, le=10_000_000)
    last_rules_verified_at: datetime | None = None
    notes: str | None = None
    approval_status: SubredditApproval | None = None
    rules: list[SubredditRuleIn] | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return SubredditBase.normalize_name(value)


class SubredditOut(SubredditBase, ORMModel):
    id: int
    project_id: int
    project_name: str = ""
    rules_text: str = ""
    rules_verified_age_days: int | None = None
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------------------- drafts


class DraftGenerateRequest(BaseModel):
    project_id: int
    subreddit_id: int
    objective: str
    topic: str = Field(min_length=3, max_length=1000)
    post_type: str = "Text post"
    link_preference: Literal["none", "optional", "preferred"] = "none"
    additional_notes: str = Field(default="", max_length=2000)

    @field_validator("objective")
    @classmethod
    def known_objective(cls, value: str) -> str:
        if value not in OBJECTIVES:
            raise ValueError("Unknown post objective")
        return value

    @field_validator("post_type")
    @classmethod
    def known_post_type(cls, value: str) -> str:
        if value not in POST_TYPES:
            raise ValueError("Unknown post type")
        return value


class DraftUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    body: str | None = Field(default=None, min_length=10)
    disclosure: str | None = None
    link_url: str | None = None
    change_note: str = Field(default="", max_length=300)

    @field_validator("link_url")
    @classmethod
    def valid_link(cls, value: str | None) -> str | None:
        return _clean_url(value)


class ApprovalRequest(BaseModel):
    note: str = Field(default="", max_length=500)
    attested: bool = False

    @model_validator(mode="after")
    def must_attest(self) -> "ApprovalRequest":
        if not self.attested:
            raise ValueError("You must confirm that you reviewed this draft against the community rules")
        return self


class RejectRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


class DuplicateRequest(BaseModel):
    subreddit_id: int
    topic: str | None = Field(default=None, max_length=1000)
    additional_notes: str = Field(default="", max_length=1000)


class ApiPublishRequest(BaseModel):
    confirmation: bool
    note: str = ""

    @model_validator(mode="after")
    def must_confirm(self) -> "ApiPublishRequest":
        if not self.confirmation:
            raise ValueError("Final confirmation is required before API submission")
        return self


class ManualPublishConfirm(BaseModel):
    url: str = Field(min_length=10, max_length=1000)
    note: str = ""
    published_at: datetime | None = None

    @field_validator("url")
    @classmethod
    def reddit_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("https://www.reddit.com/r/", "https://reddit.com/r/")):
            raise ValueError("Enter the full Reddit post URL (https://www.reddit.com/r/...)")
        return value


# ------------------------------------------------------------------------- scheduling


class SchedulePlanIn(BaseModel):
    subreddit_id: int
    objective: str = "Share a development story"
    post_type: str = "Text post"
    topic_hint: str = Field(default="", max_length=1000)
    enabled: bool = True

    @field_validator("objective")
    @classmethod
    def known_objective(cls, value: str) -> str:
        if value not in OBJECTIVES:
            raise ValueError("Unknown post objective")
        return value

    @field_validator("post_type")
    @classmethod
    def known_post_type(cls, value: str) -> str:
        if value not in POST_TYPES:
            raise ValueError("Unknown post type")
        return value


class PauseRequest(BaseModel):
    paused: bool


# -------------------------------------------------------------------------- settings


class RedditCredentialsIn(BaseModel):
    client_id: str = Field(default="", max_length=200)
    client_secret: str = Field(default="", max_length=500)
    username: str = Field(default="", max_length=120)
    password: str = Field(default="", max_length=500)
    refresh_token: str = Field(default="", max_length=1000)
    user_agent: str = Field(default="", max_length=300)


class SettingsUpdate(BaseModel):
    default_project_id: int | None = None
    gemini_model: str | None = Field(default=None, max_length=120)
    gemini_api_key: str | None = Field(default=None, max_length=500)
    clear_gemini_key: bool = False

    weekly_frequency: int | None = Field(default=None, ge=1, le=3)
    publishing_day: int | None = Field(default=None, ge=0, le=6)
    publishing_time: str | None = None
    timezone: str | None = Field(default=None, max_length=64)
    scheduling_paused: bool | None = None

    publishing_mode: Literal["manual", "api"] | None = None
    api_publishing_enabled: bool | None = None
    api_enable_acknowledged: bool = False

    generation_temperature: float | None = Field(default=None, ge=0.0, le=1.5)
    max_promo_score: int | None = Field(default=None, ge=1, le=5)
    avoid_emojis: bool | None = None
    default_include_link: bool | None = None
    extra_generation_notes: str | None = Field(default=None, max_length=3000)
    reddit: RedditCredentialsIn | None = None
    clear_reddit_credentials: bool = False

    @field_validator("publishing_time")
    @classmethod
    def valid_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            hours, minutes = value.split(":")
            if not (0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError("Time must be in HH:MM format")
        return f"{int(hours):02d}:{int(minutes):02d}"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


# -------------------------------------------------------------------------- analytics


class MetricsUpdate(BaseModel):
    upvotes: int | None = Field(default=None, ge=0, le=100_000_000)
    comments: int | None = Field(default=None, ge=0, le=100_000_000)
    views: int | None = Field(default=None, ge=0, le=1_000_000_000)
    website_visits: int | None = Field(default=None, ge=0, le=1_000_000_000)
    referral_visits: int | None = Field(default=None, ge=0, le=1_000_000_000)
    notes: str | None = Field(default=None, max_length=2000)


class ResolvePublishRequest(BaseModel):
    outcome: Literal["published", "not_published"]
    url: str | None = None
    note: str = ""

    @model_validator(mode="after")
    def url_when_published(self) -> "ResolvePublishRequest":
        if self.outcome == "published":
            if not self.url:
                raise ValueError("Enter the Reddit post URL when confirming publication")
            value = self.url.strip()
            if not value.startswith(("https://www.reddit.com/r/", "https://reddit.com/r/")):
                raise ValueError("Enter the full Reddit post URL")
            self.url = value
        return self


class GeneralResponse(BaseModel):
    ok: bool = True
    message: str = ""
    data: dict[str, Any] | None = None
