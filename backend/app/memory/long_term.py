"""V2 Long-Term Preference Memory — cross-session user profile learning.

Stores per-user preference profiles in PostgreSQL (or memory for JSON mode).
Tracks search/add_to_cart/checkout behavior to build affinity scores over time.
Session constraints override long-term defaults; decay ensures old preferences fade.

Key concepts:
- UserProfile: aggregated preferences for a user across all sessions
- Behavioral signals: search(weight 1) < add_to_cart(weight 3) < checkout(weight 5)
- Time decay: preferences older than 30 days receive half weight
- Merge: long-term(defaults) + session(override) → final constraints
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.core.config import USE_POSTGRES

logger = logging.getLogger(__name__)

# JSON fallback storage
_JSON_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "long_term_memory"
_JSON_DIR.mkdir(parents=True, exist_ok=True)

# Behavioral signal weights
WEIGHT_SEARCH = 1
WEIGHT_ADD_TO_CART = 3
WEIGHT_CHECKOUT = 5

# Decay half-life (days)
DECAY_HALF_LIFE = 30

# Max tags/categories to track per user
MAX_CATEGORIES = 10
MAX_BRANDS = 10
MAX_TAGS = 20


@dataclass
class UserProfile:
    """Aggregated long-term preference profile for a single user."""
    user_id: str
    preferred_categories: dict[str, float] = field(default_factory=dict)  # category → affinity
    preferred_brands: dict[str, float] = field(default_factory=dict)      # brand → affinity
    budget_min: float | None = None
    budget_max: float | None = None
    common_scenarios: dict[str, float] = field(default_factory=dict)      # scenario → frequency
    liked_tags: dict[str, float] = field(default_factory=dict)            # tag → affinity
    disliked_tags: dict[str, float] = field(default_factory=dict)         # tag → aversion
    total_searches: int = 0
    total_add_to_cart: int = 0
    total_checkouts: int = 0
    last_active: str = ""
    created_at: str = ""
    updated_at: str = ""

    def _normalize(self, d: dict[str, float]) -> dict[str, float]:
        """Scale values to 0-1 range."""
        if not d:
            return {}
        mx = max(d.values())
        return {k: round(v / mx, 3) if mx > 0 else 0 for k, v in d.items()}

    def to_storable(self) -> dict:
        return asdict(self)

    @classmethod
    def from_storable(cls, data: dict) -> UserProfile:
        return cls(**{k: data.get(k, v.default if isinstance(v, field) else v)
                       for k, v in cls.__dataclass_fields__.items()})


class LongTermMemory:
    """Cross-session user preference learning engine.

    Usage:
        ltm = LongTermMemory()
        await ltm.record_search("user_001", "蓝牙耳机", category="数码电子")
        profile = await ltm.get_profile("user_001")
        merged = ltm.merge_with_session(profile, session_constraints)
    """

    def __init__(self):
        self._cache: dict[str, UserProfile] = {}

    # ================================================================
    # Profile CRUD
    # ================================================================

    async def get_profile(self, user_id: str) -> UserProfile:
        """Load user profile from PG / JSON / cache."""
        if user_id in self._cache:
            return self._cache[user_id]

        profile = None
        if USE_POSTGRES:
            profile = await self._load_pg(user_id)
        if profile is None:
            profile = self._load_json(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id, created_at=_now(), updated_at=_now())

        self._cache[user_id] = profile
        return profile

    async def save_profile(self, profile: UserProfile):
        profile.updated_at = _now()
        self._cache[profile.user_id] = profile
        if USE_POSTGRES:
            await self._save_pg(profile)
        else:
            self._save_json(profile)

    # ================================================================
    # Behavioral Recording
    # ================================================================

    async def record_search(self, user_id: str, query: str, category: str = "",
                            sub_category: str = "", tags: list[str] | None = None):
        """Record a search interaction."""
        profile = await self.get_profile(user_id)
        profile.total_searches += 1
        if category:
            profile.preferred_categories[category] = \
                profile.preferred_categories.get(category, 0) + WEIGHT_SEARCH
        if sub_category:
            profile.preferred_categories[sub_category] = \
                profile.preferred_categories.get(sub_category, 0) + WEIGHT_SEARCH * 0.5
        for tag in (tags or []):
            profile.liked_tags[tag] = profile.liked_tags.get(tag, 0) + WEIGHT_SEARCH * 0.5
        profile.last_active = _now()
        self._trim(profile)
        await self.save_profile(profile)

    async def record_add_to_cart(self, user_id: str, product_id: str,
                                  category: str = "", brand: str = "", price: float = 0):
        """Record an add-to-cart (stronger signal)."""
        profile = await self.get_profile(user_id)
        profile.total_add_to_cart += 1
        if category:
            profile.preferred_categories[category] = \
                profile.preferred_categories.get(category, 0) + WEIGHT_ADD_TO_CART
        if brand:
            profile.preferred_brands[brand] = \
                profile.preferred_brands.get(brand, 0) + WEIGHT_ADD_TO_CART
        if price > 0:
            self._update_budget(profile, price)
        profile.last_active = _now()
        self._trim(profile)
        await self.save_profile(profile)

    async def record_checkout(self, user_id: str, product_ids: list[str],
                               categories: list[str] | None = None,
                               brands: list[str] | None = None,
                               total_price: float = 0):
        """Record a purchase (strongest signal)."""
        profile = await self.get_profile(user_id)
        profile.total_checkouts += 1
        for cat in (categories or []):
            profile.preferred_categories[cat] = \
                profile.preferred_categories.get(cat, 0) + WEIGHT_CHECKOUT
        for brand in (brands or []):
            profile.preferred_brands[brand] = \
                profile.preferred_brands.get(brand, 0) + WEIGHT_CHECKOUT
        if total_price > 0:
            self._update_budget(profile, total_price, is_purchase=True)
        profile.last_active = _now()
        self._trim(profile)
        await self.save_profile(profile)

    # ================================================================
    # Merge Strategy
    # ================================================================

    def merge_with_session(self, user_id: str, session_constraints) -> dict:
        """Merge long-term profile with current session constraints.

        Session constraints take priority (user's current intent).
        Long-term profile provides defaults when session doesn't specify.
        Returns a dict compatible with Constraints model.
        """
        profile = self._cache.get(user_id)
        if not profile:
            return {}

        # Apply time decay
        decay = self._calc_decay(profile)
        cats = {k: v * decay for k, v in profile.preferred_categories.items()}
        brands = {k: v * decay for k, v in profile.preferred_brands.items()}
        scenarios = {k: v * decay for k, v in profile.common_scenarios.items()}

        result = {}

        # Category: use session if present, else top long-term
        sc = session_constraints
        if not sc.category and cats:
            result["category"] = max(cats, key=cats.get)

        # Budget: use session if present, else long-term typical range
        if sc.budget_max is None and profile.budget_max:
            result["budget_max"] = profile.budget_max
        if sc.budget_min is None and profile.budget_min:
            result["budget_min"] = profile.budget_min

        # Scenario: use session if present, else most frequent long-term
        if not sc.scenario and scenarios:
            result["scenario"] = max(scenarios, key=scenarios.get)

        # Must tags: merge
        merged_tags = list(set(sc.must_tags or []))
        if merged_tags:
            result["must_tags"] = merged_tags

        # Exclude tags from long-term dislikes
        result["exclude_tags"] = sorted(
            profile.disliked_tags.keys(),
            key=lambda k: profile.disliked_tags[k],
            reverse=True,
        )[:5]

        # Top brands
        result["preferred_brands"] = sorted(brands, key=brands.get, reverse=True)[:5]

        result["_source"] = "long_term_memory"
        result["_decay"] = round(decay, 2)
        result["_profile_age_days"] = _days_since(profile.last_active or profile.created_at)

        return {k: v for k, v in result.items() if v and not k.startswith("_")}

    # ================================================================
    # Housekeeping
    # ================================================================

    def forget(self, user_id: str):
        self._cache.pop(user_id, None)
        if USE_POSTGRES:
            try:
                import asyncio
                async def _del():
                    from app.repositories.pg_preference_repo import get_preference_repo
                    get_preference_repo().forget(f"ltm:{user_id}")
                try:
                    loop = asyncio.get_running_loop()
                    import nest_asyncio
                    nest_asyncio.apply(loop)
                    loop.run_until_complete(_del())
                except RuntimeError:
                    asyncio.run(_del())
            except Exception:
                pass
        # Also remove JSON file
        fp = _JSON_DIR / f"{user_id}.json"
        if fp.exists():
            fp.unlink(missing_ok=True)

    def _calc_decay(self, profile: UserProfile) -> float:
        """Exponential decay based on days since last activity."""
        days = _days_since(profile.last_active or profile.created_at)
        return 0.5 ** (days / DECAY_HALF_LIFE)

    def _update_budget(self, profile: UserProfile, price: float, is_purchase: bool = False):
        w = 2 if is_purchase else 1
        if profile.budget_min is None:
            profile.budget_min = price
            profile.budget_max = price
        else:
            # EMA-like update
            alpha = 0.3 * w
            mid = (profile.budget_min + profile.budget_max) / 2
            new_mid = mid + alpha * (price - mid)
            spread = max((profile.budget_max - profile.budget_min) * (1 - alpha * 0.5), 50)
            profile.budget_min = round(max(new_mid - spread / 2, 0), 2)
            profile.budget_max = round(new_mid + spread / 2, 2)

    def _trim(self, profile: UserProfile):
        """Keep only top-N items in each category."""
        for field_name, max_n in [
            ("preferred_categories", MAX_CATEGORIES),
            ("preferred_brands", MAX_BRANDS),
            ("liked_tags", MAX_TAGS),
            ("disliked_tags", MAX_TAGS),
        ]:
            d = getattr(profile, field_name)
            if len(d) > max_n:
                trimmed = dict(sorted(d.items(), key=lambda x: x[1], reverse=True)[:max_n])
                setattr(profile, field_name, trimmed)

    # ================================================================
    # Persistence
    # ================================================================

    async def _load_pg(self, user_id: str) -> Optional[UserProfile]:
        try:
            from app.repositories.pg_preference_repo import get_preference_repo
            repo = get_preference_repo()
            data = repo.get(f"ltm:{user_id}", user_id)
            if data and "preferred_categories" in data:
                return UserProfile.from_storable(data)
        except Exception as e:
            logger.debug(f"PG load failed for {user_id}: {e}")
        return None

    async def _save_pg(self, profile: UserProfile):
        try:
            from app.repositories.pg_preference_repo import get_preference_repo
            repo = get_preference_repo()
            repo.update(f"ltm:{user_id}", profile.to_storable(), profile.user_id)
        except Exception as e:
            logger.debug(f"PG save failed for {profile.user_id}: {e}")

    def _load_json(self, user_id: str) -> Optional[UserProfile]:
        fp = _JSON_DIR / f"{user_id}.json"
        if not fp.exists():
            return None
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            return UserProfile.from_storable(data)
        except Exception:
            return None

    def _save_json(self, profile: UserProfile):
        fp = _JSON_DIR / f"{profile.user_id}.json"
        fp.write_text(json.dumps(profile.to_storable(), ensure_ascii=False, indent=2),
                      encoding="utf-8")


# ================================================================
# Helpers
# ================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _days_since(iso_str: str) -> float:
    if not iso_str:
        return 999
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return 999


# ================================================================
# Global Singleton
# ================================================================

_ltm: LongTermMemory | None = None


def get_long_term_memory() -> LongTermMemory:
    global _ltm
    if _ltm is None:
        _ltm = LongTermMemory()
    return _ltm
