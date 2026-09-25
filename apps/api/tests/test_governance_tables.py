"""Offline governance tests: normalized RBAC, prompt/rule versioning, pagination."""

from datetime import date
from types import SimpleNamespace as NS

from app.api.pagination import LEGACY_CAP, apply_db_pagination, clamp_limit, clamp_offset
from app.db.base import Base
from app.models.business import CalculationRule, PromptVersion, Role, UserRole
from app.services import access as access_module
from app.services.access import resolve_user_roles, set_user_roles
from app.services.answering import prompts as prompts_module
from app.services.calculator import engine as calc_engine


class FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)
        self.offset_n: int | None = None
        self.limit_n: int | None = None

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, n):
        self.offset_n = int(n)
        return self

    def limit(self, n):
        self.limit_n = int(n)
        return self

    def all(self):
        rows = self._rows[self.offset_n or 0 :]
        if self.limit_n is not None:
            rows = rows[: self.limit_n]
        return rows

    def first(self):
        rows = self.all()
        return rows[0] if rows else None

    def count(self):
        return len(self._rows)


class FakeSession:
    def __init__(self, role_rows=None, user_role_rows=None, extra=None, profile=None):
        self.role_rows = role_rows or []
        self.user_role_rows = list(user_role_rows or [])
        self.extra = extra
        self.profile = profile
        self.added: list = []
        self.deleted: list = []
        self.last_query: FakeQuery | None = None

    def query(self, *models):
        from app.models.business import AuditLog

        first = models[0] if models else None
        if first is Role:
            q = FakeQuery(self.role_rows)
        elif first is UserRole:
            q = FakeQuery(self.user_role_rows)
        elif first is AuditLog:
            q = FakeQuery(self.extra or [])
        else:
            q = FakeQuery(self.extra if isinstance(self.extra, list) else [])
        self.last_query = q
        return q

    def get(self, model, key):
        if model is Role:
            return next((r for r in self.role_rows if r.name == key), None)
        if self.profile is not None and model is not None and key == getattr(
            self.profile, "user_id", None
        ):
            return self.profile
        if isinstance(self.extra, dict):
            return self.extra.get(key)
        return None

    def add(self, row):
        self.added.append(row)
        if isinstance(row, UserRole):
            self.user_role_rows.append(row)

    def delete(self, row):
        self.deleted.append(row)
        if row in self.user_role_rows:
            self.user_role_rows.remove(row)


def _profile(uid="u1", roles=None):
    return NS(user_id=uid, roles=list(roles or ["user"]))


# --- models & migration chain ---


def test_governance_tables_registered():
    tables = Base.metadata.tables
    for name in ("roles", "user_roles", "prompt_versions", "calculation_rules"):
        assert name in tables


def test_single_active_prompt_guard():
    table = Base.metadata.tables["prompt_versions"]
    indexes = {index.name for index in table.indexes}
    assert "uq_prompt_versions_single_active" in indexes


# --- RBAC ---


def test_resolve_roles_prefers_db_rows():
    session = FakeSession(
        user_role_rows=[NS(role_name="user"), NS(role_name="admin")],
        profile=_profile(roles=["user"]),
    )
    assert resolve_user_roles(session, session.profile) == ["admin", "user"]


def test_resolve_roles_falls_back_to_jsonb():
    session = FakeSession(user_role_rows=[], profile=_profile(roles=["legal_reviewer"]))
    assert resolve_user_roles(session, session.profile) == ["legal_reviewer"]


def test_resolve_roles_no_profile():
    assert resolve_user_roles(FakeSession(), None) == ["user"]


def test_set_user_roles_writes_both_stores():
    profile = _profile(roles=["user"])
    session = FakeSession(
        role_rows=[NS(name="user"), NS(name="admin")],
        user_role_rows=[NS(user_id="u1", role_name="user")],
        profile=profile,
    )
    result = set_user_roles(session, "u1", ["admin", "user"])
    assert result == ["admin", "user"]
    assert profile.roles == ["admin", "user"]
    assert {r.role_name for r in session.user_role_rows} == {"admin", "user"}


def test_set_user_roles_removes_revoked():
    profile = _profile(roles=["admin", "user"])
    stale = NS(user_id="u1", role_name="admin")
    session = FakeSession(
        role_rows=[NS(name="user")],
        user_role_rows=[stale, NS(user_id="u1", role_name="user")],
        profile=profile,
    )
    set_user_roles(session, "u1", ["user"])
    assert stale in session.deleted
    assert profile.roles == ["user"]


# --- prompt versions ---


def test_prompt_default_without_db():
    prompts_module.reset_active_prompt_cache()
    template = prompts_module.default_prompt_template()
    assert template.prompt_version_id == prompts_module.PROMPT_VERSION_ID


def test_prompt_cache_override_and_reset():
    prompts_module.reset_active_prompt_cache()
    try:
        session = FakeSession(
            extra=[
                NS(
                    version_id="v99",
                    system_prompt="sys",
                    user_template="usr",
                )
            ]
        )
        # FakeSession.query returns `extra` for unknown models.
        version = prompts_module.refresh_active_prompt_cache(session)
        assert version == "v99"
        assert prompts_module.default_prompt_template().prompt_version_id == "v99"
    finally:
        prompts_module.reset_active_prompt_cache()
    assert (
        prompts_module.default_prompt_template().prompt_version_id
        == prompts_module.PROMPT_VERSION_ID
    )


def test_prompt_refresh_empty_keeps_default():
    prompts_module.reset_active_prompt_cache()
    assert prompts_module.refresh_active_prompt_cache(FakeSession()) is None


# --- calculator rules ---


def test_calculator_code_fallback_without_session():
    rule = calc_engine.get_rule("thr")
    assert rule.version == "pp-36-2021-v1"


def test_calculator_db_override():
    session = FakeSession(
        extra=[
            NS(
                rule_type="thr",
                version="test-v9",
                legal_source="Test Source",
                effective_from=date(2024, 1, 1),
                effective_until=None,
                formula_identifier="thr_proportional_months_over_12",
                status="active",
            )
        ]
    )
    rule = calc_engine.get_rule("thr", session)
    assert rule.version == "test-v9"
    assert rule.legal_source == "Test Source"


def test_calculator_still_deterministic_with_session():
    from app.services.calculator import CalculationInput, calculate

    session = FakeSession(extra=[])
    first = calculate(CalculationInput("thr", 6_000_000, 6), session)
    assert first.amount == 3_000_000


# --- pagination ---


def test_clamp_bounds():
    assert clamp_limit(None) is None
    assert clamp_limit(0) == 1
    assert clamp_limit(10_000) == 500
    assert clamp_offset(-5) == 0


def test_apply_db_pagination_legacy_cap():
    query = FakeQuery(list(range(5)))
    page = apply_db_pagination(query, None, 0)
    assert page.limit_n == LEGACY_CAP
    assert page.all() == list(range(5))


def test_apply_db_pagination_slices():
    query = FakeQuery(list(range(10)))
    page = apply_db_pagination(query, 3, 4)
    assert (page.offset_n, page.limit_n) == (4, 3)
    assert page.all() == [4, 5, 6]


def test_access_module_known_roles():
    assert set(access_module.KNOWN_ROLES) >= {"admin", "legal_reviewer", "user"}


def test_new_models_importable():
    assert CalculationRule.__tablename__ == "calculation_rules"
    assert PromptVersion.__tablename__ == "prompt_versions"
    assert Role.__tablename__ == "roles"
    assert UserRole.__tablename__ == "user_roles"
