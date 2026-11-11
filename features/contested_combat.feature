Feature: Combat in a contested game
  The attacking seat names a seat for each attacker, each attacked seat declares its own blockers,
  the attacking seat states what happens to the creatures, and the service deals the combat
  damage to seats and keeps commander damage per commander per seat.

  Background:
    Given the Atraxa test deck is loaded
    And the Omnath test deck is loaded

  # @spec CMBT-030, CMBT-031, CMBT-037, CMBT-039, CMBT-061, TOOL-079
  Scenario: Attackers attack seats, and each attacked seat declares its blockers
    Given a started contested game against 2 Omnath decks with the tested seat first
    And seat S1 puts "Grizzly Bears" onto the battlefield
    And seat S1 puts "Llanowar Elves" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Elvish Mystic" onto the battlefield
    And seat S2 has ended its turn
    And seat S3 puts "Birds of Paradise" onto the battlefield
    And seat S3 has ended its turn
    When seat S1 attacks with targets {"Grizzly Bears": 2, "Llanowar Elves": 3}
    Then the response is OK
    And the response says "Attacking S2 with Grizzly Bears; S3 with Llanowar Elves."
    When seat S2 passes
    And seat S3 passes
    And seat S1 advances to "combat_damage"
    Then the response is OK
    And the response says "(blocks) for S2: attacked by Grizzly Bears (c"
    And the status line shows "Act S2 blocks"
    When seat S2 answers its blocks choice with blocks {"Elvish Mystic": "Grizzly Bears"}
    Then the response is OK
    And the status line shows "Act S3 blocks"
    When seat S3 answers its blocks choice with blocks {}
    Then the response is OK
    And the status line shows "Act S1 turn"
    When seat S1 advances to "combat_damage"
    Then seat S2's life is 40
    And seat S3's life is 39

  # @spec CMBT-061, CMBT-062, CMBT-066
  Scenario: The attacking seat states what happens to the creatures, and the service deals the damage to seats
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Atraxa, Praetors' Voice" onto the battlefield
    And seat S1 puts "Grizzly Bears" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Elvish Mystic" onto the battlefield
    And seat S2 has ended its turn
    When seat S1 attacks with ["Atraxa, Praetors' Voice", "Grizzly Bears"]
    And seat S2 passes
    And seat S1 advances to "declare_blockers"
    Then the status line shows "Act S2 blocks"
    When seat S2 answers its blocks choice with blocks {"Elvish Mystic": "Grizzly Bears"}
    And seat S1 advances to "combat_damage"
    Then the response says "Atraxa, Praetors' Voice dealt 4 combat damage to S2."
    And the response says "S2 life now 36; commander damage from Atraxa, Praetors' Voice 4."
    When seat S1 records an immediate effect with delta {"move": {"graveyard": ["Elvish Mystic"]}}
    Then the response is OK
    And "Elvish Mystic" is in seat S2's graveyard
    And seat S2's life is 36
    And the status line shows "Cmdr 4"

  # @spec CMBT-063, CMBT-064, CMBT-098, CMBT-101
  Scenario: A blocked attacker deals the seat it attacks only the trample damage its seat states
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Grizzly Bears" onto the battlefield
    And seat S1 puts "Craterhoof Behemoth" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Elvish Mystic" onto the battlefield
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 has ended its turn
    When seat S1 attacks with ["Grizzly Bears", "Craterhoof Behemoth"]
    And seat S2 passes
    And seat S1 advances to "declare_blockers"
    And seat S2 answers its blocks choice with blocks {"Elvish Mystic": "Craterhoof Behemoth", "Llanowar Elves": "Grizzly Bears"}
    And seat S1 states trample damage {"Craterhoof Behemoth": 4}
    Then the response is OK
    And the response says "Trample damage: Craterhoof Behemoth 4 to S2."
    When seat S1 advances to "combat_damage"
    Then seat S2's life is 36

  # @spec CMBT-081, CMBT-083, CMBT-090, CMBT-091, TOOL-079
  Scenario: A block the attacker's flying forbids is refused, and an override records it
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Birds of Paradise" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Elvish Mystic" onto the battlefield
    And seat S2 has ended its turn
    When seat S1 attacks with ["Birds of Paradise"]
    And seat S2 passes
    And seat S1 advances to "declare_blockers"
    Then the response says ", flying)."
    When seat S2 answers its blocks choice with blocks {"Elvish Mystic": "Birds of Paradise"}
    Then the response is REJECTED
    And the response says "Elvish Mystic cannot block Birds of Paradise, which has flying"
    When seat S2 answers its blocks choice with blocks {"Elvish Mystic": "Birds of Paradise"} and override "it gained reach this turn"
    Then the response is OK
    And the response says "Elvish Mystic blocks Birds of Paradise"
