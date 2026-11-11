@http
Feature: Contested games over HTTP, one client per seat
  The real service, on SQLite, played by separate agents: each seat calls through its own MCP
  client with its own seat id, sees its own game, and waits while the others act.

  Background:
    Given the Atraxa test deck is loaded
    And the Omnath test deck is loaded

  # @spec GAME-056, GAME-074, GAME-077, APP-061, APP-077
  Scenario Outline: A contested game starts with one, two or three opposing seats, each played through its own client
    When I start a contested game against <opponents> Omnath decks with seed 42
    Then the response is OK
    And the response lists <seats> seats in turn order
    And each seat was given its own seat id
    And each seat's client is answered as that seat

    Examples:
      | opponents | seats |
      | 1         | 2     |
      | 2         | 3     |
      | 3         | 4     |

  # @spec APP-036, APP-037, GAME-091, REC-040, TOOL-035, TOOL-037, APP-077
  Scenario: Every response to a seat begins with a digest of the other seats' public events
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S1 records an effect with delta {"draw": 1}
    And seat S2 asks for the state
    Then the response is OK
    And the response begins with a digest line for change #4 made by S1
    And the digest says "S1 drew a card"
    And the digest names no card of seat S1's hand

  # @spec STACK-030, STACK-031, STACK-039, APP-077
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
    And the status line has no Stack field

  # @spec CMBT-030, CMBT-031, CMBT-037, CMBT-039, APP-077
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
    And the status line shows "Act S2 blocks"
    When seat S2 waits
    Then the response says "You are asked to answer the blocks choice."
    When seat S2 answers its blocks choice with blocks {"Elvish Mystic": "Grizzly Bears"}
    Then the response is OK
    And the status line shows "Act S3 blocks"
    When seat S3 waits
    And seat S3 answers its blocks choice with blocks {}
    Then the response is OK
    And the status line shows "Act S1 turn"
    When seat S1 advances to "combat_damage"
    Then seat S2's life is 40
    And seat S3's life is 39

  # @spec APP-063, APP-077
  Scenario: wait returns at once for the seat to act, with what it is asked
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S1 waits
    Then the response is OK
    And the response says "You are asked to take your turn."

  # @spec APP-064, APP-068, APP-015, APP-077
  Scenario: wait returns when another seat, acting through its own client, makes the waiting seat the seat to act
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S2 starts waiting with a timeout of 30 seconds
    Then seat S2's wait is still open after 1 second
    When seat S1 ends its turn
    Then seat S2's wait returns "OK You are asked to take your turn." well before its timeout

  # @spec GAME-036, GAME-126, APP-055, APP-077
  Scenario: A resend is recognised against the sending seat's own change after another seat acted
    Given a contested game against 1 Omnath deck with seed 42 and the tested seat at position 1
    When seat S1 takes a mulligan after change 1
    And seat S2 takes a mulligan
    And seat S1 takes a mulligan after change 1
    Then the response says "Already applied as change #2; nothing was applied again."
    And the game's change number is 3

  # @spec REC-027, REC-028, REC-052, APP-015, APP-077
  Scenario: A full game played by four seats, each through its own client at once, produces one complete log
    Given a contested game against 3 Omnath decks with seed 42 and the tested seat at position 1
    When every seat plays through its own client at once, S4 conceding in round 2 and the tested seat ending the game in round 3
    Then every seat's agent stopped without a problem
    And seat S2 is told the game has ended
    And the log read by seat S3 holds every change of the game in change-number order
    And the log holds changes made by every seat
    And the log's call records name every seat
