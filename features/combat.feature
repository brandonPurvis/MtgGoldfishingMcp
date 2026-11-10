Feature: Combat
  The agent declares attackers and decides what the imaginary opponents block; the service
  taps the attackers and, on entering combat damage, adds up the damage dealt.

  Background:
    Given a game in the first main step of turn 1

  Scenario: Unblocked attackers deal combat damage, and the commander deals commander damage
    Given "Grizzly Bears" is on the battlefield
    And my commander "Atraxa, Praetors' Voice" is on the battlefield
    When I attack with "Grizzly Bears" and "Atraxa, Praetors' Voice", both with haste
    Then the response is OK
    And the status line begins "T1 declare_attackers ·"
    When I advance to "combat_damage"
    Then the response is OK
    And the response says "Grizzly Bears"
    And the status line shows "Dmg 6/120 · Cmdr 4/0/0"

  Scenario: A blocked attacker deals no damage
    Given "Grizzly Bears" is on the battlefield
    When I attack with "Grizzly Bears" with haste, and it is blocked
    And I advance to "combat_damage"
    Then the status line shows "Dmg 0/120"
