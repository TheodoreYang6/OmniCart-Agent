"""Shared recognition for explicit cart-add requests."""

import re

_CART_ADD = r"(?:加(?:入到?|到|进)?|放(?:到|进|入))(?:我(?:的)?|自己(?:的)?)?购物车|加购|全部加入"
_ADD_REQUEST = re.compile(_CART_ADD)
_NON_REQUEST = re.compile(
    r"(?:怎么|怎样|如何|不要|不用|不必|先不|暂不|不想|已经|别(?=加|放|再|帮|把|给)|不(?=加|放))"
    rf"[^，。！？,.!?]*?(?:{_CART_ADD})"
    rf"|(?:{_CART_ADD})(?:失败|没成功|不成功|的?教程|的?步骤)"
)


def is_cart_add_request(message: str) -> bool:
    text = re.sub(r"\s+", "", message)
    return bool(_ADD_REQUEST.search(text) and not _NON_REQUEST.search(text))
