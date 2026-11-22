"""One application database, plus explicitly chosen paths for tests."""
from contextlib import closing
from pathlib import Path
import sqlite3

DEFAULT_DB = Path(__file__).resolve().parent.parent / "dbs" / "inventory.db"


def get_connection(db_path=DEFAULT_DB):
    """Open an existing SQLite file; the caller owns and closes the connection."""
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def create_database(db_path=DEFAULT_DB, products=None):
    """Create a products database with optional seed rows; never overwrite a file."""
    rows = []
    for product in products or []:
        name, quantity, price_cents = product["name"], product.get("quantity", 0), product["price_cents"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Product name must not be blank")
        if type(quantity) is not int or quantity < 0 or type(price_cents) is not int or price_cents < 0:
            raise ValueError("Invalid seed quantity or price_cents")
        rows.append((product.get("id"), name.strip(), quantity, price_cents))

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=False)
    try:
        with closing(get_connection(path)) as conn, conn:
            conn.execute("""
                CREATE TABLE products (
                    id INTEGER PRIMARY KEY CHECK (id > 0),
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (length(trim(name)) > 0),
                    quantity INTEGER NOT NULL DEFAULT 0 CHECK (typeof(quantity) = 'integer' AND quantity >= 0),
                    price_cents INTEGER NOT NULL DEFAULT 0 CHECK (typeof(price_cents) = 'integer' AND price_cents >= 0)
                )
            """)
            conn.executemany("INSERT INTO products(id, name, quantity, price_cents) VALUES (?, ?, ?, ?)", rows)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path

if __name__ == "__main__":
    create_database()
