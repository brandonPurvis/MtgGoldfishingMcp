"""Reading the structured arguments of `play`, `effect` and `choose` into value objects.

Arguments arrive as received (plain mappings, lists and strings). A malformed one is
returned as an error; nothing here raises for bad input.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from mtg_goldfishing.domain.deck.definitions import read_definition
from mtg_goldfishing.domain.deck.model import CardDefinition
from mtg_goldfishing.domain.events import Error, ErrorKind
from mtg_goldfishing.domain.game.model import Destination, TokenSpec
from mtg_goldfishing.domain.game.seats import SeatNumber
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.steps import Step

DELTA_KEYS: tuple[str, ...] = (
    "untap",
    "tap",
    "mana",
    "tokens",
    "counters",
    "move",
    "commander_stays",
    "discard",
    "fetch",
    "draw",
    "life",
    "damage",
    "shuffle",
    "look",
    "search",
)
CONTESTED_DELTA_KEYS: tuple[str, ...] = (
    "counter",
    "untap",
    "tap",
    "mana",
    "tokens",
    "counters",
    "control",
    "move",
    "commander_stays",
    "discard",
    "fetch",
    "draw",
    "life",
    "damage",
    "shuffle",
    "ask",
    "look_at_hand",
    "look",
    "search",
)
"""The delta keys of a contested game, in the order they are applied."""
EXPECT_KEYS: tuple[str, ...] = (
    "hand",
    "lands",
    "untapped_lands",
    "life",
    "pool",
    "library",
    "tax",
    "damage_dealt",
    "step",
)
CONTESTED_EXPECT_KEYS: tuple[str, ...] = tuple(key for key in EXPECT_KEYS if key != "damage_dealt")
_CHOICES_KEYS = ("x", "extra_cost", "modes", "targets", "notes", "definition")
_TOKEN_KEYS = ("name", "count", "types", "pt", "produces", "sacrifice_to_produce", "tapped")
_LOOK_KEYS = ("n", "from", "rest")
_SEARCH_KEYS = ("filter",)
_ASK_KEYS = ("seats", "text")
_REVEALS = ("look", "search", "look_at_hand")

Names = tuple[str, ...]
ByDestination = tuple[tuple[Destination, Names], ...]
BySeat = tuple[tuple[SeatNumber, int], ...]
"""Signed amounts by seat number, in the order given."""


def _malformed(subject: str, names: Names = ()) -> Error:
    return Error(ErrorKind.MALFORMED_ARGUMENT, subject=subject, names=names)


def _whole(value: object, minimum: int | None = None) -> int | None:
    """The value as a whole number of at least `minimum`, or None when it is not one."""
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    if minimum is not None and value < minimum:
        return None
    return value


def _unknown(data: Mapping[object, object], allowed: tuple[str, ...]) -> Names:
    return tuple(sorted(str(key) for key in data if key not in allowed))


def read_names(value: object, subject: str) -> Names | Error:
    """A list of card names, or one name on its own."""
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return _malformed(subject)


def read_destination(value: object) -> Destination | Error:
    destination = Destination.named(value) if isinstance(value, str) else None
    if destination is None:
        return Error(ErrorKind.UNKNOWN_DESTINATION, subject=str(value))
    return destination


def read_by_destination(value: object, subject: str) -> ByDestination | Error:
    """`{ destination: [name] }`, keeping the order given."""
    if not isinstance(value, Mapping):
        return _malformed(subject)
    entries: list[tuple[Destination, Names]] = []
    for key, names in value.items():
        destination = read_destination(key)
        if isinstance(destination, Error):
            return destination
        read = read_names(names, f"{subject}.{key}")
        if isinstance(read, Error):
            return read
        entries.append((destination, read))
    return tuple(entries)


def read_mana(value: object, *, produced: bool) -> ManaString | Error:
    """A mana string; mana to be made may hold only colors, colorless and numbers."""
    mana = ManaString.read(value) if isinstance(value, str) else None
    if mana is None or (produced and not mana.can_be_produced()):
        return Error(ErrorKind.UNPARSEABLE_MANA, subject=str(value))
    return mana


# ---------------------------------------------------------------------------------- delta


@dataclass(frozen=True)
class Look:
    """Reveal up to `n` cards from one end of the library; the rest go to `rest`."""

    n: int
    from_bottom: bool
    rest: Destination

    def __post_init__(self) -> None:
        if self.n < 1:
            raise ValueError("a look reveals at least one card")


@dataclass(frozen=True)
class Search:
    """Reveal the library sorted by name, limited to cards matching `filter`."""

    filter: str | None = None


@dataclass(frozen=True)
class CounterChange:
    card: str
    changes: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class AskEntry:
    """What an effect requires of other seats: `seats` by number, or every other seat still
    in the game when `opponents`; `text` says what is required."""

    text: str
    seats: tuple[SeatNumber, ...] = ()
    opponents: bool = False

    def __post_init__(self) -> None:
        if self.opponents == bool(self.seats):
            raise ValueError("an ask names its seats, or the opponents, and not both")


@dataclass(frozen=True)
class Delta:
    """The outcome of a play or effect, applied in the fixed order of its fields.

    `counter`, `life_by_seat`, `damage_by_seat`, `control`, `ask` and `look_at_hand`
    belong to a contested game; `damage` to a goldfish game.
    """

    counter: Names = ()
    untap: Names = ()
    tap: Names = ()
    mana: ManaString | None = None
    tokens: tuple[TokenSpec, ...] = ()
    counters: tuple[CounterChange, ...] = ()
    control: tuple[tuple[SeatNumber, Names], ...] = ()
    move: ByDestination = ()
    commander_stays: bool = False
    discard: Names = ()
    fetch: ByDestination = ()
    draw: int = 0
    life: int = 0
    life_by_seat: BySeat = ()
    damage: int = 0
    damage_by_seat: BySeat = ()
    shuffle: bool = False
    ask: tuple[AskEntry, ...] = ()
    look_at_hand: SeatNumber | None = None
    look: Look | None = None
    search: Search | None = None

    def __post_init__(self) -> None:
        reveals = [self.look, self.search, self.look_at_hand]
        if sum(reveal is not None for reveal in reveals) > 1:
            raise ValueError("a delta holds one of look, search and look_at_hand at most")
        if self.draw < 0:
            raise ValueError("a delta draws no fewer than zero cards")

    @property
    def creates_choices(self) -> tuple[str, ...]:
        """The keys it holds that create pending choices."""
        held = {
            "ask": bool(self.ask),
            "look_at_hand": self.look_at_hand is not None,
            "look": self.look is not None,
            "search": self.search is not None,
        }
        return tuple(key for key, given in held.items() if given)

    @property
    def seats_named(self) -> tuple[SeatNumber, ...]:
        """Every seat number the delta names, in the order its keys give them."""
        named = [seat for seat, _ in self.control]
        named += [seat for seat, _ in self.life_by_seat]
        named += [seat for seat, _ in self.damage_by_seat]
        named += [seat for entry in self.ask for seat in entry.seats]
        if self.look_at_hand is not None:
            named.append(self.look_at_hand)
        return tuple(named)


def _read_token(value: object) -> TokenSpec | Error:
    if not isinstance(value, Mapping):
        return _malformed("tokens")
    unknown = _unknown(value, _TOKEN_KEYS)
    if unknown:
        return _malformed("tokens", unknown)
    name, types = value.get("name"), value.get("types")
    if not isinstance(name, str) or not name.strip():
        return _malformed("tokens.name")
    if not isinstance(types, str):
        return _malformed("tokens.types")
    count = _whole(value.get("count", 1), minimum=1)
    if count is None:
        return _malformed("tokens.count")
    pt = value.get("pt")
    if pt is not None and not isinstance(pt, str):
        return _malformed("tokens.pt")
    produces: list[ManaString] = []
    if value.get("produces") is not None:
        options = read_names(value["produces"], "tokens.produces")
        if isinstance(options, Error):
            return options
        for option in options:
            mana = read_mana(option, produced=True)
            if isinstance(mana, Error):
                return mana
            produces.append(mana)
    flags: dict[str, bool] = {}
    for flag in ("sacrifice_to_produce", "tapped"):
        setting = value.get(flag, False)
        if not isinstance(setting, bool):
            return _malformed(f"tokens.{flag}")
        flags[flag] = setting
    return TokenSpec(
        name=name.strip(),
        types=types,
        count=count,
        pt=pt,
        produces=tuple(produces),
        sacrifice_to_produce=flags["sacrifice_to_produce"],
        tapped=flags["tapped"],
    )


def _read_counters(value: object) -> tuple[CounterChange, ...] | Error:
    if not isinstance(value, Mapping):
        return _malformed("counters")
    changes: list[CounterChange] = []
    for card, kinds in value.items():
        if not isinstance(card, str) or not isinstance(kinds, Mapping):
            return _malformed("counters")
        amounts: list[tuple[str, int]] = []
        for kind, amount in kinds.items():
            change = _whole(amount)
            if not isinstance(kind, str) or not kind.strip() or change is None:
                return _malformed(f"counters.{card}")
            amounts.append((kind.strip(), change))
        changes.append(CounterChange(card, tuple(amounts)))
    return tuple(changes)


def _read_look(value: object) -> Look | Error:
    if not isinstance(value, Mapping):
        return _malformed("look")
    unknown = _unknown(value, _LOOK_KEYS)
    if unknown:
        return _malformed("look", unknown)
    n = _whole(value.get("n"), minimum=1)
    if n is None:
        return _malformed("look.n")
    end = value.get("from", "top")
    if end not in ("top", "bottom"):
        return _malformed("look.from")
    if value.get("rest") is None:
        return Error(ErrorKind.LOOK_WITHOUT_REST)
    rest = read_destination(value["rest"])
    if isinstance(rest, Error):
        return rest
    return Look(n, end == "bottom", rest)


def _read_search(value: object) -> Search | Error:
    if not isinstance(value, Mapping):
        return _malformed("search")
    unknown = _unknown(value, _SEARCH_KEYS)
    if unknown:
        return _malformed("search", unknown)
    text = value.get("filter")
    if text is not None and not isinstance(text, str):
        return _malformed("search.filter")
    return Search(text.strip() or None) if text is not None else Search()


def _read_int(value: object, key: str, *, minimum: int | None = None) -> int | Error:
    whole = _whole(value, minimum)
    return _malformed(key) if whole is None else whole


def _read_bool(value: object, key: str) -> bool | Error:
    return value if isinstance(value, bool) else _malformed(key)


def _seat_number(value: object) -> SeatNumber | None:
    """A seat number given as a whole number from 1, or as text holding one (a JSON key)."""
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        return None
    return SeatNumber(value)


def _read_by_seat(value: object, key: str) -> BySeat | Error:
    """`{ seat number: signed amount }`."""
    if not isinstance(value, Mapping):
        return _malformed(key)
    amounts: list[tuple[SeatNumber, int]] = []
    for seat_text, amount in value.items():
        seat = _seat_number(seat_text)
        change = _whole(amount)
        if seat is None or change is None:
            return _malformed(key)
        amounts.append((seat, change))
    return tuple(amounts)


def _read_control(value: object) -> tuple[tuple[SeatNumber, Names], ...] | Error:
    """`{ seat number: [name] }`: the permanents each seat now controls."""
    if not isinstance(value, Mapping):
        return _malformed("control")
    entries: list[tuple[SeatNumber, Names]] = []
    for seat_text, names in value.items():
        seat = _seat_number(seat_text)
        read = read_names(names, "control")
        if seat is None or isinstance(read, Error):
            return _malformed("control")
        entries.append((seat, read))
    return tuple(entries)


def _read_ask_entry(value: object) -> AskEntry | Error:
    if not isinstance(value, Mapping) or set(value) != set(_ASK_KEYS):
        return _malformed("ask", _unknown(value, _ASK_KEYS) if isinstance(value, Mapping) else ())
    text, seats = value["text"], value["seats"]
    if not isinstance(text, str) or not text.strip():
        return _malformed("ask.text")
    if seats == "opponents":
        return AskEntry(text.strip(), opponents=True)
    if not isinstance(seats, list) or not seats:
        return _malformed("ask.seats")
    numbers = [_seat_number(seat) if not isinstance(seat, str) else None for seat in seats]
    if any(number is None for number in numbers):
        return _malformed("ask.seats")
    return AskEntry(text.strip(), seats=tuple(n for n in numbers if n is not None))


def _read_ask(value: object) -> tuple[AskEntry, ...] | Error:
    if not isinstance(value, list) or not value:
        return _malformed("ask")
    entries: list[AskEntry] = []
    for item in value:
        entry = _read_ask_entry(item)
        if isinstance(entry, Error):
            return entry
        entries.append(entry)
    return tuple(entries)


# @spec PLAY-125
def _read_counter(value: object) -> Names | Error:
    """`counter`: a list of stack item ids or names of spells' cards on the stack."""
    if not isinstance(value, list) or not all(
        isinstance(entry, str) and entry.strip() for entry in value
    ):
        return _malformed("counter")
    return tuple(entry.strip() for entry in value)


def _read_look_at_hand(value: object) -> SeatNumber | Error:
    seat = None if isinstance(value, str) else _seat_number(value)
    return _malformed("look_at_hand") if seat is None else seat


# @spec PLAY-005, PLAY-057, PLAY-074, PLAY-075, PLAY-076, PLAY-126, PLAY-127, PLAY-128
# @spec APP-028
def read_delta(data: object, *, contested: bool = False) -> Delta | Error:
    """Read a delta as received: unknown keys, bad mana and unknown destinations are errors.

    A goldfish game's delta may not use what only a contested game has (`control`, `ask`,
    `look_at_hand`, `life` or `damage` as a map from seat number); a contested game's gives
    `damage` only as such a map.
    """
    if data is None:
        return Delta()
    if not isinstance(data, Mapping):
        return _malformed("delta")
    keys = CONTESTED_DELTA_KEYS if contested else DELTA_KEYS
    unknown = _unknown(data, CONTESTED_DELTA_KEYS)
    if unknown:
        return Error(ErrorKind.UNKNOWN_DELTA_KEY, subject=unknown[0], names=keys)
    if not contested:
        only = [k for k in CONTESTED_DELTA_KEYS if k not in DELTA_KEYS and data.get(k) is not None]
        only += [k for k in ("life", "damage") if isinstance(data.get(k), Mapping)]
        if only:
            return Error(ErrorKind.CONTESTED_ONLY, subject=only[0])
    if data.get("look") is not None and data.get("search") is not None:
        return Error(ErrorKind.LOOK_AND_SEARCH)
    if sum(data.get(key) is not None for key in _REVEALS) > 1:
        return Error(ErrorKind.TOO_MANY_REVEALS)
    if contested and data.get("damage") is not None and not isinstance(data["damage"], Mapping):
        return Error(ErrorKind.DAMAGE_NEEDS_SEATS)
    fields: dict[str, object] = {}
    readers: dict[str, Callable[[object], object]] = {
        "untap": lambda v: read_names(v, "untap"),
        "tap": lambda v: read_names(v, "tap"),
        "mana": lambda v: read_mana(v, produced=True),
        "tokens": _read_tokens,
        "counters": _read_counters,
        "move": lambda v: read_by_destination(v, "move"),
        "commander_stays": lambda v: _read_bool(v, "commander_stays"),
        "discard": lambda v: read_names(v, "discard"),
        "fetch": lambda v: read_by_destination(v, "fetch"),
        "draw": lambda v: _read_int(v, "draw", minimum=0),
        "life": lambda v: _read_int(v, "life"),
        "damage": lambda v: _read_int(v, "damage"),
        "shuffle": lambda v: _read_bool(v, "shuffle"),
        "look": _read_look,
        "search": _read_search,
        "control": _read_control,
        "counter": _read_counter,
        "ask": _read_ask,
        "look_at_hand": _read_look_at_hand,
    }
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        field_name = key
        if key in ("life", "damage") and isinstance(value, Mapping):
            read: object = _read_by_seat(value, key)
            field_name = f"{key}_by_seat"
        else:
            read = readers[key](value)
        if isinstance(read, Error):
            return read
        fields[field_name] = read
    return Delta(**fields)  # type: ignore[arg-type]


def _read_tokens(value: object) -> tuple[TokenSpec, ...] | Error:
    entries = value if isinstance(value, list) else [value]
    specs: list[TokenSpec] = []
    for entry in entries:
        spec = _read_token(entry)
        if isinstance(spec, Error):
            return spec
        specs.append(spec)
    return tuple(specs)


# -------------------------------------------------------------------------------- choices


@dataclass(frozen=True)
class Choices:
    """What a player announces while casting. Modes, targets and notes are recorded only."""

    x: int | None = None
    extra_cost: ManaString | None = None
    modes: Names = ()
    targets: Names = ()
    notes: str | None = None
    definition: CardDefinition | None = None

    def __post_init__(self) -> None:
        if self.x is not None and self.x < 0:
            raise ValueError("X is never negative")


def _recorded(value: object) -> Names:
    """Modes and targets are never judged: whatever was given is kept as text."""
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return (str(value),)


# @spec PLAY-055, APP-028
def read_choices(data: object) -> Choices | Error:
    if data is None:
        return Choices()
    if not isinstance(data, Mapping):
        return _malformed("choices")
    unknown = _unknown(data, _CHOICES_KEYS)
    if unknown:
        return _malformed("choices", unknown)
    x = None
    if data.get("x") is not None:
        read_x = _read_int(data["x"], "choices.x", minimum=0)
        if isinstance(read_x, Error):
            return read_x
        x = read_x
    extra = None
    if data.get("extra_cost") is not None:
        read_extra = read_mana(data["extra_cost"], produced=False)
        if isinstance(read_extra, Error):
            return read_extra
        extra = read_extra
    definition = None
    if data.get("definition") is not None:
        read = read_definition(data["definition"])
        if isinstance(read, Error):
            return read
        definition = read
    return Choices(
        x=x,
        extra_cost=extra,
        modes=_recorded(data["modes"]) if data.get("modes") is not None else (),
        targets=_recorded(data["targets"]) if data.get("targets") is not None else (),
        notes=str(data["notes"]) if data.get("notes") is not None else None,
        definition=definition,
    )


# --------------------------------------------------------------------------- cast triggers

_CAST_TRIGGER_KEYS = ("source", "delta", "choices")


@dataclass(frozen=True)
class CastTrigger:
    """A triggered ability of the casting seat's own on casting the spell, stated with the
    `play` that casts it: what triggered, its delta read and as stated, and its choices,
    which are recorded only."""

    source: str
    delta: Delta
    stated: dict[str, object]
    choices: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("a cast trigger names what triggered")


def _copied(data: Mapping[object, object]) -> dict[str, object]:
    return {str(key): copy.deepcopy(value) for key, value in data.items()}


def _read_cast_trigger(entry: object, index: int, *, contested: bool) -> CastTrigger | Error:
    subject = f"cast_triggers[{index}]"
    if not isinstance(entry, Mapping):
        return _malformed(subject)
    unknown = _unknown(entry, _CAST_TRIGGER_KEYS)
    if unknown:
        return _malformed(f"{subject}.{unknown[0]}", _CAST_TRIGGER_KEYS)
    source, delta, choices = entry.get("source"), entry.get("delta"), entry.get("choices")
    if not isinstance(source, str) or not source.strip():
        return _malformed(f"{subject}.source")
    if not isinstance(delta, Mapping):
        return _malformed(f"{subject}.delta")
    if choices is not None and not isinstance(choices, Mapping):
        return _malformed(f"{subject}.choices")
    read = read_delta(delta, contested=contested)
    if isinstance(read, Error):
        return read
    if not contested and (read.look is not None or read.search is not None):
        return Error(ErrorKind.CAST_TRIGGER_REVEALS, subject=source)
    return CastTrigger(
        source, read, _copied(delta), _copied(choices) if choices is not None else None
    )


# @spec PLAY-131, PLAY-137, PLAY-142
def read_cast_triggers(data: object, *, contested: bool) -> tuple[CastTrigger, ...] | Error:
    """`play`'s `cast_triggers`, in the order listed: each an object with a `source` holding
    more than whitespace, a `delta` object, possibly empty, and optionally a `choices` object,
    and nothing else. Each delta is read as any delta of that kind of game is; in a goldfish
    game it may not hold `look` or `search`. The choices are kept as stated, never read."""
    if data is None:
        return ()
    if not isinstance(data, list | tuple):
        return _malformed("cast_triggers")
    triggers: list[CastTrigger] = []
    for index, entry in enumerate(data):
        read = _read_cast_trigger(entry, index, contested=contested)
        if isinstance(read, Error):
            return read
        triggers.append(read)
    return tuple(triggers)


# --------------------------------------------------------------------------------- expect

ExpectedValue = int | ManaString | Step


@dataclass(frozen=True)
class Expectation:
    """One value the agent believes will hold once the call is applied."""

    key: str
    value: ExpectedValue

    def __post_init__(self) -> None:
        if self.key not in EXPECT_KEYS:
            raise ValueError(f"not an expect key: {self.key}")


def _read_expected(key: str, value: object) -> ExpectedValue | Error:
    if key == "pool":
        if isinstance(value, str) and value.strip() in ("", "{}"):
            return ManaString()
        return read_mana(value, produced=True)
    if key == "step":
        step = Step.named(value) if isinstance(value, str) else None
        return step if step is not None else Error(ErrorKind.UNKNOWN_STEP, subject=str(value))
    return _read_int(value, f"expect.{key}")


# @spec PLAY-005, PLAY-070, PLAY-108, APP-028
def read_expect(data: object, *, contested: bool = False) -> tuple[Expectation, ...] | Error:
    """Read `expect`; any key not allowed is an error listing the allowed keys. A contested
    game has no `damage_dealt`."""
    if data is None:
        return ()
    if not isinstance(data, Mapping):
        return _malformed("expect")
    allowed = CONTESTED_EXPECT_KEYS if contested else EXPECT_KEYS
    unknown = _unknown(data, allowed)
    if unknown:
        return Error(ErrorKind.UNKNOWN_EXPECT_KEY, subject=unknown[0], names=allowed)
    expectations: list[Expectation] = []
    for key in allowed:
        if key not in data:
            continue
        value = _read_expected(key, data[key])
        if isinstance(value, Error):
            return value
        expectations.append(Expectation(key, value))
    return tuple(expectations)


# ----------------------------------------------------------------------------- selections


def read_blocks(data: object) -> tuple[tuple[str, str], ...] | Error:
    """`{ blocker: attacker }`, keeping the order given."""
    if data is None:
        return ()
    if not isinstance(data, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        return _malformed("blocks")
    return tuple((str(key), str(value)) for key, value in data.items())


# @spec APP-028
def read_selections(data: object) -> ByDestination | Error:
    if data is None:
        return ()
    return read_by_destination(data, "selections")


def read_rest_order(data: object) -> Names | Error:
    if data is None:
        return ()
    return read_names(data, "rest_order")
