"""Verify a bounded port of Lamport's InnerFIFO with two-phase channels."""

import argparse
from enum import Enum, auto
from typing import Annotated

from tlacraftpy import (
    MaxLen,
    Specification,
    Status,
    action,
    any_action,
    append,
    check,
    exists,
    export,
    head,
    initial,
    invariant,
    leads_to,
    state,
    tail,
    temporal,
    unchanged,
    weak_fairness,
)

CAPACITY = 2


class Message(Enum):
    """Messages carried by the finite FIFO model."""

    A = auto()
    B = auto()


class Bit(Enum):
    """Two handshake phases, corresponding to the source model's zero and one."""

    Zero = 0
    One = 1


@state
class State:
    """Input and output channel fields plus a bounded queue of messages."""

    in_value: Message
    in_ready: Bit
    in_ack: Bit
    out_value: Message
    out_ready: Bit
    out_ack: Bit
    q: Annotated[tuple[Message, ...], MaxLen(CAPACITY)]


@initial
def init(s: State) -> bool:
    """Start with acknowledged channels and an empty queue."""
    return s.in_ack == s.in_ready and s.out_ack == s.out_ready and s.q == ()


@action
def ssend(s: State, t: State) -> bool:
    """Send an arbitrary message on the acknowledged input channel."""
    return exists(
        Message,
        lambda msg: (
            s.in_ready == s.in_ack
            and t.in_value == msg
            and t.in_ready != s.in_ready
            and unchanged(s.in_ack)
            and unchanged(s.out_value)
            and unchanged(s.out_ready)
            and unchanged(s.out_ack)
            and unchanged(s.q)
        ),
    )


@action
def buf_rcv(s: State, t: State) -> bool:
    """Acknowledge the input message and append it while capacity is available."""
    return (
        s.in_ready != s.in_ack
        and len(s.q) < CAPACITY
        and t.in_ack != s.in_ack
        and unchanged(s.in_value)
        and unchanged(s.in_ready)
        and unchanged(s.out_value)
        and unchanged(s.out_ready)
        and unchanged(s.out_ack)
        and t.q == append(s.q, s.in_value)
    )


@action
def buf_send(s: State, t: State) -> bool:
    """Move the oldest queued message onto the acknowledged output channel."""
    return (
        len(s.q) > 0
        and s.out_ready == s.out_ack
        and t.out_value == head(s.q)
        and t.out_ready != s.out_ready
        and t.q == tail(s.q)
        and unchanged(s.in_value)
        and unchanged(s.in_ready)
        and unchanged(s.in_ack)
        and unchanged(s.out_ack)
    )


@action
def rrcv(s: State, t: State) -> bool:
    """Acknowledge the output message."""
    return (
        s.out_ready != s.out_ack
        and t.out_ack != s.out_ack
        and unchanged(s.out_value)
        and unchanged(s.out_ready)
        and unchanged(s.in_value)
        and unchanged(s.in_ready)
        and unchanged(s.in_ack)
        and unchanged(s.q)
    )


@invariant
def bounded(s: State) -> bool:
    """Keep queue length within the configured capacity."""
    return len(s.q) <= CAPACITY


@temporal
def input_acknowledged(s: State) -> bool:
    """Every pending input handshake eventually receives an acknowledgment."""
    return leads_to(s.in_ready != s.in_ack, s.in_ready == s.in_ack)


@temporal
def output_acknowledged(s: State) -> bool:
    """Every pending output handshake eventually receives an acknowledgment."""
    return leads_to(s.out_ready != s.out_ack, s.out_ready == s.out_ack)


def make_system(*, fair: bool = True) -> Specification:
    """Build the bounded InnerFIFO port with optional progress assumptions.

    Args:
        fair: Apply weak fairness to buffer receive, buffer send, and output
            receive when True.

    Returns:
        Specification: Input channel, FIFO buffer, and output channel model.
    """
    return Specification(
        state=State,
        init=init,
        next=any_action(ssend, buf_rcv, buf_send, rrcv),
        fairness=[weak_fairness(a) for a in (buf_rcv, buf_send, rrcv)] if fair else [],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--without-fairness", action="store_true")
    parser.add_argument("--tlc-jar")
    args = parser.parse_args()
    system = make_system(fair=not args.without_fairness)
    properties = [input_acknowledged, output_acknowledged]
    invariants = [bounded]
    if args.export_only:
        artifacts = export(
            system, properties=properties, invariants=invariants, module="FIFO"
        )
        print(artifacts.tla)
        print(artifacts.cfg)
    else:
        result = check(
            system,
            properties=properties,
            invariants=invariants,
            module="FIFO",
            tlc_jar=args.tlc_jar,
            timeout=60,
        )
        raise SystemExit(
            {Status.Passed: 0, Status.Violated: 1, Status.Incomplete: 2}[result.status]
        )
