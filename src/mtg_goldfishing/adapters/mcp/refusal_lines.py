"""The wording of refusals: one per kind of error and one per kind of rule check.

Each wording says what was wrong and, where the agent can act on it, what to do.
"""

from __future__ import annotations

from typing import assert_never

from mtg_goldfishing.domain.events import CheckKind, Error, ErrorKind, FailedCheck, Refused
from mtg_goldfishing.domain.game.model import MAXIMUM_HAND, Destination
from mtg_goldfishing.domain.steps import STEPS


def _listed(names: tuple[str, ...]) -> str:
    return ", ".join(names)


def _cards(count: int) -> str:
    return f"{count} card" if count == 1 else f"{count} cards"


def _mana_symbols(colors: tuple[str, ...]) -> str:
    return "".join("{" + color + "}" for color in colors)


# @spec TOOL-026
def error_text(error: Error) -> str:
    """The one wording of an error's kind, filled with its facts."""
    subject = error.subject or ""
    names = _listed(error.names)
    match error.kind:
        case ErrorKind.UNKNOWN_GAME:
            return f"No game with id {subject}. Check the game id, or start a game with new_game."
        case ErrorKind.NOT_ACCEPTED_IN_STATUS:
            status = (error.zone or "").replace("_", " ")
            return f"{subject} is not accepted while the game is {status}. Accepted now: {names}."
        case ErrorKind.STALE_CHANGE:
            return (
                f"The game is now at change #{error.number}, so your picture of it is stale."
                " Check the latest status line or call get_state,"
                f" then send the call with after={error.number}."
            )
        case ErrorKind.UNKNOWN_DECK:
            return f"No loaded deck with id {subject}. Load the deck with load_deck first."
        case ErrorKind.BAD_TURN_LIMIT:
            return f"turn_limit must be a positive whole number, not {subject}."
        case ErrorKind.BAD_RESULT:
            return f"result must be one of {names}, not {subject}."
        case ErrorKind.CARD_NOT_IN_ZONE:
            elsewhere = f"; it is in the {error.found_in}" if error.found_in else ""
            return f"No {subject} in {error.zone or 'the expected zone'}{elsewhere}."
        case ErrorKind.TOO_FEW_MATCHING:
            return (
                f"{subject} is named {error.expected} times but only {error.number} match."
                " A name given more than once means that many different cards."
            )
        case ErrorKind.INSTANCE_REPEATED:
            return f"Instance {subject} is named more than once in one list; name it once."
        case ErrorKind.MALFORMED_ARGUMENT:
            about = f" ({names})" if names else ""
            return f"Argument {subject} is malformed{about}. Correct its shape and send again."
        case ErrorKind.UNKNOWN_DELTA_KEY:
            return f"Unknown delta key {subject}. Delta keys are {names}."
        case ErrorKind.UNKNOWN_EXPECT_KEY:
            return f"Unknown expect key {subject}. Expect keys are {names}."
        case ErrorKind.UNPARSEABLE_MANA:
            return (
                f"{subject} is not a mana string. Write mana as symbols in braces, like {{2}}{{G}}."
            )
        case ErrorKind.UNKNOWN_DESTINATION:
            known = _listed(tuple(destination.value for destination in Destination))
            return f"Unknown destination {subject}. Destinations are {known}."
        case ErrorKind.UNKNOWN_ZONE:
            return (
                f"Unknown zone {subject} for from."
                " Use hand, command, graveyard, exile, library or outside."
            )
        case ErrorKind.UNKNOWN_STEP:
            steps = _listed(tuple(step.value for step in STEPS))
            return f"Unknown step {subject}. Steps are {steps}."
        case ErrorKind.LOOK_AND_SEARCH:
            return "A delta cannot hold both look and search. Record them in separate calls."
        case ErrorKind.LOOK_WITHOUT_REST:
            return "look needs rest: the destination for the cards not selected."
        case ErrorKind.CARD_DATA_NEEDED:
            return (
                f"No card data for {subject}. To play it from outside the game,"
                " give a definition in choices."
            )
        case ErrorKind.NOT_IN_LIBRARY:
            return f"No {subject} in the library."
        case ErrorKind.WRONG_CHOICE:
            return (
                f"{subject} is not the pending choice. Use the choice id the CHOICE response gave."
            )
        case ErrorKind.NOT_REVEALED:
            return f"{subject} was not revealed by the pending choice."
        case ErrorKind.SOURCE_MANA_UNKNOWN:
            return (
                f"{subject} has no mana reading; state its mana in pay.with"
                f' as {{"source": "{subject}", "mana": "{{G}}"}}.'
            )
        case ErrorKind.SOURCE_TAPPED:
            return f"{subject} is already tapped and cannot pay."
        case ErrorKind.BOTTOM_NOT_IN_HAND:
            return f"No {subject} in hand to put on the bottom."
        case ErrorKind.BOTTOM_WITHOUT_KEEP:
            return "bottom is given only with keep: true."
        case ErrorKind.DISCARD_NOT_IN_HAND:
            return f"No {subject} in hand to discard."
        case ErrorKind.DISCARD_WITHOUT_CLEANUP:
            return (
                "discard is given only on an advance that enters cleanup, and this one does not."
                " Send it without discard."
            )
        case ErrorKind.ATTACKER_NOT_ON_BATTLEFIELD:
            return f"No {subject} on the battlefield to attack with."
        case ErrorKind.NOT_AN_ATTACKER:
            return f"{subject} is not among the attackers."
        case ErrorKind.BAD_COMMANDER_TARGET:
            return (
                f"commander_target {subject} is not valid. Give 0, 1 or 2,"
                " or a map from each attacking commander to 0, 1 or 2."
            )
        case ErrorKind.LINE_UNREADABLE:
            return f"Line {error.number} cannot be read: {subject}. Write <count> <name>."
        case ErrorKind.COUNT_NOT_POSITIVE:
            return f"Line {error.number} has a count below 1: {subject}."
        case ErrorKind.NO_COMMANDER:
            return "No commander given. Name it in commander."
        case ErrorKind.TOO_MANY_COMMANDERS:
            return f"{error.number} commanders given ({names}); at most {error.expected}."
        case ErrorKind.COMMANDER_NOT_FOUND:
            return f"Commander {subject} was not found. Check its spelling."
        case ErrorKind.CARDS_NOT_FOUND:
            return (
                f"Cards not found: {names}. Check their spelling,"
                " or give each a definition with a type_line."
            )
        case ErrorKind.CARD_DATA_UNAVAILABLE:
            return (
                f"Card data is unavailable right now for: {names}. This is temporary;"
                " try again later, or give each a definition with a type_line."
            )
        case ErrorKind.DEFINITION_NOT_IN_DECK:
            return f"There is a definition for {subject}, which is not in the deck."
        case ErrorKind.DEFINITION_NEEDS_TYPE_LINE:
            return f"{subject} was not found, so its definition needs a type_line."
        case ErrorKind.CHANGED_UNDERNEATH:
            return "The game changed while this call was applied, so nothing was. Send it again."
        case ErrorKind.INTERNAL_FAILURE:
            return (
                "Something failed inside the service, not caused by the call, and nothing was"
                " applied. Send the call again; if it fails again, report it."
            )
        case _:
            assert_never(error.kind)


# @spec TOOL-026
def check_text(check: FailedCheck) -> str:
    """The one wording of a rule check's kind, filled with its facts."""
    subject = check.subject or ""
    names = _listed(check.names)
    step = check.step.value if check.step else "no step"
    match check.kind:
        case CheckKind.COST_NOT_PAYABLE:
            short = f"; not enough {_mana_symbols(check.names)}" if check.names else ""
            return f"Cost {check.cost} not payable: {check.number} mana available{short}."
        case CheckKind.LAND_DROP_USED:
            return "The land drop for this turn is already used."
        case CheckKind.SPELL_TIMING:
            return f"{subject} is not an instant and has no flash, but the game is in {step}."
        case CheckKind.LAND_TIMING:
            return f"Lands are played in a main step; the game is in {step}."
        case CheckKind.EXPLICIT_COST:
            return f"The cost {check.cost} given for {subject} cannot be checked."
        case CheckKind.SUMMONING_SICK_SOURCE:
            return f"{subject} is summoning-sick, so it cannot tap for mana."
        case CheckKind.BOTTOM_COUNT:
            return (
                f"Keeping puts {_cards(check.expected or 0)} on the bottom;"
                f" bottom names {check.number}."
            )
        case CheckKind.HAND_TOO_BIG:
            return (
                f"The hand is {_cards(check.number or 0)} over {MAXIMUM_HAND} at cleanup."
                f" Give discard naming {_cards(check.number or 0)}."
            )
        case CheckKind.DISCARD_COUNT:
            return (
                f"Cleanup needs {_cards(check.expected or 0)} discarded;"
                f" discard names {check.number}."
            )
        case CheckKind.ATTACK_TOO_EARLY:
            return f"Attacking from {step} skips the first main step."
        case CheckKind.COMBAT_OVER:
            return (
                f"Combat is over for this turn (the game is in {step});"
                " an override makes this an additional combat."
            )
        case CheckKind.NOT_A_CREATURE:
            return f"{subject} is not a creature."
        case CheckKind.ATTACKER_TAPPED:
            return f"{subject} is tapped."
        case CheckKind.SUMMONING_SICK_ATTACKER:
            return f"{subject} entered the battlefield this turn and has no haste."
        case CheckKind.POWER_NOT_A_NUMBER:
            return f"{subject} has no numeric power; give its damage in damage."
        case CheckKind.DECK_SIZE:
            return f"The deck has {check.number} cards, not {check.expected}."
        case CheckKind.SINGLETON:
            return f"{subject} appears {check.number} times; at most {check.expected} allowed."
        case CheckKind.COLOR_IDENTITY:
            return f"Outside the commanders' color identity: {names}."
        case CheckKind.LEGALITY:
            return f"Not legal in Commander: {names}."
        case CheckKind.COMMANDER_ELIGIBILITY:
            return f"Cannot be a commander: {names}."
        case _:
            assert_never(check.kind)


_LAND_CHECKS = frozenset({CheckKind.LAND_DROP_USED, CheckKind.LAND_TIMING})


def _overriding(tool: str | None, checks: tuple[FailedCheck, ...]) -> str:
    """What an override would do, in the words of the call."""
    match tool:
        case "play":
            return "play" if all(check.kind in _LAND_CHECKS for check in checks) else "cast"
        case "effect":
            return "record it"
        case "attack":
            return "attack"
        case "advance":
            return "advance"
        case "mulligan":
            return "keep"
        case "load_deck":
            return "load the deck"
        case _:
            return "apply it"


def _counted(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def refusal_lines(refused: Refused, tool: str | None) -> list[str]:
    """The summary of a refused call, then each error and failed check when there are several."""
    errors, checks = refused.errors, refused.checks
    error_lines = [f"Error: {error_text(error)}" for error in errors]
    check_lines = [f"Rule check: {check_text(check)}" for check in checks]
    if errors:
        if len(errors) == 1 and not checks:
            return [error_text(errors[0])]
        headline = f"Nothing was applied: {_counted(len(errors), 'error', 'errors')}"
        if checks:
            counted = _counted(len(checks), "failed rule check", "failed rule checks")
            needs = "rule check would" if len(checks) == 1 else "rule checks would"
            headline += f" and {counted}. Fix the errors; the {needs} also need override"
        return [f"{headline}.", *error_lines, *check_lines]
    advice = f"Resubmit with override to {_overriding(tool, checks)} anyway"
    if len(checks) == 1:
        return [f"{check_text(checks[0])} {advice}."]
    if not checks:
        return ["Nothing was applied."]
    return [
        f"{len(checks)} rule checks failed. {advice}; one override covers them all.",
        *check_lines,
    ]
