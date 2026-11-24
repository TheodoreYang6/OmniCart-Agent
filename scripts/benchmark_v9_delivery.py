"""Measure first checked text, category hits, budget adherence and SSE consistency."""

import argparse
import json
from statistics import median
from time import perf_counter
from uuid import uuid4

import httpx

CASES = (
    ("推荐500元以内的真无线耳机", 500, ("耳机", "Buds", "AirPods", "FreeBuds")),
    ("推荐200元以内的保温杯", 200, ("保温杯", "保温壶")),
    ("推荐200元以内的面膜", 200, ("面膜",)),
)


def measure(client, base_url, query, budget, expected):
    cards = []
    chunks = []
    result = None
    first_text_ms = None
    first_cards_ms = None
    started = perf_counter()
    with client.stream("POST", f"{base_url.rstrip('/')}/api/recommend/stream", json={
        "message": query, "session_id": uuid4().hex,
    }) as response:
        response.raise_for_status()
        event = ""
        for line in response.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[6:])
            if event == "recommendations":
                cards = payload["primary_products"]
                first_cards_ms = round((perf_counter() - started) * 1000)
            if event == "token":
                if first_text_ms is None:
                    first_text_ms = round((perf_counter() - started) * 1000)
                chunks.append(payload["text"])
            if event == "result":
                result = payload
    if result is None or first_text_ms is None:
        raise RuntimeError(f"Stream did not return checked text for {query}")
    return {
        "query": query,
        "first_cards_ms": first_cards_ms,
        "first_checked_text_ms": first_text_ms,
        "category_hit": any(word.casefold() in (card.get("title") or "").casefold()
                            for card in cards for word in expected),
        "budget_pass": bool(cards) and all(0 < float(card.get("price") or 0) <= budget for card in cards),
        "checked_body_matches_sse": "".join(chunks) == result["answer"],
        "checked_body_uses_cards": bool(cards) and all(
            (card.get("title") or "") in result["answer"] for card in cards
        ),
        "fact_fallback": bool((result.get("harness_report") or {}).get("fallback_used")),
        "primary_cards": [{k: card.get(k) for k in ("product_id", "title", "price")} for card in cards],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normal_url")
    parser.add_argument("fallback_url")
    args = parser.parse_args()
    baseline = {}
    with httpx.Client(timeout=120) as client:
        for label, url in (("normal", args.normal_url), ("fallback", args.fallback_url)):
            results = [measure(client, url, *case) for case in CASES]
            baseline[label] = {
                "median_first_checked_text_ms": median(row["first_checked_text_ms"] for row in results),
                "cases": results,
            }
    print(json.dumps(baseline, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
