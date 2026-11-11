"""A small library of cards with their readings given by hand.

Domain tests arrange games from these, so a test of payment or play does not depend on
the card reader reading text correctly.
"""

from __future__ import annotations

from dataclasses import replace

from mtg_goldfishing.domain.cards import Card, Face
from mtg_goldfishing.domain.mana import ManaString, Restriction
from mtg_goldfishing.domain.reading.model import (
    AnyColor,
    AnyColorScope,
    CardReading,
    Choice,
    Counted,
    EntersTappedReading,
    FaceReading,
    Fixed,
    KeywordGrant,
    KeywordReading,
    ManaAbility,
    PermanentsCount,
    StepTrigger,
    Whose,
)
from mtg_goldfishing.domain.steps import Step

M = ManaString.parse


def taps_for(mana: str, **options: object) -> ManaAbility:
    return ManaAbility(produces=Fixed(M(mana)), **options)  # type: ignore[arg-type]


def taps_for_either(*mana: str, **options: object) -> ManaAbility:
    return ManaAbility(produces=Choice(tuple(M(m) for m in mana)), **options)  # type: ignore[arg-type]


def taps_for_any(amount: int = 1, **options: object) -> ManaAbility:
    return ManaAbility(produces=AnyColor(amount), **options)  # type: ignore[arg-type]


def _card(
    name: str,
    cost: str,
    type_line: str,
    text: str = "",
    *,
    pt: str | None = None,
    identity: str = "",
) -> Card:
    power, toughness = pt.split("/") if pt else (None, None)
    face = Face(name, M(cost), type_line, text, power, toughness)
    return Card(name, (face,), color_identity=tuple(identity))


def _reading(**fields: object) -> CardReading:
    return CardReading((FaceReading(**fields),))  # type: ignore[arg-type]


OWN = KeywordReading(own=True)

LIBRARY: dict[str, tuple[Card, CardReading]] = {}


def _add(card: Card, reading: CardReading | None = None) -> None:
    LIBRARY[card.name] = (card, reading or CardReading((FaceReading(),)))


for land, color in [
    ("Forest", "G"),
    ("Island", "U"),
    ("Plains", "W"),
    ("Swamp", "B"),
    ("Mountain", "R"),
]:
    _add(
        _card(land, "", f"Basic Land — {land}", identity=color),
        _reading(mana_abilities=(taps_for("{" + color + "}"),)),
    )

_add(_card("Wastes", "", "Basic Land"), _reading(mana_abilities=(taps_for("{C}"),)))
_add(
    _card("Command Tower", "", "Land"),
    _reading(mana_abilities=(ManaAbility(AnyColor(1, AnyColorScope.COMMANDER_IDENTITY)),)),
)
_add(
    _card("City of Brass", "", "Land"),
    _reading(mana_abilities=(taps_for_any(life=1),)),
)
_add(
    _card("Caves of Koilos", "", "Land", identity="WB"),
    _reading(mana_abilities=(taps_for("{C}"), taps_for_either("{W}", "{B}", life=1))),
)
_add(
    _card("Mishra's Workshop", "", "Land"),
    _reading(
        mana_abilities=(
            taps_for(
                "{C}{C}{C}",
                restriction=Restriction(
                    "Spend this mana only to cast artifact spells.", ("Artifact",)
                ),
            ),
        )
    ),
)
_add(
    _card("Temple of Plenty", "", "Land — Temple", identity="GW"),
    _reading(
        mana_abilities=(taps_for_either("{G}", "{W}"),),
        enters_tapped=EntersTappedReading(tapped=True),
    ),
)
_add(
    _card("Glacial Fortress", "", "Land", identity="WU"),
    _reading(
        mana_abilities=(taps_for_either("{W}", "{U}"),),
        enters_tapped=EntersTappedReading(
            assumptions=("assumes it enters untapped: unless you control a Plains or an Island",)
        ),
    ),
)
_add(
    _card("Gaea's Cradle", "", "Legendary Land"),
    _reading(mana_abilities=(ManaAbility(Counted(PermanentsCount("creature"), M("{G}"))),)),
)
_add(_card("Sol Ring", "{1}", "Artifact"), _reading(mana_abilities=(taps_for("{C}{C}"),)))
_add(
    _card("Arcane Signet", "{2}", "Artifact"),
    _reading(mana_abilities=(ManaAbility(AnyColor(1, AnyColorScope.COMMANDER_IDENTITY)),)),
)
_add(
    _card("Azorius Signet", "{2}", "Artifact", identity="WU"),
    _reading(mana_abilities=(taps_for("{W}{U}", mana_cost=M("{1}")),)),
)
_add(
    _card("Lotus Petal", "{0}", "Artifact"),
    _reading(mana_abilities=(taps_for_any(sacrifices=True),)),
)
_add(
    _card("Mana Vault", "{1}", "Artifact"),
    _reading(mana_abilities=(taps_for("{C}{C}{C}"),)),
)
_add(
    _card("Llanowar Elves", "{G}", "Creature — Elf Druid", pt="1/1", identity="G"),
    _reading(mana_abilities=(taps_for("{G}"),)),
)
_add(
    _card("Birds of Paradise", "{G}", "Creature — Bird", pt="0/1", identity="G"),
    _reading(mana_abilities=(taps_for_any(),)),
)
_add(
    _card("Elvish Guidance Lord", "{1}{G}", "Creature — Elf", pt="2/2", identity="G"),
    _reading(
        mana_abilities=(
            ManaAbility(
                Fixed(M("{G}{G}")),
                restriction=Restriction(
                    "Spend this mana only to cast creature spells.", ("Creature",)
                ),
            ),
        )
    ),
)
_add(_card("Grizzly Bears", "{1}{G}", "Creature — Bear", pt="2/2", identity="G"))
_add(_card("Tarmogoyf", "{1}{G}", "Creature — Lhurgoyf", pt="*/1+*", identity="G"))
_add(_card("Shivan Dragon", "{4}{R}{R}", "Creature — Dragon", pt="5/5", identity="R"))
_add(
    _card("Goblin Guide", "{R}", "Creature — Goblin Scout", pt="2/2", identity="R"),
    _reading(haste=OWN),
)
_add(
    _card("Serra Angel", "{3}{W}{W}", "Creature — Angel", pt="4/4", identity="W"),
    _reading(vigilance=OWN),
)
_add(
    _card("Concordant Crossroads", "{G}", "World Enchantment", identity="G"),
    _reading(haste=KeywordReading(grant=KeywordGrant(includes_self=True))),
)
_add(
    _card("Goblin Warchief", "{1}{R}{R}", "Creature — Goblin", pt="2/2", identity="R"),
    _reading(haste=KeywordReading(grant=KeywordGrant(includes_self=True, subtype="Goblin"))),
)
_add(
    _card("Phyrexian Arena", "{1}{B}{B}", "Enchantment", identity="B"),
    _reading(step_triggers=(StepTrigger(Step.UPKEEP),)),
)
_add(
    _card("Rhystic Study", "{2}{U}", "Enchantment", identity="U"),
    _reading(step_triggers=(StepTrigger(Step.UPKEEP),)),
)
_add(
    _card("Black Vise", "{1}", "Artifact"),
    _reading(step_triggers=(StepTrigger(Step.UPKEEP, Whose.OPPONENTS),)),
)
_add(
    _card("Howling Mine", "{2}", "Artifact"),
    _reading(step_triggers=(StepTrigger(Step.DRAW, Whose.EACH),)),
)
_add(
    _card("Sulfuric Vortex", "{1}{R}{R}", "Enchantment", identity="R"),
    _reading(step_triggers=(StepTrigger(Step.UPKEEP, Whose.EACH),)),
)
_add(
    _card("Bloodchief Ascension", "{B}", "Enchantment", identity="B"),
    _reading(step_triggers=(StepTrigger(Step.END, Whose.EACH),)),
)
_add(
    _card("Banner of Each Combat", "{2}", "Artifact"),
    _reading(step_triggers=(StepTrigger(Step.BEGIN_COMBAT, Whose.EACH),)),
)
_add(
    _card("Mystic Remora", "{U}", "Enchantment", identity="U"),
    _reading(step_triggers=(StepTrigger(Step.UPKEEP, Whose.CONTROLLER),)),
)
_add(_card("Cultivate", "{2}{G}", "Sorcery", identity="G"))
_add(_card("Rampant Growth", "{1}{G}", "Sorcery", identity="G"))
_add(_card("Lightning Bolt", "{R}", "Instant", identity="R"))
_add(_card("Counterspell", "{U}{U}", "Instant", identity="U"))
_add(_card("Selesnya Charm", "{G}{W}", "Instant", identity="GW"))
_add(_card("Ponder", "{U}", "Sorcery", identity="U"))
_add(_card("Fireball", "{X}{R}", "Sorcery", identity="R"))
_add(_card("Dismember", "{1}{B/P}{B/P}", "Instant", identity="B"))
_add(_card("Snow Thing", "{S}{G}", "Snow Creature — Elemental", pt="2/2", identity="G"))
_add(_card("Ancestral Vision", "", "Sorcery", identity="U"))
_add(
    _card("Brazen Flash", "{1}{U}", "Creature — Faerie", pt="1/1", identity="U"),
    _reading(flash=OWN),
)
_add(
    _card(
        "Atraxa, Praetors' Voice",
        "{G}{W}{U}{B}",
        "Legendary Creature — Phyrexian Angel Horror",
        pt="4/4",
        identity="WUBG",
    ),
    _reading(vigilance=OWN),
)
_add(
    _card(
        "Kenrith, the Returned King",
        "{4}{W}",
        "Legendary Creature — Human Noble",
        pt="5/5",
        identity="WUBRG",
    ),
)
_add(
    _card(
        "Thrasios, Triton Hero",
        "{G}{U}",
        "Legendary Creature — Merfolk Wizard",
        pt="1/3",
        identity="GU",
    )
)
_add(
    _card(
        "Tymna the Weaver",
        "{1}{W}{B}",
        "Legendary Creature — Human Cleric",
        pt="2/2",
        identity="WB",
    )
)

_valki = Card(
    "Valki, God of Lies // Tibalt, Cosmic Impostor",
    (
        Face("Valki, God of Lies", M("{1}{B}"), "Legendary Creature — God", "", "2", "1"),
        Face("Tibalt, Cosmic Impostor", M("{5}{B}{R}"), "Legendary Planeswalker — Tibalt", ""),
    ),
    layout="modal_dfc",
    color_identity=("B", "R"),
)
LIBRARY[_valki.name] = (_valki, CardReading((FaceReading(), FaceReading())))

_fire_ice = Card(
    "Fire // Ice",
    (
        Face("Fire", M("{1}{R}"), "Instant"),
        Face("Ice", M("{1}{U}"), "Instant"),
    ),
    layout="split",
    color_identity=("U", "R"),
)
LIBRARY[_fire_ice.name] = (_fire_ice, CardReading((FaceReading(), FaceReading())))

_land_back = Card(
    "Sea Gate Restoration // Sea Gate, Reborn",
    (
        Face("Sea Gate Restoration", M("{4}{U}{U}{U}"), "Sorcery"),
        Face("Sea Gate, Reborn", M(""), "Land"),
    ),
    layout="modal_dfc",
    color_identity=("U",),
)
LIBRARY[_land_back.name] = (
    _land_back,
    CardReading((FaceReading(), FaceReading(mana_abilities=(taps_for("{U}"),)))),
)


def card(name: str) -> Card:
    return LIBRARY[name][0]


def reading(name: str) -> CardReading:
    return LIBRARY[name][1]


def with_reading(name: str, **fields: object) -> tuple[Card, CardReading]:
    found, current = LIBRARY[name]
    return found, CardReading((replace(current.faces[0], **fields),))  # type: ignore[arg-type]
