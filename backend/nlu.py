import re
import os
import json
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables (OpenAI API key)
load_dotenv()


# -------------------------------------------------------------
# PART A - SIMPLE RULE-BASED NLU
# -------------------------------------------------------------
def extract_with_rules(text: str):
    """
    Simple rule-based NLU to extract quantity, item, modifiers and budget.
    Works offline and handles basic user messages.
    """

    text_lower = text.lower()

    data = {
        "quantity": 1,
        "item": None,
        "modifiers": [],
        "budget": None,
        "is_veg": None
    }

    # ------------------------------------------------------
    # STEP 1 — Budget Extraction FIRST
    # ------------------------------------------------------
    budget_match = (
        re.search(r"under\s*₹?(\d+)", text_lower)
        or re.search(r"below\s*₹?(\d+)", text_lower)
        or re.search(r"less than\s*₹?(\d+)", text_lower)
    )

    if budget_match:
        data["budget"] = int(budget_match.group(1))
        # remove budget number so quantity won't pick it up
        text_lower = text_lower.replace(budget_match.group(1), "")

    # ------------------------------------------------------
    # STEP 2 — Quantity Extraction AFTER removing budget
    # ------------------------------------------------------
    qty_match = re.search(r"\b(\d+)\b", text_lower)
    if qty_match:
        data["quantity"] = int(qty_match.group(1))

    # ------------------------------------------------------
    # STEP 3 — Item Extraction
    # ------------------------------------------------------
    possible_items = [
        "pizza", "burger", "biryani", "pasta",
        "sandwich", "dosa", "fries", "taco", "noodles"
    ]

    for item in possible_items:
        if item in text_lower:
            data["item"] = item
            break

    # ------------------------------------------------------
    # STEP 4 — Modifiers
    # ------------------------------------------------------
    if "cheese" in text_lower or "cheesy" in text_lower:
        data["modifiers"].append("extra cheese")

    if "spicy" in text_lower:
        data["modifiers"].append("spicy")

    # ------------------------------------------------------
    # STEP 5 — Veg / Non-Veg
    # ------------------------------------------------------
    if "non veg" in text_lower or "non-veg" in text_lower:
        data["is_veg"] = False
    elif "veg" in text_lower:
        data["is_veg"] = True

    return data



# -------------------------------------------------------------
# PART B - ADVANCED LLM NLU (OpenAI JSON Extractor)
# -------------------------------------------------------------
def extract_with_llm(text: str):
    """
    Uses OpenAI to extract structured food-ordering details.
    Returns clean JSON.
    """

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY in .env file")

    client = OpenAI(api_key=api_key)

    prompt = f"""
    Extract structured food-ordering information:

    - quantity (integer)
    - item (string)
    - modifiers (array)
    - budget (integer or null)
    - priority (array: rating, delivery_time, discount, price)
    - veg_or_nonveg ("veg", "nonveg", null)

    Return ONLY valid JSON.

    User message: "{text}"
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a food-ordering extraction engine."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)



# -------------------------------------------------------------
# PART C - MASTER NLU FUNCTION (RULE + LLM)
# -------------------------------------------------------------
def extract_user_intent(text: str):
    """
    Tries LLM extraction first (if API key exists).
    Falls back to rule-based if OpenAI API fails or is disabled.
    """

    if os.getenv("OPENAI_API_KEY"):
        try:
            return extract_with_llm(text)
        except Exception as e:
            print("LLM failed, falling back to rule-based:", e)

    return extract_with_rules(text)
