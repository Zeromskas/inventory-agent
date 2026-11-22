"""Keyword baseline using the original simple parsing heuristics.

Reads the first matching price/quantity, takes new names from single or double quotes,
and falls back to listing all products when no name matches. These deliberately
limited rules can produce wrong answers or changes; evaluation measures that.
No LLM, task IDs, or gold outcomes are used to choose actions.
"""
from copy import deepcopy
import json
import re
from string import punctuation

from inventory.database import DEFAULT_DB
from inventory.run_result import RunResult
from inventory.tools.tool_dispatcher import execute_tool


class ScriptedBaseline:
    def __init__(self, db_path=DEFAULT_DB):
        self.db_path = db_path

    @staticmethod
    def _describe(product):
        return f"{product['name']}: quantity {product['quantity']}, price {product['price']:.2f} EUR"

    @staticmethod
    def _candidate_products(text, products):
        text = text.casefold()
        # exact match first
        exact = [p for p in products if p["name"].casefold() in text]
        if exact:
            return exact
        # match by words in product name, ignoring plurals
        words = [word.strip(punctuation).removesuffix("s") for word in text.split()]
        # ignore short words to avoid false matches like "a" or "an"
        words = [word for word in words if len(word) > 2]
        return [p for p in products if any(word in p["name"].casefold() for word in words)]

    def _find_price(self, text):
        text = text.casefold()
        # Original first-number heuristic, including whole numbers.
        match = re.search(r"(?<![\w.])-?\d+(?:[.,]\d+)?(?![\w.])", text)
        if match:
            price_str = match.group().replace(",", ".")
            try:
                return float(price_str)
            except ValueError:
                pass
        match = re.search(r"(?<![\w.])-?\d+(?![\w.])\s*(?:euros?|eur|€)", text)
        if match:
            price_str = match.group().split()[0]
            try:
                return float(price_str)
            except ValueError:
                pass
        return None

    def _find_quantity(self, text):
        text = text.casefold()
        match = re.search(r"(?<![\w.])-?\d+(?![\w.])\s*(?!euros?|eur|€)", text)
        if match:
            quantity_str = match.group().split()[0]
            try:
                return int(quantity_str)
            except ValueError:
                pass
        return None

    def _create_product(self, text, call):
        match = re.search(r"([\"'])(.*?)\1", text)
        if not match or not match.group(2).strip():
            raise ValueError('Please provide a product name enclosed in single or double quotes.')
        name = match.group(2).strip()
        price = self._find_price(text)
        if price is None:
            raise ValueError("Please provide a price in euros.")
        quantity = self._find_quantity(text)
        if quantity is None:
            quantity = 0
        if price < 0:
                    return f"Price cannot be negative."
        if quantity < 0:
            return f"Quantity cannot be negative."
        result = call("add_product", {"name": name, "price": price, "quantity": quantity})
        if not result["success"]:
            if result["error"] == "PRODUCT_ALREADY_EXISTS":
                raise ValueError(f"Product '{name}' already exists.")
            raise ValueError(f"Could not add product: {result['error']}.")
        return f"Added {self._describe(result['data'])}"

    def _update_product(self, text, products, call):
        candidates = self._candidate_products(text, products)
        if not candidates:
            raise ValueError("No matching product in inventory.")
        if len(candidates) > 1:
            names = ", ".join(p["name"] for p in candidates)
            raise ValueError(f"Which product do you mean: {names}?")
        product = candidates[0]
        price = self._find_price(text)
        quantity = self._find_quantity(text)
        if price is None and quantity is None:
            raise ValueError("Please specify a new price or quantity.")
        if price is not None and price < 0:
            return f"Price cannot be negative."
        if quantity is not None and quantity < 0:
            return f"Quantity cannot be negative."
        arguments = {"product_id": product["id"]}
        if price is not None:
            arguments["price"] = price
        if quantity is not None:
            arguments["quantity"] = quantity
        result = call("modify_product", arguments)
        if not result["success"]:
            return f"Could not update product: {result['error']}."
        return f"Updated: {self._describe(result['data'])}"

    def _list_products(self, text, products):
        candidates = self._candidate_products(text, products)
        if candidates:
            return "; ".join(self._describe(p) for p in candidates)
        return "; ".join(self._describe(p) for p in products) or "No products in inventory."

    def run(self, messages: list[dict]) -> RunResult:
        if not messages or messages[-1]["role"] != "user":
            raise ValueError("Messages must end with a user request")
        history = deepcopy(messages)
        tool_calls = []

        def call(name, arguments):
            result = execute_tool(name, arguments, db_path=self.db_path)
            tool_calls.append({"name": name, "arguments": deepcopy(arguments), "result": deepcopy(result)})
            history.append({"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": name, "arguments": deepcopy(arguments)}}]})
            history.append({"role": "tool", "tool_name": name, "content": json.dumps(result)})
            if result["error"] in {"DATABASE_ERROR", "TOOL_EXECUTION_FAILED", "UNKNOWN_TOOL"}:
                raise RuntimeError(f"Could not execute tool: {result['error']}.")
            return result

        def finish(answer, reason="completed"):
            history.append({"role": "assistant", "content": answer})
            return RunResult(answer, tool_calls, reason, history)

        text = history[-1]["content"].strip().rstrip(".?!")
        words = {word.strip(punctuation).casefold() for word in text.split()}

        try:
            result = call("list_products", {})
            if not result["success"]:
                raise ValueError(f"Could not list products: {result['error']}.")
            products = result["data"]
            if words & {"list", "show", "do"}:
                answer = self._list_products(text, products)
            elif words & {"add", "create"}:
                answer = self._create_product(text, call)
            elif words & {"change", "modify", "set", "update"}:
                answer = self._update_product(text, products, call)
            else:
                answer = "Unsupported request. Please list, show, add, create, change, or modify a product."
            return finish(answer)
        except ValueError as exc:
            return finish(str(exc))
        except RuntimeError as exc:
            return finish(str(exc), "execution_error")
