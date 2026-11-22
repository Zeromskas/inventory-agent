"""Shared validation for product creation and partial updates."""
from decimal import Decimal


def price_to_cents(price):
    """Convert a euro amount exactly; never silently round fractional cents."""
    if type(price) not in (int, float):
        raise ValueError("Price must be a number in euros")
    amount = Decimal(str(price))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Price must be finite and nonnegative")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError("Price must have at most two decimal places")
    return int(cents)


def validate_product(name, quantity, price, *, allow_none=False) -> str | None:
    """Return an error code, or None when the supplied fields are valid."""
    if not (allow_none and name is None):
        if not isinstance(name, str) or not name.strip():
            return "INVALID_PRODUCT_NAME"
    if not (allow_none and quantity is None):
        if type(quantity) is not int or quantity < 0:
            return "INVALID_QUANTITY"
    if not (allow_none and price is None):
        try:
            price_to_cents(price)
        except ValueError:
            return "INVALID_PRICE"
    return None
