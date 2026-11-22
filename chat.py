"""Terminal chat and conversation history. Run: python3 project/chat.py"""
import json

from inventory.agent import InventoryAgent, MODEL
from inventory.database import DEFAULT_DB, create_database


def main():
    if not DEFAULT_DB.exists():
        create_database(DEFAULT_DB)
    agent = InventoryAgent()
    messages = []
    print(f"Inventory assistant ({MODEL})")
    print("Commands: /reset, /exit")
    while True:
        try:
            request = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not request:
            continue
        if request.lower() in {"/exit", "/quit"}:
            break
        if request.lower() == "/reset":
            messages = []
            print("Conversation history cleared.")
            continue
        messages.append({"role": "user", "content": request})
        result = agent.run(messages)
        messages = result.messages
        for call in result.tool_calls:
            print(f"Tool: {call['name']}({json.dumps(call['arguments'], ensure_ascii=False)})")
        print(f"\nAssistant: {result.answer}")


if __name__ == "__main__":
    main()
