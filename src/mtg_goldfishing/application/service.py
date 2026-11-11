"""The service: one method per tool, each answering a call with its outcome and response text.

A driving adapter hands each call's arguments over as received, keyed by the tool's
parameter names, and gets back an `Answer`: the outcome and the text `Renderer` produced
for it, which is also what the call record keeps. An absent argument and a null one are
the same. A call whose arguments the adapter could not shape at all goes to
`malformed_call`, so that it too is answered and recorded.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from mtg_goldfishing.application.outcome import Answer
from mtg_goldfishing.application.ports import (
    CardCatalog,
    Clock,
    DeckRepository,
    GameChanges,
    GameLocks,
    GameRepository,
    IdSource,
    RecordStore,
    Renderer,
    UnitOfWork,
)
from mtg_goldfishing.application.use_cases import (
    advance,
    attack,
    choose,
    effect,
    end_game,
    get_log,
    get_state,
    load_deck,
    malformed_call,
    mulligan,
    new_game,
    passing,
    play,
    wait,
)
from mtg_goldfishing.application.use_cases.handling import Ports

Arguments = Mapping[str, object]


# @spec APP-009, APP-011, APP-049, APP-050
class Service:
    """The use cases, one per tool, over the ports they reach the outside world through."""

    def __init__(
        self,
        *,
        games: GameRepository,
        decks: DeckRepository,
        records: RecordStore,
        unit_of_work: UnitOfWork,
        catalog: CardCatalog,
        locks: GameLocks,
        ids: IdSource,
        clock: Clock,
        renderer: Renderer,
        changes: GameChanges,
    ) -> None:
        self._ports = Ports(
            games=games,
            decks=decks,
            records=records,
            unit_of_work=unit_of_work,
            catalog=catalog,
            locks=locks,
            ids=ids,
            clock=clock,
            renderer=renderer,
            changes=changes,
        )

    def load_deck(self, arguments: Arguments) -> Answer:
        """`cards, commander, definitions?, refresh?, override?`"""
        return load_deck.load_deck(self._ports, arguments)

    def new_game(self, arguments: Arguments) -> Answer:
        """`deck_id, seed?, turn_limit?, draw_first_turn?`"""
        return new_game.new_game(self._ports, arguments)

    def mulligan(self, arguments: Arguments) -> Answer:
        """`game_id, keep, bottom?, override?, after?`"""
        return mulligan.mulligan(self._ports, arguments)

    def get_state(self, arguments: Arguments) -> Answer:
        """`game_id, detail?`"""
        return get_state.get_state(self._ports, arguments)

    def play(self, arguments: Arguments) -> Answer:
        """`game_id, card, from?, to?, delta?, choices?, pay?, expect?, reason?, override?,
        after?`"""
        return play.play(self._ports, arguments)

    def effect(self, arguments: Arguments) -> Answer:
        """`game_id, source, delta, choices?, pay?, expect?, reason?, override?, after?`"""
        return effect.effect(self._ports, arguments)

    def choose(self, arguments: Arguments) -> Answer:
        """`game_id, choice_id, selections?, rest_order?, delta?, blocks?, restate?,
        override?, after?`"""
        return choose.choose(self._ports, arguments)

    def attack(self, arguments: Arguments) -> Answer:
        """`game_id, attackers?, blocked?, commander_target?, damage?, vigilance?, haste?,
        targets?, evasion?, trample?, reason?, override?, after?`"""
        return attack.attack(self._ports, arguments)

    def advance(self, arguments: Arguments) -> Answer:
        """`game_id, to?, discard?, override?, after?`"""
        return advance.advance(self._ports, arguments)

    def pass_(self, arguments: Arguments) -> Answer:
        """`game_id, after?`"""
        return passing.pass_(self._ports, arguments)

    def wait(self, arguments: Arguments) -> Answer:
        """`game_id, timeout?`"""
        return wait.wait(self._ports, arguments)

    def end_game(self, arguments: Arguments) -> Answer:
        """`game_id, result, notes?, after?`"""
        return end_game.end_game(self._ports, arguments)

    def get_log(self, arguments: Arguments) -> Answer:
        """`game_id, since?, include_snapshots?, include_calls?`"""
        return get_log.get_log(self._ports, arguments)

    def malformed_call(self, tool: str, arguments: Arguments, problems: Sequence[str]) -> Answer:
        """A call the adapter could not shape; `problems` names each argument at fault."""
        return malformed_call.malformed_call(self._ports, tool, arguments, problems)
