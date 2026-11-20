"""Check action fairness defaults, specification overrides, and WF/SF semantics."""

import tempfile
import unittest
from dataclasses import FrozenInstanceError
from enum import Enum, auto
from pathlib import Path

from tlacraftpy import (
    Specification,
    SpecificationError,
    Status,
    action,
    any_action,
    check,
    compile_spec,
    initial,
    invariant,
    leads_to,
    state,
    strong_fairness,
    strongly_fair,
    temporal,
    unchanged,
    until,
    weak_fairness,
    weakly_fair,
)
from tlacraftpy.model import StrongFairness, WeakFairness
from tlc import TLCTestCase


class Gate(Enum):
    Open = auto()
    Closed = auto()


class Work(Enum):
    Pending = auto()
    Done = auto()


@state
class State:
    gate: Gate
    work: Work


@initial
def init(s: State) -> bool:
    return s.gate == Gate.Open and s.work == Work.Pending


@weakly_fair
@action
def toggle(s: State, t: State) -> bool:
    return t.gate != s.gate and unchanged(s.work)


@strongly_fair
@action
def finish(s: State, t: State) -> bool:
    return (
        s.gate == Gate.Open
        and s.work == Work.Pending
        and t.work == Work.Done
        and unchanged(s.gate)
    )


@weakly_fair
@action
def complete(s: State, t: State) -> bool:
    return s.work == Work.Pending and t.work == Work.Done and unchanged(s.gate)


@action
def idle(s: State, t: State) -> bool:
    return unchanged(s.gate) and unchanged(s.work)


@invariant
def pending(s: State) -> bool:
    return s.work == Work.Pending


@temporal
def eventually_done(s: State) -> bool:
    return leads_to(True, s.work == Work.Done)


@temporal
def pending_until_done(s: State) -> bool:
    return until(s.work == Work.Pending, s.work == Work.Done)


class FairnessCompilerTests(unittest.TestCase):
    def test_defaults_and_mixed_compilation(self) -> None:
        spec = Specification(State, init, (a for a in (toggle, finish, idle)))
        self.assertEqual(spec.next, (toggle, finish, idle))
        self.assertEqual(
            spec.fairness, (weak_fairness(toggle), strong_fairness(finish))
        )
        self.assertIs(spec.fairness[0].action, toggle)
        self.assertIs(spec.fairness[1].action, finish)
        source = compile_spec(spec).tla
        self.assertIn("WF_vars(A0)", source)
        self.assertIn("SF_vars(A1)", source)
        self.assertNotIn("WF_vars(A2)", source)
        self.assertNotIn("SF_vars(A2)", source)
        with self.assertRaises(FrozenInstanceError):
            toggle.default_fairness = None

    def test_explicit_fairness_replaces_all_defaults(self) -> None:
        for assumptions in ([], (), iter(())):
            spec = Specification(State, init, any_action(toggle, finish), assumptions)
            self.assertEqual(spec.fairness, ())
            source = compile_spec(spec).tla
            self.assertNotIn("WF_vars", source)
            self.assertNotIn("SF_vars", source)
        spec = Specification(
            State, init, any_action(toggle, finish), iter([weak_fairness(finish)])
        )
        self.assertEqual(spec.fairness, (weak_fairness(finish),))
        source = compile_spec(spec).tla
        self.assertIn("WF_vars(A1)", source)
        self.assertNotIn("WF_vars(A0)", source)
        self.assertNotIn("SF_vars", source)
        spec = Specification(State, init, any_action(toggle), [strong_fairness(toggle)])
        self.assertIn("SF_vars(A0)", compile_spec(spec).tla)

    def test_none_inherits_and_undecorated_actions_have_no_default(self) -> None:
        spec = Specification(State, init, any_action(complete), fairness=None)
        self.assertEqual(spec.fairness, (weak_fairness(complete),))
        self.assertEqual(Specification(State, init, any_action(idle)).fairness, ())

    def test_decorators_preserve_source_and_reject_conflicts(self) -> None:
        decorated = weakly_fair(idle)
        self.assertIs(decorated.fn, idle.fn)
        self.assertEqual(decorated.kind, "action")
        self.assertEqual(decorated.name, "idle")
        self.assertIsNone(idle.default_fairness)
        self.assertIs(weakly_fair(decorated), decorated)
        self.assertIs(strongly_fair(finish), finish)
        self.assertIn(
            "WF_vars(A0)",
            compile_spec(Specification(State, init, any_action(decorated))).tla,
        )
        for decorate, target in ((weakly_fair, finish), (strongly_fair, complete)):
            with self.subTest(decorate=decorate), self.assertRaises(SpecificationError):
                decorate(target)

    def test_invalid_fairness_targets(self) -> None:
        for fn in (weakly_fair, strongly_fair, weak_fairness, strong_fairness):
            for target in (init, pending, eventually_done, idle.fn, object()):
                with self.subTest(fn=fn, target=target):
                    with self.assertRaises(SpecificationError):
                        fn(target)
        for assumption in (
            weak_fairness(finish),
            strong_fairness(finish),
            WeakFairness(init),
            StrongFairness(init),
            finish,
        ):
            with self.subTest(assumption=assumption):
                with self.assertRaises(SpecificationError):
                    Specification(State, init, any_action(toggle), [assumption])
        # An equal copy is not the same registered action object.
        with self.assertRaises(SpecificationError):
            Specification(
                State, init, any_action(idle), [weak_fairness(weakly_fair(idle))]
            )


class FairnessIntegrationTests(TLCTestCase):
    def verify(self, spec: Specification, expected: Status) -> None:
        for prop in (eventually_done, pending_until_done):
            with self.subTest(property=prop.name), tempfile.TemporaryDirectory() as tmp:
                result = check(
                    spec,
                    properties=[prop],
                    tlc_jar=self.tla2tools_jar,
                    output_dir=tmp,
                    timeout=30,
                    verbose=False,
                )
                self.assertIs(
                    result.status, expected, Path(result.artifacts.log).read_text()
                )
                if expected is Status.Violated:
                    self.assertEqual(result.property_name, prop.name)
                    self.assertIsNotNone(result.counterexample)
                    self.assertIsNotNone(result.counterexample.loop_start)

    def test_weak_default_and_explicit_disabling(self) -> None:
        self.verify(Specification(State, init, any_action(complete)), Status.Passed)
        self.verify(
            Specification(State, init, any_action(complete), fairness=[]),
            Status.Violated,
        )

    def test_strong_fairness_for_intermittently_enabled_action(self) -> None:
        # Weakly fair toggling forces recurring opportunities to finish. Weak
        # fairness for finish still admits a loop that skips every opportunity.
        actions = any_action(toggle, finish)
        self.verify(Specification(State, init, actions), Status.Passed)
        self.verify(
            Specification(
                State, init, actions, [weak_fairness(toggle), weak_fairness(finish)]
            ),
            Status.Violated,
        )
        self.verify(Specification(State, init, actions, fairness=[]), Status.Violated)

    def test_strong_fairness_counts_state_changing_steps(self) -> None:
        self.verify(
            Specification(State, init, any_action(idle), [strong_fairness(idle)]),
            Status.Violated,
        )
