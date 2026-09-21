from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)

# Well-known + common typo domains for major providers. Blocking these prevents
# sign-ups with obvious misspellings such as "gmial.co" when "gmail.com" was meant.
_TYPO_DOMAINS: set[str] = {
    # gmail
    "gmial.com", "gmial.co", "gmial.id", "gamil.com", "gamil.co", "gmail.co",
    "gmail.ocm", "gmail.cmo", "gmailcom.com", "gmaill.com", "gmai.com",
    "gmaill.co", "gmale.com", "gmali.com", "gmiall.com", "gmail.con",
    "gmail.c.om", "gmaill.net", "gmaill.org", "gmail1.com",
    "gmiall.co", "gmails.com", "gmailss.com", "gmil.com", "gmeil.com",
    "geemail.com", "gmial.net", "gamil.net", "gmailcon",
    "gmiall.com.co",
    # yahoo
    "ahoo.com", "yhhhoo.com", "yahho.com", "yahooo.com", "yahoo.cm",
    "yahoo.co", "yhooo.com", "yahoo.con", "yahhoo.com", "yahuu.com",
    "yaho.com", "yhoo.com",
    # hotmail / outlook
    "hotmal.com", "hotmil.com", "hotmial.com", "hotmail.cm", "hotmail.co",
    "hotmaill.com", "hotmail.con", "hotmial.co", "oeutlook.com",
    "outlok.com", "outloo.com", "outloook.com", "outllook.com", "outllok.com",
    "outlokk.com", "outook.com", "outllook.co", "outlook.co", "outlok.co",
    # proton / icloud / others
    "protonmal.com", "protonmial.com", "pmail.com", "iclod.com", "icloud.co",
    "iclod.co", "icloud.cm", "icloud.com.co", "icloudd.com", "icloudid.com",
}

# Known providers mapped to their acceptable domains. If the first label of a
# domain matches a known provider but the full domain is not in its accepted set,
# the address is treated as a misspelling (e.g. "gmail.cop", "gmail.con").
_KNOWN_PROVIDER_DOMAINS: dict[str, set[str]] = {
    "gmail": {"gmail.com"},
    "yahoo": {"yahoo.com", "yahoo.co.id", "yahoo.co.uk", "yahoo.ca", "yahoo.co.in"},
    "outlook": {"outlook.com", "outlook.com.br"},
    "hotmail": {"hotmail.com", "hotmail.de", "hotmail.co.uk", "hotmail.fr"},
    "icloud": {"icloud.com"},
    "me": {"me.com"},
    "mac": {"mac.com"},
    "protonmail": {"protonmail.com"},
    "proton": {"proton.me"},
    "pm": {"pm.me"},
}

_COMMON_PASSWORDS: set[str] = {
    "password",
    "password1",
    "password123",
    "12345678",
    "123456789",
    "1234567890",
    "qwertyuiop",
    "qwerty123",
    "qwerty",
    "abc12345",
    "abc123",
    "letmein",
    "iloveyou",
    "welcome123",
    "admin123",
    "admin1234",
    "kerjapedia",
    "kerjapedia123",
    "11111111",
    "22222222",
    "00000000",
    "football",
    "dragon",
    "monkey",
    "master",
    "superman",
    "baobab",
    "p@ssw0rd",
    "trustno1",
}


def _validate_email(value: str) -> str:
    if not _EMAIL_PATTERN.match(value):
        raise ValueError("Invalid email format.")
    domain = value.rsplit("@", 1)[1].lower()
    if domain in _TYPO_DOMAINS:
        raise ValueError("Email domain is a common misspelling.")
    base = domain.split(".")[0]
    accepted = _KNOWN_PROVIDER_DOMAINS.get(base)
    if accepted is not None and domain not in accepted:
        raise ValueError("Email domain is a common misspelling.")
    return value


class HealthResponse(ApiModel):
    status: str
    service: str


class LoginRequest(ApiModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class RegisterRequest(ApiModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)

    @model_validator(mode="after")
    def validate_password_strength(self) -> RegisterRequest:
        password = self.password
        local = self.email.split("@")[0].lower() if "@" in self.email else ""
        if password.lower() in _COMMON_PASSWORDS:
            raise ValueError("Password too common.")
        if len(set(password)) == 1:
            raise ValueError("Password uses a repeated character.")
        if len(local) >= 3 and local in password.lower():
            raise ValueError("Password must not include the email.")
        classes = sum(
            [
                bool(re.search(r"[a-z]", password)),
                bool(re.search(r"[A-Z]", password)),
                bool(re.search(r"[0-9]", password)),
                bool(re.search(r"[^a-zA-Z0-9]", password)),
            ]
        )
        if len(password) >= 4 and classes < 3:
            raise ValueError("Password is too weak.")
        return self


class ProfileUpdateRequest(ApiModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)


class EmailOtpVerifyRequest(ApiModel):
    email: str = Field(min_length=3, max_length=160)
    token: str = Field(min_length=4, max_length=64)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class EmailResendRequest(ApiModel):
    email: str = Field(min_length=3, max_length=160)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class UserResponse(ApiModel):
    user_id: str
    email: str
    name: str
    roles: list[str]


class LoginMethodsResponse(ApiModel):
    email_exists: bool
    has_password: bool
    providers: list[str]


class LoginResponse(ApiModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(ApiModel):
    refresh_token: str = Field(min_length=10, max_length=1000)


class GoogleAuthRequest(ApiModel):
    id_token: str = Field(min_length=20, max_length=10000)


class MessageResponse(ApiModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AskRequest(ApiModel):
    question: str = Field(min_length=4, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=80)
    top_k: int = Field(default=5, ge=1, le=8)


class AskResponse(ApiModel):
    conversation_id: str
    answer: dict[str, Any]
    latency_ms: int
    retrieval_score: float | None
    token_usage: dict[str, int]


class ConversationSummary(ApiModel):
    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationDetail(ApiModel):
    conversation_id: str
    title: str
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime


class ConversationUpdateRequest(ApiModel):
    title: str = Field(min_length=1, max_length=80)


class DocumentSummary(ApiModel):
    document_id: str
    title: str
    short_title: str
    regulation_type: str
    number: int
    year: int
    legal_status: str
    topics: list[str]
    source_url: str
    pdf_url: str


class DocumentUpdateRequest(ApiModel):
    legal_status: str | None = Field(default=None, max_length=80)
    topics: list[str] | None = None
    verification_status: str | None = Field(default=None, max_length=80)
    source_url: str | None = Field(default=None, max_length=1000)


class DocumentRelationshipRequest(ApiModel):
    to_document_id: str = Field(min_length=3, max_length=80)
    relationship_type: Literal[
        "amended_by",
        "revoked_by",
        "replaced_by",
        "implements",
        "implemented_by",
        "related_to",
    ]
    confidence: Literal["low", "medium", "high"] = "medium"
    notes: str | None = Field(default=None, max_length=1000)
    from_article: str | None = Field(default=None, max_length=80)
    to_article: str | None = Field(default=None, max_length=80)
    evidence_url: str | None = Field(default=None, max_length=1000)


class DocumentVerificationRequest(ApiModel):
    verification_type: Literal["source", "legal"]
    status: Literal["verified", "rejected", "pending"]
    evidence_url: str | None = Field(default=None, max_length=1000)
    notes: str = Field(default="", max_length=2000)


class IngestionBuildReviewRequest(ApiModel):
    status: Literal["approved", "rejected"]
    page_dispositions: dict[
        str,
        Literal[
            "intentionally_blank",
            "ocr_verified",
            "table_verified",
            "accepted_with_reason",
        ],
    ] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=4000)


class PublicationRequest(ApiModel):
    action: Literal["publish", "unpublish"]


class RetrievalPlaygroundRequest(ApiModel):
    question: str = Field(min_length=4, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)
    regulation_type: str | None = Field(default=None, max_length=40)
    year: int | None = Field(default=None, ge=1945, le=2100)
    legal_status: str | None = Field(default=None, max_length=40)


class IngestionJobRequest(ApiModel):
    document_id: str = Field(min_length=3, max_length=80)
    persist_db: bool = False
    force: bool = False


class FeedbackRequest(ApiModel):
    question: str = Field(min_length=4, max_length=2000)
    answer_id: str | None = Field(default=None, max_length=120)
    conversation_id: str | None = Field(default=None, max_length=80)
    rating: Literal["helpful", "not_helpful"]
    issue_category: (
        Literal[
            "citation_incorrect",
            "answer_incomplete",
            "outdated_regulation",
            "other",
        ]
        | None
    ) = Field(default=None, max_length=80)
    comment: str | None = Field(default=None, max_length=1000)


class EvaluationQuestionInput(ApiModel):
    question_id: str = Field(min_length=5, max_length=120)
    category: str = Field(min_length=2, max_length=80)
    question: str = Field(min_length=4, max_length=2000)
    expected_answer: str = Field(min_length=4, max_length=4000)
    expected_document_ids: list[str]
    expected_articles: list[str]
    expected_topics: list[str]
    should_refuse: bool = False
    hard_negative: bool = False
    verified_by: str = Field(default="unknown", max_length=120)
    status: str = Field(default="needs_human_review", max_length=80)
    split: Literal["development", "test"] = "development"
    scenario_tags: list[
        Literal[
            "follow_up",
            "typo",
            "bilingual",
            "topic_switch",
            "historical",
            "complex",
            "hard_negative",
            "prompt_injection",
        ]
    ] = Field(default_factory=list)


class EvaluationDatasetRequest(ApiModel):
    name: str = Field(min_length=3, max_length=120)
    questions: list[EvaluationQuestionInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_unique_questions(self) -> EvaluationDatasetRequest:
        question_ids = [question.question_id for question in self.questions]
        normalized_texts = [
            " ".join(question.question.lower().split()) for question in self.questions
        ]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("Evaluation question_id values must be unique.")
        if len(set(normalized_texts)) != len(normalized_texts):
            raise ValueError("Evaluation question texts must be unique.")
        return self


class EvaluationQuestionReviewRequest(ApiModel):
    status: Literal["verified", "rejected"]
    notes: str = Field(default="", max_length=2000)


class EvaluationRunRequest(ApiModel):
    dataset_id: str = Field(min_length=3, max_length=120)
    release_id: str | None = Field(default=None, min_length=3, max_length=160)
    top_k: int = Field(default=5, ge=1, le=10)
    experiment_modes: list[Literal["upstash"]] = Field(
        default_factory=lambda: ["upstash"],
        min_length=1,
        max_length=1,
    )
