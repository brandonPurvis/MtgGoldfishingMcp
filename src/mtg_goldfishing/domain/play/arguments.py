"""Reading the structured arguments of `play`, `effect` and `choose` into value objects.

Arguments arrive as received (plain mappings, lists and strings). A malformed one is
returned as an error; nothing here raises for bad input.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from mtg_goldfishing.domain.deck.definitions import read_definition
from mtg_goldfishing.domain.deck.model import CardDefinition
from mtg_goldfishing.domain.events import Error, ErrorKind
from mtg_goldfishing.domain.game.model import Destination, TokenSpec
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
_CHOICES_KEYS = ("x", "extra_cost", "modes", "targets", "notes", "definition")
_TOKEN_KEYS = ("name", "count", "types", "pt", "produces", "sacrifice_to_produce", "tapped")
_LOOK_KEYS = ("n", "from", "rest")
_SEARCH_KEYS = ("filter",)

Names = tuple[str, ...]
ByDestination = tuple[tuple[Destination, Names], ...]


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
class Delta:
    """The outcome of a play or effect, applied in the fixed order of its fields."""

    untap: Names = ()
    tap: Names = ()
    mana: ManaString | None = None
    tokens: tuple[TokenSpec, ...] = ()
    counters: tuple[CounterChange, ...] = ()
    move: ByDestination = ()
    commander_stays: bool = False
    discard: Names = ()
    fetch: ByDestination = ()
    draw: int = 0
    life: int = 0
    damage: int = 0
    shuffle: bool = False
    look: Look | None = None
    search: Search | None = None

    def __post_init__(self) -> None:
        if self.look is not None and self.search is not None:
            raise ValueError("a delta holds a look or a search, not both")
        if self.draw < 0:
            raise ValueError("a delta draws no fewer than zero cards")


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


# @spec PLAY-005, PLAY-057, APP-028
def read_delta(data: object) -> Delta | Error:
    """Read a delta as received: unknown keys, bad mana and unknown destinations are errors."""
    if data is None:
        return Delta()
    if not isinstance(data, Mapping):
        return _malformed("delta")
    unknown = _unknown(data, DELTA_KEYS)
    if unknown:
        return Error(ErrorKind.UNKNOWN_DELTA_KEY, subject=unknown[0], names=DELTA_KEYS)
    if data.get("look") is not None and data.get("search") is not None:
        return Error(ErrorKind.LOOK_AND_SEARCH)
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
    }
    for key in DELTA_KEYS:
        if data.get(key) is None:
            continue
        read = readers[key](data[key])
        if isinstance(read, Error):
            return read
        fields[key] = read
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


# @spec PLAY-005, PLAY-070, APP-028
def read_expect(data: object) -> tuple[Expectation, ...] | Error:
    """Read `expect`; any key not allowed is an error listing the allowed keys."""
    if data is None:
        return ()
    if not isinstance(data, Mapping):
        return _malformed("expect")
    unknown = _unknown(data, EXPECT_KEYS)
    if unknown:
        return Error(ErrorKind.UNKNOWN_EXPECT_KEY, subject=unknown[0], names=EXPECT_KEYS)
    expectations: list[Expectation] = []
    for key in EXPECT_KEYS:
        if key not in data:
            continue
        value = _read_expected(key, data[key])
        if isinstance(value, Error):
            return value
        expectations.append(Expectation(key, value))
    return tuple(expectations)


# ----------------------------------------------------------------------------- selections


# @spec APP-028
def read_selections(data: object) -> ByDestination | Error:
    if data is None:
        return ()
    return read_by_destination(data, "selections")


def read_rest_order(data: object) -> Names | Error:
    if data is None:
        return ()
    return read_names(data, "rest_order")
