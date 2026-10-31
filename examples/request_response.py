"""Run normally to check with TLC; --export-only needs no Java/TLC."""
import argparse
from enum import Enum, auto

from pytla import (
    Specification, Status, action, any_action, check, export, initial,
    leads_to, state, temporal, weak_fairness,
)


class Phase(Enum):
    Idle = auto()
    Requested = auto()
    Responded = auto()


@state
class State:
    phase: Phase


@initial
def init(s):
    return s.phase == Phase.Idle


@action
def request(s, t):
    return s.phase == Phase.Idle and t.phase == Phase.Requested


@action
def respond(s, t):
    return s.phase == Phase.Requested and t.phase == Phase.Responded


@action
def reset(s, t):
    return s.phase == Phase.Responded and t.phase == Phase.Idle


@temporal
def every_request_gets_response(s):
    return leads_to(s.phase == Phase.Requested, s.phase == Phase.Responded)


def make_system(*, fair=True):
    return Specification(
        state=State, init=init, next=any_action(request, respond, reset),
        fairness=[weak_fairness(respond)] if fair else [],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--without-fairness", action="store_true")
    parser.add_argument("--tlc-jar")
    args = parser.parse_args()
    system = make_system(fair=not args.without_fairness)
    properties = [every_request_gets_response]
    if args.export_only:
        artifacts = export(system, properties=properties, module="RequestResponse")
        print(artifacts.tla)
        print(artifacts.cfg)
    else:
        result = check(system, properties=properties, tlc_jar=args.tlc_jar,
                       module="RequestResponse")
        raise SystemExit({Status.Passed: 0, Status.Violated: 1, Status.Incomplete: 2}[result.status])
