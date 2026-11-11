"""The card reader: four narrow readings of a card face's rules text, type line and keywords.

Reading is pure: text in, reading out, no game state. When text matches a known form only
partly, the reader returns its best reading together with the assumptions it made; it never
guesses silently. Reminder text (in parentheses) is ignored.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from mtg_goldfishing.domain.cards import Card, Face
from mtg_goldfishing.domain.mana import MANA_KINDS, ManaString, Restriction
from mtg_goldfishing.domain.reading.model import (
    AMOUNT_ASSUMED_ONE,
    ASSUMES_ANY_COLOR,
    ASSUMES_CONDITION_MET,
    ASSUMES_ONE_COLOR,
    ASSUMES_UNTAPPED_PREFIX,
    ENTERS_UNTAPPED,
    IGNORES_ACTIVATION_CONDITION,
    IGNORES_CONDITIONAL_BONUS,
    RESTRICTION_NOT_UNDERSTOOD,
    AnyColor,
    AnyColorScope,
    CardReading,
    CardsInGraveyardCount,
    CardsInHandCount,
    Choice,
    Count,
    Counted,
    CountersOnSelfCount,
    DevotionCount,
    EntersTappedReading,
    EntersTappedReport,
    FaceReading,
    Fixed,
    KeywordGrant,
    KeywordReading,
    KeywordReport,
    ManaAbility,
    PermanentsCount,
    Produces,
    ReadAbility,
    ReadingReport,
    StepTrigger,
    UnreadAbility,
    Whose,
)
from mtg_goldfishing.domain.steps import STEPS, Step

# The card reader as a whole


# @spec READ-001, READ-002
def read_face(face: Face, card: Card) -> FaceReading:
    """Everything the reader works out from one face; `card` gives the card-level facts."""
    text = _FaceText.of(face, card)
    mana_abilities, unread = read_mana_abilities(text)
    return FaceReading(
        mana_abilities=mana_abilities,
        unread_mana_abilities=unread,
        step_triggers=read_step_triggers(text),
        haste=read_keyword("haste", text),
        vigilance=read_keyword("vigilance", text),
        flash=read_keyword("flash", text),
        enters_tapped=read_enters_tapped(text),
    )


# @spec READ-001
@cache
def read_card(card: Card) -> CardReading:
    """The reading of each face of a card, in face order."""
    return CardReading(tuple(read_face(face, card) for face in card.faces))


# @spec READ-027
def report(cards: Iterable[tuple[Card, CardReading]]) -> ReadingReport:
    """What a caller can show about the readings of a set of cards, named by face."""
    read_exactly: list[ReadAbility] = []
    read_with_assumptions: list[ReadAbility] = []
    unread: list[UnreadAbility] = []
    step_triggers: list[tuple[str, Step]] = []
    keywords: list[KeywordReport] = []
    enters_tapped: list[EntersTappedReport] = []
    assumed_untapped: list[EntersTappedReport] = []
    for card, reading in cards:
        for face, face_reading in zip(card.faces, reading.faces, strict=False):
            name = face.name
            for ability in face_reading.mana_abilities:
                listed = read_exactly if ability.is_exact else read_with_assumptions
                listed.append(ReadAbility(name, ability))
            unread.extend(UnreadAbility(name, text) for text in face_reading.unread_mana_abilities)
            steps = dict.fromkeys(trigger.step for trigger in face_reading.step_triggers)
            step_triggers.extend((name, step) for step in steps)
            for keyword, keyword_reading in (
                ("haste", face_reading.haste),
                ("vigilance", face_reading.vigilance),
            ):
                if keyword_reading.present:
                    keywords.append(KeywordReport(name, keyword, keyword_reading))
            tapped = face_reading.enters_tapped
            if tapped.tapped:
                enters_tapped.append(EntersTappedReport(name, tapped))
            elif tapped.assumptions:
                assumed_untapped.append(EntersTappedReport(name, tapped))
    return ReadingReport(
        read_exactly=tuple(read_exactly),
        read_with_assumptions=tuple(read_with_assumptions),
        unread=tuple(unread),
        step_triggers=tuple(step_triggers),
        keywords=tuple(keywords),
        enters_tapped=tuple(enters_tapped),
        assumed_untapped=tuple(assumed_untapped),
    )


# The text of a face, as the reader sees it

_REMINDER_TEXT = re.compile(r"\s*\([^()]*\)")
_SENTENCE_BREAK = re.compile(r"(?<=\.)\s+")
_SELF_WORDS = (
    "this creature",
    "this artifact",
    "this land",
    "this enchantment",
    "this permanent",
    "this vehicle",
    "this planeswalker",
    "this battle",
    "this token",
    "this card",
    "it",
)


@dataclass(frozen=True)
class _FaceText:
    """A face's rules text split into abilities, with reminder text removed."""

    face: Face
    card: Card
    lines: tuple[str, ...]
    self_reference: str  # a regex alternation naming the permanent itself

    @classmethod
    def of(cls, face: Face, card: Card) -> _FaceText:
        lines = tuple(
            line
            for line in (
                _REMINDER_TEXT.sub("", raw).strip() for raw in face.oracle_text.splitlines()
            )
            if line
        )
        names = {face.name, card.name, face.name.split(",")[0]}
        alternatives = [re.escape(name) for name in sorted(names, key=len, reverse=True)]
        alternatives += [re.escape(words) for words in _SELF_WORDS]
        return cls(face, card, lines, "(?:" + "|".join(alternatives) + ")")


def _sentences(text: str) -> list[str]:
    return [sentence for sentence in _SENTENCE_BREAK.split(text.strip()) if sentence]


# Mana abilities

_ADDS_MANA = re.compile(r"\badds?\b[^.]*?(?:\{[^}]+\}|\bmana\b)", re.IGNORECASE)
_ABILITY_WORD = re.compile(r"^[A-Z][A-Za-z' ]* — ")
_ACTIVATED = re.compile(r'^(?P<cost>[^:"]+?):\s+(?P<effect>.+)$')
_TRIGGER_START = re.compile(r"^(?:when|whenever|at)\b", re.IGNORECASE)
_BASIC_LAND_TYPES = {
    "plains": "W",
    "island": "U",
    "swamp": "B",
    "mountain": "R",
    "forest": "G",
}
_AMOUNTS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_AMOUNT = "(?P<amount>" + "|".join(_AMOUNTS) + ")"
_COLOR_NAMES = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_CARD_TYPES = (
    "Artifact",
    "Battle",
    "Creature",
    "Enchantment",
    "Instant",
    "Kindred",
    "Land",
    "Planeswalker",
    "Sorcery",
    "Tribal",
)
_OPTION_SEPARATOR = re.compile(r",\s*(?:or\s+)?|\s+or\s+")
_LIST_SEPARATOR = re.compile(r",\s*(?:or\s+|and\s+)?|\s+or\s+|\s+and\s+")


# @spec READ-003, READ-015, READ-016, READ-024, READ-025, READ-026, READ-045
def read_mana_abilities(text: _FaceText) -> tuple[tuple[ManaAbility, ...], tuple[str, ...]]:
    """The face's mana abilities, each read separately, and those that add mana unread.

    An ability that adds mana but gets no reading is listed as unread only when the card's
    produced colors are known.
    """
    read: list[ManaAbility] = list(_basic_land_abilities(text.face))
    unread: list[str] = []
    for line in text.lines:
        if not _ADDS_MANA.search(line):
            continue
        ability = _read_mana_ability(line, text)
        if ability is None:
            if text.card.produced_colors:
                unread.append(line)
        elif ability not in read:
            read.append(ability)
    return tuple(read), tuple(unread)


def _basic_land_abilities(face: Face) -> Iterable[ManaAbility]:
    seen: set[str] = set()
    for word in re.findall(r"[A-Za-z]+", face.type_line):
        kind = _BASIC_LAND_TYPES.get(word.lower())
        if kind is None or kind in seen:
            continue
        seen.add(kind)
        symbol = "{" + kind + "}"
        yield ManaAbility(produces=Fixed(ManaString.parse(symbol)), text=f"{{T}}: Add {symbol}.")


@dataclass(frozen=True)
class _Cost:
    taps: bool
    mana: ManaString
    life: int
    sacrifices: bool
    other: str | None


def _read_cost(cost: str, self_reference: str) -> _Cost:
    taps, sacrifices, life = False, False, 0
    mana = ManaString()
    other: list[str] = []
    for part in (piece.strip() for piece in cost.split(",")):
        symbols = ManaString.read(part)
        life_payment = re.fullmatch(r"pay (\d+) life", part, re.IGNORECASE)
        if part == "{T}":
            taps = True
        elif symbols:
            mana += symbols
        elif life_payment:
            life += int(life_payment.group(1))
        elif re.fullmatch(rf"sacrifice {self_reference}", part, re.IGNORECASE):
            sacrifices = True
        else:
            other.append(part)
    return _Cost(taps, mana, life, sacrifices, ", ".join(other) or None)


def _read_mana_ability(line: str, text: _FaceText) -> ManaAbility | None:
    activated = _ACTIVATED.match(_ABILITY_WORD.sub("", line))
    if activated is None or _TRIGGER_START.match(activated["cost"]):
        return None
    cost = _read_cost(activated["cost"], text.self_reference)
    if not (cost.taps or cost.sacrifices):
        return None
    sentences = _sentences(activated["effect"])
    adds = next((i for i, sentence in enumerate(sentences) if sentence.startswith("Add ")), None)
    produces: Produces | None = None
    assumptions: list[str] = []
    if adds is not None:
        produces, assumptions = _read_produces(sentences[adds], text.self_reference)
    if produces is None:
        produces = _one_mana_of_produced_colors(activated["effect"], text.card)
        if produces is None:
            return None
        assumptions = [AMOUNT_ASSUMED_ONE]
    life = cost.life
    restriction: Restriction | None = None
    for sentence in sentences[adds + 1 :] if adds is not None else ():
        damage = re.fullmatch(
            rf"{text.self_reference} deals (\d+) damage to you\.?", sentence, re.IGNORECASE
        )
        if sentence.startswith("Spend this mana only"):
            restriction, understood = _read_restriction(sentence)
            if not understood:
                assumptions.append(RESTRICTION_NOT_UNDERSTOOD)
        elif sentence.startswith(("Activate only", "Activate this ability only")):
            assumptions.append(IGNORES_ACTIVATION_CONDITION)
        elif re.match(r"^If\b.*\badd\b.*\binstead\b", sentence, re.IGNORECASE):
            assumptions.append(IGNORES_CONDITIONAL_BONUS)
        elif damage:
            life += int(damage.group(1))
    return ManaAbility(
        produces=produces,
        taps=cost.taps,
        mana_cost=cost.mana,
        life=life,
        sacrifices=cost.sacrifices,
        other_cost=cost.other,
        restriction=restriction,
        assumptions=tuple(dict.fromkeys(assumptions)),
        text=line,
    )


def _producible(text: str) -> ManaString | None:
    mana = ManaString.read(text.strip())
    return mana if mana and mana.can_be_produced() else None


def _any_color(text: str) -> AnyColor | None:
    """`one mana of any color` or `... in your commander's color identity`, for counted mana."""
    match = re.fullmatch(
        rf"{_AMOUNT} mana of any (?:one )?color(?P<identity> in your commander's color identity)?",
        text,
    )
    if match is None:
        return None
    scope = AnyColorScope.COMMANDER_IDENTITY if match["identity"] else AnyColorScope.ANY
    return AnyColor(_AMOUNTS[match["amount"]], scope)


# @spec READ-004, READ-005, READ-006, READ-011, READ-012, READ-013, READ-022, READ-023
def _read_produces(sentence: str, self_reference: str) -> tuple[Produces | None, list[str]]:
    """What an `Add ...` sentence makes, with any assumption; None when it cannot be read."""
    body = sentence.removeprefix("Add ").rstrip(".").strip()
    fixed = _producible(body)
    if fixed is not None:
        return Fixed(fixed), []
    options = [_producible(option) for option in _OPTION_SEPARATOR.split(body)]
    if len(options) >= 2 and all(options):
        return Choice(tuple(option for option in options if option)), []
    any_color = _any_color(body)
    if any_color is not None:
        return any_color, []
    if match := re.fullmatch(rf"{_AMOUNT} mana of any (?:color|type) that .+ could produce", body):
        return AnyColor(_AMOUNTS[match["amount"]]), [ASSUMES_ANY_COLOR]
    if match := re.fullmatch(rf"{_AMOUNT} mana in any combination of colors", body):
        return AnyColor(_AMOUNTS[match["amount"]]), [ASSUMES_ONE_COLOR]
    if match := re.fullmatch(r"(?P<mana>.+?) for each (?P<count>.+)", body):
        mana = _producible(match["mana"]) or _any_color(match["mana"])
        count = _read_count(match["count"], self_reference)
        if mana is not None and count is not None:
            return Counted(count, mana), []
    if match := re.fullmatch(
        r"an amount of (?P<mana>(?:\{[WUBRGC]\})+) equal to your devotion to (?P<colors>.+)", body
    ):
        devotion = _devotion(match["colors"])
        if devotion is not None:
            return Counted(devotion, ManaString.parse(match["mana"])), []
    if match := re.fullmatch(
        r"X mana of any one color, where X is your devotion to (?P<colors>.+)", body
    ):
        devotion = _devotion(match["colors"])
        if devotion is not None:
            return Counted(devotion, AnyColor()), []
    return None, []


def _read_count(text: str, self_reference: str) -> Count | None:
    if text == "card in your hand":
        return CardsInHandCount()
    if text == "card in your graveyard":
        return CardsInGraveyardCount()
    if match := re.fullmatch(r"(?P<word>[A-Za-z-]+) card in your graveyard", text):
        return CardsInGraveyardCount(match["word"])
    if match := re.fullmatch(r"(?P<word>[A-Za-z-]+) (?:you control|on the battlefield)", text):
        return PermanentsCount(match["word"])
    if match := re.fullmatch(
        rf"(?P<counter>[a-z-]+) counter on {self_reference}", text, re.IGNORECASE
    ):
        return CountersOnSelfCount(match["counter"])
    return None


def _devotion(text: str) -> DevotionCount | None:
    colors = [_COLOR_NAMES.get(word.strip().lower()) for word in _LIST_SEPARATOR.split(text)]
    if not colors or not all(colors):
        return None
    return DevotionCount(tuple(color for color in colors if color))


# @spec READ-014, READ-020
def _read_restriction(sentence: str) -> tuple[Restriction, bool]:
    """The restriction a `Spend this mana only ...` sentence states, and whether it was mapped."""
    match = re.fullmatch(
        r"Spend this mana only to cast (?:an? )?(?P<types>[a-z ,]+?) spells?"
        r"(?: or activate abilities of [^.]+)?\.?",
        sentence,
    )
    if match:
        types = tuple(word.strip().capitalize() for word in _LIST_SEPARATOR.split(match["types"]))
        if types and all(card_type in _CARD_TYPES for card_type in types):
            return Restriction(sentence, types), True
    return Restriction(sentence), False


# @spec READ-021
def _one_mana_of_produced_colors(effect: str, card: Card) -> Produces | None:
    """One mana of the ability's own colors, or else of the card's produced colors."""
    if not card.produced_colors:
        return None
    named = set(re.findall(r"\{([WUBRGC])\}", effect))
    kinds = [kind for kind in MANA_KINDS if kind in (named or set(card.produced_colors))]
    options = tuple(ManaString.parse("{" + kind + "}") for kind in kinds)
    if not options:
        return None
    return Fixed(options[0]) if len(options) == 1 else Choice(options)


# Step triggers

_WHOSE_PREFIXES: tuple[tuple[str, Whose], ...] = (
    ("your next ", Whose.CONTROLLER),
    ("your ", Whose.CONTROLLER),
    ("each opponent's ", Whose.OPPONENTS),
    ("each player's ", Whose.EACH),
    ("each ", Whose.EACH),
    ("the next ", Whose.EACH),
    ("the ", Whose.EACH),
)
_STEP_NAMES: tuple[tuple[Step, str], ...] = (
    (Step.UPKEEP, "upkeep"),
    (Step.DRAW, "draw step"),
    (Step.MAIN1, "(?:precombat|first) main phase"),
    (Step.MAIN2, "(?:postcombat|second) main phase"),
    (Step.END, "end step"),
)
_OPPONENTS_STEPS = (Step.UPKEEP, Step.DRAW, Step.END)


def _phrase(text: str) -> re.Pattern[str]:
    return re.compile(r"\bat the beginning of " + text + r"\b", re.IGNORECASE)


_STEP_PHRASES: tuple[tuple[Step, Whose, re.Pattern[str]], ...] = (
    *(
        (step, whose, _phrase(re.escape(prefix) + name))
        for step, name in _STEP_NAMES
        for prefix, whose in _WHOSE_PREFIXES
        if whose is not Whose.OPPONENTS or step in _OPPONENTS_STEPS
    ),
    (Step.BEGIN_COMBAT, Whose.CONTROLLER, _phrase("combat on your turn")),
    (Step.BEGIN_COMBAT, Whose.EACH, _phrase("each combat")),
)
_WHOSE_ORDER = (Whose.CONTROLLER, Whose.EACH, Whose.OPPONENTS)


# @spec READ-028, READ-029, READ-030, READ-031, READ-032, READ-033, READ-034, READ-035
# @spec READ-046, READ-047, READ-048, READ-052, READ-053, READ-054
def read_step_triggers(text: _FaceText) -> tuple[StepTrigger, ...]:
    """The face's beginning-of-step triggers, each step and `whose` pair once, in step order.

    `your` (and `your next`) reads as the controller's turn; `each`, `each player's`, `the`
    and `the next` as each turn; `each opponent's` as opponents' turns, for the upkeep, the
    draw step and the end step only. Any other wording naming opponents or other players
    matches no pattern and is no trigger.
    """
    rules_text = "\n".join(text.lines)
    found = {(step, whose) for step, whose, phrase in _STEP_PHRASES if phrase.search(rules_text)}
    return tuple(
        StepTrigger(step, whose)
        for step in STEPS
        for whose in _WHOSE_ORDER
        if (step, whose) in found
    )


# Haste, vigilance and flash

_CONDITION = re.compile(r"\b(?:as long as|during|if|unless|while)\b", re.IGNORECASE)
# A keyword given for a limited time: until end of turn, or gained this turn. A condition that
# only speaks of the turn (`As long as you've cast a spell this turn`) does not limit it.
_LIMITED_TIME = re.compile(r"\buntil end of turn\b|\bgains?\b[^.]*\bthis turn\b", re.IGNORECASE)
_GRANT = re.compile(
    r"(?:^|,\s*)(?:(?P<all>[Aa]ll creatures)"
    r"|(?P<other>[Oo]ther )?(?:[Cc]reatures|(?P<subtype>[A-Z][A-Za-z'-]*) creatures"
    r"|(?P<plural>[A-Z][A-Za-z'-]*s)) you control)"
    r" (?:get [^.]*? and )?have (?P<keywords>[^.]*)"
)
_NOT_SUBTYPES = frozenset(
    {
        "Artifact",
        "Attacking",
        "Black",
        "Blocking",
        "Blue",
        "Colorless",
        "Green",
        "Legendary",
        "Multicolored",
        "Nontoken",
        "Other",
        "Red",
        "Tapped",
        "Token",
        "Untapped",
        "White",
    }
)
_NOT_PLURAL_SUBTYPES = frozenset(
    {
        "Artifacts",
        "Creatures",
        "Enchantments",
        "Lands",
        "Others",
        "Permanents",
        "Planeswalkers",
        "Spells",
        "Tokens",
    }
)


# @spec READ-036, READ-037, READ-038, READ-039, READ-040, READ-044
def read_keyword(keyword: str, text: _FaceText) -> KeywordReading:
    """Whether the face has `keyword` itself, grants it to creatures you control, or neither.

    Only haste and vigilance are read as grants. Keywords given for a limited time and those
    conferred through attachment are not read.
    """
    own = False
    grant: KeywordGrant | None = None
    assumptions: list[str] = []
    for line in text.lines:
        if keyword in _keyword_line_items(line):
            own = True
            continue
        for sentence in _sentences(line):
            if _LIMITED_TIME.search(sentence):
                continue
            conditional = bool(_CONDITION.search(sentence))
            if _has_keyword_itself(keyword, sentence, text.self_reference):
                own = True
            elif keyword != "flash" and (found := _granted(keyword, sentence)) is not None:
                grant = found
            else:
                continue
            if conditional:
                assumptions.append(ASSUMES_CONDITION_MET)
    return KeywordReading(own=own, grant=grant, assumptions=tuple(dict.fromkeys(assumptions)))


def _keyword_line_items(line: str) -> tuple[str, ...]:
    """The keywords of a keyword line (`Flying, vigilance`); empty for an ability sentence."""
    if line.endswith(".") or ":" in line:
        return ()
    return tuple(item.strip().lower() for item in line.split(","))


def _keyword_named(keyword: str, listed: str) -> bool:
    listed = _CONDITION.split(listed, maxsplit=1)[0]
    return keyword in re.findall(r"[a-z]+", listed.lower())


def _has_keyword_itself(keyword: str, sentence: str, self_reference: str) -> bool:
    match = re.search(
        rf"\b{self_reference} (?:gets [^.]*? and )?has (?P<keywords>[^.]*)",
        sentence,
        re.IGNORECASE,
    )
    return match is not None and _keyword_named(keyword, match["keywords"])


def _granted(keyword: str, sentence: str) -> KeywordGrant | None:
    match = _GRANT.search(sentence)
    if match is None or not _keyword_named(keyword, match["keywords"]):
        return None
    subtype: str | None = match["subtype"]
    if subtype in _NOT_SUBTYPES:
        return None
    plural: str | None = match["plural"]
    if plural is not None:
        if plural in _NOT_PLURAL_SUBTYPES:
            return None
        subtype = _singular(plural)
    return KeywordGrant(includes_self=not match["other"], subtype=subtype)


_SINGULAR_ENDING_IE = frozenset({"Faeries", "Zombies"})


def _singular(plural: str) -> str:
    """A plural creature subtype in its singular form: Goblins, Elves, Allies, Zombies."""
    if plural.endswith("ves"):
        return plural[:-3] + "f"
    if plural.endswith("ies") and plural not in _SINGULAR_ENDING_IE:
        return plural[:-3] + "y"
    return plural[:-1]


# Entering tapped


# @spec READ-041, READ-042, READ-043
def read_enters_tapped(text: _FaceText) -> EntersTappedReading:
    """Whether the permanent enters tapped; conditional text is read as untapped, assumed."""
    enters_tapped = re.compile(
        rf"\b{text.self_reference} enters(?: the battlefield)? tapped", re.IGNORECASE
    )
    for line in text.lines:
        sentences = _sentences(line)
        for index, sentence in enumerate(sentences):
            if not enters_tapped.search(sentence):
                continue
            condition = _entering_condition(sentence, sentences[:index])
            if condition is None:
                return EntersTappedReading(tapped=True)
            return EntersTappedReading(assumptions=(ASSUMES_UNTAPPED_PREFIX + condition,))
    return ENTERS_UNTAPPED


_STAYS_TAPPED = re.compile(r",? and (?:it )?(?:doesn't|does not) untap during [^.]*", re.IGNORECASE)


def _entering_condition(sentence: str, before: list[str]) -> str | None:
    """The condition or choice an enters-tapped sentence is subject to, as written.

    A rider saying the permanent does not untap is not a condition on entering tapped.
    """
    sentence = _STAYS_TAPPED.sub("", sentence)
    if match := re.search(r"\bunless (?P<condition>[^.]+)", sentence):
        return "unless " + match["condition"]
    if re.match(r"^If you don't\b", sentence) and before:
        return re.sub(r"^As .+? enters, ", "", before[-1]).rstrip(".")
    if match := re.match(r"^If (?P<condition>[^,]+),", sentence):
        return "if " + match["condition"]
    if _CONDITION.search(sentence) or re.search(r"\byou may\b", sentence, re.IGNORECASE):
        return sentence.rstrip(".")
    return None
