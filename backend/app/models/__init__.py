"""SQLAlchemy ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.product import ProductModel
from app.models.cart_item import CartItemModel
from app.models.user_preference import UserPreferenceModel
from app.models.user import UserModel
from app.models.address import AddressModel

__all__ = ["Base", "ProductModel", "CartItemModel", "UserPreferenceModel", "UserModel", "AddressModel"]
