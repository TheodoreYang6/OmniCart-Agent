#!/usr/bin/env python3
"""Compare ownership costs without assuming unknown prices or eligibility."""

import argparse
import json
from pathlib import Path


def require_int(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def compare(data: dict) -> dict:
    budget = require_int(data.get("budget_fen"), "budget_fen", 1, 100_000_000)
    months = require_int(data.get("months"), "months", 1, 120)
    products = data.get("products")
    if not isinstance(products, list) or not 2 <= len(products) <= 8:
        raise ValueError("provide two to eight products")

    rows = []
    for product in products:
        name = product.get("name")
        source = product.get("source")
        if not all(isinstance(value, str) and value.strip() for value in (name, source)):
            raise ValueError("each product requires a name and a source")
        eligible = product.get("eligible")
        if eligible is not None and type(eligible) is not bool:
            raise ValueError("eligible must be true, false or null")
        costs = {key: product.get(key) for key in ("price_fen", "shipping_fen", "monthly_fen")}
        for key, value in costs.items():
            if value is not None:
                require_int(value, key, 0, 100_000_000)
        missing = [key for key, value in costs.items() if value is None]
        total = None if missing else costs["price_fen"] + costs["shipping_fen"] + months * costs["monthly_fen"]
        rows.append({
            "name": name, "source": source, **costs, "eligible": eligible, "missing_costs": missing,
            "total_fen": total, "within_budget": total <= budget if total is not None else None,
        })
    viable = sorted(
        (row for row in rows if row["eligible"] is True and row["within_budget"] is True),
        key=lambda row: row["total_fen"],
    )
    return {"budget_fen": budget, "months": months, "products": rows, "recommended": viable[0]["name"] if viable else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        result = compare(json.loads(args.input.read_text(encoding="utf-8")))
    except (AttributeError, OSError, ValueError) as exc:
        parser.exit(1, f"Invalid comparison input: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
