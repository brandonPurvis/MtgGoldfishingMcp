Feature: Effects that reach other seats in a contested game
  A seat's delta may move, tap and destroy other seats' public cards, change any seat's life and
  take control of a permanent. Anything another seat must decide, or that touches its hand or
  library, is asked of that seat as a pending choice, which it answers with its own delta.

  Background:
    Given the Atraxa test deck is loaded
    And the Omnath test deck is loaded

  # @spec PLAY-097, PLAY-098, PLAY-099, GAME-109
  Scenario: An effect that makes another seat discard waits for that seat's answer
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S1 records an effect with delta {"ask": [{"seats": "opponents", "text": "discard a card"}]}
    Then the response is OK
    And the response says "(ask) for S2: discard a card."
    And the status line shows "Act S2 ask"
    When seat S1 advances
    Then the response is ERROR
    And the response says "S2 is asked to answer the ask choice"
    When seat S2 answers its ask choice by discarding a card
    Then the response is OK
    And seat S2's graveyard holds 1 card
    And the status line shows "Act S1 turn"

  # @spec PLAY-138, GAME-179, TOOL-087
  Scenario: An answer naming a card shows its answer text to every seat
    Given a started contested game against 2 Omnath decks with the tested seat first
    When seat S1 records an effect with delta {"ask": [{"seats": [2], "text": "name a card"}]}
    And seat S2 answers its ask choice with text "Lightning Bolt"
    Then the response is OK
    And the response says "(ask): "Lightning Bolt"."
    When seat S3 asks for the state
    Then the digest says "(ask): "Lightning Bolt""

  # @spec PLAY-102, PLAY-103, GAME-090
  Scenario: Looking at another seat's hand shows those cards to the looking seat only
    Given a started contested game against 2 Omnath decks with the tested seat first
    When seat S1 records an effect with delta {"look_at_hand": 2}
    Then the response is CHOICE
    And the response shows the cards of seat S2's hand as revealed
    And the status line shows "Act you hand"
    When seat S3 asks for the state
    Then the response does not show the cards of seat S2's hand
    When seat S1 chooses the first revealed card for its owner's graveyard
    Then the response is OK
    And seat S2's graveyard holds 1 card
    And seat S2 holds 6 cards

  # @spec PLAY-087, PLAY-088, PLAY-091, PLAY-092, PLAY-095
  Scenario: A delta destroys and exiles another seat's permanents and changes any seat's life
    Given a started contested game against 2 Omnath decks with the tested seat first
    And seat S1 has ended its turn
    And seat S2 puts "Elvish Mystic" onto the battlefield
    And seat S2 puts "Birds of Paradise" onto the battlefield
    And seat S2 has ended its turn
    And seat S3 has ended its turn
    When seat S1 records an effect with delta {"move": {"graveyard": ["Elvish Mystic"], "exile": ["Birds of Paradise"]}, "damage": {"2": 3}, "life": {"3": -2, "1": 1}}
    And seat S2 passes
    Then the response is OK
    And "Elvish Mystic" is in seat S2's graveyard
    And "Birds of Paradise" is in seat S2's exile
    And seat S2's life is 37
    And seat S3's life is 38
    And seat S1's life is 41

  # @spec PLAY-094, GAME-100, GAME-101, GAME-124
  Scenario: A delta changes control of a permanent, and its owner and controller are kept apart
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 has ended its turn
    And seat S2 puts "Elvish Mystic" onto the battlefield
    And seat S2 has ended its turn
    When seat S1 records an effect with delta {"control": {"1": ["Elvish Mystic"]}}
    And seat S2 passes
    Then the response is OK
    And seat S1 controls "Elvish Mystic" owned by seat S2
    When seat S1 asks for the state
    Then the response says "Elvish Mystic (owner S2)"
    When seat S1 records an effect with delta {"move": {"graveyard": ["Elvish Mystic"]}}
    Then "Elvish Mystic" is in seat S2's graveyard

  # @spec PLAY-079, GAME-157, TOOL-067
  Scenario: A delta that reaches into another seat's hand is refused
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S1 discards the first card in seat S2's hand by its instance id
    Then the response is ERROR
    And the response says the card is in a hidden zone of S2
    And the response says "Other seats' hands and libraries are reached through ask."
    And the game did not change

  # @spec PLAY-144, TOOL-094
  Scenario: A move that takes a card from another seat's zone names that seat
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Sol Ring" onto the battlefield
    And seat S1 has recorded an effect with delta {"control": {"2": ["Sol Ring"]}}
    When seat S1 records an immediate effect with delta {"move": {"hand": ["Sol Ring"]}}
    Then the response is OK
    And the response says "Moved Sol Ring: S2's battlefield → hand."
    When seat S2 asks for the state
    Then the digest says "Moved Sol Ring: S2's battlefield → hand"
