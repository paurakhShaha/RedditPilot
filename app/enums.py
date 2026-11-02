"""Shared status vocabulary.

These values are stored in the database and rendered directly in the UI, so
they use human-readable labels where the specification defines them.
"""

from __future__ import annotations

from enum import StrEnum


class DraftStatus(StrEnum):
    PENDING_REVIEW = "Pending Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    SCHEDULED = "Scheduled"
    PUBLISHED = "Published"
    FAILED = "Failed"
    ARCHIVED = "Archived"


class SubredditApproval(StrEnum):
    SUITABLE = "suitable"
    REVIEW = "review"
    PROHIBITED = "prohibited"
    NOT_RECOMMENDED = "not_recommended"


class SelfPromotionPolicy(StrEnum):
    ALLOWED_WITH_DISCLOSURE = "allowed_with_disclosure"
    RESTRICTED = "restricted"
    PROHIBITED = "prohibited"
    UNKNOWN = "unknown"


class LinksPolicy(StrEnum):
    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    NOT_ALLOWED = "not_allowed"
    UNKNOWN = "unknown"


class ScheduleStatus(StrEnum):
    PLANNED = "planned"
    GENERATING = "generating"
    DRAFT_READY = "draft_ready"
    APPROVED = "approved"
    PUBLISHED = "published"
    SKIPPED = "skipped"
    FAILED = "failed"


class PublishMode(StrEnum):
    MANUAL = "manual"
    API = "api"


class PublishedStatus(StrEnum):
    PUBLISHED = "published"
    UNCERTAIN = "uncertain"


class Severity(StrEnum):
    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


OBJECTIVES = [
    "Introduce a new project",
    "Share a useful resource",
    "Ask for constructive feedback",
    "Share a development story",
    "Discuss an interesting technical challenge",
    "Present a project launch",
    "Share a lesson learned",
]

POST_TYPES = [
    "Text post",
    "Discussion",
    "Question",
    "Project showcase",
    "Tutorial",
    "Feedback request",
]

PROMOTIONAL_OBJECTIVES = {
    "Introduce a new project",
    "Present a project launch",
    "Share a useful resource",
    "Project showcase",
}

WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
