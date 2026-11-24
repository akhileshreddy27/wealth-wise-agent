"""Categoriser agent: places transactions the keyword rules couldn't ("other") into a category.

One batched Gemini call with a JSON schema whose category field is an enum, so the model
can only answer with categories the app knows.
"""
import json

from wealthwise.ai.gemini import AIUnavailable, generate
from wealthwise.expenses.categories import EXPENSE_CATEGORIES

SYSTEM = ("You categorise Indian bank-statement transactions. For each item, pick the single best category "
          "from the allowed list, based on the merchant / narration. Use 'other' only if nothing fits.")


def categorize_with_ai(notes: list[str]) -> list[str] | None:
    """Return one category per note, or None if AI is off or the call fails."""
    if not notes:
        return []
    schema = {"type": "array", "items": {"type": "object", "properties": {
        "index": {"type": "integer"},
        "category": {"type": "string", "enum": list(EXPENSE_CATEGORIES)}}, "required": ["index", "category"]}}
    prompt = "Categories: " + ", ".join(f"{k} ({v['label']})" for k, v in EXPENSE_CATEGORIES.items()) + \
             "\n\nTransactions:\n" + "\n".join(f"{i}. {n}" for i, n in enumerate(notes))
    try:
        result = json.loads(generate(prompt, SYSTEM, json_schema=schema, temperature=0).text)
    except AIUnavailable:
        return None
    except Exception:  # network / quota / malformed output: keep the rule-based categories
        return None
    out = ["other"] * len(notes)
    for item in result:
        if 0 <= item.get("index", -1) < len(notes) and item.get("category") in EXPENSE_CATEGORIES:
            out[item["index"]] = item["category"]
    return out
