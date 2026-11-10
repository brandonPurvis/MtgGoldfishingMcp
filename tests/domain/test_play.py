"""Playing cards, recording effects, and finishing looks and searches."""

from __future__ import annotations

import pytest

from mtg_goldfishing.domain.cards import Card, Face
from mtg_goldfishing.domain.events import (
    AlreadySo,
    AlreadySoKind,
    AssumptionKind,
    AssumptionMade,
    CardMoved,
    CardPlayed,
    CardsDrawn,
    CardsRevealed,
    CheckKind,
    ChecksOverridden,
    CostPaid,
    ErrorKind,
    ExpectationMismatched,
    NothingRevealed,
    NoticeKind,
    NoticeRaised,
)
from mtg_goldfishing.domain.game.model import Destination, GameStatus, Reminder, Zone
from mtg_goldfishing.domain.game.results import Applied, Refusal
from mtg_goldfishing.domain.mana import ManaString
from mtg_goldfishing.domain.play.choosing import choose
from mtg_goldfishing.domain.play.playing import effect, play
from mtg_goldfishing.domain.steps import Step
from tests.support.builders import Situation, a_game

M = ManaString.parse


def played(situation: Situation, card: str, **arguments: object) -> Applied:
    result = play(situation.game, situation.deck, card=card, **arguments)  # type: ignore[arg-type]
    assert isinstance(result, Applied), result
    situation.game = result.game
    return result


def refused_play(situation: Situation, card: str, **arguments: object) -> Refusal:
    result = play(situation.game, situation.deck, card=card, **arguments)  # type: ignore[arg-type]
    assert isinstance(result, Refusal), result
    return result


def recorded(situation: Situation, delta: object, **arguments: object) -> Applied:
    result = effect(situation.game, situation.deck, source="test", delta=delta, **arguments)  # type: ignore[arg-type]
    assert isinstance(result, Applied), result
    situation.game = result.game
    return result


def refused_effect(situation: Situation, delta: object, **arguments: object) -> Refusal:
    result = effect(situation.game, situation.deck, source="test", delta=delta, **arguments)  # type: ignore[arg-type]
    assert isinstance(result, Refusal), result
    return result


def chosen(situation: Situation, **arguments: object) -> Applied:
    result = choose(situation.game, situation.deck, **arguments)  # type: ignore[arg-type]
    assert isinstance(result, Applied), result
    situation.game = result.game
    return result


TREASURE = {
    "name": "Treasure",
    "types": "Artifact — Treasure",
    "produces": ["{W}", "{U}", "{B}", "{R}", "{G}"],
    "sacrifice_to_produce": True,
}


def forests(n: int = 3) -> tuple[str, ...]:
    return ("Forest",) * n


# ------------------------------------------------------------------ refusals


# @spec PLAY-001
def test_a_refused_play_leaves_the_game_exactly_as_it_was() -> None:
    situation = a_game().with_hand("Shivan Dragon").with_battlefield(*forests()).build()
    before = situation.game.copy()
    refused_play(situation, "Shivan Dragon")
    assert situation.game == before


# @spec PLAY-002
def test_an_error_refuses_the_call_even_with_an_override() -> None:
    situation = a_game().build()
    result = refused_play(situation, "Shivan Dragon", override="please")
    assert result.errors[0].kind is ErrorKind.CARD_NOT_IN_ZONE


# @spec PLAY-003
def test_every_failed_rule_check_is_listed() -> None:
    situation = a_game().in_step(Step.END).with_hand("Shivan Dragon").build()
    result = refused_play(situation, "Shivan Dragon")
    assert sorted(c.kind.value for c in result.checks) == ["cost_not_payable", "spell_timing"]


# @spec PLAY-004
def test_an_override_applies_the_call_and_names_the_overridden_checks() -> None:
    situation = a_game().in_step(Step.END).with_hand("Lightning Bolt", "Grizzly Bears")
    built = situation.with_battlefield(*forests()).build()
    result = played(built, "Grizzly Bears", override="flash from Vedalken Orrery")
    overridden = next(e for e in result.events if isinstance(e, ChecksOverridden))
    assert [c.kind for c in overridden.checks] == [CheckKind.SPELL_TIMING]


# @spec PLAY-005
@pytest.mark.parametrize(
    ("delta", "kind"),
    [
        ({"teleport": ["Forest"]}, ErrorKind.UNKNOWN_DELTA_KEY),
        ({"mana": "{Q}"}, ErrorKind.UNPARSEABLE_MANA),
        ({"move": {"moon": ["Forest"]}}, ErrorKind.UNKNOWN_DESTINATION),
        ({"look": {"n": 1, "rest": "graveyard"}, "search": {}}, ErrorKind.LOOK_AND_SEARCH),
    ],
)
def test_a_malformed_delta_is_an_error(delta: object, kind: ErrorKind) -> None:
    situation = a_game().with_battlefield("Forest").with_library("Island").build()
    assert refused_effect(situation, delta).errors[0].kind is kind


# @spec PLAY-005
def test_an_unknown_expect_key_is_an_error() -> None:
    situation = a_game().build()
    result = refused_effect(situation, {}, expect={"mood": "good"})
    assert result.errors[0].kind is ErrorKind.UNKNOWN_EXPECT_KEY


# @spec PLAY-006
def test_a_change_that_is_already_so_is_applied_as_far_as_it_can_be_and_noted() -> None:
    situation = a_game().with_battlefield("Forest", tapped=True).with_battlefield("Island").build()
    result = recorded(
        situation, {"tap": ["Forest"], "untap": ["Island"], "counters": {"Island": {"charge": -1}}}
    )
    assert AlreadySo("Forest", AlreadySoKind.ALREADY_TAPPED) in result.events
    assert AlreadySo("Island", AlreadySoKind.ALREADY_UNTAPPED) in result.events
    assert AlreadySo("Island", AlreadySoKind.COUNTER_AT_ZERO, "charge") in result.events
    assert situation.game.instance("c2").counters == {}


# ------------------------------------------------------------------ play: source


# @spec PLAY-007
def test_without_from_the_card_is_looked_for_in_hand_then_the_command_zone() -> None:
    situation = (
        a_game().with_commander("Thrasios, Triton Hero").with_battlefield(*forests(4)).build()
    )
    situation.game.instance("c1").zone = Zone.COMMAND
    result = played(situation, "Thrasios, Triton Hero", pay={"cost": "{G}"}, override="test")
    assert result.summary == CardPlayed(
        "Thrasios, Triton Hero", "Thrasios, Triton Hero", "command", "battlefield", False
    )


# @spec PLAY-008
def test_a_card_can_be_played_from_the_graveyard() -> None:
    situation = a_game().with_graveyard("Lightning Bolt").with_battlefield("Mountain").build()
    result = played(situation, "Lightning Bolt", from_zone="graveyard", to="exile")
    assert situation.names_in(Zone.EXILE) == ["Lightning Bolt"]
    assert isinstance(result.summary, CardPlayed)


# @spec PLAY-009
def test_playing_from_the_library_disturbs_nothing_else_in_it() -> None:
    situation = a_game().with_library("Island", "Forest", "Swamp", "Plains").build()
    played(situation, "Swamp", from_zone="library")
    assert situation.names_in(Zone.LIBRARY) == ["Island", "Forest", "Plains"]


# @spec PLAY-010
def test_a_card_from_outside_the_game_is_created_from_its_card_data() -> None:
    wish = Card("Lightning Helix", (Face("Lightning Helix", M("{R}{W}"), "Instant"),))
    situation = a_game().with_battlefield("Mountain", "Plains").build()
    result = played(situation, "Lightning Helix", from_zone="outside", outside=wish)
    assert situation.names_in(Zone.GRAVEYARD) == ["Lightning Helix"]
    assert isinstance(result.summary, CardPlayed)


# @spec PLAY-010
def test_a_card_from_outside_the_game_can_come_from_a_definition() -> None:
    situation = a_game().with_battlefield("Forest").build()
    played(
        situation,
        "Homemade Elf",
        from_zone="outside",
        choices={
            "definition": {
                "name": "Homemade Elf",
                "mana_cost": "{G}",
                "type_line": "Creature — Elf",
            }
        },
    )
    assert situation.names_in(Zone.BATTLEFIELD) == ["Forest", "Homemade Elf"]


# @spec PLAY-011
def test_a_card_from_outside_without_data_or_definition_is_an_error_asking_for_one() -> None:
    situation = a_game().build()
    result = refused_play(situation, "Mystery Card", from_zone="outside")
    assert result.errors[0].kind is ErrorKind.CARD_DATA_NEEDED


# @spec PLAY-012
def test_naming_one_face_plays_that_face_and_its_cost() -> None:
    situation = a_game().with_hand("Fire // Ice").with_battlefield("Island", "Forest").build()
    result = played(situation, "Ice")
    paid = next(e for e in result.events if isinstance(e, CostPaid))
    assert paid.cost == M("{1}{U}")


# ------------------------------------------------------------------ play: lands


# @spec PLAY-013
def test_a_land_costs_nothing_and_uses_the_land_drop_from_any_zone() -> None:
    situation = a_game().with_graveyard("Forest").build()
    played(situation, "Forest", from_zone="graveyard")
    assert situation.game.land_drops_used == 1


# @spec PLAY-013
def test_the_land_face_of_a_modal_card_is_played_as_a_land() -> None:
    situation = a_game().with_hand("Sea Gate Restoration // Sea Gate, Reborn").build()
    played(situation, "Sea Gate, Reborn")
    land = situation.game.battlefield[0]
    assert (land.face, situation.game.land_drops_used) == (1, 1)


# @spec PLAY-014
def test_a_second_land_in_a_turn_fails_the_land_drop_check() -> None:
    situation = a_game().with_hand("Forest").with_land_drops_used(1).build()
    assert [c.kind for c in refused_play(situation, "Forest").checks] == [CheckKind.LAND_DROP_USED]


# @spec PLAY-015
def test_a_land_outside_a_main_step_fails_the_timing_check() -> None:
    situation = a_game().in_step(Step.END).with_hand("Forest").build()
    assert [c.kind for c in refused_play(situation, "Forest").checks] == [CheckKind.LAND_TIMING]


# ------------------------------------------------------------------ play: spells


# @spec PLAY-016
def test_the_cost_is_mana_cost_with_x_plus_extra_cost() -> None:
    situation = a_game().with_hand("Fireball").with_battlefield(*("Mountain",) * 6).build()
    result = played(situation, "Fireball", choices={"x": 3, "extra_cost": "{2}"})
    paid = next(e for e in result.events if isinstance(e, CostPaid))
    assert paid.cost == M("{3}{R}{2}")


# @spec PLAY-017
def test_a_commander_cast_from_the_command_zone_pays_tax_for_each_earlier_cast() -> None:
    situation = (
        a_game()
        .with_commander("Thrasios, Triton Hero")
        .with_battlefield(*forests(2), "Island", "Island")
        .build()
    )
    situation.game.commander_casts["c1"] = 1
    result = played(situation, "Thrasios, Triton Hero")
    paid = next(e for e in result.events if isinstance(e, CostPaid))
    assert paid.cost == M("{G}{U}{2}")
    assert situation.game.commander_casts["c1"] == 2


# @spec PLAY-018
def test_x_is_zero_when_not_announced_and_the_assumption_is_stated() -> None:
    situation = a_game().with_hand("Fireball").with_battlefield("Mountain").build()
    result = played(situation, "Fireball")
    assert AssumptionMade(AssumptionKind.X_IS_ZERO, "Fireball") in result.events


# @spec PLAY-019
def test_a_spell_with_no_mana_cost_costs_nothing_and_says_so() -> None:
    situation = a_game().with_hand("Ancestral Vision").build()
    result = played(situation, "Ancestral Vision")
    assert AssumptionMade(AssumptionKind.NO_MANA_COST, "Ancestral Vision") in result.events


# @spec PLAY-020
def test_a_sorcery_speed_spell_outside_a_main_step_fails_the_timing_check() -> None:
    situation = a_game().in_step(Step.UPKEEP).with_hand("Ponder").with_battlefield("Island").build()
    assert [c.kind for c in refused_play(situation, "Ponder").checks] == [CheckKind.SPELL_TIMING]


# @spec PLAY-020
def test_instants_and_flash_cards_may_be_cast_outside_a_main_step() -> None:
    situation = (
        a_game()
        .in_step(Step.END)
        .with_hand("Lightning Bolt", "Brazen Flash")
        .with_battlefield("Mountain", "Island", "Island")
        .build()
    )
    played(situation, "Lightning Bolt")
    played(situation, "Brazen Flash")


# @spec PLAY-021
def test_an_effect_with_an_unpayable_pay_fails_the_cost_check() -> None:
    situation = a_game().build()
    result = refused_effect(situation, {}, pay={"cost": "{3}"})
    assert [c.kind for c in result.checks] == [CheckKind.COST_NOT_PAYABLE]


# @spec PLAY-022
def test_an_overridden_unpayable_cost_taps_nothing_and_plays_the_card_unpaid() -> None:
    situation = a_game().with_hand("Shivan Dragon").with_battlefield("Mountain").build()
    result = played(situation, "Shivan Dragon", override="cost reduced")
    assert CostPaid(M("{4}{R}{R}"), unpaid=True) in result.events
    assert not situation.named("Mountain").tapped


# @spec PAY-037
def test_an_explicit_cost_on_play_fails_a_rule_check_without_override() -> None:
    situation = a_game().with_hand("Shivan Dragon").with_battlefield("Mountain").build()
    result = refused_play(situation, "Shivan Dragon", pay={"cost": "{R}"})
    assert [c.kind for c in result.checks] == [CheckKind.EXPLICIT_COST]


# @spec PAY-040
def test_an_explicit_cost_on_an_effect_is_not_a_rule_check() -> None:
    situation = a_game().with_battlefield("Mountain").build()
    recorded(situation, {}, pay={"cost": "{R}"})
    assert situation.game.instance("c1").tapped


# ------------------------------------------------------------------ play: destination


# @spec PLAY-023
def test_a_permanent_goes_to_the_battlefield_having_entered_this_turn() -> None:
    situation = a_game().with_hand("Grizzly Bears").with_battlefield(*forests(2)).build()
    played(situation, "Grizzly Bears")
    assert situation.named("Grizzly Bears").entered_turn == 3


# @spec PLAY-024
def test_an_instant_or_sorcery_goes_to_the_graveyard() -> None:
    situation = a_game().with_hand("Lightning Bolt").with_battlefield("Mountain").build()
    played(situation, "Lightning Bolt")
    assert situation.names_in(Zone.GRAVEYARD) == ["Lightning Bolt"]


# @spec PLAY-025
def test_to_names_where_the_card_ends_up() -> None:
    situation = a_game().with_hand("Lightning Bolt").with_battlefield("Mountain").build()
    played(situation, "Lightning Bolt", to="exile")
    assert situation.names_in(Zone.EXILE) == ["Lightning Bolt"]


# @spec PLAY-026
def test_a_permanent_read_as_entering_tapped_enters_tapped() -> None:
    situation = a_game().with_hand("Temple of Plenty").build()
    played(situation, "Temple of Plenty")
    assert situation.named("Temple of Plenty").tapped


# @spec PLAY-027
def test_an_assumption_behind_entering_untapped_is_stated() -> None:
    situation = a_game().with_hand("Glacial Fortress").build()
    result = played(situation, "Glacial Fortress")
    assumptions = [e for e in result.events if isinstance(e, AssumptionMade)]
    assert assumptions[0].text is not None
    assert not situation.named("Glacial Fortress").tapped


# @spec PLAY-028
def test_the_delta_is_applied_after_the_card_reaches_its_destination() -> None:
    situation = (
        a_game()
        .with_hand("Cultivate")
        .with_battlefield(*forests(3))
        .with_library("Plains", "Island", "Forest")
        .build()
    )
    played(
        situation,
        "Cultivate",
        delta={"fetch": {"battlefield_tapped": ["Plains"], "hand": ["Forest"]}},
    )
    assert situation.named("Plains").tapped
    assert situation.names_in(Zone.GRAVEYARD) == ["Cultivate"]


# ------------------------------------------------------------------ effect


# @spec PLAY-029, PLAY-032
def test_an_effect_moves_only_what_its_delta_says_and_takes_any_source_text() -> None:
    situation = a_game().with_battlefield("Grizzly Bears").build()
    result = effect(
        situation.game,
        situation.deck,
        source="an imagined Swords to Plowshares",
        delta={"move": {"exile": ["Grizzly Bears"]}},
    )
    assert isinstance(result, Applied)
    assert [c.name for c in result.game.in_zone(Zone.EXILE)] == ["Grizzly Bears"]


# @spec PLAY-030
def test_an_effect_pays_before_its_delta_so_its_own_mana_cannot_pay() -> None:
    situation = a_game().build()
    result = refused_effect(situation, {"mana": "{G}"}, pay={"cost": "{G}"})
    assert [c.kind for c in result.checks] == [CheckKind.COST_NOT_PAYABLE]


# @spec PLAY-031
def test_an_effect_without_pay_pays_nothing() -> None:
    situation = a_game().with_battlefield("Forest").build()
    result = recorded(situation, {"life": 1})
    assert not any(isinstance(e, CostPaid) for e in result.events)


# ------------------------------------------------------------------ delta


# @spec PLAY-033
def test_delta_keys_apply_in_their_fixed_order_whatever_order_they_are_written_in() -> None:
    situation = a_game().with_battlefield("Forest").with_library("Island").build()
    recorded(situation, {"shuffle": True, "draw": 1, "untap": ["Forest"], "tap": ["Forest"]})
    assert situation.game.instance("c1").tapped
    assert situation.names_in(Zone.HAND) == ["Island"]


# @spec PLAY-034
def test_mana_in_a_delta_goes_to_the_pool() -> None:
    situation = a_game().build()
    recorded(situation, {"mana": "{G}{G}"})
    assert str(situation.game.mana_pool) == "{G}{G}"


# @spec PLAY-035
def test_tokens_are_created_on_the_battlefield_as_described() -> None:
    situation = a_game().build()
    recorded(
        situation,
        {
            "tokens": [
                {
                    "name": "Treasure",
                    "count": 2,
                    "types": "Artifact — Treasure",
                    "produces": ["{W}", "{U}", "{B}", "{R}", "{G}"],
                    "sacrifice_to_produce": True,
                },
                {
                    "name": "Elf Warrior",
                    "types": "Creature — Elf Warrior",
                    "pt": "1/1",
                    "tapped": True,
                },
            ]
        },
    )
    names = [(c.name, c.tapped, c.entered_turn) for c in situation.game.battlefield]
    assert names == [("Treasure", False, 3), ("Treasure", False, 3), ("Elf Warrior", True, 3)]


# @spec PLAY-036
def test_counters_change_by_signed_amounts_and_vanish_at_zero() -> None:
    situation = a_game().with_battlefield("Grizzly Bears", counters={"+1/+1": 2}).build()
    recorded(situation, {"counters": {"Grizzly Bears": {"+1/+1": -2, "stun": 1}}})
    assert situation.game.instance("c1").counters == {"stun": 1}


# @spec PLAY-037
def test_move_finds_cards_in_hand_then_public_zones_and_says_where_from() -> None:
    situation = a_game().with_graveyard("Grizzly Bears").build()
    result = recorded(situation, {"move": {"hand": ["Grizzly Bears"]}})
    assert CardMoved("Grizzly Bears", "graveyard", "hand") in result.events


# @spec PLAY-038
def test_move_never_takes_a_card_from_the_library() -> None:
    situation = a_game().with_library("Grizzly Bears").build()
    result = refused_effect(situation, {"move": {"hand": ["Grizzly Bears"]}})
    assert result.errors[0].kind is ErrorKind.CARD_NOT_IN_ZONE


# @spec PLAY-039
def test_discard_moves_cards_from_hand_to_graveyard() -> None:
    situation = a_game().with_hand("Ponder").build()
    recorded(situation, {"discard": ["Ponder"]})
    assert situation.names_in(Zone.GRAVEYARD) == ["Ponder"]


# @spec PLAY-040
def test_a_card_fetched_to_the_top_of_the_library_stays_on_top_after_the_shuffle() -> None:
    situation = a_game().with_library("Island", "Forest", "Swamp", "Plains", "Mountain").build()
    recorded(situation, {"fetch": {"library_top": ["Mountain"]}})
    assert situation.names_in(Zone.LIBRARY)[0] == "Mountain"
    assert situation.game.shuffles == 1


# @spec PLAY-041
def test_fetching_a_card_not_in_the_library_is_an_error() -> None:
    situation = a_game().with_library("Island").build()
    result = refused_effect(situation, {"fetch": {"hand": ["Forest"]}})
    assert result.errors[0].kind is ErrorKind.NOT_IN_LIBRARY


# @spec PLAY-042
def test_draw_moves_cards_from_the_top_and_lists_exactly_those_drawn() -> None:
    situation = a_game().with_library("Island", "Forest", "Swamp").build()
    result = recorded(situation, {"draw": 2})
    assert CardsDrawn(("Island", "Forest")) in result.events


# @spec PLAY-043, PLAY-044
def test_life_and_damage_change_by_the_amounts_given() -> None:
    situation = a_game().build()
    recorded(situation, {"life": -3, "damage": 6})
    assert (situation.game.life, situation.game.damage_dealt) == (37, 6)


# @spec PLAY-045
def test_shuffle_shuffles_the_library() -> None:
    situation = a_game().with_library("Island", "Forest").build()
    recorded(situation, {"shuffle": True})
    assert situation.game.shuffles == 1


# @spec PLAY-046
def test_a_card_moved_to_battlefield_tapped_enters_tapped() -> None:
    situation = a_game().with_hand("Grizzly Bears").build()
    recorded(situation, {"move": {"battlefield_tapped": ["Grizzly Bears"]}})
    assert situation.named("Grizzly Bears").tapped


# @spec PLAY-047
def test_any_card_arriving_on_the_battlefield_has_entered_this_turn() -> None:
    situation = a_game().with_graveyard("Grizzly Bears").build()
    recorded(situation, {"move": {"battlefield": ["Grizzly Bears"]}})
    assert situation.named("Grizzly Bears").entered_turn == 3


# @spec PLAY-048
def test_a_card_leaving_the_battlefield_loses_its_tapped_state_and_counters() -> None:
    situation = (
        a_game().with_battlefield("Grizzly Bears", tapped=True, counters={"+1/+1": 1}).build()
    )
    recorded(situation, {"move": {"hand": ["Grizzly Bears"]}})
    bears = situation.named("Grizzly Bears")
    assert (bears.tapped, bears.counters) == (False, {})


# @spec PLAY-049
def test_a_token_leaving_the_battlefield_ceases_to_exist() -> None:
    situation = a_game().build()
    recorded(situation, {"tokens": [{"name": "Goblin", "types": "Creature — Goblin", "pt": "1/1"}]})
    recorded(situation, {"move": {"graveyard": ["Goblin"]}})
    assert situation.game.cards == []


# @spec PLAY-050
def test_a_land_put_onto_the_battlefield_by_an_effect_uses_no_land_drop() -> None:
    situation = a_game().with_library("Forest").build()
    recorded(situation, {"fetch": {"battlefield": ["Forest"]}})
    assert situation.game.land_drops_used == 0


# @spec PLAY-051
def test_end_conditions_are_examined_after_every_applied_call() -> None:
    situation = a_game().build()
    result = recorded(situation, {"damage": 120})
    assert NoticeRaised(NoticeKind.DAMAGE) in result.events


# ------------------------------------------------------------------ commanders


# @spec PLAY-052
def test_a_commander_bound_for_the_graveyard_goes_to_the_command_zone() -> None:
    situation = a_game().with_commander("Atraxa, Praetors' Voice", zone=Zone.BATTLEFIELD).build()
    result = recorded(situation, {"move": {"graveyard": ["Atraxa, Praetors' Voice"]}})
    assert situation.names_in(Zone.COMMAND) == ["Atraxa, Praetors' Voice"]
    assert any(isinstance(e, CardMoved) and e.commander_redirected for e in result.events)


# @spec PLAY-053
def test_commander_stays_lets_a_commander_go_to_the_graveyard() -> None:
    situation = a_game().with_commander("Atraxa, Praetors' Voice", zone=Zone.BATTLEFIELD).build()
    recorded(
        situation, {"move": {"graveyard": ["Atraxa, Praetors' Voice"]}, "commander_stays": True}
    )
    assert situation.names_in(Zone.GRAVEYARD) == ["Atraxa, Praetors' Voice"]


# @spec PLAY-054
def test_a_commander_moved_to_hand_goes_to_hand() -> None:
    situation = a_game().with_commander("Atraxa, Praetors' Voice", zone=Zone.BATTLEFIELD).build()
    recorded(situation, {"move": {"hand": ["Atraxa, Praetors' Voice"]}})
    assert situation.names_in(Zone.HAND) == ["Atraxa, Praetors' Voice"]


# @spec PLAY-055
def test_modes_targets_and_notes_are_recorded_and_never_judged() -> None:
    situation = a_game().with_hand("Lightning Bolt").with_battlefield("Mountain").build()
    played(
        situation,
        "Lightning Bolt",
        choices={"modes": ["deal 3"], "targets": ["the moon"], "notes": "anything"},
    )


# ------------------------------------------------------------------ pending choices


# @spec PLAY-056, PLAY-061
def test_look_reveals_cards_from_an_end_of_the_library_and_waits_for_a_choice() -> None:
    situation = a_game().with_library("Island", "Forest", "Swamp", "Plains").build()
    result = recorded(situation, {"look": {"n": 3, "from": "bottom", "rest": "library_bottom"}})
    revealed = next(e for e in result.events if isinstance(e, CardsRevealed))
    assert [c.name for c in revealed.cards] == ["Plains", "Swamp", "Forest"]
    assert situation.game.status is GameStatus.PENDING_CHOICE


# @spec PLAY-057
def test_look_without_rest_is_an_error() -> None:
    situation = a_game().with_library("Island").build()
    result = refused_effect(situation, {"look": {"n": 1}})
    assert result.errors[0].kind is ErrorKind.LOOK_WITHOUT_REST


# @spec PLAY-058
def test_search_reveals_the_library_sorted_by_name_and_filtered() -> None:
    situation = a_game().with_library("Island", "Grizzly Bears", "Forest", "Swamp").build()
    result = recorded(situation, {"search": {"filter": "basic"}})
    revealed = next(e for e in result.events if isinstance(e, CardsRevealed))
    assert [c.name for c in revealed.cards] == ["Forest", "Island", "Swamp"]


# @spec PLAY-059, PLAY-060
def test_a_search_that_reveals_nothing_completes_and_still_shuffles() -> None:
    situation = a_game().with_library("Island").build()
    result = recorded(situation, {"search": {"filter": "dragon"}})
    assert NothingRevealed("search") in result.events
    assert situation.game.status is GameStatus.ACTIVE
    assert situation.game.shuffles == 1


# @spec PLAY-062, PLAY-063
def test_choose_places_selected_cards_and_sends_the_rest_where_the_look_said() -> None:
    situation = a_game().with_library("Island", "Forest", "Swamp", "Plains").build()
    recorded(situation, {"look": {"n": 3, "from": "top", "rest": "graveyard"}})
    assert situation.game.pending_choice is not None
    chosen(
        situation,
        choice_id=situation.game.pending_choice.choice_id,
        selections={"hand": ["Forest"]},
    )
    assert situation.names_in(Zone.HAND) == ["Forest"]
    assert situation.names_in(Zone.GRAVEYARD) == ["Island", "Swamp"]
    assert situation.game.status is GameStatus.ACTIVE


# @spec PLAY-063
def test_rest_order_decides_the_order_of_the_rest() -> None:
    situation = a_game().with_library("Island", "Forest", "Swamp", "Plains").build()
    recorded(situation, {"look": {"n": 3, "from": "top", "rest": "library_top"}})
    assert situation.game.pending_choice is not None
    chosen(
        situation,
        choice_id=situation.game.pending_choice.choice_id,
        selections={},
        rest_order=["Swamp", "Island", "Forest"],
    )
    assert situation.names_in(Zone.LIBRARY) == ["Swamp", "Island", "Forest", "Plains"]


# @spec PLAY-064
def test_choosing_after_a_search_shuffles_before_placing_selected_cards_on_top() -> None:
    situation = a_game().with_library("Island", "Forest", "Swamp", "Plains").build()
    recorded(situation, {"search": {}})
    assert situation.game.pending_choice is not None
    chosen(
        situation,
        choice_id=situation.game.pending_choice.choice_id,
        selections={"library_top": ["Plains"]},
    )
    assert situation.names_in(Zone.LIBRARY)[0] == "Plains"
    assert situation.game.shuffles == 1


# @spec PLAY-065
def test_several_cards_selected_to_the_top_go_first_named_on_top_above_the_rest() -> None:
    situation = a_game().with_library("Island", "Forest", "Swamp", "Plains").build()
    recorded(situation, {"look": {"n": 3, "rest": "library_top"}})
    assert situation.game.pending_choice is not None
    chosen(
        situation,
        choice_id=situation.game.pending_choice.choice_id,
        selections={"library_top": ["Swamp", "Island"]},
    )
    assert situation.names_in(Zone.LIBRARY) == ["Swamp", "Island", "Forest", "Plains"]


# @spec PLAY-066
def test_choosing_with_a_wrong_id_or_an_unrevealed_card_is_an_error() -> None:
    situation = a_game().with_library("Island", "Forest").build()
    recorded(situation, {"look": {"n": 1, "rest": "graveyard"}})
    wrong = choose(situation.game, situation.deck, choice_id="x99", selections={})
    unrevealed = choose(
        situation.game, situation.deck, choice_id="x1", selections={"hand": ["Forest"]}
    )
    assert isinstance(wrong, Refusal)
    assert wrong.errors[0].kind is ErrorKind.WRONG_CHOICE
    assert isinstance(unrevealed, Refusal)
    assert unrevealed.errors[0].kind is ErrorKind.NOT_REVEALED


# @spec PLAY-067
def test_selecting_nothing_is_allowed() -> None:
    situation = a_game().with_library("Island").build()
    recorded(situation, {"look": {"n": 1, "rest": "graveyard"}})
    chosen(situation, choice_id="x1", selections={})
    assert situation.names_in(Zone.GRAVEYARD) == ["Island"]


# ------------------------------------------------------------------ expect


# @spec PLAY-068, PLAY-069
def test_an_expectation_that_differs_is_a_warning_and_the_call_still_applies() -> None:
    situation = a_game().with_battlefield("Forest").build()
    result = recorded(situation, {"life": -1}, expect={"life": 40, "lands": 1})
    assert ExpectationMismatched("life", "39", "40") in result.events
    assert situation.game.life == 39


# @spec PLAY-070
def test_the_unknown_expect_key_error_lists_the_allowed_keys() -> None:
    situation = a_game().build()
    error = refused_effect(situation, {}, expect={"mood": 1}).errors[0]
    assert "untapped_lands" in error.names


# @spec PLAY-071
def test_expected_tax_is_the_higher_of_two_commanders_next_cast() -> None:
    situation = a_game().with_commander("Thrasios, Triton Hero", "Tymna the Weaver").build()
    situation.game.commander_casts["c2"] = 2
    result = recorded(situation, {}, expect={"tax": 4})
    assert not any(isinstance(e, ExpectationMismatched) for e in result.events)


# @spec PLAY-072
def test_expected_pool_ignores_order() -> None:
    situation = a_game().build()
    result = recorded(situation, {"mana": "{G}{R}"}, expect={"pool": "{R}{G}"})
    assert not any(isinstance(e, ExpectationMismatched) for e in result.events)


# @spec PLAY-073
def test_expectations_on_a_call_that_creates_a_choice_are_checked_at_once() -> None:
    situation = a_game().with_library("Island", "Forest").build()
    result = recorded(situation, {"look": {"n": 1, "rest": "graveyard"}}, expect={"library": 1})
    assert ExpectationMismatched("library", "2", "1") in result.events


def test_a_played_card_goes_where_to_says_using_the_destination_names() -> None:
    assert Destination.named("battlefield_tapped") is Destination.BATTLEFIELD_TAPPED


# ------------------------------------------------------------------ across segments


# @spec PAY-010
def test_a_treasure_token_named_in_pay_with_pays_and_is_sacrificed() -> None:
    situation = a_game().with_hand("Lightning Bolt").build()
    recorded(situation, {"tokens": [TREASURE]})
    result = played(situation, "Lightning Bolt", pay={"with": ["Treasure"]})
    paid = next(e for e in result.events if isinstance(e, CostPaid))
    assert paid.sacrificed == ("Treasure",)


# @spec PAY-010
def test_a_card_whose_definition_gives_produces_is_a_mana_source() -> None:
    situation = a_game().with_hand("Grizzly Bears").with_battlefield("Forest").build()
    played(
        situation,
        "Homemade Rock",
        from_zone="outside",
        choices={
            "definition": {
                "name": "Homemade Rock",
                "mana_cost": "{0}",
                "type_line": "Artifact",
                "produces": "{G}",
            }
        },
    )
    played(situation, "Grizzly Bears")
    assert all(c.tapped for c in situation.game.battlefield if c.name != "Grizzly Bears")


# @spec GAME-019
def test_a_counters_map_accepts_an_instance_id_as_a_key() -> None:
    situation = a_game().with_battlefield("Grizzly Bears", "Grizzly Bears").build()
    recorded(situation, {"counters": {"C2": {"+1/+1": 1}}})
    assert (situation.game.instance("c1").counters, situation.game.instance("c2").counters) == (
        {},
        {"+1/+1": 1},
    )


# @spec GAME-020
def test_a_card_leaving_the_battlefield_returns_to_its_first_face() -> None:
    situation = a_game().with_hand("Sea Gate Restoration // Sea Gate, Reborn").build()
    played(situation, "Sea Gate, Reborn")
    recorded(situation, {"move": {"hand": ["Sea Gate, Reborn"]}})
    assert situation.game.hand[0].face == 0


# @spec PLAY-026
def test_a_permanent_fetched_onto_the_battlefield_enters_tapped_when_read_so() -> None:
    situation = a_game().with_library("Temple of Plenty").build()
    recorded(situation, {"fetch": {"battlefield": ["Temple of Plenty"]}})
    assert situation.named("Temple of Plenty").tapped


# @spec PLAY-052
def test_a_discarded_commander_goes_to_the_command_zone() -> None:
    situation = a_game().with_commander("Atraxa, Praetors' Voice", zone=Zone.HAND).build()
    recorded(situation, {"discard": ["Atraxa, Praetors' Voice"]})
    assert situation.names_in(Zone.COMMAND) == ["Atraxa, Praetors' Voice"]


# @spec PLAY-052
def test_a_commander_selected_to_the_graveyard_in_choose_goes_to_the_command_zone() -> None:
    situation = a_game().with_commander("Atraxa, Praetors' Voice", zone=Zone.LIBRARY).build()
    recorded(situation, {"look": {"n": 1, "rest": "library_top"}})
    chosen(situation, choice_id="x1", selections={"graveyard": ["Atraxa, Praetors' Voice"]})
    assert situation.names_in(Zone.COMMAND) == ["Atraxa, Praetors' Voice"]


# @spec PLAY-012
def test_a_creature_face_played_from_a_modal_card_enters_on_that_face() -> None:
    situation = a_game().with_hand("Valki, God of Lies // Tibalt, Cosmic Impostor")
    built = situation.with_battlefield("Swamp", "Mountain", *forests(5)).build()
    result = played(built, "Tibalt, Cosmic Impostor")
    paid = next(e for e in result.events if isinstance(e, CostPaid))
    valki = built.named("Valki, God of Lies // Tibalt, Cosmic Impostor")
    assert (paid.cost, valki.face) == (M("{5}{B}{R}"), 1)


# @spec REC-009, REC-010
def test_an_effect_whose_source_names_a_permanent_answers_its_reminder() -> None:
    situation = a_game().in_step(Step.UPKEEP).with_battlefield("Phyrexian Arena").build()
    situation.game.reminders.append(Reminder("c1", "Phyrexian Arena", Step.UPKEEP))
    result = effect(situation.game, situation.deck, source="phyrexian arena", delta={"life": -1})
    assert isinstance(result, Applied)
    assert result.game.reminders[0].answered


# @spec REC-009, REC-010
def test_an_effect_answers_the_reminder_of_a_permanent_no_longer_on_the_battlefield() -> None:
    situation = a_game().in_step(Step.UPKEEP).with_battlefield("Phyrexian Arena").build()
    arena = situation.named("Phyrexian Arena")
    situation.game.reminders.append(Reminder(arena.id, "Phyrexian Arena", Step.UPKEEP))
    arena.zone = Zone.GRAVEYARD
    result = effect(situation.game, situation.deck, source="Phyrexian Arena", delta={"life": -1})
    assert isinstance(result, Applied)
    assert result.game.reminders[0].answered


def test_an_effect_whose_source_names_no_permanent_answers_no_reminder() -> None:
    situation = a_game().in_step(Step.UPKEEP).with_battlefield("Phyrexian Arena").build()
    situation.game.reminders.append(Reminder("c1", "Phyrexian Arena", Step.UPKEEP))
    result = effect(situation.game, situation.deck, source="an opponent", delta={"life": -1})
    assert isinstance(result, Applied)
    assert not result.game.reminders[0].answered


def test_an_effect_given_a_malformed_pay_is_an_error() -> None:
    situation = a_game().build()
    result = refused_effect(situation, {}, pay={"cost": "{Q}"})
    assert result.errors[0].kind is ErrorKind.UNPARSEABLE_MANA


def test_choices_with_a_negative_x_is_an_error() -> None:
    situation = a_game().with_hand("Fireball").with_battlefield("Mountain").build()
    result = refused_play(situation, "Fireball", choices={"x": -1})
    assert result.errors[0].kind is ErrorKind.MALFORMED_ARGUMENT
