"""Games, loaded decks and records worth storing: rich enough to exercise every shape."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from mtg_goldfishing.domain.deck.model import (
    CardDefinition,
    DeckCard,
    DeckEntry,
    LoadedDeck,
    OverriddenChecks,
)
from mtg_goldfishing.domain.events import (
    AdvanceStopped,
    AssumptionKind,
    AssumptionMade,
    AttackDeclared,
    CardPlayed,
    CardsRevealed,
    CheckKind,
    CostPaid,
    EnteredStep,
    Error,
    ErrorKind,
    FailedCheck,
    LibraryShuffled,
    NoticeKind,
    Refused,
    RevealedCard,
    StepsEntered,
    StopReason,
)
from mtg_goldfishing.domain.game.model import (
    Attack,
    CardInstance,
    Game,
    GameResult,
    GameStatus,
    LastChange,
    PaymentRecord,
    PendingChoice,
    Reminder,
    Result,
    TokenSpec,
    TurnStats,
    Zone,
)
from mtg_goldfishing.domain.game.seats import SeatId, SeatNumber
from mtg_goldfishing.domain.mana import Mana, ManaString, Restriction
from mtg_goldfishing.domain.reading.reader import read_card
from mtg_goldfishing.domain.records.model import (
    CallRecord,
    ContestedEntry,
    ContestedSnapshot,
    HandCard,
    LogEntry,
    Payment,
    PermanentRecord,
    ReminderRecord,
    TurnSnapshot,
)
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import a_game
from tests.support.card_data import recorded_card
from tests.support.library import LIBRARY

M = ManaString.parse
VALKI = recorded_card("Valki, God of Lies // Tibalt, Cosmic Impostor")
BONECRUSHER = recorded_card("Bonecrusher Giant // Stomp")


def a_rich_game(game_id: str = "gtest000001") -> Game:
    """A game with cards in every zone, a pending choice, a declared attack and a last change."""
    situation = (
        a_game()
        .with_card(VALKI, read_card(VALKI))
        .with_commander(VALKI.name)
        .with_hand("Cultivate", "Sol Ring")
        .with_battlefield("Forest", tapped=True, counters={"charge": 2})
        .with_battlefield("Llanowar Elves", entered_turn=3)
        .with_graveyard("Grizzly Bears")
        .with_exile("Shivan Dragon")
        .with_library("Island", "Plains", "Swamp")
        .in_step(Step.DECLARE_ATTACKERS, turn=4)
        .with_pool_units(Mana("G"), Mana("C", Restriction("Only creatures.", ("Creature",))))
        .build()
    )
    game = situation.game
    seat = game.tested
    game.game_id = game_id
    seat.seat_id = SeatId(game_id)
    game.turn_limit = 10
    game.change = 12
    seat.mulligans = 1
    seat.shuffles = 2
    game.imaginary_opponents.damage_dealt = 7
    game.status = GameStatus.PENDING_CHOICE
    seat.turn_stats = TurnStats(
        mana_available=5, mana_spent=3, payments=[PaymentRecord(M("{2}{G}"), 3, life=1)]
    )
    token = CardInstance(
        id=game.new_instance_id(),
        name="Elf Warrior",
        zone=Zone.BATTLEFIELD,
        owner=seat.number,
        controller=seat.number,
        is_token=True,
        entered_turn=4,
        token=TokenSpec("Elf Warrior", "Creature — Elf Warrior", pt="1/1", produces=(M("{G}"),)),
    )
    defined = CardInstance(
        id=game.new_instance_id(),
        name=BONECRUSHER.name,
        zone=Zone.HAND,
        owner=seat.number,
        controller=seat.number,
        face=1,
        definition=BONECRUSHER,
        reading=read_card(BONECRUSHER),
    )
    game.cards.extend([token, defined])
    elves = situation.named("Llanowar Elves")
    game.declared_attack = Attack(
        attackers=[elves.id, token.id],
        blocked=[token.id],
        damage={elves.id: 1},
        commander_targets={elves.id: 2},
    )
    game.tapped_by_attacks = [elves.id]
    game.pending = [
        PendingChoice(
            choice_id="x1",
            seat=seat.number,
            source="Cultivate",
            kind="look",
            revealed=["c9", "c10"],
            rest=None,
        )
    ]
    game.notices = [NoticeKind.DAMAGE, NoticeKind.TURN_LIMIT]
    seat.reminders = [Reminder(elves.id, "Llanowar Elves", Step.UPKEEP, answered=True)]
    game.snapshot_turns = [1, 2, 3]
    game.result = Result(GameResult.STALLED, "ran out of turns")
    seat.last_change = LastChange(
        tool="play",
        arguments={"card": "Cultivate", "delta": {"search": ["Forest"], "nested": [1, None]}},
        summary=CardPlayed("Cultivate", "Cultivate", "hand", "graveyard", is_land=False),
        events=(
            CostPaid(M("{2}{G}"), tapped=("Forest",), surplus="{G}"),
            StepsEntered((EnteredStep(4, Step.MAIN1), EnteredStep(4, Step.BEGIN_COMBAT))),
            CardsRevealed("x1", "look", (RevealedCard("c9", "Island"),)),
            AttackDeclared(("c5",), (), (("c5", 2),), ("c5",)),
            AssumptionMade(AssumptionKind.X_IS_ZERO, card="Cultivate"),
            AdvanceStopped(StopReason.REMINDER, Step.UPKEEP, None),
            LibraryShuffled(),
            Refused(
                (Error(ErrorKind.CARD_NOT_IN_ZONE, "Sol Ring", zone="hand"),),
                (FailedCheck(CheckKind.COST_NOT_PAYABLE, cost=M("{1}"), step=Step.MAIN1),),
            ),
        ),
        change=12,
    )
    return game


def a_rich_deck(deck_id: str = "drich") -> LoadedDeck:
    """A loaded deck with multi-faced cards, readings, definitions and overridden checks."""
    sol_ring, sol_ring_reading = LIBRARY["Sol Ring"]
    return LoadedDeck(
        deck_id=deck_id,
        commanders=(VALKI.name,),
        entries=(DeckEntry("Sol Ring", 1), DeckEntry(BONECRUSHER.name, 1)),
        cards=(
            DeckCard(VALKI, read_card(VALKI)),
            DeckCard(BONECRUSHER, read_card(BONECRUSHER)),
            DeckCard(sol_ring, sol_ring_reading),
            *(DeckCard(*LIBRARY[name]) for name in ("Command Tower", "Gaea's Cradle")),
        ),
        definitions=(
            CardDefinition(
                "Sol Ring",
                mana_cost=M("{1}"),
                produces=(M("{C}{C}"),),
                keywords=(),
                enters_tapped=False,
            ),
        ),
        overrides=(
            OverriddenChecks(
                (FailedCheck(CheckKind.DECK_SIZE, number=3, expected=100),), "a test deck"
            ),
        ),
    )


def a_log_entry(seq: int, *, tool: str = "play") -> LogEntry:
    return LogEntry(
        seq=seq,
        turn=3,
        step=Step.MAIN1,
        tool=tool,
        arguments={"card": "Sol Ring", "after": seq - 1, "pay": ["Forest"]},
        outcome={"hand": ["Forest", "Island"]},
        card="Sol Ring",
        from_zone="hand",
        delta={"to": "battlefield", "added": {"shuffles": 0}},
        choices=None,
        paid=Payment("{1}", ("Forest",), 0, "", ""),
        drawn=("Island",),
        steps=(Step.MAIN1,),
        reason="ramp",
        override=None,
        overridden_checks=("cost_not_payable",),
        expect_mismatches=(),
        reminders=(ReminderRecord("Phyrexian Arena", Step.UPKEEP, "c4", "Phyrexian Arena", 3),),
        assumptions=("x is zero",),
        notices=("damage",),
    )


def a_snapshot(turn: int, *, written_by: int) -> TurnSnapshot:
    return TurnSnapshot(
        turn=turn,
        hand=(HandCard("Cultivate", payable=True),),
        battlefield=(PermanentRecord("Forest", tapped=True, counters=(("charge", 1),)),),
        graveyard=("Grizzly Bears",),
        lands=1,
        mana_available=1,
        mana_spent=1,
        land_drop_made=True,
        life=40,
        damage_dealt=2,
        commander_damage=(("Atraxa", (0, 2, 0)),),
        unanswered_reminders=(ReminderRecord("Phyrexian Arena", Step.UPKEEP),),
        written_by=written_by,
    )


def a_call(game_id: str | None, change: int | None, *, tool: str = "advance") -> CallRecord:
    return CallRecord(
        time=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        game_id=game_id,
        tool=tool,
        arguments={"game_id": game_id, "to": "main2", "flags": [True, 1.5]},
        status="OK",
        response=f"OK · change {change}",
        is_override=False,
        change=change,
    )


# ---------------------------------------------------------------------------------------
# Records of a contested game.
# ---------------------------------------------------------------------------------------


def a_contested_reminder(seat: int, table_turn: int) -> ReminderRecord:
    """A reminder of Phyrexian Arena's upkeep trigger issued to a seat in a table turn."""
    return ReminderRecord(
        "Phyrexian Arena",
        Step.UPKEEP,
        "c4",
        "Phyrexian Arena",
        table_turn,
        seat=SeatNumber(seat),
    )


def a_contested_log_entry(
    seq: int,
    *,
    seat: int,
    table_turn: int,
    tool: str = "effect",
    source: str | None = None,
    reminders: tuple[ReminderRecord, ...] = (),
    public: tuple[Any, ...] = (),
) -> LogEntry:
    """A log entry of a seat of a contested game, made in a table turn."""
    arguments: dict[str, object] = {} if source is None else {"source": source}
    entry: Any = replace(
        a_log_entry(seq, tool=tool),
        turn=1,
        arguments=arguments,
        card=source,
        reminders=reminders,
    )
    return replace(
        entry,
        contested=ContestedEntry(
            seat=SeatNumber(seat),
            active=SeatNumber(seat),
            table_turn=table_turn,
            round=1,
            public=public,
        ),
    )


def a_contested_snapshot(turn: int, *, table_turn: int, written_by: int) -> TurnSnapshot:
    """A snapshot of seat 2's own turn `turn`, in a contested game's table turn `table_turn`."""
    snapshot: Any = replace(a_snapshot(turn, written_by=written_by), damage_dealt=0)
    return replace(
        snapshot,
        commander_damage=(),
        contested=ContestedSnapshot(
            seat=SeatNumber(2),
            table_turn=table_turn,
            round=1,
            lives=((SeatNumber(1), 40), (SeatNumber(2), 33)),
            eliminated=(),
            commander_damage=(("Atraxa", ((SeatNumber(1), 4),)),),
        ),
    )
