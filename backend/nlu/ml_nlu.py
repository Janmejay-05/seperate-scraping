import spacy
from sentence_transformers import SentenceTransformer, util

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# Load SentenceTransformer (for semantic similarity)
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# Predefined modifiers
MODIFIERS = [
    "extra cheese", "double cheese", "spicy", "less spicy",
    "crispy", "grilled", "tandoori", "butter", "peri peri"
]

# Veg keywords
VEG_WORDS = ["veg", "vegetarian", "pure veg", "only veg"]
NONVEG_WORDS = ["non veg", "non-veg", "chicken", "meat", "egg"]

# Budget keywords
BUDGET_TRIGGERS = ["under", "below", "less than", "<", "upto", "up to"]

# Quantity patterns
import re
QTY_PATTERN = re.compile(r"\b(\d+)\b")

# Dish embedding store (auto-grows from scrapers later)
DISH_LIBRARY = [
    "pizza", "burger", "biryani", "dosa", "pasta", "garlic bread",
    "fries", "wrap", "momos", "noodles", "manchurian",
    "sandwich", "paneer tikka", "taco", "shawarma"
]


def detect_dish(text):
    """Find closest matching dish using embeddings."""
    text_emb = embedder.encode(text, convert_to_tensor=True)
    dish_embs = embedder.encode(DISH_LIBRARY, convert_to_tensor=True)

    scores = util.cos_sim(text_emb, dish_embs)[0]
    best_idx = int(scores.argmax())
    best_score = float(scores.max())

    if best_score < 0.30:   # very low similarity
        return None

    return DISH_LIBRARY[best_idx]


def extract_ml_intent(text):
    doc = nlp(text.lower())
    data = {
        "quantity": None,
        "item": None,
        "modifiers": [],
        "budget": None,
        "is_veg": None,
    }

    # 1. Quantity
    m = QTY_PATTERN.search(text)
    if m:
        data["quantity"] = int(m.group(1))

    # 2. Veg / Non-veg
    if any(v in text.lower() for v in VEG_WORDS):
        data["is_veg"] = True
    elif any(v in text.lower() for v in NONVEG_WORDS):
        data["is_veg"] = False

    # 3. Budget
    for w in BUDGET_TRIGGERS:
        if w in text.lower():
            nums = re.findall(r"\b\d+\b", text)
            if nums:
                data["budget"] = int(nums[-1])
            break

    # 4. Modifiers (exact match)
    for m in MODIFIERS:
        if m in text.lower():
            data["modifiers"].append(m)

    # 5. Detect dish using ML
    data["item"] = detect_dish(text)

    return data
