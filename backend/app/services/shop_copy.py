"""购物动作的确定性口语模板（LLM 回退与高频加购文案共用）。"""


def cart_added(brand_title: str, sku_label: str, cart_count: int, cart_total: float) -> str:
    spec = f"（{sku_label}）" if sku_label else ""
    return f"已帮你把「{brand_title}」{spec}放进购物车，现在一共 {cart_count} 件，合计 ¥{cart_total:.0f}。需要的话可以直接结算。"


def sku_picker(title: str, sku_count: int) -> str:
    return f"「{title}」有 {sku_count} 个规格，选一个我帮你加。"


def order_preview_fallback(item_count: int, total: float, has_address: bool) -> str:
    if has_address:
        return f"帮你整理好了，一共 {item_count} 件，合计 ¥{total:.0f}。确认没问题就下单，地址不对可以改。"
    return f"帮你整理好了，一共 {item_count} 件，合计 ¥{total:.0f}。还差一个收货地址，先填一下。"


def order_created_fallback(order_id: str, item_count: int, total: float, eta: str) -> str:
    return f"下单成功，订单号 {order_id}，共 {item_count} 件，合计 ¥{total:.0f}，预计 {eta}。"
