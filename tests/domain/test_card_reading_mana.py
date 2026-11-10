"""The card reader's reading of mana abilities."""

from mtg_goldfishing.domain.cards import Card
from mtg_goldfishing.domain.mana import ManaString, Restriction
from mtg_goldfishing.domain.reading.model import (
    AMOUNT_ASSUMED_ONE,
    ASSUMES_ANY_COLOR,
    ASSUMES_ONE_COLOR,
    IGNORES_ACTIVATION_CONDITION,
    IGNORES_CONDITIONAL_BONUS,
    RESTRICTION_NOT_UNDERSTOOD,
    AnyColor,
    AnyColorScope,
    CardsInGraveyardCount,
    CardsInHandCount,
    Choice,
    Counted,
    DevotionCount,
    Fixed,
    ManaAbility,
    PermanentsCount,
)
from mtg_goldfishing.domain.reading.reader import read_card
from tests.support.cards import a_card


def mana(text: str) -> ManaString:
    return ManaString.parse(text)


def abilities_of(card: Card) -> tuple[ManaAbility, ...]:
    return read_card(card).faces[0].mana_abilities


def the_ability_of(card: Card) -> ManaAbility:
    (ability,) = abilities_of(card)
    return ability


def unread_of(card: Card) -> tuple[str, ...]:
    return read_card(card).faces[0].unread_mana_abilities


# Forms read exactly


# @spec READ-003
def test_a_tap_ability_that_adds_one_symbol_is_read_as_that_fixed_mana() -> None:
    llanowar_elves = a_card("Llanowar Elves", "{T}: Add {G}.", "Creature — Elf Druid")
    assert the_ability_of(llanowar_elves) == ManaAbility(
        produces=Fixed(mana("{G}")), taps=True, text="{T}: Add {G}."
    )


# @spec READ-003
def test_a_tap_ability_that_adds_several_symbols_is_read_as_all_of_them() -> None:
    sol_ring = a_card("Sol Ring", "{T}: Add {C}{C}.")
    assert the_ability_of(sol_ring).produces == Fixed(mana("{C}{C}"))


# @spec READ-004
def test_two_options_joined_by_or_are_read_as_a_choice() -> None:
    glacial_fortress = a_card(
        "Glacial Fortress",
        "This land enters tapped unless you control a Plains or an Island.\n{T}: Add {W} or {U}.",
        "Land",
    )
    assert the_ability_of(glacial_fortress).produces == Choice((mana("{W}"), mana("{U}")))


# @spec READ-004
def test_a_comma_separated_list_of_options_is_read_as_a_choice_among_all_of_them() -> None:
    jungle_shrine = a_card(
        "Jungle Shrine", "This land enters tapped.\n{T}: Add {R}, {G}, or {W}.", "Land"
    )
    assert the_ability_of(jungle_shrine).produces == Choice((mana("{R}"), mana("{G}"), mana("{W}")))


# @spec READ-005
def test_one_mana_of_any_color_is_read_as_any_color() -> None:
    birds = a_card(
        "Birds of Paradise", "Flying\n{T}: Add one mana of any color.", "Creature — Bird"
    )
    assert the_ability_of(birds) == ManaAbility(
        produces=AnyColor(1, AnyColorScope.ANY), text="{T}: Add one mana of any color."
    )


# @spec READ-005
def test_a_stated_amount_of_any_one_color_is_read_as_that_amount() -> None:
    gilded_lotus = a_card("Gilded Lotus", "{T}: Add three mana of any one color.")
    assert the_ability_of(gilded_lotus).produces == AnyColor(3, AnyColorScope.ANY)


# @spec READ-006
def test_any_color_in_the_commanders_identity_is_read_as_that_scope() -> None:
    arcane_signet = a_card(
        "Arcane Signet", "{T}: Add one mana of any color in your commander's color identity."
    )
    assert the_ability_of(arcane_signet).produces == AnyColor(1, AnyColorScope.COMMANDER_IDENTITY)


# @spec READ-007
def test_mana_symbols_in_the_cost_are_the_abilitys_mana_cost() -> None:
    azorius_signet = a_card("Azorius Signet", "{1}, {T}: Add {W}{U}.")
    assert the_ability_of(azorius_signet) == ManaAbility(
        produces=Fixed(mana("{W}{U}")),
        mana_cost=mana("{1}"),
        text="{1}, {T}: Add {W}{U}.",
    )


# @spec READ-008
def test_a_life_payment_in_the_cost_is_the_abilitys_life_cost() -> None:
    horizon_canopy = a_card(
        "Horizon Canopy",
        "{T}, Pay 1 life: Add {G} or {W}.\n{1}, {T}, Sacrifice this land: Draw a card.",
        "Land",
    )
    assert the_ability_of(horizon_canopy).life == 1


# @spec READ-008
def test_damage_the_ability_deals_to_its_controller_is_the_abilitys_life_cost() -> None:
    ancient_tomb = a_card(
        "Ancient Tomb", "{T}: Add {C}{C}. This land deals 2 damage to you.", "Land"
    )
    ability = the_ability_of(ancient_tomb)
    assert (ability.produces, ability.life, ability.assumptions) == (Fixed(mana("{C}{C}")), 2, ())


# @spec READ-009
def test_sacrificing_the_permanent_itself_marks_the_ability_as_sacrificing() -> None:
    lotus_petal = a_card("Lotus Petal", "{T}, Sacrifice this artifact: Add one mana of any color.")
    ability = the_ability_of(lotus_petal)
    assert (ability.taps, ability.sacrifices, ability.other_cost) == (True, True, None)


# @spec READ-009
def test_sacrificing_the_permanent_by_name_marks_the_ability_as_sacrificing() -> None:
    lotus_petal = a_card("Lotus Petal", "{T}, Sacrifice Lotus Petal: Add one mana of any color.")
    assert the_ability_of(lotus_petal).sacrifices


# @spec READ-010
def test_any_other_part_of_the_cost_is_carried_verbatim() -> None:
    gemstone_mine = a_card(
        "Gemstone Mine",
        "This land enters with three mining counters on it.\n"
        "{T}, Remove a mining counter from this land: Add one mana of any color. "
        "If there are no mining counters on this land, sacrifice it.",
        "Land",
    )
    ability = the_ability_of(gemstone_mine)
    assert (ability.other_cost, ability.sacrifices) == (
        "Remove a mining counter from this land",
        False,
    )


# @spec READ-011
def test_mana_for_each_creature_you_control_is_counted_over_creatures() -> None:
    gaeas_cradle = a_card(
        "Gaea's Cradle", "{T}: Add {G} for each creature you control.", "Legendary Land"
    )
    assert the_ability_of(gaeas_cradle).produces == Counted(
        PermanentsCount("creature"), mana("{G}")
    )


# @spec READ-011
def test_mana_for_each_permanent_of_a_subtype_you_control_is_counted_over_that_subtype() -> None:
    elvish_archdruid = a_card(
        "Elvish Archdruid",
        "Other Elf creatures you control get +1/+1.\n{T}: Add {G} for each Elf you control.",
        "Creature — Elf Druid",
    )
    assert the_ability_of(elvish_archdruid).produces == Counted(PermanentsCount("Elf"), mana("{G}"))


# @spec READ-011
def test_any_color_for_each_permanent_you_control_is_counted_any_color() -> None:
    wirewood_channeler = a_card(
        "Wirewood Channeler",
        "{T}: Add one mana of any color for each Elf you control.",
        "Creature — Elf Druid",
    )
    assert the_ability_of(wirewood_channeler).produces == Counted(
        PermanentsCount("Elf"), AnyColor()
    )


# @spec READ-011
def test_mana_for_each_permanent_on_the_battlefield_is_counted_over_your_permanents() -> None:
    priest_of_titania = a_card(
        "Priest of Titania", "{T}: Add {G} for each Elf on the battlefield.", "Creature — Elf Druid"
    )
    ability = the_ability_of(priest_of_titania)
    assert (ability.produces, ability.assumptions) == (
        Counted(PermanentsCount("Elf"), mana("{G}")),
        (),
    )


# @spec READ-012
def test_mana_equal_to_devotion_is_counted_over_that_devotion() -> None:
    karametras_acolyte = a_card(
        "Karametra's Acolyte",
        "{T}: Add an amount of {G} equal to your devotion to green. (Each {G} in the mana costs "
        "of permanents you control counts toward your devotion to green.)",
        "Creature — Human Druid",
    )
    assert the_ability_of(karametras_acolyte).produces == Counted(
        DevotionCount(("G",)), mana("{G}")
    )


# @spec READ-013
def test_mana_for_each_card_in_hand_is_counted_over_the_hand() -> None:
    hand_source = a_card("Hand Source", "{T}: Add {C} for each card in your hand.")
    assert the_ability_of(hand_source).produces == Counted(CardsInHandCount(), mana("{C}"))


# @spec READ-013
def test_mana_for_each_card_of_a_type_in_the_graveyard_is_counted_over_the_graveyard() -> None:
    graveyard_source = a_card(
        "Graveyard Source", "{T}: Add {B} for each creature card in your graveyard."
    )
    assert the_ability_of(graveyard_source).produces == Counted(
        CardsInGraveyardCount("creature"), mana("{B}")
    )


# @spec READ-014
def test_spending_limited_to_a_card_type_is_a_restriction_to_that_type() -> None:
    ancient_ziggurat = a_card(
        "Ancient Ziggurat",
        "{T}: Add one mana of any color. Spend this mana only to cast a creature spell.",
        "Land",
    )
    ability = the_ability_of(ancient_ziggurat)
    assert (ability.restriction, ability.assumptions) == (
        Restriction("Spend this mana only to cast a creature spell.", ("Creature",)),
        (),
    )


# @spec READ-014
def test_spending_limited_to_several_card_types_lists_each_of_them() -> None:
    source = a_card(
        "Spell Source",
        "{T}: Add {U}. Spend this mana only to cast instant or sorcery spells.",
    )
    restriction = the_ability_of(source).restriction
    assert restriction is not None
    assert restriction.card_types == ("Instant", "Sorcery")


# @spec READ-015
def test_a_basic_land_type_gives_its_tap_ability_without_rules_text() -> None:
    forest = a_card("Forest", "", "Basic Land — Forest")
    assert the_ability_of(forest) == ManaAbility(produces=Fixed(mana("{G}")), text="{T}: Add {G}.")


# @spec READ-015, READ-016
def test_each_basic_land_type_gives_its_own_tap_ability() -> None:
    hallowed_fountain = a_card(
        "Hallowed Fountain",
        "({T}: Add {W} or {U}.)\nAs this land enters, you may pay 2 life. "
        "If you don't, it enters tapped.",
        "Land — Plains Island",
    )
    assert [ability.produces for ability in abilities_of(hallowed_fountain)] == [
        Fixed(mana("{W}")),
        Fixed(mana("{U}")),
    ]


# @spec READ-016
def test_each_mana_ability_of_a_face_is_read_separately() -> None:
    talisman = a_card(
        "Talisman of Progress",
        "{T}: Add {C}.\n{T}: Add {W} or {U}. This artifact deals 1 damage to you.",
    )
    assert abilities_of(talisman) == (
        ManaAbility(produces=Fixed(mana("{C}")), text="{T}: Add {C}."),
        ManaAbility(
            produces=Choice((mana("{W}"), mana("{U}"))),
            life=1,
            text="{T}: Add {W} or {U}. This artifact deals 1 damage to you.",
        ),
    )


# @spec READ-017
def test_damage_from_a_separate_triggered_ability_is_not_a_life_cost() -> None:
    city_of_brass = a_card(
        "City of Brass",
        "Whenever this land becomes tapped, it deals 1 damage to you.\n"
        "{T}: Add one mana of any color.",
        "Land",
    )
    assert the_ability_of(city_of_brass).life == 0


# Best guesses


# @spec READ-018
def test_an_activation_condition_is_ignored_and_stated() -> None:
    temple = a_card(
        "Temple of the False God",
        "{T}: Add {C}{C}. Activate only if you control five or more lands.",
        "Land",
    )
    ability = the_ability_of(temple)
    assert (ability.produces, ability.assumptions) == (
        Fixed(mana("{C}{C}")),
        (IGNORES_ACTIVATION_CONDITION,),
    )


# @spec READ-019
def test_a_conditional_bonus_is_ignored_and_stated() -> None:
    ilysian_caryatid = a_card(
        "Ilysian Caryatid",
        "{T}: Add one mana of any color. If you control a creature with power 4 or greater, "
        "add two mana of any one color instead.",
        "Creature — Plant",
    )
    ability = the_ability_of(ilysian_caryatid)
    assert (ability.produces, ability.assumptions) == (
        AnyColor(1),
        (IGNORES_CONDITIONAL_BONUS,),
    )


# @spec READ-020
def test_a_restriction_naming_no_card_type_has_no_card_types_and_is_stated() -> None:
    pillar = a_card(
        "Pillar of the Paruns",
        "{T}: Add one mana of any color. Spend this mana only to cast a multicolored spell.",
        "Land",
    )
    ability = the_ability_of(pillar)
    assert (ability.restriction, ability.assumptions) == (
        Restriction("Spend this mana only to cast a multicolored spell."),
        (RESTRICTION_NOT_UNDERSTOOD,),
    )


# @spec READ-021
def test_an_unreadable_amount_is_one_mana_of_the_produced_color_and_is_stated() -> None:
    overgrown_battlement = a_card(
        "Overgrown Battlement",
        "Defender\n{T}: Add {G} for each creature you control with defender.",
        "Creature — Wall",
        produced_colors=("G",),
    )
    ability = the_ability_of(overgrown_battlement)
    assert (ability.produces, ability.assumptions) == (Fixed(mana("{G}")), (AMOUNT_ASSUMED_ONE,))


# @spec READ-021
def test_an_unreadable_amount_with_several_produced_colors_is_a_choice_of_one_of_them() -> None:
    faeburrow_elder = a_card(
        "Faeburrow Elder",
        "Vigilance\nThis creature gets +1/+1 for each color among permanents you control.\n"
        "{T}: For each color among permanents you control, add one mana of that color.",
        "Creature — Treefolk Druid",
        produced_colors=("G", "W"),
    )
    ability = the_ability_of(faeburrow_elder)
    assert (ability.produces, ability.assumptions) == (
        Choice((mana("{W}"), mana("{G}"))),
        (AMOUNT_ASSUMED_ONE,),
    )


# @spec READ-022
def test_colors_a_land_an_opponent_controls_could_produce_are_read_as_any_color() -> None:
    exotic_orchard = a_card(
        "Exotic Orchard",
        "{T}: Add one mana of any color that a land an opponent controls could produce.",
        "Land",
    )
    ability = the_ability_of(exotic_orchard)
    assert (ability.produces, ability.assumptions) == (AnyColor(1), (ASSUMES_ANY_COLOR,))


# @spec READ-022
def test_types_a_land_you_control_could_produce_are_read_as_any_color() -> None:
    reflecting_pool = a_card(
        "Reflecting Pool",
        "{T}: Add one mana of any type that a land you control could produce.",
        "Land",
    )
    ability = the_ability_of(reflecting_pool)
    assert (ability.produces, ability.assumptions) == (AnyColor(1), (ASSUMES_ANY_COLOR,))


# @spec READ-023
def test_an_amount_in_any_combination_of_colors_is_read_as_that_amount_of_one_color() -> None:
    cascading_cataracts = a_card(
        "Cascading Cataracts",
        "Indestructible\n{T}: Add {C}.\n{5}, {T}: Add five mana in any combination of colors.",
        "Land",
    )
    combination = abilities_of(cascading_cataracts)[1]
    assert (combination.produces, combination.mana_cost, combination.assumptions) == (
        AnyColor(5),
        mana("{5}"),
        (ASSUMES_ONE_COLOR,),
    )


# No reading


# @spec READ-024
def test_an_ability_that_neither_taps_nor_sacrifices_has_no_reading() -> None:
    pentad_prism = a_card(
        "Pentad Prism",
        "Sunburst (This artifact enters with a charge counter on it for each color of mana "
        "spent to cast it.)\n"
        "Remove a charge counter from this artifact: Add one mana of any color.",
    )
    assert abilities_of(pentad_prism) == ()


# @spec READ-024
def test_a_mana_filter_has_no_reading() -> None:
    filter_source = a_card("Filter Source", "{1}: Add {R}.")
    assert abilities_of(filter_source) == ()


# @spec READ-025
def test_mana_added_by_a_triggered_ability_has_no_reading() -> None:
    wild_growth = a_card(
        "Wild Growth",
        "Enchant land\nWhenever enchanted land is tapped for mana, "
        "its controller adds an additional {G}.",
        "Enchantment — Aura",
    )
    assert abilities_of(wild_growth) == ()


# @spec READ-026
def test_an_ability_with_no_reading_on_a_card_with_produced_colors_is_unread() -> None:
    pentad_prism = a_card(
        "Pentad Prism",
        "Remove a charge counter from this artifact: Add one mana of any color.",
        produced_colors=("W", "U", "B", "R", "G"),
    )
    assert unread_of(pentad_prism) == (
        "Remove a charge counter from this artifact: Add one mana of any color.",
    )


# @spec READ-016, READ-026
def test_a_card_can_have_one_ability_read_and_another_unread() -> None:
    coalition_relic = a_card(
        "Coalition Relic",
        "{T}: Add one mana of any color.\n{T}: Put a charge counter on this artifact.\n"
        "At the beginning of your first main phase, remove all charge counters from this "
        "artifact. Add one mana of any color for each charge counter removed this way.",
        produced_colors=("W", "U", "B", "R", "G"),
    )
    reading = read_card(coalition_relic).faces[0]
    assert (len(reading.mana_abilities), len(reading.unread_mana_abilities)) == (1, 1)


# @spec READ-026
def test_an_ability_with_no_reading_on_a_card_without_produced_colors_is_not_unread() -> None:
    pentad_prism = a_card(
        "Pentad Prism", "Remove a charge counter from this artifact: Add one mana of any color."
    )
    assert unread_of(pentad_prism) == ()
