# Card Reading — Specs

Design: `card-reading-design.md`. Prefix: `READ`.

## General

- [x] **READ-001**: The card reader shall produce every reading from a card face's rules text, type line and keywords alone, without access to game state.
- [x] **READ-002**: The card reader shall attach to every mana ability reading, keyword reading and enters-tapped reading a list of assumptions, which is empty when the text matched a known form exactly.

## Mana abilities: forms read exactly

- [x] **READ-003**: When a face's rules text contains an ability of the form `{T}: Add <mana symbols>.`, the card reader shall read a mana ability that taps and produces that fixed mana.
- [x] **READ-004**: When a mana ability's text offers alternatives joined by `or` (`{T}: Add {W} or {U}.`, `{T}: Add {R}, {G}, or {W}.`), the card reader shall read it as a choice among those options.
- [x] **READ-005**: When a mana ability's text adds a stated number of mana `of any color` or `of any one color`, the card reader shall read it as that amount of any color.
- [x] **READ-006**: When a mana ability's text adds mana of any color `in your commander's color identity`, the card reader shall read it as any color among the commander's color identity.
- [x] **READ-007**: When a mana ability's cost includes mana symbols, the card reader shall record those symbols as the ability's mana cost.
- [x] **READ-008**: When a mana ability's cost includes a life payment, or the ability's own text deals damage to its controller, the card reader shall record that amount as the ability's life cost.
- [x] **READ-009**: When a mana ability's cost includes sacrificing the permanent itself, the card reader shall mark the ability as sacrificing.
- [x] **READ-010**: When a mana ability's cost includes anything other than `{T}`, mana symbols, a life payment, or sacrificing the permanent itself, the card reader shall record that part of the cost verbatim as the ability's other cost.
- [x] **READ-011**: When a mana ability's text adds mana `for each <type> you control`, the card reader shall read it as a counted amount over permanents the controller has whose type line contains that type word, ignoring case.
- [x] **READ-012**: When a mana ability's text adds an amount equal to the controller's devotion to one or more colors, the card reader shall read it as a counted amount over that devotion.
- [x] **READ-013**: When a mana ability's text adds mana for each card in the controller's hand or graveyard, the card reader shall read it as a counted amount over that zone.
- [x] **READ-014**: When a mana ability's text restricts spending to spells of named card types (`Spend this mana only to cast creature spells`), the card reader shall record a restriction listing those card types.
- [x] **READ-015**: When a face's type line contains a basic land type (`Plains`, `Island`, `Swamp`, `Mountain`, `Forest`), the card reader shall read the corresponding tap-for-one-mana ability even if the rules text is empty.
- [x] **READ-016**: When a face has more than one mana ability, the card reader shall read each ability separately.
- [x] **READ-017**: The card reader shall not include in a mana ability's life cost any life lost through a separate triggered ability on the same card.

## Mana abilities: best guesses

- [x] **READ-018**: When a mana ability carries a condition on its activation, the card reader shall read it as always usable and add the assumption "ignores activation condition".
- [x] **READ-019**: When a mana ability adds more mana under a condition, the card reader shall read the unconditional amount and add the assumption "ignores conditional bonus".
- [x] **READ-020**: When a mana ability carries a spending restriction that names no card types the reader recognises, the card reader shall record a restriction with no card types and add the assumption "restriction not understood".
- [x] **READ-021**: When a mana ability's amount cannot be read but the card's produced colors are known, the card reader shall read one mana of those colors and add the assumption "amount assumed to be one".
- [x] **READ-022**: When a mana ability's colors depend on what other permanents could produce, the card reader shall read it as any color and add the assumption "assumes any color".
- [x] **READ-023**: When a mana ability adds a stated amount `in any combination of colors`, the card reader shall read it as that amount of any color and add the assumption "assumes one color for the whole amount".

## Mana abilities: no reading

- [x] **READ-024**: When an ability adds mana but its cost neither taps nor sacrifices the permanent, the card reader shall give that ability no reading.
- [x] **READ-025**: When mana is added by a triggered ability rather than an activated one, the card reader shall give that ability no reading.
- [x] **READ-026**: When a card has produced colors but an ability of it has no reading, the card reader shall report that ability as unread.

## Reporting

- [x] **READ-027**: When asked to report on a set of cards, the card reader shall list separately: mana abilities read exactly, mana abilities read with assumptions together with each assumption, unread mana abilities, cards with step triggers, cards that have or grant haste or vigilance, and cards that enter tapped or are assumed to enter untapped.

## Step triggers

- [x] **READ-028**: When a face's rules text contains a beginning-of-upkeep phrase that applies to the controller (`At the beginning of your upkeep`, `of each upkeep`, `of each player's upkeep`), the card reader shall read a step trigger for `upkeep`.
- [x] **READ-029**: When a face's rules text contains a beginning-of-draw-step phrase that applies to the controller, the card reader shall read a step trigger for `draw`.
- [x] **READ-030**: When a face's rules text contains `At the beginning of your precombat main phase` or `of your first main phase`, the card reader shall read a step trigger for `main1`.
- [x] **READ-031**: When a face's rules text contains `At the beginning of combat on your turn` or `of each combat`, the card reader shall read a step trigger for `begin_combat`.
- [x] **READ-032**: When a face's rules text contains `At the beginning of your postcombat main phase` or `of your second main phase`, the card reader shall read a step trigger for `main2`.
- [x] **READ-033**: When a face's rules text contains a beginning-of-end-step phrase that applies to the controller (`At the beginning of your end step`, `of each end step`, `of each player's end step`, `of the end step`), the card reader shall read a step trigger for `end`.
- [x] **READ-034**: When a beginning-of-step phrase names only opponents, the card reader shall read no step trigger from it.
- [x] **READ-035**: When a face has several triggers for the same step, the card reader shall read that step once.

## Haste, vigilance and flash

- [x] **READ-036**: When haste, vigilance or flash stands as an ability of the card itself, on its own line or in a comma-separated keyword line, the card reader shall read that keyword as the card's own.
- [x] **READ-037**: When a static ability gives haste or vigilance to creatures the controller has (`Creatures you control have`, `Other creatures you control have`, `<Subtype> creatures you control have`), including as one item in a longer list, the card reader shall read a grant of that keyword recording whether it includes the card itself and any subtype it is limited to.
- [x] **READ-038**: When rules text gives haste or vigilance for a limited time (`until end of turn`), the card reader shall not read it as a grant.
- [x] **READ-039**: When haste or vigilance is conferred through attachment (`Equipped creature has`, `Enchanted creature has`), the card reader shall not read it.
- [x] **READ-040**: When a card has or grants haste or vigilance only under a condition, the card reader shall read the keyword as present and add the assumption "assumes its condition is met".
- [x] **READ-044**: When a static ability gives haste or vigilance to `<plural subtype> you control` (`Goblins you control have haste`), the card reader shall read a grant limited to that subtype in its singular form.

## Entering tapped

- [x] **READ-041**: When a face's rules text says without condition that the permanent enters tapped, the card reader shall read the permanent as entering tapped.
- [x] **READ-042**: When a face's rules text says the permanent enters tapped subject to a condition or a choice, the card reader shall read it as entering untapped and add an assumption that quotes the condition.
- [x] **READ-043**: When a face's rules text says nothing about entering tapped, the card reader shall read the permanent as entering untapped with no assumption.
