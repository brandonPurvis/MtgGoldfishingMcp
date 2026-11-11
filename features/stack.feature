Feature: The stack and response windows
  In a contested game a spell or an ability goes on the stack with the delta its controller
  stated, and resolves once every other seat has passed on it, newest first. Seats are asked
  one at a time in turn order whether they respond: when something is put on the stack, after
  attackers are declared, and in the end step. A seat with no untapped permanents is passed
  automatically, and a seat reminded of a step trigger on another seat's turn is waited on.

  Background:
    Given the Atraxa test deck is loaded
    And the Omnath test deck is loaded

  # @spec STACK-003, STACK-014, STACK-016, STACK-024, STACK-034, TOOL-046, TOOL-060
  Scenario: A spell with no responses resolves with the delta it was cast with
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 has ended its turn
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 has ended its turn
    And seat S1 holds "Grizzly Bears"
    And seat S1 has "{1}{G}" in its pool
    When seat S1 casts "Grizzly Bears" with delta {"counters": {"Grizzly Bears": {"+1/+1": 1}}}
    Then the response is OK
    And the response says "Put s1 on the stack: Grizzly Bears from S1."
    And the status line shows "Stack 1"
    And the status line shows "Act S2 respond"
    When seat S2 passes
    Then the response is OK
    And the response says "s1 resolved: Grizzly Bears from S1."
    And "Grizzly Bears" is on seat S1's battlefield
    And the stack is empty

  @wip
  # @spec STACK-086, STACK-087, STACK-090, STACK-034
  Scenario: Cast triggers no other seat can answer resolve before their spell within the play
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 holds "Grizzly Bears"
    And seat S1 has "{1}{G}" in its pool
    When seat S1 casts "Grizzly Bears" with cast triggers [{"source": "first", "delta": {"life": 1}}, {"source": "second", "delta": {"life": 2}}]
    Then the response is OK
    And the response says "Put s3 on the stack: first from S1."
    And the response says "s3 resolved: first from S1."
    And the response says "s2 resolved: second from S1."
    And the response says "s1 resolved: Grizzly Bears from S1."
    And seat S1's life is 43
    And "Grizzly Bears" is on seat S1's battlefield
    And the stack is empty

  @wip
  # @spec STACK-089, STACK-023
  Scenario: A cast trigger that resolves leaves its spell to resolve as it was cast
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 has ended its turn
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 has ended its turn
    And seat S1 holds "Grizzly Bears"
    And seat S1 has "{1}{G}" in its pool
    When seat S1 casts "Grizzly Bears" with cast triggers [{"source": "Guttersnipe", "delta": {"life": 1}}]
    Then the status line shows "Act S2 respond"
    When seat S2 passes
    Then the response says "s2 resolved: Guttersnipe from S1."
    And the status line shows "Act S2 respond"
    When seat S2 passes
    Then the response says "s1 resolved: Grizzly Bears from S1."
    And "Grizzly Bears" is on seat S1's battlefield

  # @spec STACK-030, STACK-031, STACK-039, TOOL-061
  Scenario: A counterspell cast in response resolves first and counters the held spell
    Given a started contested game against the Atraxa deck with the tested seat first
    And seat S1 puts "Sol Ring" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Sol Ring" onto the battlefield
    And seat S2 holds "Counterspell"
    And seat S2 has ended its turn
    And seat S1 holds "Grizzly Bears"
    And seat S1 has "{1}{G}" in its pool
    When seat S1 casts "Grizzly Bears"
    And seat S2 adds "{U}{U}" to its pool
    And seat S2 casts "Counterspell" with delta {"counter": ["Grizzly Bears"]}
    Then the response is OK
    And the response says "Put s2 on the stack: Counterspell from S2."
    And the status line shows "Act S1 respond"
    When seat S1 passes
    Then the response says "s2 resolved: Counterspell from S2."
    And the response says "s1 was countered: Grizzly Bears from S1."
    And "Grizzly Bears" is in seat S1's graveyard
    And the stack is empty

  # @spec STACK-039, STACK-035, STACK-050, STACK-023
  Scenario: A response restarts the asking from the seat after the responder, and items resolve newest first
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Sol Ring" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 has ended its turn
    And seat S1 holds "Grizzly Bears"
    And seat S1 has "{1}{G}" in its pool
    When seat S1 casts "Grizzly Bears"
    And seat S2 records an effect from "a trick" with delta {"life": {"2": 1}}
    Then the status line shows "Act S1 respond"
    When seat S1 passes
    Then the response says "s2 resolved: a trick from S2."
    And seat S2's life is 41
    And the stack holds 1 item
    And the status line shows "Act S2 respond"

  # @spec STACK-023, STACK-024, STACK-025, STACK-026
  Scenario: A spell that waited under a resolved item is confirmed by its controller
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Sol Ring" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 has ended its turn
    And seat S1 holds "Grizzly Bears"
    And seat S1 has "{1}{G}" in its pool
    When seat S1 casts "Grizzly Bears" with delta {"counters": {"Grizzly Bears": {"+1/+1": 1}}}
    And seat S2 records an effect from "a trick" with delta {"life": {"2": 1}}
    And seat S1 passes
    And seat S2 passes
    Then the status line shows "Act S1 resolve"
    When seat S1 confirms its resolve choice
    Then the response is OK
    And "Grizzly Bears" is on seat S1's battlefield
    And the stack is empty

  # @spec STACK-025, STACK-027
  Scenario: A spell that waited under a resolved item is restated by its controller
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Sol Ring" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 has ended its turn
    And seat S1 holds "Grizzly Bears"
    And seat S1 has "{1}{G}" in its pool
    When seat S1 casts "Grizzly Bears"
    And seat S2 records an effect from "a removal spell" with delta {"life": {"2": 1}}
    And seat S1 passes
    And seat S2 passes
    And seat S1 restates its resolve choice with {"delta": {}, "to": "graveyard"}
    Then the response is OK
    And "Grizzly Bears" is in seat S1's graveyard
    And the stack is empty

  # @spec STACK-046, STACK-047, STACK-048, STACK-049
  Scenario: A seat with no untapped permanents is passed automatically, and the automatic pass is reported
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 holds "Grizzly Bears"
    And seat S1 has "{1}{G}" in its pool
    When seat S1 casts "Grizzly Bears"
    Then the response is OK
    And the response says "S2 passed automatically on s1: no untapped permanents."
    And the response says "s1 resolved: Grizzly Bears from S1."
    And "Grizzly Bears" is on seat S1's battlefield
    When seat S2 asks for the state
    Then the digest says "S2 passed automatically on s1"

  # @spec STACK-036, STACK-040, STACK-041, STACK-044, CMBT-034
  Scenario: After attackers are declared, another seat removes an attacker in the attack window
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Grizzly Bears" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 has ended its turn
    When seat S1 attacks with ["Grizzly Bears"]
    Then the status line shows "Act S2 respond"
    When seat S2 records an effect from "a removal spell" with delta {"move": {"graveyard": ["Grizzly Bears"]}}
    And seat S1 passes
    Then "Grizzly Bears" is in seat S1's graveyard
    And the status line shows "Act S2 respond"
    When seat S2 passes
    Then the status line shows "Act S1 turn"
    When seat S1 advances to "combat_damage"
    Then seat S2's life is 40

  # @spec STACK-037, STACK-045, TURN-056, TURN-057
  Scenario: In the end step a window opens in which another seat acts at the end of the turn
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 has ended its turn
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 has ended its turn
    When seat S1 advances to "cleanup"
    Then the response is OK
    And the response says "Stopped at end: the other seats are being asked whether they respond"
    And the status line shows "Act S2 respond"
    When seat S2 records an effect from "an instant" with delta {"life": {"1": -1}}
    And seat S1 passes
    Then seat S1's life is 39
    And the status line shows "Act S2 respond"
    When seat S2 passes
    Then the status line shows "Act S1 turn"

  # @spec STACK-007, STACK-020
  Scenario: A triggered ability recorded with effect goes on the stack and can be responded to
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Sol Ring" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 has ended its turn
    When seat S1 records an effect from "Phyrexian Arena" with delta {"life": -1}
    Then the response says "Put s1 on the stack: Phyrexian Arena from S1."
    And seat S1's life is 40
    When seat S2 records an effect from "a response" with delta {"life": {"2": 2}}
    And seat S1 passes
    Then seat S2's life is 42
    When seat S2 passes
    And seat S1 confirms its resolve choice
    Then seat S1's life is 39

  # @spec STACK-056, STACK-057
  Scenario: An event trigger of a seat not taking its turn is recorded at that seat's next window
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 puts "Grizzly Bears" onto the battlefield
    And seat S1 has ended its turn
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 puts "Birds of Paradise" onto the battlefield
    And seat S2 has ended its turn
    When seat S1 attacks with ["Grizzly Bears"]
    And seat S2 passes
    And seat S1 advances to "declare_blockers"
    And seat S2 answers its blocks choice with blocks {"Llanowar Elves": "Grizzly Bears"}
    And seat S1 advances to "combat_damage"
    And seat S1 records an immediate effect with delta {"move": {"graveyard": ["Llanowar Elves"]}}
    Then the status line shows "Act you turn"
    When seat S1 advances to "end"
    Then the status line shows "Act S2 respond"
    When seat S2 records an effect from "Llanowar Elves" with delta {"life": {"2": 1}}
    Then the response is OK
    And the response says "Put s1 on the stack: Llanowar Elves from S2."

  # @spec TURN-048, TURN-051, TURN-052, TURN-063, GAME-111, READ-034
  Scenario: A step trigger of another seat's permanent becomes a reminder for that seat, and the game waits on it
    Given the Omnath test deck is loaded with "Sylvan Library" defined as "At the beginning of each opponent's upkeep, you gain 1 life."
    And a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 has ended its turn
    And seat S2 puts "Sylvan Library" onto the battlefield
    When seat S2 ends its turn
    Then the response says "Reminder (upkeep) for S2: Sylvan Library"
    And the status line shows "Act you trigger"
    When seat S1 advances
    Then the response is ERROR
    When seat S2 records an effect from "Sylvan Library" with delta {"life": 1}
    Then the response is OK
    And seat S2's life is 41

  # @spec GAME-118, STACK-052, TOOL-050
  Scenario: A seat that is not asked may not pass
    Given a started contested game against 1 Omnath deck with the tested seat first
    And seat S1 has ended its turn
    And seat S2 puts "Llanowar Elves" onto the battlefield
    And seat S2 has ended its turn
    And seat S1 holds "Grizzly Bears"
    And seat S1 has "{1}{G}" in its pool
    When seat S1 casts "Grizzly Bears"
    And seat S1 passes
    Then the response is ERROR
    And the response says "Not your seat's call: S2 is asked to respond to s1. Call wait to be told when it is yours."

  # @spec STACK-062, GAME-129
  Scenario: An eliminated seat is skipped by response windows
    Given a started contested game against 2 Omnath decks with the tested seat first
    And seat S1 holds "Grizzly Bears"
    And seat S1 has "{1}{G}" in its pool
    When seat S2 concedes
    And seat S1 casts "Grizzly Bears"
    Then the response says "S3 passed automatically on s1"
    And the response does not say "S2 passed"
