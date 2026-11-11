Feature: Elimination and the end of a contested game
  A seat at 0 life, or dealt 21 combat damage by one commander, is eliminated by the service; an
  opposing seat may concede. The cards an eliminated seat owns leave the game and it takes no
  more turns. Only the tested seat ends the game, and it may do so at any time.

  Background:
    Given the Atraxa test deck is loaded
    And the Omnath test deck is loaded

  # @spec GAME-129, GAME-132, GAME-133, GAME-136, GAME-138, TURN-031
  Scenario: A seat at 0 life is eliminated, its cards leave the game and it takes no more turns
    Given a started contested game against 2 Omnath decks with the tested seat first
    And seat S1 puts "Sol Ring" onto the battlefield
    And seat S1 has recorded an effect with delta {"control": {"2": ["Sol Ring"]}}
    And seat S1 has ended its turn
    And seat S2 puts "Elvish Mystic" onto the battlefield
    And seat S2 has ended its turn
    And seat S3 has ended its turn
    And seat S1 has recorded an effect with delta {"control": {"1": ["Elvish Mystic"]}}
    When seat S1 records an effect with delta {"damage": {"2": 40}}
    And seat S2 passes
    Then the response is OK
    And the response says "S2 is eliminated: its life is 0 or less."
    And seat S2 is eliminated
    And no card seat S2 owns is left in the game
    And seat S1 controls "Sol Ring" owned by seat S1
    When seat S1 ends its turn
    Then seat S3 is the active seat

  # @spec GAME-130, CMBT-062, CMBT-065
  Scenario: A seat dealt 21 combat damage by one commander is eliminated
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Atraxa, Praetors' Voice" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 has ended its turn
    When seat S1 attacks with ["Atraxa, Praetors' Voice"] dealing {"Atraxa, Praetors' Voice": 21}
    And seat S1 advances to "combat_damage"
    Then the response says "S2 is eliminated: 21 or more combat damage from one commander."
    And seat S2's life is 19
    And seat S2 is eliminated

  # @spec GAME-131, GAME-136
  Scenario: An opposing seat concedes, and the game goes on without it
    Given a started contested game against 2 Omnath decks with the tested seat first
    When seat S3 concedes
    Then the response is OK
    And the response says "S3 conceded and is eliminated."
    And seat S3 is eliminated
    And the game has not ended
    When seat S1 ends its turn
    And seat S2 ends its turn
    Then seat S1 is the active seat

  # @spec GAME-158, GAME-159
  Scenario: An opposing seat concedes during mulligans, and the game starts without it
    Given a contested game against 1 Omnath deck with seed 42 and the tested seat at position 1
    When seat S1 keeps its hand
    And seat S2 concedes
    Then the response is OK
    And the response says "S1 T1 untap → upkeep → draw → main1"
    And seat S1 is the active seat

  # @spec GAME-142, GAME-143
  Scenario: Notices are raised when every opponent and when the tested seat is eliminated
    Given a started contested game against 2 Omnath decks with the tested seat first
    When seat S1 records an effect with delta {"damage": {"2": 40, "3": 40}}
    Then the response says "Notice: every opposing seat has been eliminated"
    When seat S1 records an effect with delta {"life": -40}
    Then the response says "Notice: the tested seat has been eliminated"
    And the response says "Notice: every opposing seat has been eliminated"

  # @spec GAME-045, GAME-131, GAME-148
  Scenario: Only the tested seat ends the game, even while the game waits on another seat
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S1 records an effect with delta {"ask": [{"seats": [2], "text": "sacrifice a creature"}]}
    Then the status line shows "Act S2 ask"
    When seat S1 ends the game as a "win"
    Then the response is OK
    And the game has ended
