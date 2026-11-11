Feature: Playing cards
  The agent says what it plays and what each card does; the service uses the land drop,
  pays the cost, moves the card, and refuses what card data says is not allowed unless
  the agent overrides it. What is structurally impossible can never be overridden.

  Background:
    Given a game in the first main step of turn 1

  Scenario: Play a land, then cast a spell the service pays for automatically
    Given "Grizzly Bears" and "Forest" are in my hand
    And "Forest" is on the battlefield
    When I play "Forest"
    Then the response is OK
    And the response says "Played Forest."
    When I play "Grizzly Bears"
    Then the response is OK
    And the response says "Cast Grizzly Bears."
    And the response says "Paid {1}{G}: tapped Forest, Forest."
    And the status line shows "Lands 2 (0 untapped)"
    And "Grizzly Bears" is on the battlefield

  Scenario: A failed rule check is refused, then applied with an override
    Given "Forest" and "Forest" are in my hand
    And I have played "Forest"
    When I play "Forest"
    Then the response is REJECTED
    And the response says "The land drop for this turn is already used."
    And the response says "Resubmit with override"
    And the response does not carry the error flag
    And the game did not change
    When I play "Forest" with override "Azusa lets me play an extra land"
    Then the response is OK
    And the status line shows "Lands 2 (2 untapped)"

  Scenario: An error cannot be overridden
    When I play "Black Lotus" with override "I am sure it is in my hand"
    Then the response is ERROR
    And the response says "No Black Lotus in hand or command."
    And the response carries the error flag
    And the game did not change

  Scenario: A call sent twice with after is applied once
    Given "Forest" is in my hand
    When I play "Forest" after the change number I last saw
    And I send the same call again
    Then the response says "Already applied as change"
    And the game's change number went up by one in all

  Scenario: A call missing a required parameter is answered as an error and recorded
    When I call play without naming a card
    Then the response is ERROR
    And the response says "Argument card is malformed."
    And the response carries the error flag
    And the call is kept as a call record

  # @spec STACK-001, TOOL-039
  Scenario: A goldfish game shows no stack, window or automatic pass
    Given "Grizzly Bears" is in my hand
    And "Forest" is on the battlefield
    And "Command Tower" is on the battlefield
    When I play "Grizzly Bears"
    Then the response is OK
    And the response does not say "on the stack"
    And the response does not say "passed automatically"
    And the status line has no seat, Act or Stack field

  # @spec PLAY-135, TOOL-086
  Scenario: A spell's cast trigger is applied before the spell, and the response says so
    Given "Llanowar Elves" is in my hand
    And "Forest" is on the battlefield
    When I cast "Llanowar Elves" with cast triggers [{"source": "Thousand-Year Storm", "delta": {"draw": 1}}]
    Then the response is OK
    And the response says "Cast trigger: Thousand-Year Storm."
    And "Llanowar Elves" is on the battlefield

  # @spec GAME-186, GAME-187, TOOL-095
  @wip
  Scenario: Asking for a card's rules text answers it in place of the listing
    Given "Sol Ring" is in my hand
    When I ask for the rules text of "Sol Ring"
    Then the response is OK
    And the response says "Rules text of 1 card."
    And the response says "Sol Ring {1} · Artifact"
    And the response says "  {T}: Add {C}{C}."
    And the response does not say "Hand ("
