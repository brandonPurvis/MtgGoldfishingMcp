Feature: Starting and taking turns in a contested game
  A contested game seats the tested deck against one to three opposing decks. Each seat is
  played through its own seat id, sees its own hand and every public zone, and takes its
  mulligans and turns in the turn order the seed draws.

  Background:
    Given the Atraxa test deck is loaded
    And the Omnath test deck is loaded

  # @spec GAME-056, GAME-074, GAME-077, APP-061, APP-076
  Scenario Outline: A contested game starts with one, two or three opposing seats
    When I start a contested game against <opponents> Omnath decks with seed 42
    Then the response is OK
    And the response lists <seats> seats in turn order
    And each seat was given its own seat id

    Examples:
      | opponents | seats |
      | 1         | 2     |
      | 2         | 3     |
      | 3         | 4     |

  # @spec GAME-080, GAME-082, GAME-087
  Scenario: The same decks and seed give the same turn order and opening hands
    When I start a contested game against 2 Omnath decks with seed 42
    And I start another contested game against 2 Omnath decks with seed 42
    Then both contested games have the same turn order
    And every seat of both games was dealt the same opening hand

  # @spec GAME-063, GAME-083, GAME-085, GAME-086
  Scenario: The tested seat's opening hand is the same in a goldfish game and a contested game
    When I start a game with seed 42
    And I start a contested game against 3 Omnath decks with seed 42
    Then the tested seat of the contested game holds the goldfish game's opening hand

  # @spec GAME-081
  Scenario: new_game fixes the tested seat's position in turn order
    When I start a contested game against 2 Omnath decks with seed 42 and the tested seat at position 3
    Then the response is OK
    And the response lists the tested seat as S3

  # @spec GAME-073
  Scenario: A position outside the seats is an error
    When I start a contested game against 1 Omnath deck with seed 42 and the tested seat at position 3
    Then the response is ERROR
    And the response says "position must be from 1 to 2"
    And the response has no status line

  # @spec GAME-066, GAME-067
  Scenario: Starting life is set per seat
    When I start a contested game against the Omnath deck and the Atraxa deck with seed 42 and starting life 40, 30, 20
    Then the response lists life 40 for the tested seat on the Atraxa deck
    And the response lists life 30 for the opposing seat on the Omnath deck
    And the response lists life 20 for the opposing seat on the Atraxa deck

  # @spec GAME-068
  Scenario: A seat with no starting life given starts at 40
    When I start a contested game against 2 Omnath decks with seed 42
    Then every seat starts with life 40

  # @spec GAME-057
  Scenario: An opposing seat may use the tested seat's own deck
    When I start a contested game against the Atraxa deck with seed 42
    Then the response is OK
    And every seat plays the Atraxa deck

  # @spec GAME-102, GAME-103, GAME-105, GAME-106, GAME-107, GAME-088, TOOL-048, TOOL-092
  Scenario: Every seat takes its own mulligans and turn 1 begins once every seat has kept
    Given a contested game against 1 Omnath deck with seed 42 and the tested seat at position 1
    When seat S2 takes a mulligan
    Then the response is OK
    And the response shows seat S2's hand
    And the status line reads "Mulligan 1 · Hand 7 · Act S1 you · #2"
    When seat S1 keeps its hand
    Then the response is OK
    And the status line reads "Mulligan 0 · Hand 7 · Act S2 (0 s) · #3"
    When seat S2 keeps its hand
    Then the response is OK
    And the response says "S1 T1 untap → upkeep → draw → main1"
    And the response says "S1 drew a card."
    And the status line begins "T0 main1 (S1) · You S2 · Hand 7 ·"
    And seat S1 holds 8 cards

  # @spec TURN-031, TURN-033, TURN-040, TOOL-042
  Scenario: Turns pass from seat to seat, and T<n> counts the viewing seat's own turns
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S1 ends its turn
    Then the response is OK
    And the response says "S2 T1 untap → upkeep → draw → main1"
    And the status line begins "T1 main1 (S2) · You S1 ·"
    And seat S2's status line begins "T1 main1 (S2) · You S2 ·"
    And the game is in round 1
    When seat S2 ends its turn
    Then the response says "S1 T2 untap → upkeep → draw → main1"
    And the status line begins "T1 main1 (S1) · You S2 ·"
    And seat S1's status line begins "T2 main1 (S1) · You S1 ·"
    And the game is in round 2

  # @spec GAME-144, TURN-025
  Scenario: A turn limit in a contested game counts rounds
    Given a started contested game against 1 Omnath deck with the tested seat first and a turn limit of 2
    When seat S1 ends its turn
    Then the response does not say "Notice: turn limit reached"
    When seat S2 ends its turn
    Then the response says "Notice: turn limit reached"

  # @spec GAME-118, APP-056, TOOL-050
  Scenario: A call from a seat that has nothing to do is an error
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S2 advances
    Then the response is ERROR
    And the response says "Not your seat's call: S1 is asked to take its turn. Call wait to be told when it is yours."
    And the game did not change

  # @spec GAME-088, GAME-089, GAME-121, GAME-122, APP-035, TOOL-051
  Scenario: A seat's state shows its own hand, every public zone, and the sizes of other seats' hands and libraries
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S2 asks for the state
    Then the response is OK
    And the state lists seat S2's hand and no other
    And the response lists "S1 · Life 40 · Hand 8 · Library 91"
    And the response lists "S2 (you) · Life 40 · Hand 7 · Library 92"
    And the response lists "Command zone (1): Atraxa, Praetors' Voice"
    And the response lists "Command zone (1): Omnath, Locus of Mana"

  # @spec GAME-114, GAME-152, REC-055
  Scenario: Any seat may read the log at any time
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S2 asks for the game's log
    Then the response is JSON about the current game
    And the log has an entry for "mulligan"
    And the log holds seat S1's opening hand

  # @spec GAME-076, TOOL-039
  Scenario: A goldfish game's tested seat id is its game id, and its responses have no contested fields
    Given I have started a game with seed 42
    When I keep the hand
    Then the response is OK
    And the status line has no seat, Act or Stack field

  # @spec TOOL-090, TOOL-091, APP-094, GAME-182
  Scenario: A seat that is not to act reads how long the seat to act has been asked
    Given a started contested game against 1 Omnath deck with the tested seat first
    When 4 minutes pass
    And seat S2 asks for the state
    Then the status line shows "Act S1 turn (4 min) · #"
    When seat S1 asks for the state
    Then the status line shows "Act you turn · #"

  # @spec TOOL-041, TOOL-093
  Scenario: The status line shows the commander damage the calling seat has taken
    Given a started contested game against 1 Omnath deck with the tested seat first
    When seat S2 asks for the state
    Then the status line shows "Cmdr 0 · Cmdr taken 0 · Tax 0"
