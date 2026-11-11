Feature: Coordinating the seats of a contested game
  Seats act one at a time. A seat with nothing to do calls wait, which returns when it has,
  and every response to a seat begins with what the other seats did since its last call.
  Every seat's call is recognised as a resend against that seat's own most recent change,
  and the records name the seat behind every entry and call.

  Background:
    Given the Atraxa test deck is loaded
    And the Omnath test deck is loaded

  # @spec APP-036, APP-037, GAME-091, REC-040, TOOL-035, TOOL-037
  Scenario: Every response to a seat begins with a digest of the other seats' public events
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S1 records an effect with delta {"draw": 1}
    And seat S2 asks for the state
    Then the response is OK
    And the response begins with a digest line for change #4 made by S1
    And the digest says "S1 drew a card"
    And the digest names no card of seat S1's hand

  # @spec APP-081, GAME-154, TOOL-057
  Scenario: A seat's digest names the card it drew when another seat's call began its turn
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S2's hand is noted
    When seat S1 ends its turn
    And seat S2 asks for the state
    Then the digest names the card seat S2 drew

  # @spec TOOL-038
  Scenario: A response with nothing new from the other seats has no digest lines
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S1 records an effect with delta {"life": 1}
    And seat S2 asks for the state
    And seat S2 asks for the state
    Then the response has no digest lines

  # @spec APP-063, APP-064
  Scenario: wait returns at once for the seat to act, with what it is asked
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S1 waits
    Then the response is OK
    And the response says "You are asked to take your turn."

  # @spec APP-064, APP-068
  Scenario: wait returns when another seat's change makes the waiting seat the seat to act
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S2 starts waiting
    And seat S1 ends its turn
    Then seat S2's wait returns "OK You are asked to take your turn."

  # @spec APP-066, APP-096, TOOL-063
  @wip
  Scenario: wait times out and names the seat the game is waiting on and for how long
    Given a started contested game against 1 Omnath deck with the tested seat first
    When 2 minutes pass
    And seat S2 waits with a timeout of 1 second
    Then the response is OK
    And the response says "Still waiting: S1 is asked to take its turn (for 2 min)."

  # @spec GAME-036, GAME-126, APP-055
  Scenario: A resend is recognised against the sending seat's own change after another seat acted
    Given a contested game against 1 Omnath deck with seed 42 and the tested seat at position 1
    When seat S1 takes a mulligan after change 1
    And seat S2 takes a mulligan
    And seat S1 takes a mulligan after change 1
    Then the response says "Already applied as change #2; nothing was applied again."
    And the game's change number is 3

  # @spec GAME-037, GAME-127
  Scenario: A changing call with a stale after is an error
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S1 records an effect sent after change 2 with delta {"life": 1}
    Then the response is ERROR
    And the response says "The game is now at change #3"
    And the game did not change

  # @spec REC-028, REC-052, REC-056
  Scenario: Every log entry and call record names its seat, and the record holds the opposing decks
    Given a started contested game against 2 Omnath decks with the tested seat first
    When seat S2 asks for the state
    And seat S3 asks for the game's log with the call records
    Then every log entry and call record names the seat that made it
    And the log's game lists 2 opposing seats on the Omnath deck

  # @spec GAME-076, APP-040, TOOL-039
  Scenario: A goldfish game's responses have no digest
    Given I have started a game with seed 42
    When I keep the hand
    Then the response has no digest lines
    And the status line has no seat, Act or Stack field
