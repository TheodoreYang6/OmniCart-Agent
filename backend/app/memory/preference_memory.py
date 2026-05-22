"""V1 Preference Memory Card — session-level multi-turn preference memory.

Stores constraint state per session in memory. When USE_POSTGRES=True,
also persists to the user_preferences table for durability.
"""

from app.schemas.workflow import Constraints
from app.core.config import USE_POSTGRES


class PreferenceMemory:
    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def get(self, session_id: str) -> dict:
        if session_id not in self._sessions and USE_POSTGRES:
            try:
                from app.repositories.pg_preference_repo import get_preference_repo
                stored = get_preference_repo().get(session_id)
                if stored:
                    self._sessions[session_id] = stored
            except Exception:
                pass
        return self._sessions.get(session_id, {}).copy()

    def update(self, session_id: str, constraints: Constraints):
        if session_id not in self._sessions:
            self._sessions[session_id] = {}

        stored = self._sessions[session_id]

        if constraints.category:
            stored["category"] = constraints.category
        if constraints.sub_category:
            stored["sub_category"] = constraints.sub_category
        if constraints.budget_max is not None:
            stored["budget_max"] = constraints.budget_max
        if constraints.budget_min is not None:
            stored["budget_min"] = constraints.budget_min
        if constraints.scenario:
            stored["scenario"] = constraints.scenario

        stored_tags = set(stored.get("must_tags", []))
        stored_tags.update(constraints.must_tags)
        stored["must_tags"] = list(stored_tags)

        stored_exclude = set(stored.get("exclude_tags", []))
        stored_exclude.update(constraints.exclude_tags)
        stored["exclude_tags"] = list(stored_exclude)

        if USE_POSTGRES:
            try:
                from app.repositories.pg_preference_repo import get_preference_repo
                get_preference_repo().update(session_id, stored)
            except Exception:
                pass

    def merge_constraints(self, session_id: str, new_constraints: Constraints) -> Constraints:
        stored = self.get(session_id)

        # 话题切换检测：新旧 category 都非空且不同 → 丢弃旧约束
        new_cat = new_constraints.category
        old_cat = stored.get("category")
        if new_cat and old_cat and new_cat != old_cat:
            self.forget(session_id)
            stored = {}
        # 新 query 未检测到品类但旧约束存在 → 从 session 中清除，避免用旧品类误导检索
        if not new_cat and old_cat and session_id in self._sessions:
            self._sessions[session_id].pop("category", None)
            stored.pop("category", None)

        merged = Constraints()
        merged.category = new_constraints.category or stored.get("category")
        merged.sub_category = new_constraints.sub_category or stored.get("sub_category")
        merged.budget_max = new_constraints.budget_max or stored.get("budget_max")
        merged.budget_min = new_constraints.budget_min or stored.get("budget_min")
        merged.scenario = new_constraints.scenario or stored.get("scenario")

        merged.must_tags = list(set(new_constraints.must_tags) | set(stored.get("must_tags", [])))
        merged.exclude_tags = list(set(new_constraints.exclude_tags) | set(stored.get("exclude_tags", [])))

        return merged

    def forget(self, session_id: str):
        self._sessions.pop(session_id, None)
        if USE_POSTGRES:
            try:
                from app.repositories.pg_preference_repo import get_preference_repo
                get_preference_repo().forget(session_id)
            except Exception:
                pass


# Global singleton
_memory = PreferenceMemory()


def get_memory() -> PreferenceMemory:
    return _memory
