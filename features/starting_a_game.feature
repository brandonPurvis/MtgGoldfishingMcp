Feature: Starting a game
  An agent loads a deck once, starts goldfish games on it, and mulligans until it keeps.
  The seed fixes every shuffle, so the same loaded deck and seed give the same game.

  Background:
    Given the Atraxa test deck is loaded

  Scenario: Loading a deck gives a deck id to start games with
    Then the response is OK
    And the response says "100 cards, commander Atraxa, Praetors' Voice."
    And the response has no status line

  Scenario: The same seed deals the same opening hand
    When I start a game with seed 42
    And I start another game with seed 42
    Then both games were dealt the same opening hand

  Scenario: A mulligan deals a new hand, and keeping starts the game
    Given I have started a game with seed 42
    When I take a mulligan
    Then the response is OK
    And the status line reads "Mulligan 1 · Hand 7 · #2"
    When I keep the hand
    Then the response is OK
    And the response says "T1 untap → upkeep → draw → main1"
    And the status line begins "T1 main1 · Hand 8 ·"
