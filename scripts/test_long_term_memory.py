#!/usr/bin/env python
"""Long-Term Memory test — simulate user behavior learning over time."""

import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def test():
    from app.memory.long_term import get_long_term_memory, LongTermMemory

    ltm = get_long_term_memory()
    user = "test_user_001"

    # Clean state
    ltm.forget(user)
    print("1. Clean profile")
    p = await ltm.get_profile(user)
    print(f"   categories: {p.preferred_categories}")
    print(f"   searches: {p.total_searches}")

    # Simulate user searching for Bluetooth earphones several times
    print("\n2. Record 3 searches for 蓝牙耳机 (数码电子)")
    for _ in range(3):
        await ltm.record_search(user, "蓝牙耳机推荐", category="数码电子", sub_category="真无线耳机")
    p = await ltm.get_profile(user)
    print(f"   categories: {p.preferred_categories}")
    print(f"   searches: {p.total_searches}")

    # Add to cart
    print("\n3. Record add-to-cart (QCY MeloBuds, 199元)")
    await ltm.record_add_to_cart(user, "p_digital_026", category="数码电子", brand="QCY", price=199)
    p = await ltm.get_profile(user)
    print(f"   brands: {p.preferred_brands}")
    print(f"   budget range: {p.budget_min}-{p.budget_max}")
    print(f"   add_to_cart: {p.total_add_to_cart}")

    # Checkout (strongest signal)
    print("\n4. Record checkout (漫步者耳机, 169元)")
    await ltm.record_checkout(user, ["p_digital_030"], categories=["数码电子"], brands=["漫步者"], total_price=169)
    p = await ltm.get_profile(user)
    print(f"   categories: {p.preferred_categories}")
    print(f"   brands: {p.preferred_brands}")
    print(f"   budget range: {p.budget_min}-{p.budget_max}")
    print(f"   checkouts: {p.total_checkouts}")

    # Search for different category
    print("\n5. Record search for 防晒霜 (美妆护肤) — different category")
    await ltm.record_search(user, "推荐一款防晒霜", category="美妆护肤")
    p = await ltm.get_profile(user)
    print(f"   categories: {p.preferred_categories}")
    print(f"   searches: {p.total_searches}")

    # Test merge with session
    print("\n6. Merge with session constraints")
    from app.schemas.workflow import Constraints
    session = Constraints(category=None, budget_max=None, scenario=None)
    merged = ltm.merge_with_session(user, session)
    print(f"   long-term defaults: {merged}")

    # Test merge with session override
    print("\n7. Merge with session override (user explicitly sets category)")
    session2 = Constraints(category="服饰运动", budget_max=300, scenario="sport")
    merged2 = ltm.merge_with_session(user, session2)
    print(f"   merged (session overrides): category={merged2.get('category')}, budget={merged2.get('budget_max')}")

    # Persistence test
    print("\n8. Persistence test — reload profile")
    p2 = await ltm.get_profile(user)
    print(f"   same profile? {p.total_searches == p2.total_searches}")
    print(f"   budget: {p2.budget_min}-{p2.budget_max}")

    print("\n[OK] Long-Term Memory test PASSED")


if __name__ == "__main__":
    asyncio.run(test())
