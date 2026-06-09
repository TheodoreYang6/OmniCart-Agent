"""SQLAlchemy ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.product import ProductModel
from app.models.cart_item import CartItemModel
from app.models.user import UserModel
from app.models.address import AddressModel
from app.models.conversation import ConversationModel, ConversationMessageModel
from app.models.user_preference_entry import UserPreferenceEntry
from app.models.order import OrderModel

__all__ = [
    "Base",
    "ProductModel", "CartItemModel", "UserModel", "AddressModel",
    "ConversationModel", "ConversationMessageModel",
    "UserPreferenceEntry", "OrderModel",
]
