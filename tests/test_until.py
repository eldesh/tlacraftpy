"""Check strong-until semantics, including quantified and negated properties."""

import tempfile
import unittest
from enum import Enum, auto
from pathlib import Path

from tlacraftpy import (
    CheckResult,
    Specification,
    SpecificationError,
    Status,
    action,
    any_action,
    check,
    compile_spec,
    exists,
    forall,
    initial,
    invariant,
    leads_to,
    state,
    temporal,
    unchanged,
    until,
    weak_fairness,
)
from tlacraftpy.model import Definition
from tlc import TLCTestCase


class Phase(Enum):
    Waiting = auto()
    Gap = auto()
    Done = auto()
    After = auto()


@state
class State:
    phase: Phase


@initial
def waiting(s: State) -> bool:
    return s.phase == Phase.Waiting


@initial
def done(s: State) -> bool:
    return s.phase == Phase.Done


@initial
def gap(s: State) -> bool:
    return s.phase == Phase.Gap


@action
def finish(s: State, t: State) -> bool:
    return s.phase == Phase.Waiting and t.phase == Phase.Done


@action
def interrupt(s: State, t: State) -> bool:
    return s.phase == Phase.Waiting and t.phase == Phase.Gap


@action
def resume(s: State, t: State) -> bool:
    return s.phase == Phase.Gap and t.phase == Phase.Done


@action
def forget(s: State, t: State) -> bool:
    return s.phase == Phase.Done and t.phase == Phase.After


@action
def idle(s: State, t: State) -> bool:
    return unchanged(s.phase)


@temporal
def waits_until_done(s: State) -> bool:
    return until(s.phase == Phase.Waiting, s.phase == Phase.Done)


@temporal
def eventually_done(s: State) -> bool:
    return leads_to(True, s.phase == Phase.Done)


@temporal
def not_until(s: State) -> bool:
    return not until(s.phase == Phase.Waiting, s.phase == Phase.Done)


@temporal
def either_until(s: State) -> bool:
    return until(s.phase == Phase.Waiting, s.phase == Phase.Done) or until(
        s.phase != Phase.After, s.phase == Phase.Gap
    )


@temporal
def every_phase_before_after(s: State) -> bool:
    return forall(Phase, lambda phase: until(s.phase != Phase.After, s.phase == phase))


@temporal
def every_phase_before_gap(s: State) -> bool:
    return forall(Phase, lambda phase: until(s.phase != Phase.Gap, s.phase == phase))


@temporal
def initially_one_phase(s: State) -> bool:
    return exists(Phase, lambda phase: until(False, s.phase == phase))


@temporal
def two_bindings(s: State) -> bool:
    return forall(
        Phase,
        lambda phase: exists(
            Phase, lambda other: until(False, s.phase == phase or s.phase == other)
        ),
    )


@temporal
def false_until_true(s: State) -> bool:
    return until(False, True)


@temporal
def true_until_true(s: State) -> bool:
    return until(True, True)


@temporal
def true_until_false(s: State) -> bool:
    return until(True, False)


@temporal
def false_until_false(s: State) -> bool:
    return until(False, False)


@temporal
def nested_until(s: State) -> bool:
    return until(True, until(True, s.phase == Phase.Done))


@temporal
def until_in_leads_to(s: State) -> bool:
    return leads_to(True, until(True, s.phase == Phase.Done))


@temporal
def non_boolean(s: State) -> bool:
    return until(s.phase, True)


@temporal
def missing_argument(s: State) -> bool:
    return until(True)


@temporal
def keyword_arguments(s: State) -> bool:
    return until(True, Q=True)


@initial
def until_in_initial(s: State) -> bool:
    return until(True, s.phase == Phase.Done)


@action
def until_in_action(s: State, t: State) -> bool:
    return until(True, s.phase == t.phase)


@invariant
def until_in_invariant(s: State) -> bool:
    return until(True, s.phase == Phase.Done)


def system(init: Definition, *actions: Definition, fair: bool = True) -> Specification:
    return Specification(
        State,
        init,
        any_action(*actions),
        [weak_fairness(a) for a in actions] if fair else [],
    )


class UntilCompilerTests(unittest.TestCase):
    def test_invalid_operands_and_contexts(self) -> None:
        spec = system(waiting, finish)
        for prop in (
            nested_until,
            until_in_leads_to,
            non_boolean,
            missing_argument,
            keyword_arguments,
        ):
            with self.subTest(prop=prop.name), self.assertRaises(SpecificationError):
                compile_spec(spec, properties=[prop])
        invalid = (
            (system(until_in_initial, finish), {}),
            (system(waiting, until_in_action), {}),
            (spec, {"invariants": [until_in_invariant]}),
        )
        for model, options in invalid:
            with self.subTest(model=model), self.assertRaises(SpecificationError):
                compile_spec(model, **options)
        with self.assertRaises(SpecificationError):
            until(True, True)

    def test_histories_are_local_to_each_compilation(self) -> None:
        spec = system(waiting, finish)
        first = compile_spec(spec, properties=[waits_until_done])
        self.assertEqual(first, compile_spec(spec, properties=[waits_until_done]))
        plain = compile_spec(spec, properties=[eventually_done])
        self.assertNotIn("h0", plain.tla)
        self.assertEqual(first.mapping["variables"], {"v0": "phase"})


class UntilIntegrationTests(TLCTestCase):
    def verify(
        self, model: Specification, prop: Definition, expected: Status
    ) -> CheckResult:
        with tempfile.TemporaryDirectory() as directory:
            result = check(
                model,
                properties=[prop],
                tlc_jar=self.tla2tools_jar,
                output_dir=directory,
                timeout=30,
                verbose=False,
            )
            self.assertIs(
                result.status, expected, Path(result.artifacts.log).read_text()
            )
            if expected is Status.Violated:
                self.assertEqual(result.property_name, prop.name)
            if result.counterexample is not None:
                for state in result.counterexample.states:
                    self.assertEqual(set(state.values), {"phase"})
            return result

    def test_strong_until_boundaries(self) -> None:
        cases = (
            (system(waiting, finish, forget), Status.Passed),
            (system(done, forget), Status.Passed),
            (system(waiting, idle, fair=False), Status.Violated),
            (system(gap, resume), Status.Violated),
            (system(waiting, interrupt, resume), Status.Violated),
        )
        for model, expected in cases:
            with self.subTest(
                init=model.init.name, actions=tuple(a.name for a in model.next)
            ):
                result = self.verify(model, waits_until_done, expected)
                if model.init is gap or interrupt in model.next:
                    self.assertIsNotNone(result.counterexample)
                    self.assertIsNone(result.counterexample.loop_start)
                    self.assertEqual(
                        len(result.counterexample.states), 1 if model.init is gap else 2
                    )
                elif expected is Status.Violated:
                    self.assertIsNotNone(result.counterexample.loop_start)
        self.verify(system(waiting, interrupt, resume), eventually_done, Status.Passed)

    def test_negation_and_multiple_untils(self) -> None:
        self.verify(system(waiting, idle, fair=False), not_until, Status.Passed)
        self.verify(system(waiting, finish, forget), not_until, Status.Violated)
        self.verify(system(waiting, interrupt, resume), either_until, Status.Passed)

    def test_safety_property_name_with_multiple_properties(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = check(
                system(waiting, interrupt, resume),
                properties=[eventually_done, waits_until_done],
                tlc_jar=self.tla2tools_jar,
                output_dir=directory,
                timeout=30,
                verbose=False,
            )
            self.assertIs(result.status, Status.Violated)
            self.assertEqual(result.property_name, "waits_until_done")
            self.assertIsNone(result.counterexample.loop_start)

    def test_constant_predicates(self) -> None:
        model = system(waiting, idle, fair=False)
        for prop, expected in (
            (false_until_true, Status.Passed),
            (true_until_true, Status.Passed),
            (true_until_false, Status.Violated),
            (false_until_false, Status.Violated),
        ):
            with self.subTest(prop=prop.name):
                self.verify(model, prop, expected)

    def test_quantified_until(self) -> None:
        model = system(waiting, interrupt, resume, forget)
        self.verify(model, every_phase_before_after, Status.Passed)
        self.verify(model, every_phase_before_gap, Status.Violated)
        self.verify(model, initially_one_phase, Status.Passed)
        self.verify(model, two_bindings, Status.Passed)
