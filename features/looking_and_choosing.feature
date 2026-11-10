Feature: Looking at cards and choosing where they go
  A look reveals cards the agent could not otherwise see, and the game waits for the agent
  to say where they go before anything else happens.

  Background:
    Given a game in the first main step of turn 1

  Scenario: A look leaves a pending choice that choose finishes
    When I record an effect from "Ponder" that looks at the top 3 cards, the rest going to "library_top"
    Then the response is CHOICE
    And the response says "(look) revealed:"
    And the status line ends with "CHOICE pending"
    And the response does not carry the error flag
    When I advance to "main2"
    Then the response is ERROR
    And the response says "Accepted now: get_state, choose, end_game, get_log."
    When I choose the first revealed card for my hand
    Then the response is OK
    And the status line does not show a pending choice
    And my hand holds one card more than before the look
