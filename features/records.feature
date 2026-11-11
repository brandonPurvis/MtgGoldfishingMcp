Feature: Records
  Every accepted change is logged with the agent's choices and reasons, and `get_log`
  returns the game's records as JSON for an analysis process to read.

  Background:
    Given a game in the first main step of turn 1

  Scenario: The log is returned as JSON
    Given "Forest" is in my hand
    And I have played "Forest"
    When I ask for the game's log
    Then the response is JSON about the current game
    And the log has an entry for "play"
    And the response does not carry the error flag

  Scenario: Ending the game records the result and verdict
    When I end the game as a "win" with the verdict "fast mana carried it"
    Then the response is OK
    And the status line begins "Ended (win) ·"
    When I ask for the game's log
    Then the response is JSON about the current game
    And the log's game has the result "win"

  # @spec REC-090, TOOL-010
  Scenario: The log can be narrowed to the calls of some tools
    Given "Forest" is in my hand
    And I have played "Forest"
    When I advance to "main2"
    And I ask for the game's log of only the "play" calls
    Then the response is JSON about the current game
    And every log entry is for "play"
    And the log has an entry for "play"

  # @spec REC-095
  Scenario: A log filter naming something that is not a tool is refused
    When I ask for the game's log of only the "plya" calls
    Then the response says "plya, which are not tools"
    And the response carries the error flag
