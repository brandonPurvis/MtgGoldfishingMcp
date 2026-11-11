"""Paying costs: the pool, mana sources, the auto payment system and agent-directed payment."""

from __future__ import annotations

from mtg_goldfishing.domain.cards import Card, Face
from mtg_goldfishing.domain.events import (
    AssumptionKind,
    AssumptionMade,
    CheckKind,
    CostPaid,
    Error,
    ErrorKind,
    FailedCheck,
)
from mtg_goldfishing.domain.game.model import Zone
from mtg_goldfishing.domain.mana import Mana, ManaString, Restriction
from mtg_goldfishing.domain.payment.auto import choose_payment
from mtg_goldfishing.domain.payment.matching import Requirement, assign
from mtg_goldfishing.domain.payment.paying import (
    PayInstructions,
    PayWith,
    apply_payment,
    plan_payment,
    read_pay,
)
from mtg_goldfishing.domain.payment.sources import available_sources, count
from mtg_goldfishing.domain.reading.model import (
    CardReading,
    FaceReading,
    PermanentsCount,
)
from tests.support.builders import TESTED, Situation, a_game

M = ManaString.parse
CREATURE = "Creature — Bear"
SORCERY = "Sorcery"


def pay(
    situation: Situation,
    cost: str,
    *,
    paying_for: str | None = SORCERY,
    instructions: PayInstructions | None = None,
) -> tuple[CostPaid | None, list[Error | FailedCheck]]:
    """Plan and apply a payment on the situation's game; return what was paid and problems."""
    game, deck = situation.game, situation.deck
    plan, problems = plan_payment(
        game,
        deck,
        TESTED,
        M(cost),
        paying_for=paying_for,
        playing=None,
        instructions=instructions or PayInstructions(),
        subject="the card",
    )
    if plan is None:
        return None, problems
    events = apply_payment(game, deck, TESTED, plan)
    paid = next(e for e in events if isinstance(e, CostPaid))
    return paid, problems


def tapped_names(situation: Situation) -> list[str]:
    return sorted(c.name for c in situation.game.battlefield_of(TESTED) if c.tapped)


def units(*kinds: str) -> list[frozenset[str]]:
    return [frozenset(k) for k in kinds]


# @spec PAY-002
def test_a_colored_symbol_is_paid_only_by_its_color() -> None:
    need = Requirement.of(M("{G}"), phyrexian_life=0)
    assert assign(need, units("U")) is None
    assert assign(need, units("G")) is not None


# @spec PAY-002
def test_a_colorless_symbol_is_paid_only_by_colorless_mana() -> None:
    need = Requirement.of(M("{C}"), phyrexian_life=0)
    assert assign(need, units("G")) is None
    assert assign(need, units("C")) is not None


# @spec PAY-003
def test_a_number_is_paid_by_that_much_mana_of_any_kind() -> None:
    need = Requirement.of(M("{3}"), phyrexian_life=0)
    assert assign(need, units("G", "C")) is None
    assert assign(need, units("G", "C", "W")) is not None


# @spec PAY-004
def test_a_two_color_hybrid_is_paid_by_either_color() -> None:
    need = Requirement.of(M("{W/U}"), phyrexian_life=0)
    assert assign(need, units("U")) is not None
    assert assign(need, units("G")) is None


# @spec PAY-004
def test_a_generic_hybrid_is_paid_by_its_color_or_two_of_anything() -> None:
    need = Requirement.of(M("{2/W}"), phyrexian_life=0)
    assert assign(need, units("W")) is not None
    assert assign(need, units("G", "C")) is not None
    assert assign(need, units("G")) is None


# @spec PAY-005
def test_snow_is_paid_as_generic_and_the_assumption_is_stated() -> None:
    situation = a_game().with_battlefield("Forest", "Wastes").build()
    plan, _ = plan_payment(
        situation.game,
        situation.deck,
        TESTED,
        M("{S}{G}"),
        paying_for=CREATURE,
        playing=None,
        instructions=PayInstructions(),
        subject="Snow Thing",
    )
    assert plan is not None
    events = apply_payment(situation.game, situation.deck, TESTED, plan)
    assert AssumptionMade(AssumptionKind.SNOW_AS_GENERIC) in events
    assert tapped_names(situation) == ["Forest", "Wastes"]


# @spec PAY-006
def test_mana_in_the_pool_is_spent_before_any_source_is_tapped() -> None:
    situation = a_game().with_battlefield("Forest").with_pool("{G}").build()
    paid, _ = pay(situation, "{G}")
    assert paid is not None
    assert paid.from_pool == "{G}"
    assert tapped_names(situation) == []
    assert str(situation.game.tested.mana_pool) == "{}"


# @spec PAY-006, PAY-019
def test_pool_mana_goes_to_the_narrowest_requirement_so_the_rest_stays_payable() -> None:
    situation = a_game().with_battlefield("Island").with_pool("{W}").build()
    paid, problems = pay(situation, "{W/U}{W}")
    assert problems == []
    assert paid is not None
    assert paid.from_pool == "{W}"
    assert tapped_names(situation) == ["Island"]


# @spec PAY-006, PAY-019
def test_pool_mana_is_spent_on_whichever_hybrid_leaves_the_rest_payable() -> None:
    situation = a_game().with_battlefield("Plains").with_pool("{U}").build()
    paid, problems = pay(situation, "{W/U}{U/B}")
    assert problems == []
    assert paid is not None
    assert paid.from_pool == "{U}"
    assert tapped_names(situation) == ["Plains"]


# @spec PAY-007
def test_mana_a_source_makes_beyond_the_cost_goes_to_the_pool_and_is_reported() -> None:
    situation = a_game().with_battlefield("Sol Ring").build()
    paid, _ = pay(situation, "{1}")
    assert paid is not None
    assert paid.surplus == "{C}"
    assert str(situation.game.tested.mana_pool) == "{C}"


# @spec PAY-008
def test_restricted_mana_in_the_pool_pays_only_for_a_card_of_its_type() -> None:
    creatures = Restriction("creature spells", ("Creature",))
    situation = a_game().with_pool_units(Mana("G", creatures)).build()
    _, problems = pay(situation, "{G}", paying_for=SORCERY)
    assert [p.kind for p in problems] == [CheckKind.COST_NOT_PAYABLE]
    paid, _ = pay(situation, "{G}", paying_for=CREATURE)
    assert paid is not None


# @spec PAY-008
def test_restricted_mana_in_the_pool_never_pays_for_an_effect() -> None:
    creatures = Restriction("creature spells", ("Creature",))
    situation = a_game().with_pool_units(Mana("G", creatures)).build()
    _, problems = pay(situation, "{G}", paying_for=None)
    assert [p.kind for p in problems] == [CheckKind.COST_NOT_PAYABLE]


# @spec PAY-042
def test_surplus_from_a_restricted_source_keeps_its_restriction_in_the_pool() -> None:
    situation = a_game().with_battlefield("Mishra's Workshop").build()
    paid, _ = pay(situation, "{1}", paying_for="Artifact")
    assert paid is not None
    assert str(situation.game.tested.mana_pool) == "{C}*{C}*"


# @spec PAY-011
def test_a_counted_amount_is_evaluated_from_the_game_at_the_moment_of_payment() -> None:
    situation = a_game().with_battlefield("Gaea's Cradle", "Grizzly Bears", "Grizzly Bears").build()
    paid, _ = pay(situation, "{G}{G}")
    assert paid is not None
    assert paid.tapped == ("Gaea's Cradle",)


# @spec READ-011, PAY-011
def test_a_count_of_a_type_matches_whole_words_of_type_lines_ignoring_case() -> None:
    werebear = Card("Werebear Cub", (Face("Werebear Cub", M("{G}"), "Creature — Werebear"),))
    situation = (
        a_game()
        .with_card(werebear, CardReading((FaceReading(),)))
        .with_battlefield("Gaea's Cradle", "Grizzly Bears", "Werebear Cub")
        .build()
    )
    cradle = situation.named("Gaea's Cradle")
    bears = count(situation.game, situation.deck, cradle, PermanentsCount("bear"))
    assert bears == 1


# @spec PAY-012
def test_tapped_sources_are_not_used() -> None:
    situation = a_game().with_battlefield("Forest", tapped=True).build()
    _, problems = pay(situation, "{G}")
    assert [p.kind for p in problems] == [CheckKind.COST_NOT_PAYABLE]


# @spec PAY-012
def test_a_source_that_sacrifices_itself_is_never_used_automatically() -> None:
    situation = a_game().with_battlefield("Lotus Petal").build()
    _, problems = pay(situation, "{G}")
    assert [p.kind for p in problems] == [CheckKind.COST_NOT_PAYABLE]


# @spec PAY-013
def test_a_creature_that_entered_this_turn_is_not_used_as_a_mana_source() -> None:
    situation = a_game().in_step(None, turn=3).with_battlefield("Llanowar Elves", entered_turn=3)
    built = situation.build()
    built.game.step = None
    _, problems = pay(built, "{G}")
    assert [p.kind for p in problems] == [CheckKind.COST_NOT_PAYABLE]


# @spec PAY-013
def test_a_creature_that_entered_this_turn_is_used_when_another_permanent_grants_haste() -> None:
    situation = (
        a_game()
        .with_battlefield("Llanowar Elves", entered_turn=3)
        .with_battlefield("Concordant Crossroads")
        .build()
    )
    paid, _ = pay(situation, "{G}")
    assert paid is not None
    assert paid.tapped == ("Llanowar Elves",)


# @spec PAY-014
def test_a_restricted_source_is_used_only_for_a_card_of_its_types() -> None:
    situation = a_game().with_battlefield("Elvish Guidance Lord").build()
    _, problems = pay(situation, "{G}", paying_for=SORCERY)
    assert [p.kind for p in problems] == [CheckKind.COST_NOT_PAYABLE]
    paid, _ = pay(situation, "{G}", paying_for=CREATURE)
    assert paid is not None


# @spec PAY-015
def test_a_source_that_costs_life_is_not_used_when_it_would_take_life_below_one() -> None:
    situation = a_game().with_life(1).with_battlefield("City of Brass").build()
    _, problems = pay(situation, "{R}")
    assert [p.kind for p in problems] == [CheckKind.COST_NOT_PAYABLE]


# @spec PAY-015
def test_life_costing_sources_are_not_used_when_together_they_would_take_life_below_one() -> None:
    situation = a_game().with_life(2).with_battlefield("City of Brass", "City of Brass").build()
    _, problems = pay(situation, "{R}{R}")
    assert [p.kind for p in problems] == [CheckKind.COST_NOT_PAYABLE]


# @spec PAY-016, PAY-012
def test_a_source_whose_ability_costs_mana_has_that_cost_paid_in_the_same_payment() -> None:
    situation = a_game().with_battlefield("Forest", "Azorius Signet").build()
    paid, _ = pay(situation, "{W}{U}")
    assert paid is not None
    assert sorted(paid.tapped) == ["Azorius Signet", "Forest"]


# @spec PAY-017
def test_using_a_source_that_costs_life_takes_that_life_and_says_so() -> None:
    situation = a_game().with_battlefield("City of Brass").build()
    paid, _ = pay(situation, "{R}")
    assert paid is not None
    assert paid.life == 1
    assert situation.game.tested.life == 39


# @spec PAY-018, PAY-019
def test_the_auto_payment_system_pays_a_cost_from_available_sources() -> None:
    situation = a_game().with_battlefield("Forest", "Forest", "Island").build()
    paid, problems = pay(situation, "{2}{G}")
    assert problems == []
    assert paid is not None
    assert tapped_names(situation) == ["Forest", "Forest", "Island"]


# @spec PAY-020
def test_an_unpayable_cost_reports_the_cost_the_mana_available_and_the_missing_color() -> None:
    situation = a_game().with_battlefield("Forest", "Forest").build()
    _, problems = pay(situation, "{U}{U}")
    assert problems == [
        FailedCheck(
            CheckKind.COST_NOT_PAYABLE, subject="the card", cost=M("{U}{U}"), number=2, names=("U",)
        )
    ]


# @spec PAY-021
def test_phyrexian_symbols_are_paid_with_life_while_life_stays_positive() -> None:
    situation = a_game().with_battlefield("Swamp").build()
    paid, _ = pay(situation, "{1}{B/P}{B/P}")
    assert paid is not None
    assert paid.life == 4
    assert situation.game.tested.life == 36
    assert tapped_names(situation) == ["Swamp"]


# @spec PAY-021
def test_phyrexian_symbols_are_paid_with_mana_when_life_would_drop_below_one() -> None:
    situation = a_game().with_life(2).with_battlefield("Swamp", "Swamp").build()
    paid, _ = pay(situation, "{B/P}{B/P}")
    assert paid is not None
    assert paid.life == 0
    assert tapped_names(situation) == ["Swamp", "Swamp"]


# @spec PAY-021
def test_phyrexian_symbols_are_paid_with_mana_when_paying_life_leaves_no_valid_payment() -> None:
    situation = a_game().with_life(3).with_battlefield("City of Brass", "Forest").build()
    paid, problems = pay(situation, "{G/P}{B}")
    assert problems == []
    assert paid is not None
    assert tapped_names(situation) == ["City of Brass", "Forest"]
    assert situation.game.tested.life == 2


# @spec PAY-021
def test_the_phyrexian_symbol_paid_with_life_is_one_that_leaves_a_valid_payment() -> None:
    situation = a_game().with_life(3).with_battlefield("Forest").build()
    paid, problems = pay(situation, "{G/P}{U/P}")
    assert problems == []
    assert paid is not None
    assert situation.game.tested.life == 1
    assert tapped_names(situation) == ["Forest"]


# @spec PAY-022, PAY-023
def test_the_auto_payment_system_keeps_a_card_in_hand_castable() -> None:
    situation = (
        a_game()
        .with_battlefield("Plains", "Plains", "Plains", "Forest", "Forest")
        .with_hand("Selesnya Charm")
        .build()
    )
    pay(situation, "{1}{W}{W}")
    assert tapped_names(situation) == ["Forest", "Plains", "Plains"]


# @spec PAY-023
def test_a_commander_in_the_command_zone_counts_as_a_card_to_keep_castable() -> None:
    situation = (
        a_game()
        .with_commander("Thrasios, Triton Hero")
        .with_battlefield("Island", "Island", "Forest", "Wastes")
        .build()
    )
    pay(situation, "{1}{U}")
    assert tapped_names(situation) == ["Island", "Wastes"]


# @spec PAY-023
def test_a_card_to_keep_castable_counts_only_if_mana_could_pay_its_phyrexian_symbols() -> None:
    situation = (
        a_game()
        .with_battlefield("Swamp", "Swamp", "Forest", "Island")
        .with_hand("Dismember")
        .build()
    )
    pay(situation, "{1}")
    assert tapped_names(situation) == ["Forest"]


# @spec PAY-024
def test_when_cards_castable_tie_the_payment_keeping_more_colors_wins() -> None:
    situation = a_game().with_battlefield("Forest", "Island", "Island").build()
    pay(situation, "{1}")
    assert tapped_names(situation) == ["Island"]


# @spec PAY-024
def test_colorless_mana_is_not_a_color_kept_available() -> None:
    situation = a_game().with_battlefield("Wastes", "Forest", "Forest").build()
    pay(situation, "{1}")
    assert tapped_names(situation) == ["Wastes"]


# @spec PAY-025
def test_when_colors_tie_the_payment_keeping_more_mana_wins() -> None:
    situation = a_game().with_battlefield("Plains", "Plains", "Plains").build()
    pay(situation, "{2/W}")
    assert tapped_names(situation) == ["Plains"]


# @spec PAY-026
def test_lands_are_tapped_before_creatures() -> None:
    situation = a_game().with_battlefield("Llanowar Elves", "Forest").build()
    pay(situation, "{G}")
    assert tapped_names(situation) == ["Forest"]


# @spec PAY-027
def test_when_everything_else_ties_the_lowest_instance_ids_are_used() -> None:
    situation = a_game().with_battlefield("Forest", "Forest").build()
    pay(situation, "{G}")
    assert [c.id for c in situation.game.battlefield_of(TESTED) if c.tapped] == ["c1"]


# @spec PAY-028
def test_the_same_game_and_cost_give_the_same_payment_every_time() -> None:
    def tapped_ids() -> list[str]:
        situation = (
            a_game()
            .with_battlefield("Forest", "Island", "Plains", "City of Brass", "Sol Ring")
            .with_hand("Counterspell", "Selesnya Charm")
            .build()
        )
        pay(situation, "{2}{G}")
        return [c.id for c in situation.game.battlefield_of(TESTED) if c.tapped]

    assert len({tuple(tapped_ids()) for _ in range(5)}) == 1


# @spec PAY-029
def test_the_search_stops_after_the_limit_and_uses_the_best_payment_examined() -> None:
    situation = a_game().with_battlefield("Forest", "Island", "Island").build()
    sources = available_sources(situation.game, situation.deck, TESTED, paying_for=None)
    requirement = Requirement.of(M("{1}"), phyrexian_life=0)
    found = choose_payment(requirement, [], sources, [], life_budget=39, limit=1)
    assert found is not None
    payment, _ = found
    assert [s.name for s in payment.sources] == ["Forest"]


# @spec PAY-043
def test_a_payment_tapping_a_spare_source_is_used_when_no_other_was_examined() -> None:
    situation = a_game().with_battlefield("Wastes", "Sol Ring").build()
    sources = available_sources(situation.game, situation.deck, TESTED, paying_for=None)
    requirement = Requirement.of(M("{2}"), phyrexian_life=0)
    found = choose_payment(requirement, [], sources, [], life_budget=39, limit=1)
    assert found is not None
    payment, _ = found
    assert [s.name for s in payment.sources] == ["Wastes", "Sol Ring"]


# @spec PAY-041
def test_a_permanent_with_several_mana_abilities_pays_through_any_of_them() -> None:
    situation = a_game().with_battlefield("Caves of Koilos").build()
    paid, problems = pay(situation, "{W}")
    assert problems == []
    assert paid is not None
    assert paid.tapped == ("Caves of Koilos",)
    assert situation.game.tested.life == 39


# @spec PAY-041
def test_a_permanent_is_used_through_at_most_one_of_its_mana_abilities() -> None:
    situation = a_game().with_battlefield("Caves of Koilos").build()
    _, problems = pay(situation, "{C}{W}")
    assert [p.kind for p in problems] == [CheckKind.COST_NOT_PAYABLE]


# @spec PAY-041, PAY-026
def test_a_land_with_a_free_and_a_life_ability_pays_through_the_free_one_when_either_will_do() -> (
    None
):
    situation = a_game().with_battlefield("Caves of Koilos").build()
    paid, _ = pay(situation, "{1}")
    assert paid is not None
    assert paid.life == 0
    assert situation.game.tested.life == 40


# @spec PAY-030
def test_a_named_source_is_used_first_and_the_rest_is_paid_automatically() -> None:
    situation = a_game().with_battlefield("Lotus Petal", "Forest").build()
    paid, _ = pay(
        situation, "{1}{G}", instructions=PayInstructions(with_sources=(PayWith("Lotus Petal"),))
    )
    assert paid is not None
    assert paid.sacrificed == ("Lotus Petal",)
    assert paid.tapped == ("Forest",)
    assert situation.names_in(Zone.GRAVEYARD) == ["Lotus Petal"]


# @spec PAY-030
def test_pool_mana_and_a_named_source_s_mana_are_spent_together() -> None:
    situation = a_game().with_battlefield("Sol Ring", "Forest").with_pool("{G}").build()
    paid, problems = pay(
        situation, "{2}{G}", instructions=PayInstructions(with_sources=(PayWith("Sol Ring"),))
    )
    assert problems == []
    assert paid is not None
    assert tapped_names(situation) == ["Sol Ring"]


# @spec PAY-031
def test_a_named_source_with_stated_mana_makes_exactly_that_mana() -> None:
    situation = a_game().with_battlefield("Mana Vault").build()
    paid, _ = pay(
        situation,
        "{1}",
        instructions=PayInstructions(with_sources=(PayWith("Mana Vault", M("{C}{C}")),)),
    )
    assert paid is not None
    assert str(situation.game.tested.mana_pool) == "{C}"


# @spec PAY-032
def test_a_named_source_offering_a_choice_makes_the_option_that_serves_the_cost() -> None:
    situation = a_game().with_battlefield("Birds of Paradise").build()
    paid, problems = pay(
        situation, "{U}", instructions=PayInstructions(with_sources=(PayWith("Birds of Paradise"),))
    )
    assert problems == []
    assert paid is not None
    assert str(situation.game.tested.mana_pool) == "{}"


# @spec PAY-032, PAY-041
def test_a_named_source_with_several_mana_abilities_uses_the_one_that_serves_the_cost() -> None:
    situation = a_game().with_battlefield("Caves of Koilos").build()
    paid, problems = pay(
        situation, "{B}", instructions=PayInstructions(with_sources=(PayWith("Caves of Koilos"),))
    )
    assert problems == []
    assert paid is not None
    assert paid.life == 1
    assert str(situation.game.tested.mana_pool) == "{}"


# @spec PAY-033
def test_naming_a_permanent_without_a_mana_reading_or_stated_mana_is_an_error() -> None:
    situation = a_game().with_battlefield("Grizzly Bears").build()
    _, problems = pay(
        situation, "{G}", instructions=PayInstructions(with_sources=(PayWith("Grizzly Bears"),))
    )
    assert problems == [Error(ErrorKind.SOURCE_MANA_UNKNOWN, subject="Grizzly Bears")]


# @spec PAY-034
def test_naming_a_tapped_permanent_as_a_source_is_an_error() -> None:
    situation = a_game().with_battlefield("Forest", tapped=True).build()
    _, problems = pay(
        situation, "{G}", instructions=PayInstructions(with_sources=(PayWith("Forest"),))
    )
    assert problems == [Error(ErrorKind.SOURCE_TAPPED, subject="Forest")]


# @spec PAY-035
def test_naming_a_summoning_sick_creature_as_a_source_fails_a_rule_check() -> None:
    situation = a_game().with_battlefield("Llanowar Elves", entered_turn=3).build()
    paid, problems = pay(
        situation, "{G}", instructions=PayInstructions(with_sources=(PayWith("Llanowar Elves"),))
    )
    assert problems == [FailedCheck(CheckKind.SUMMONING_SICK_SOURCE, subject="Llanowar Elves")]
    assert paid is not None


# @spec PAY-036
def test_an_explicit_cost_is_paid_in_place_of_the_computed_cost() -> None:
    situation = a_game().with_battlefield("Forest").build()
    paid, _ = pay(situation, "{4}{G}", instructions=PayInstructions(cost=M("{G}")))
    assert paid is not None
    assert paid.cost == M("{G}")


# @spec PAY-038
def test_life_named_in_pay_is_paid_as_part_of_the_cost() -> None:
    situation = a_game().with_battlefield("Forest").build()
    paid, _ = pay(situation, "{G}", instructions=PayInstructions(life=3))
    assert paid is not None
    assert (situation.game.tested.life, tapped_names(situation)) == (37, ["Forest"])


# @spec PAY-039
def test_a_payment_reports_cost_sources_life_pool_and_surplus() -> None:
    situation = a_game().with_battlefield("Sol Ring", "City of Brass").with_pool("{R}").build()
    paid, _ = pay(situation, "{2}{R}")
    assert paid == CostPaid(
        cost=M("{2}{R}"), tapped=("Sol Ring",), from_pool="{R}", life=0, surplus=""
    )


# @spec APP-028
def test_a_malformed_pay_argument_is_an_error_not_an_exception() -> None:
    assert isinstance(read_pay({"with": 3}), Error)
    assert isinstance(read_pay({"cost": "{Q}"}), Error)
    assert isinstance(read_pay("Forest"), Error)


# @spec PAY-043
def test_the_auto_payment_system_taps_no_source_the_payment_could_do_without() -> None:
    situation = (
        a_game()
        .with_battlefield("Wastes", "Wastes", "Wastes", "Wastes", "Wastes")
        .with_battlefield("Forest", "Island", "Plains")
        .build()
    )
    paid, problems = pay(situation, "{3}{W}")
    assert problems == []
    assert paid is not None
    assert len(paid.tapped) == 4
    assert str(situation.game.tested.mana_pool) == "{}"
