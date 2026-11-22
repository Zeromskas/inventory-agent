"""The three product operations exposed to the agent and scripted baseline."""

PRICE = {
    "type": "number", "minimum": 0,
    "description": "Unit price in euros, with at most two decimal places (e.g. 29.95). Never invent a price.",
}
NAME = {"type": "string", "minLength": 1, "description": "Product name; must not be blank."}
QUANTITY = {"type": "integer", "minimum": 0, "description": "Absolute stock quantity."}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_products",
            "description": (
                "List product IDs, names, quantities and unit prices in euros (price). Use query to find a product, "
                "check stock or price, or omit it to return all products."
            ),
            "parameters": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "query": {"type": ["string"], "default": "", "description": "Case-insensitive literal name substring; omit to list all products."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": (
                "Create a product with a generated ID. Requires its name and price (euros). "
                "Quantity defaults to zero when unspecified. If the price is missing, ask the user. "
                "Returns PRODUCT_ALREADY_EXISTS for a duplicate; do not modify the existing product automatically."
            ),
            "parameters": {
                "type": "object", "additionalProperties": False,
                "properties": {"name": NAME, "price": PRICE, "quantity": {**QUANTITY, "default": 0}},
                "required": ["name", "price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_product",
            "description": (
                "Modify an existing product by a known ID. Supply at least one of name, quantity, or price; "
                "omitted fields stay unchanged. Quantity is the NEW TOTAL, not an increment. "
                "For relative stock changes, list the product first and calculate the new total. "
                "Resolve ambiguous names before writing. Returns PRODUCT_NOT_FOUND, "
                "PRODUCT_ALREADY_EXISTS, NO_CHANGES, or a validation error when appropriate."
            ),
            "parameters": {
                "type": "object", "additionalProperties": False,
                "properties": {"product_id": {"type": "integer", "minimum": 1,
                                              "description": "ID returned by a preceding list_products lookup; never guess."},
                               "name": NAME, "quantity": QUANTITY, "price": PRICE},
                "required": ["product_id"],
            },
        },
    },
]
