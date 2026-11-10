Feature: Moving through the turn
  `advance` does each step's automatic actions, and stops early when the agent has
  something to do: a step trigger to resolve, or cards to discard before cleanup.

  Background:
    Given a game in the first main step of turn 1

  Scenario: Advance stops for a reminder, and continues when sent again
    Given "Phyrexian Arena" is on the battlefield
    And I have discarded down to seven cards
    When I advance to "main1"
    Then the response is OK
    And the response says "Reminder (upkeep): Phyrexian Arena"
    And the response says "Stopped at upkeep for the reminder."
    And the status line begins "T2 upkeep ·"
    When I record an effect from "Phyrexian Arena" that draws 1 card and changes my life by -1
    Then the response is OK
    And the status line shows "Life 39"
    When I advance to "main1"
    Then the status line begins "T2 main1 ·"

  Scenario: Discard down to seven at cleanup
    Given I hold 8 cards
    When I advance to "cleanup"
    Then the response is OK
    And the response says "Stopped at end"
    And the status line begins "T1 end · Hand 8 ·"
    When I advance to "cleanup" discarding "Forest"
    Then the response is OK
    And the status line begins "T1 cleanup · Hand 7 ·"
    And "Forest" is in my graveyard
