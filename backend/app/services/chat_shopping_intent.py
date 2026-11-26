"""Model interpretation for the public chat entry point."""

import asyncio
import json
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.model_gateway.gateway import get_model_gateway
from app.prompts.agent_prompts import SHOPPING_ACTION_SYSTEM

logger = logging.getLogger(__name__)


class ShoppingIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal[
        "workflow", "clarify", "cart.add", "cart.select_sku", "cart.view", "cart.remove",
        "cart.update_qty", "cart.clear", "order.list", "order.detail", "order.track",
        "order.cancel", "order.pay", "order.preview", "payment.quote", "payment.confirm",
        "payment.status", "report.open", "address.edit", "preference.list", "preference.save",
        "preference.delete", "conversation.history", "conversation.reset", "inventory.check",
        "product.copy", "product.search",
    ]
    product: list[str] = Field(default_factory=list, max_length=5)
    cart: str = Field(default="", max_length=20)
    order: str = Field(default="", max_length=20)
    sku: str = Field(default="", max_length=20)
    quantity: int | None = Field(default=None, ge=1, le=99)
    ordinal: int | None = Field(default=None, ge=1, le=100)
    budget_max: float | None = Field(default=None, gt=0, le=1_000_000)
    query: str = Field(default="", max_length=160)
    question: str = Field(default="", max_length=200)
    continue_after: bool = False


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON field")
    return result


def _parse_decision(raw: str) -> ShoppingIntent:
    content = (raw or "").strip()
    if content.startswith("```") and content.endswith("```"):
        content = content.split("\n", 1)[-1][:-3].strip()
    data = json.loads(content, object_pairs_hook=_unique_fields)
    if isinstance(data, dict):
        # Accept only representation differences. The action, extra fields, ranges
        # and candidate ownership still have to pass their respective checks.
        data = {
            field: value for field, value in data.items()
            if value is not None or field not in ShoppingIntent.model_fields or field == "action"
        }
        if isinstance(data.get("product"), str):
            data["product"] = [data["product"]]
    return ShoppingIntent.model_validate(data)


async def understand_shopping_turn(message: str, context: dict) -> ShoppingIntent | None:
    """Allow one model retry before handing any plan to the executor."""
    prompt = json.dumps({"message": message, **context}, ensure_ascii=False, default=str)
    system = SHOPPING_ACTION_SYSTEM
    gateway = get_model_gateway()
    deadline = asyncio.get_running_loop().time() + 12
    for attempt in range(1, 3):
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(gateway.chat("shopping_action", prompt, system=system),
                                         timeout=min(remaining, 7))
            return _parse_decision(raw)
        except ValidationError as exc:
            codes = sorted({error["type"] for error in exc.errors(include_input=False)})
            logger.warning("Shopping decision schema invalid on attempt %d (%s)", attempt, ", ".join(codes))
        except ValueError:
            logger.warning("Shopping decision invalid JSON on attempt %d", attempt)
        except TimeoutError:
            logger.warning("Shopping decision timed out on attempt %d", attempt)
        except Exception as exc:
            logger.warning("Shopping decision provider failed on attempt %d (%s)", attempt, type(exc).__name__)
        system = SHOPPING_ACTION_SYSTEM + (
            "\n重新判断原消息。只返回一个 JSON 对象，其字段名称必须在上述列表中。"
            "product 必须用数组，数量用整数，无关字段省略；目标不明确就返回 clarify 并填写 question。"
        )
    return None
