from contextlib import closing
import sqlite3

from ..database import DEFAULT_DB, get_connection
from .validation import validate_product, price_to_cents


def product_data(row):
    """Expose euro prices while keeping the storage representation private."""
    product = dict(row)
    product["price"] = product.pop("price_cents") / 100
    return product


def list_products(query: str = "", *, db_path=DEFAULT_DB) -> list[dict] | dict:
    if query is None:
        query = ""
    if not isinstance(query, str):
        return {"error": "INVALID_QUERY"}
    with closing(get_connection(db_path)) as conn:
        rows = conn.execute(
            """SELECT id, name, quantity, price_cents FROM products
               WHERE instr(lower(name), lower(?)) > 0
               ORDER BY name, id""",
            (query.strip(),),
        ).fetchall()
    return [product_data(row) for row in rows]


def add_product(name: str, price: float, quantity: int = 0, *, db_path=DEFAULT_DB) -> dict:
    error = validate_product(name, quantity, price)
    if error:
        return {"error": error}
    try:
        with closing(get_connection(db_path)) as conn, conn:
            with closing(conn.execute(
                """INSERT INTO products (name, quantity, price_cents) VALUES (?, ?, ?)
                   RETURNING id AS product_id, name, quantity, price_cents""",
                (name.strip(), quantity, price_to_cents(price)),
            )) as cursor:
                product = cursor.fetchone()
    except sqlite3.IntegrityError as exc:
        if str(exc) == "UNIQUE constraint failed: products.name":
            return {"error": "PRODUCT_ALREADY_EXISTS"}
        raise
    return product_data(product)


def modify_product(
    product_id: int,
    name: str | None = None,
    quantity: int | None = None,
    price: float | None = None,
    *, db_path=DEFAULT_DB,
) -> dict:
    """Set supplied fields to absolute values; omitted fields remain unchanged."""
    if type(product_id) is not int or product_id < 1:
        return {"error": "INVALID_PRODUCT_ID"}
    if name is None and quantity is None and price is None:
        return {"error": "NO_CHANGES"}
    error = validate_product(name, quantity, price, allow_none=True)
    if error:
        return {"error": error}

    changes = {
        "name": name.strip() if name is not None else None,
        "quantity": quantity,
        "price_cents": price_to_cents(price) if price is not None else None,
    }
    changes = {column: value for column, value in changes.items() if value is not None}
    assignments = ", ".join(f"{column} = ?" for column in changes)
    params = [*changes.values(), product_id]

    try:
        with closing(get_connection(db_path)) as conn, conn:
            with closing(conn.execute(
                f"""UPDATE products SET {assignments} WHERE id = ?
                    RETURNING id AS product_id, name, quantity, price_cents""",
                params,
            )) as cursor:
                product = cursor.fetchone()
    except sqlite3.IntegrityError as exc:
        if str(exc) == "UNIQUE constraint failed: products.name":
            return {"error": "PRODUCT_ALREADY_EXISTS"}
        raise
    return product_data(product) if product is not None else {"error": "PRODUCT_NOT_FOUND"}
