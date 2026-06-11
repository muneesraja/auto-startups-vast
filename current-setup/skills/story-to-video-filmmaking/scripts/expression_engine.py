"""
Expression expansion engine for story-to-video pipeline.

Converts raw expression descriptors into three-region facial descriptions
(mouth + eyes + brow) following the Qwen Image Edit prompting guide.

The three-region rule: for best results with Qwen Image Edit, every facial
expression should describe at least mouth + eyes + brow/forehead. Single-word
labels like "sad" or "determined" get expanded into full visual descriptors.
Already-expanded descriptors pass through unchanged.

Usage:
    from expression_engine import expand_expression, expand_expressions_for_shot

    # Single expression
    expanded = expand_expression("sad")
    # → "mouth downturned at corners, eyes downcast and glistening, brows drawn together"

    # Shot-level (all characters)
    result = expand_expressions_for_shot({"toby": "sad", "taro": "confident grin"})
    # → {"toby": "mouth downturned..., eyes..., brows...", "taro": "confident grin, direct steady gaze, chin slightly raised, brow smooth"}

Reference: references/facial-expression-vocabulary.md
"""

import re


# ── Built-in Expression Vocabulary ─────────────────────────────────────
# Each entry: (mouth_descriptor, eyes_descriptor, brow_descriptor)
# Organized by emotion category for maintainability.

EXPRESSION_MAP = {
    # ── Joy / Happiness ──
    "beaming": ("wide beaming smile", "eyes crinkled at corners", "cheeks raised high"),
    "content": ("gentle closed-mouth smile", "soft relaxed eyes", "smooth relaxed brow"),
    "happy": ("wide happy grin", "bright sparkling eyes", "raised eyebrows"),
    "excited": ("wide excited grin", "bright wide eyes", "raised eyebrows"),
    "amused": ("knowing smirk", "twinkling eyes", "one brow slightly raised"),
    "relieved": ("relieved smile", "eyes gently closed", "tension released from brow"),
    "cheerful": ("bright cheerful smile", "warm open eyes", "relaxed brow"),
    "joyful": ("wide joyful smile", "bright sparkling eyes", "raised happy eyebrows"),
    "gleeful": ("wide gleeful grin showing teeth", "bright dancing eyes", "brows raised high with delight"),
    "laughing": ("mouth wide open in laugh", "eyes crinkled shut with joy", "brows raised high"),
    "grinning": ("wide grin", "bright amused eyes", "brows slightly raised"),

    # ── Sadness / Grief ──
    "sad": ("mouth downturned at corners", "eyes downcast and glistening", "brows drawn together"),
    "crying": ("trembling lower lip, tears on cheeks", "eyes scrunched shut streaming tears", "brows pulled together in distress"),
    "upset": ("downturned mouth with trembling lip", "eyes wet and red", "brows drawn together"),
    "downcast": ("slight downturned mouth", "downcast eyes looking at ground", "heavy brow"),
    "heartbroken": ("mouth slightly open in anguish", "eyes wet and red", "brows drawn together tightly"),
    "wistful": ("faint sad smile", "distant gaze, eyes slightly unfocused", "soft wistful brow"),
    "defeated": ("slack jaw, mouth slightly open", "hollow empty eyes", "brow slack and drained"),
    "sorrowful": ("mouth pressed thin and downturned", "eyes heavy with sadness", "brows pulled together"),
    "melancholy": ("faint downturned smile", "eyes gazing into the distance", "brow softened with longing"),
    "mournful": ("trembling downturned mouth", "eyes filled with tears", "brows drawn together in grief"),

    # ── Anger / Frustration ──
    "angry": ("teeth bared in snarl", "eyes narrowed in fury", "brows pulled down hard"),
    "furious": ("bared teeth, mouth tight in rage", "eyes blazing with fury", "brows pulled down hard"),
    "scowling": ("mouth tight thin line", "eyes narrowed", "brows drawn together in deep scowl"),
    "frustrated": ("clenched jaw visible at temples", "eyes narrowed in frustration", "furrowed brow"),
    "annoyed": ("slight sneer", "eyes narrowed in irritation", "one eyebrow raised"),
    "seething": ("thin pressed lips", "cold intense stare", "jaw muscles clenched"),
    "irritated": ("tight compressed lips", "eyes narrowed with impatience", "brow slightly furrowed"),

    # ── Fear / Anxiety ──
    "scared": ("mouth open in gasp", "eyes wide with fear", "brows raised high"),
    "terrified": ("mouth wide open in silent scream", "eyes wide with terror, face pale", "brows shot up high"),
    "nervous": ("forced tight smile", "darting eyes", "small furrow in brow"),
    "anxious": ("lower lip caught between teeth", "wide watchful eyes", "worried furrowed brow"),
    "startled": ("mouth rounded in surprise", "suddenly wide eyes", "brows shot up"),
    "panicked": ("mouth gasping", "frantic wild eyes", "brows high and tense"),
    "fearful": ("mouth slightly open, breath held", "wide frightened eyes", "brows raised in alarm"),
    "worried": ("slight frown, lip slightly protruding", "wide concerned eyes", "brows drawn together with concern"),

    # ── Surprise / Shock ──
    "surprised": ("mouth open in O shape", "eyes wide", "eyebrows raised high"),
    "amazed": ("jaw dropped", "eyes wide with wonder", "brows raised to hairline"),
    "shocked": ("mouth slack open", "wide unblinking eyes", "brows frozen high"),
    "stunned": ("mouth hanging slightly", "eyes unfocused, blank stare", "brows flat"),
    "astonished": ("mouth covered by hand", "eyes round and huge", "brows raised to hairline"),
    "awestruck": ("mouth slightly open in wonder", "wide eyes filled with amazement", "brows lifted high"),

    # ── Confusion / Uncertainty ──
    "confused": ("slight frown", "squinting eyes", "brow deeply furrowed"),
    "puzzled": ("slight frown", "eyes looking to the side", "one eyebrow raised"),
    "doubtful": ("tight skeptical mouth", "narrowed eyes", "one brow slightly raised"),
    "hesitant": ("lower lip caught between teeth", "wide uncertain eyes", "brow creased with worry"),
    "wondering": ("mouth slightly open", "wide curious eyes", "brows slightly raised"),
    "uncertain": ("wavering smile fading to frown", "darting uncertain eyes", "brows slightly knit"),

    # ── Calm / Neutral / Confident ──
    "calm": ("soft closed-mouth smile", "gentle relaxed eyes", "smooth relaxed brow"),
    "neutral": ("mouth at rest, neither smiling nor frowning", "calm open eyes", "brow smooth and level"),
    "confident": ("confident slight smile", "direct steady gaze", "chin slightly raised, brow smooth"),
    "serene": ("peaceful half-smile", "eyes gently half-lidded", "smooth relaxed brow"),
    "stoic": ("flat neutral line, mouth set", "level direct gaze", "brow smooth and unreadable"),
    "peaceful": ("gentle closed-mouth smile", "soft calm eyes", "relaxed smooth brow"),
    "composed": ("slight composed smile", "steady calm eyes", "smooth unruffled brow"),

    # ── Smug / Sly / Mischievous ──
    "smug": ("self-satisfied grin", "half-lidded amused eyes", "chin raised"),
    "sly": ("knowing half-smile", "eyes narrowed to slits", "one brow arched"),
    "mischievous": ("wide playful grin", "sparkling eyes", "brows raised playfully"),
    "taunting": ("mocking smirk", "challenging direct gaze", "chin thrust forward"),
    "playful": ("wide playful grin", "bright dancing eyes", "brows raised with humor"),

    # ── Determination / Resolve ──
    "determined": ("mouth set in firm line", "eyes focused and intense", "brow furrowed with resolve"),
    "resolute": ("jaw set firmly, mouth compressed", "eyes steady and unwavering", "brow slightly furrowed"),
    "focused": ("lips pressed together", "eyes narrowed in concentration", "brow slightly creased"),
    "tense": ("mouth clenched tight", "eyes narrowed and alert", "brow furrowed"),
    "stubborn": ("jaw jutted forward", "eyes fixed and unyielding", "brows drawn together"),
    "brave": ("slight determined smile", "eyes steady and courageous", "brow firm and set"),

    # ── Shame / Embarrassment ──
    "embarrassed": ("tight awkward forced smile", "eyes looking down in shame", "face flushed red"),
    "ashamed": ("lips compressed tight", "eyes averted to ground", "head bowed low"),
    "guilty": ("slight wince", "eyes refusing to meet viewer", "jaw tight"),
    "humiliated": ("mouth trembling, trying not to cry", "eyes downcast and wet", "brows drawn down in shame"),

    # ── Tired / Weary ──
    "tired": ("slight slack mouth", "drooping eyelids", "heavy brow"),
    "exhausted": ("slack mouth, slightly open", "drooping heavy eyelids", "brow weighted down"),
    "sleepy": ("suppressing a yawn", "eyes half-closed in drowsiness", "soft unfocused brow"),
    "weary": ("faint sighing mouth", "eyes dull and unfocused", "brow heavy and drawn"),
    "resigned": ("flat resigned expression, mouth slightly open", "eyes distant and blank", "brow slack"),

    # ── Hope / Wonder ──
    "hopeful": ("gentle upturned smile", "bright wide eyes gazing upward", "brows lifted with optimism"),
    "wonder": ("mouth slightly open in awe", "wide sparkling eyes", "brows raised in amazement"),
    "awe": ("mouth slightly open", "wide eyes filled with wonder", "brows raised high"),
    "curious": ("mouth slightly open, head tilted", "wide bright eyes", "brows slightly raised"),

    # ── Love / Tenderness ──
    "loving": ("soft warm smile", "gentle adoring eyes", "relaxed tender brow"),
    "tender": ("gentle soft smile", "warm loving eyes", "smooth relaxed brow"),
    "caring": ("warm gentle smile", "soft concerned eyes", "smooth brow"),
    "affectionate": ("soft loving smile", "warm gazing eyes", "brows relaxed and soft"),

    # ── Playful ──
    "playful": ("wide playful grin", "bright mischievous eyes", "brows raised with fun"),
    "teasing": ("playful smirk", "twinkling daring eyes", "one brow raised"),

    # ── Comedic Expressions ──
    "comedic surprise": ("mouth wide open in exaggerated O", "eyes huge and round with shock", "brows shot up to hairline"),
    "comedic fear": ("mouth wide open in silent scream", "eyes enormous with exaggerated terror", "brows raised impossibly high"),
    "comedic joy": ("huge ear-to-ear grin", "eyes squeezed shut with laughter", "brows raised with glee"),
    "comedic disgust": ("nose wrinkled dramatically, tongue out", "eyes squeezed shut", "brows pulled down in exaggerated distaste"),
}

# Keyword → canonical key mapping for fuzzy matching
_KEYWORD_LOOKUP = {}
for key in EXPRESSION_MAP:
    _KEYWORD_LOOKUP[key] = key
    # Common variations
    if key.endswith("ing"):
        stem = key[:-3]
        if len(stem) >= 3:
            _KEYWORD_LOOKUP[stem] = key

# Three-region indicator words
_MOUTH_WORDS = {"mouth", "smile", "grin", "lip", "jaw", "teeth", "frown", "scowl", "snarl", "sneer", "smirk"}
_EYES_WORDS = {"eyes", "gaze", "glance", "stare", "look", "squint", "eyelid", "pupil"}
_BROW_WORDS = {"brow", "eyebrow", "eyebrows", "forehead"}

# Negation phrases — character not present or expression should be ignored
_SKIP_PHRASES = {"not present in this shot", "not present", "n/a", "none", "off-screen"}


def expand_expression(raw_expr: str) -> str:
    """Expand a raw expression descriptor into a three-region facial description.

    If the expression already contains three-region descriptors (mentions mouth, eyes,
    and brow), it's returned as-is — we assume the author knew what they were doing.

    For single-word labels or partial descriptors, we expand using the built-in
    vocabulary to produce: mouth_descriptor, eyes_descriptor, brow_descriptor.

    Args:
        raw_expr: Expression text from manifest, e.g. "sad", "determined",
                  "wistful faint melancholy smile", or already-expanded descriptor.

    Returns:
        Three-region facial description following the mouth + eyes + brow pattern.
    """
    if not raw_expr:
        return "neutral relaxed face, mouth at rest, calm eyes, smooth brow"

    expr_stripped = raw_expr.strip()
    expr_lower = expr_stripped.lower()

    # Skip phrases — character not present
    if expr_lower in _SKIP_PHRASES:
        return expr_stripped

    # Neutral pass-through
    if expr_lower in ("neutral", "resting"):
        return "neutral relaxed face, mouth at rest, calm open eyes, smooth brow"

# Check if already a three-region descriptor (has mouth, eyes, brow)
    has_mouth = any(kw in expr_lower for kw in _MOUTH_WORDS)
    has_eyes = any(kw in expr_lower for kw in _EYES_WORDS)
    has_brow = any(kw in expr_lower for kw in _BROW_WORDS)

    region_count = sum([has_mouth, has_eyes, has_brow])

    if region_count >= 2:
        # Already has most regions — just augment missing ones rather than keyword expand
        # This prevents "sheepish embarrassed grin, eyes darting" from double-expanding
        missing = []
        if not has_brow:
            missing.append("brow shows intensity")
        if not has_mouth:
            missing.append("mouth reflects emotion")
        if not has_eyes:
            missing.append("eyes convey feeling")
        if missing:
            return f"{expr_stripped}, {', '.join(missing)}"
        return expr_stripped  # All 3 regions present

    # Try exact match first
    if expr_lower in EXPRESSION_MAP:
        mouth, eyes, brow = EXPRESSION_MAP[expr_lower]
        return f"{mouth}, {eyes}, {brow}"

    # Try matching individual words against vocabulary
    words = [w for w in re.split(r'[,\s]+', expr_lower) if w]
    for word in words:
        if word in EXPRESSION_MAP:
            mouth, eyes, brow = EXPRESSION_MAP[word]
            return f"{raw_expr}: {mouth}, {eyes}, {brow}"

    # Try the keyword lookup for stems/variants
    for word in words:
        if word in _KEYWORD_LOOKUP:
            canonical = _KEYWORD_LOOKUP[word]
            mouth, eyes, brow = EXPRESSION_MAP[canonical]
            return f"{raw_expr}: {mouth}, {eyes}, {brow}"

    # Try substring matching for compound emotions
    # e.g., "comedic surprise" should match the map
    if expr_lower in EXPRESSION_MAP:
        mouth, eyes, brow = EXPRESSION_MAP[expr_lower]
        return f"{mouth}, {eyes}, {brow}"

    # Fallback for 0-1 region expressions where no keyword matched:
    # Augment with generic three-region hints
    missing_regions = []
    if not has_mouth:
        missing_regions.append("mouth reflects emotion")
    if not has_eyes:
        missing_regions.append("eyes convey feeling")
    if not has_brow:
        missing_regions.append("brow shows intensity")

    if missing_regions:
        return f"{expr_stripped}, {', '.join(missing_regions)}"

    # Ultimate fallback (shouldn't reach here)
    return expr_stripped


def expand_expressions_for_shot(shot_expressions: dict, char_names: dict = None) -> dict:
    """Expand all character expressions in a shot.

    Args:
        shot_expressions: {character_id: expression_text} from manifest
        char_names: {character_id: display_name} for readability (optional)

    Returns:
        {character_id: expanded_expression_text}
    """
    expanded = {}
    for cid, expr in shot_expressions.items():
        expanded[cid] = expand_expression(expr)
    return expanded


def format_expression_for_prompt(char_id: str, expanded_expr: str, char_names: dict = None) -> str:
    """Format an expanded expression for inclusion in a Qwen prompt.

    Args:
        char_id: Character ID (e.g., "toby")
        expanded_expr: Expanded expression text
        char_names: Optional mapping of char_id → display name

    Returns:
        Formatted string like "- Toby: mouth downturned, eyes downcast, brows drawn"
    """
    name = (char_names or {}).get(char_id, char_id.capitalize())
    # Skip characters not present in this shot
    if expanded_expr.lower().strip() in _SKIP_PHRASES:
        return f"- {name}: not present in this shot"
    return f"- {name}: {expanded_expr}"


# ── Self-Test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Expression Engine Self-Test")
    print("=" * 50)

    test_cases = [
        # Single word labels
        ("sad", True),
        ("determined", True),
        ("happy", True),
        ("terrified", True),
        ("comedic surprise", True),
        # Already three-region — should pass through
        ("puzzled slight frown, eyes downcast, brow lightly creased", False),
        ("wistful faint melancholy smile, eyes gazing into the water, brow smoothed with longing", False),
        ("mouth closed tight, eyes narrowed, brow furrowed", False),
        # Two-region — should augment with missing
        ("sad eyes, frown", True),  # no brow → adds brow hint
        # Special cases
        ("not present in this shot", False),
        ("", False),
        ("neutral", False),
    ]

    for expr, should_expand in test_cases:
        result = expand_expression(expr)
        status = "✅" if should_expand else "🔄"
        print(f"\n{status} Input: {expr!r}")
        print(f"   Output: {result}")

    # Test shot-level expansion
    print("\n\nShot-level expansion test:")
    shot_expr = {
        "toby": "puzzled slight frown, eyes downcast looking at his own fur, brow lightly creased with confusion",
        "taro": "confident grin, eyes bright and focused, brows raised in concentration"
    }
    char_names = {"toby": "Toby", "taro": "Taro"}
    expanded = expand_expressions_for_shot(shot_expr, char_names)
    for cid, expr in expanded.items():
        print(f"  {cid}: {expr}")

    # Format test
    print("\nPrompt format test:")
    for cid, expr in expanded.items():
        print(f"  {format_expression_for_prompt(cid, expr, char_names)}")