import logging
import sqlite3

from jsonschema import Draft202012Validator

from ..database import DEFAULT_DB

from .tools import add_product, list_products, modify_product
from .tool_definitions import TOOLS

TOOL_FUNCTIONS = {
    "list_products": list_products,
    "add_product": add_product,
    "modify_product": modify_product,
}
VALIDATORS = {
    tool["function"]["name"]: Draft202012Validator(tool["function"]["parameters"])
    for tool in TOOLS
}
logger = logging.getLogger(__name__)


def tool_response(data=None, error=None) -> dict:
    return {"success": error is None, "data": data if error is None else None, "error": error}


def execute_tool(name: str, arguments: dict, *, db_path=DEFAULT_DB) -> dict:
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return tool_response(error="UNKNOWN_TOOL")
    error = next(VALIDATORS[name].iter_errors(arguments), None)
    if error is not None:
        return tool_response(error=f"INVALID_ARGUMENTS: {error.message}")

    try:
        result = function(**arguments, db_path=db_path)
        if isinstance(result, dict) and "error" in result:
            return tool_response(error=result["error"])
        return tool_response(data=result)
    except sqlite3.Error:
        logger.exception("Database error in tool: %s", name)
        return tool_response(error="DATABASE_ERROR")
    except (TypeError, ValueError) as exc:
        return tool_response(error=f"INVALID_ARGUMENTS: {exc}")
    except Exception:
        logger.exception("Tool execution failed: %s", name)
        return tool_response(error="TOOL_EXECUTION_FAILED")
