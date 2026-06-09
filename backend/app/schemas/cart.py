"""Cart & Checkout Schemas"""

from pydantic import BaseModel, Field

DEMO_USER_ID = "demo_user_001"


class CartItem(BaseModel):
    cart_item_id: str = ""
    user_id: str = DEMO_USER_ID
    product_id: str
    sku_id: str | None = None
    sku_label: str = ""
    title: str = ""
    brand: str = ""
    price: float = 0.0
    image_url: str = ""
    quantity: int = 1
    selected: bool = True


class CartItemCreate(BaseModel):
    product_id: str
    sku_id: str | None = None
    quantity: int = 1


class CartItemUpdate(BaseModel):
    quantity: int | None = None
    selected: bool | None = None


class Cart(BaseModel):
    user_id: str = DEMO_USER_ID
    items: list[CartItem] = Field(default_factory=list)

    @property
    def total_price(self) -> float:
        return sum(item.price * item.quantity for item in self.items if item.selected)

    @property
    def total_count(self) -> int:
        return sum(item.quantity for item in self.items if item.selected)


class CheckoutRequest(BaseModel):
    user_id: str = DEMO_USER_ID
    item_ids: list[str] = Field(default_factory=list)  # 要结算的 cart_item_id 列表
    session_id: str = ""
    conversation_id: str = ""


class CheckoutResponse(BaseModel):
    order_id: str
    user_id: str
    items: list[CartItem]
    total_price: float
    status: str = "pending"  # pending / paid / shipped
    message: str = "模拟结算成功（未执行真实支付）"
