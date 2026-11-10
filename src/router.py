"""The routing policy. Every decision comes with a one-line `why`.
Prism (prism.py) answers three questions about the prompt; this file reads those answers and looks up a tier.
The keyword rules below are the fallback when Prism fails, and a baseline classifier to compare it against."""
import re, time
from config import (ROUTE_TABLE, NEXT_TIER, ROUTER_CLASSIFIER, WORKLOAD_PRIORITY, DEFAULT_PRIORITY,
                    WORKLOAD_MIN_CONFIDENCE, DIFFICULTY_CUTS, DIFFICULTY_MIN_CONFIDENCE, INDIC_MIN_P)
import prism

# --- 1. reading Prism's answers ----------------------------------------------------
LEVELS = ["easy", "medium", "hard"]


def read_prism(p: dict, workload_min=WORKLOAD_MIN_CONFIDENCE, cuts=DIFFICULTY_CUTS,
               difficulty_min=DIFFICULTY_MIN_CONFIDENCE, indic_min=INDIC_MIN_P) -> tuple[str, str, bool, str]:
    """Raw Prism answers -> (workload, difficulty, is_indic, reason). Pure, so the benchmark can sweep thresholds.
    - workload: the top option, or "other" when Prism's confidence is below workload_min.
    - difficulty: the 0-2 score cut into easy / medium / hard; a low-confidence answer is rounded UP one level.
    - is_indic: P(yes) >= indic_min."""
    workload = p["workload"]
    wnote = f"workload {workload} (conf {p['workload_confidence']:.2f})"
    if p["workload_confidence"] < workload_min:
        workload, wnote = "other", wnote + f" < {workload_min}, treated as other"
    score = p["difficulty_score"]
    i = 0 if score < cuts[0] else 1 if score < cuts[1] else 2
    dnote = f"difficulty {score:.2f} -> {LEVELS[i]} (conf {p['difficulty_confidence']:.2f})"
    if p["difficulty_confidence"] < difficulty_min and i < 2:
        i += 1
        dnote += f" < {difficulty_min}, rounded up to {LEVELS[i]}"
    return workload, LEVELS[i], p["indic_p"] >= indic_min, f"prism: {wnote}; {dnote}; indic p={p['indic_p']:.2f}"


# --- 2. keyword rules: language ----------------------------------------------------
INDIC_SCRIPT = re.compile(r"[ऀ-෿]")  # Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam, Sinhala
ROMAN_INDIC_WORDS = {
    # Hindi / Hinglish
    "hai", "hain", "nahi", "nahin", "kya", "kyu", "kyun", "kaise", "kab", "kahan", "mera", "meri", "mere", "aap",
    "aapka", "aapke", "tum", "karo", "karna", "raha", "rahi", "rahe", "hoga", "hogi", "tha", "thi",
    "bhi", "abhi", "paisa", "paise", "chahiye", "batao", "mujhe", "humko", "yaar", "accha", "acha",
    "theek", "thik", "toh", "bhai", "kripya", "dhanyavad", "namaste", "matlab", "wala", "wale", "wali", "lekin",
    "aur", "haan", "bilkul", "jaldi", "aaj", "samajh", "gaya", "gayi", "diya", "likho", "karein", "warna",
    # Tamil / Telugu / Kannada romanised (common)
    "enna", "illai", "illa", "vanakkam", "nandri", "epdi", "seri", "irukku", "panna", "pannunga", "venum",
    "ledu", "cheppandi", "namaskaram", "kavali", "chesanu", "chesadu", "vesaru", "rayandi", "nenu", "naaku", "sare",
}
INDIC_LANGS = r"(hindi|tamil|telugu|kannada|malayalam|marathi|bengali|bangla|gujarati|punjabi|odia|oriya|urdu|hinglish)"
TARGET_INDIC = re.compile(r"\b(into|to|in)\s+(?:\w+\s+)?" + INDIC_LANGS + r"\b", re.I)  # "into formal Hindi"
WORD_RE = re.compile(r"[a-zA-Z]+")


def detect_language(prompt: str) -> tuple[str, bool]:
    """Returns (label, is_indic). Rules: any Indic-script char; >=3 romanised-Indic keywords (or >=2 making up 20% of words);
    or an explicit Indic target language ("translate into Hindi")."""
    if INDIC_SCRIPT.search(prompt):
        return "indic_script", True
    words = [w.lower() for w in WORD_RE.findall(prompt)]
    hits = sum(1 for w in words if w in ROMAN_INDIC_WORDS)
    if hits >= 3 or (words and hits / len(words) >= 0.2 and hits >= 2):
        return "romanised_indic", True
    if TARGET_INDIC.search(prompt):
        return "indic_target", True
    return "english", False


# --- 3. keyword rules: difficulty --------------------------------------------------
EASY_KW = ["classify", "classification", "label", "categorise", "categorize", "category", "yes or no", "is this",
           "sentiment", "tag", "which of the following", "intent", "one-line", "one line", "only the label",
           "वर्गीकृत", "श्रेणी", "வகைப்படுத்து", "వర్గీకరించ"]
MEDIUM_KW = ["summarise", "summarize", "summary", "extract", "translate", "translation", "list the", "pull out",
             "convert", "rewrite", "paraphrase", "सारांश", "अनुवाद", "निकालिए", "निकालें", "सुरुक्कम्", "சுருக்கம்", "மொழிபெயர்",
             "సారాంశం", "అనువదించ"]
HARD_KW = ["reason", "analyse", "analyze", "analysis", "compare", "contrast", "step by step", "step-by-step",
           "multi-step", "legal", "liability", "clause", "indemn", "jurisdiction", "financial", "calculate",
           "compute", "penalty", "reconcile", "discrepanc", "contradict", "justify", "evaluate",
           "trade-off", "tradeoff", "root cause", "recommend", "prioritise", "prioritize", "explain why",
           "implication"]
LONG_PROMPT_CHARS = 1500


def detect_difficulty(prompt: str) -> tuple[str, str]:
    """Returns (easy|medium|hard, reason). Keyword tiers; hard beats medium beats easy; long prompts bump one level."""
    p = prompt.lower()
    hard = [k for k in HARD_KW if k in p]
    med = [k for k in MEDIUM_KW if k in p]
    easy = [k for k in EASY_KW if k in p]
    if hard:
        level, reason = "hard", f"hard keywords {hard[:3]}"
    elif med:
        level, reason = "medium", f"medium keywords {med[:3]}"
    elif easy:
        level, reason = "easy", f"easy keywords {easy[:3]}"
    else:
        level, reason = "medium", "no task keywords, default medium"
    if len(prompt) > LONG_PROMPT_CHARS and level != "hard":
        level = {"easy": "medium", "medium": "hard"}[level]
        reason += f" + long prompt ({len(prompt)} chars) bumps to {level}"
    return level, reason


# --- 4. keyword rules: workload ----------------------------------------------------
WORKLOAD_RULES = [  # checked in order, first match wins
    ("classification", ["classify", "classification", "label", "categor", "intent", "sentiment", "yes or no", "वर्गीकृत", "श्रेणी"]),
    ("translation", ["translate", "translation", "अनुवाद", "மொழிபெயர்", "అనువదించ", "into english", "into hindi", "into telugu", "into tamil", "in english"]),
    ("call_centre_summary", ["call", "transcript", "agent:", "customer:", "कॉल", "अझைப்ப", "ఏజెంట్", "एजेंट"]),
    ("document_extraction", ["extract", "निकालिए", "निकालें", "invoice", "receipt", "contract", "json", "fields"]),
]


def detect_workload_rules(prompt: str) -> tuple[str, str]:
    p = prompt.lower()
    for wl, kws in WORKLOAD_RULES:
        hit = [k for k in kws if k in p]
        if hit:
            return wl, f"rules {wl} {hit[:2]}"
    return "other", "rules: no workload keywords"


def read_rules(prompt: str) -> tuple[str, str, str, bool, str]:
    """Keyword version of the same three answers -> (workload, difficulty, language, is_indic, reason)."""
    workload, wreason = detect_workload_rules(prompt)
    difficulty, dreason = detect_difficulty(prompt)
    lang, is_indic = detect_language(prompt)
    return workload, difficulty, lang, is_indic, f"{wreason}; {dreason}"


# --- 5. route: three lookups, two rules --------------------------------------------
def route(prompt: str, mode: str | None = None, classifier: str | None = None) -> dict:
    """Decide the tier for a prompt. Never sees hidden labels.
    mode: None = derive the priority from the detected workload (normal operation); or force one of
    speed | cost | balanced | quality (benchmark sensitivity runs). classifier: prism | rules."""
    t0 = time.perf_counter()
    classifier = classifier or ROUTER_CLASSIFIER
    p = None
    if classifier == "prism":
        p = prism.decide(prompt)                                           # Lookups 1 and 2, one call
        if p["error"] == "none":
            workload, difficulty, is_indic, detail = read_prism(p)
            lang = "indic" if is_indic else "english"
        else:                                                              # Prism down or slow: never block on it
            classifier = "rules (prism failed)"
            workload, difficulty, lang, is_indic, detail = read_rules(prompt)
            detail = f"prism {p['error']}: {p['detail']}; {detail}"
    elif classifier == "rules":
        workload, difficulty, lang, is_indic, detail = read_rules(prompt)
    else:
        raise ValueError(f"unknown classifier {classifier}")
    priority = mode or WORKLOAD_PRIORITY.get(workload, DEFAULT_PRIORITY)   # workload -> what the customer cares about
    if priority not in ROUTE_TABLE:
        raise ValueError(f"unknown mode {priority}")
    if is_indic and difficulty != "hard":                                  # Indic rule
        tier = "indic"
        why = f"{workload} ({priority}), {difficulty}, {lang} -> sarvam-105b (Indic rule)"
    else:
        tier = ROUTE_TABLE[priority][difficulty]                           # Lookup 3
        why = f"{workload} ({priority}{' forced' if mode else ''}), {difficulty}, {lang} -> {tier}"
    return {"tier": tier, "workload": workload, "priority": priority, "language": lang, "is_indic": is_indic,
            "difficulty": difficulty, "why": why, "detail": detail, "classifier": classifier,
            "prism": p, "router_cost_inr": p["cost_inr"] if p else 0.0,
            "router_overhead_ms": round((time.perf_counter() - t0) * 1000, 1)}


def next_tier(tier: str):
    return NEXT_TIER.get(tier)
