import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Annotated

from tlacraftpy import (
    MaxLen,
    Specification,
    SpecificationError,
    Status,
    TLCError,
    action,
    any_action,
    append,
    check,
    compile_spec,
    exists,
    export,
    forall,
    head,
    initial,
    invariant,
    state,
    tail,
    temporal,
    leads_to,
    unchanged,
    weak_fairness,
)
from tlacraftpy.runner import parse_trace, resolve_tools

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import fifo

Message = fifo.Message
Bit = fifo.Bit
LOWER = -1


@state
class SmallState:
    q: Annotated[tuple[Message, ...], MaxLen(2)]
    last: Message


@initial
def empty(s):
    """Use an empty queue and a known output value."""
    return s.q == () and s.last == Message.A


@action
def put(s, t):
    return len(s.q) < 2 and exists(
        Message, lambda msg: t.q == s.q + (msg,) and unchanged(s.last)
    )


@action
def get(s, t):
    return len(s.q) > 0 and t.last == head(s.q) and t.q == tail(s.q)


@invariant
def bounded(s):
    return LOWER < len(s.q) <= 2


@invariant
def too_short(s):
    return len(s.q) < 2


@invariant
def enum_coverage(s):
    return forall(Message, lambda msg: exists(Message, lambda item: item == msg))


@invariant
def shadowed_binding(s):
    return forall(
        Message,
        lambda msg: exists(Message, lambda msg: msg == Message.A) and msg == msg,
    )


@invariant
def impossible(s):
    return forall(Message, lambda msg: s.last == msg)


@temporal
def each_head_served(s):
    return forall(
        Message,
        lambda msg: leads_to(len(s.q) > 0 and head(s.q) == msg, s.last == msg),
    )


@action
def bad_append(s, t):
    return t.q == append(s.q, Bit.One) and unchanged(s.last)


@action
def bad_concat(s, t):
    return t.q == s.q + (Bit.One,) and unchanged(s.last)


@action
def bad_length(s, t):
    return len(s.last) > 0 and unchanged(s.q) and unchanged(s.last)


@action
def bad_domain(s, t):
    return exists(Bit, lambda msg: t.last == msg) and unchanged(s.q)


@action
def bad_predicate(s, t):
    return exists(Message, lambda msg: msg) and unchanged(s.q)


@action
def bad_shadow(s, t):
    return exists(Message, lambda s: s == Message.A) and unchanged(s.q)


@action
def bad_arity(s, t):
    return exists(Message, lambda a, b: a == b) and unchanged(s.q)


@action
def bad_sequence(s, t):
    return t.q == (Message.A, Bit.One) and unchanged(s.last)


@action
def bad_bound_domain(s, t):
    return exists(
        Message,
        lambda Message: exists(Message, lambda item: item == item),
    )


@invariant
def action_in_invariant(s):
    return unchanged(s.q)


@action
def drop_rest(s, t):
    return (
        len(s.q) > 0
        and s.out_ready == s.out_ack
        and t.out_value == head(s.q)
        and t.out_ready != s.out_ready
        and t.q == ()
        and unchanged(s.in_value)
        and unchanged(s.in_ready)
        and unchanged(s.in_ack)
        and unchanged(s.out_ack)
    )


def small_system():
    return Specification(SmallState, empty, any_action(put, get))


def graph(path, canonical):
    nodes, initial_states, edges = {}, set(), []
    for line in path.read_text().splitlines():
        node = re.match(r'^(-?\d+) \[label=("(?:\\.|[^"\\])*")', line)
        if node:
            assignments = {}
            for item in json.loads(node[2]).splitlines():
                name, value = item.removeprefix("/\\ ").split(" = ", 1)
                assignments[name] = value
            nodes[node[1]] = canonical(assignments)
            if "style = filled" in line:
                initial_states.add(nodes[node[1]])
        edge = re.match(r"^(-?\d+) -> (-?\d+) ", line)
        if edge:
            edges.append((edge[1], edge[2]))
    if not nodes or not edges:
        raise AssertionError("TLC graph dump is empty")
    return set(nodes.values()), initial_states, {(nodes[a], nodes[b]) for a, b in edges}


def original_state(values):
    def channel(value):
        match = re.fullmatch(
            r"\[val \|-> Msg([AB]), rdy \|-> ([01]), ack \|-> ([01])\]", value
        )
        if not match:
            raise AssertionError(value)
        return match[1], match[2], match[3]

    return (
        *channel(values["in"]),
        *channel(values["out"]),
        tuple(re.findall(r"Msg([AB])", values["q"])),
    )


def port_state(values):
    scalar = {"E0M0": "A", "E0M1": "B", "E1M0": "0", "E1M1": "1"}
    q = tuple(scalar[x] for x in re.findall(r"E\d+M\d+", values["v6"]))
    return (*(scalar[values[f"v{i}"]] for i in range(6)), q)


class SequenceCompilerTests(unittest.TestCase):
    def test_annotations_and_expression_types(self):
        compiled = compile_spec(small_system(), invariants=[bounded, enum_coverage])
        self.assertIn("UNION {[1..n ->", compiled.tla)
        self.assertIn("\\o", compiled.tla)
        self.assertIn("Head(", compiled.tla)
        self.assertIn("Tail(", compiled.tla)
        self.assertIn("\\A b0", compiled.tla)
        self.assertIn("\\E b1", compiled.tla)
        self.assertIn("INVARIANTS\n    I0\n    I1", compiled.cfg)
        self.assertEqual(compiled.mapping["invariants"]["I0"], "bounded")
        self.assertIn(
            "\\E b1", compile_spec(small_system(), invariants=[shadowed_binding]).tla
        )

    def test_invalid_domains(self):
        for value in (-1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(SpecificationError):
                MaxLen(value)
        for annotation in (
            tuple[Message, ...],
            Annotated[tuple[int, ...], MaxLen(2)],
            Annotated[tuple[Message, Message], MaxLen(2)],
            Annotated[tuple[Message, ...], MaxLen(1), MaxLen(2)],
        ):
            with (
                self.subTest(annotation=annotation),
                self.assertRaises(SpecificationError),
            ):
                state(type("Bad", (), {"__annotations__": {"q": annotation}}))
        zero = state(
            type(
                "EmptyOnly",
                (),
                {
                    "__annotations__": {
                        "q": Annotated[tuple[Message, ...], MaxLen(0)],
                        "last": Message,
                    }
                },
            )
        )
        compile_spec(Specification(zero, empty, any_action(put)))

    def test_invalid_expressions(self):
        for definition in (
            bad_append,
            bad_concat,
            bad_length,
            bad_domain,
            bad_predicate,
            bad_shadow,
            bad_arity,
            bad_sequence,
            bad_bound_domain,
        ):
            with (
                self.subTest(name=definition.name),
                self.assertRaises(SpecificationError),
            ):
                compile_spec(Specification(SmallState, empty, any_action(definition)))
        with self.assertRaises(SpecificationError):
            compile_spec(small_system(), invariants=[action_in_invariant])
        with self.assertRaises(SpecificationError):
            compile_spec(small_system(), invariants=[empty])

    def test_dsl_markers_raise_on_direct_calls(self):
        for operator in (append, head, tail, exists, forall):
            with (
                self.subTest(operator=operator.__name__),
                self.assertRaises(SpecificationError),
            ):
                operator()

    def test_sequence_trace_decoding(self):
        mapping = compile_spec(small_system()).mapping
        output = """1: <Initial predicate>
/\\ v0 = <<E0M0,
 E0M1>>
/\\ v1 = E0M0
2: Stuttering
"""
        trace = parse_trace(output, mapping)
        self.assertEqual(trace.states[0].values["q"], "(Message.A, Message.B)")
        self.assertEqual(trace.loop_start, 1)
        for raw, expected in (("<<>>", "()"), ("<<E0M0>>", "(Message.A,)")):
            trace = parse_trace(output.replace("<<E0M0,\n E0M1>>", raw), mapping)
            self.assertEqual(trace.states[0].values["q"], expected)
        for raw in ("<<E0M0,>>", "<<E0M0", "<<Other>>", "<<E0M0>> trailing"):
            with self.subTest(raw=raw), self.assertRaises(TLCError):
                parse_trace(output.replace("<<E0M0,\n E0M1>>", raw), mapping)


@unittest.skipUnless(
    os.environ.get("TLACRAFTPY_TLC_JAR"), "set TLACRAFTPY_TLC_JAR to run TLC"
)
class FIFOIntegrationTests(unittest.TestCase):
    def check_model(self, system, directory, **kwargs):
        try:
            return check(
                system,
                tlc_jar=os.environ["TLACRAFTPY_TLC_JAR"],
                output_dir=directory,
                timeout=60,
                verbose=False,
                **kwargs,
            )
        except TLCError as exc:
            self.fail(f"{exc}\n{(Path(directory) / 'tlc.log').read_text()}")

    def test_sequence_operations_and_invariant_counterexample(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.check_model(
                small_system(),
                directory,
                invariants=[bounded, enum_coverage, shadowed_binding],
            )
            self.assertIs(result.status, Status.Passed)
            result = self.check_model(
                small_system(), directory, invariants=[impossible]
            )
            self.assertIs(result.status, Status.Violated)
            self.assertEqual(result.property_name, "impossible")
            self.assertEqual(len(result.counterexample.states), 1)
            fair_system = Specification(
                SmallState, empty, any_action(put, get), [weak_fairness(get)]
            )
            result = self.check_model(
                fair_system, directory, properties=[each_head_served]
            )
            self.assertIs(result.status, Status.Passed)
            result = self.check_model(small_system(), directory, invariants=[too_short])
            self.assertIs(result.status, Status.Violated)
            self.assertEqual(result.property_name, "too_short")
            self.assertIsNone(result.counterexample.loop_start)
            self.assertEqual(result.counterexample.states[0].values["q"], "()")
            self.assertIn(", ", result.counterexample.states[-1].values["q"])

    def test_fifo_progress_and_stuttering_counterexample(self):
        for fair, expected in ((True, Status.Passed), (False, Status.Violated)):
            with self.subTest(fair=fair), tempfile.TemporaryDirectory() as directory:
                result = self.check_model(
                    fifo.make_system(fair=fair),
                    directory,
                    invariants=[fifo.bounded],
                    properties=[fifo.input_acknowledged],
                )
                self.assertIs(result.status, expected)
                if not fair:
                    self.assertEqual(result.property_name, "input_acknowledged")
                    self.assertIsNotNone(result.counterexample.loop_start)
                    self.assertIn("q", result.counterexample.states[-1].values)

    def run_dump(self, directory, module, cfg, java, jar):
        run = subprocess.run(
            [
                java,
                "-Xmx512m",
                "-XX:+UseParallelGC",
                "-cp",
                str(jar),
                "tlc2.TLC",
                "-tool",
                "-workers",
                "1",
                "-config",
                cfg,
                "-metadir",
                str(directory / "states"),
                "-dump",
                "dot",
                str(directory / "graph.dot"),
                module,
            ],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return directory / "graph.dot"

    def test_state_graph_matches_upstream_and_detects_dropped_messages(self):
        fixtures = Path(__file__).parent / "fixtures/fifo"
        java, jar = resolve_tools(Path(fifo.__file__), os.environ["TLACRAFTPY_TLC_JAR"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original"
            shutil.copytree(fixtures, original)
            reference = graph(
                self.run_dump(
                    original, "ReferenceFIFO", "ReferenceFIFO.cfg", java, jar
                ),
                original_state,
            )
            self.assertEqual(len(reference[0]), 344)
            self.assertEqual(len(reference[1]), 16)
            self.assertEqual(len(reference[2]), 648)
            for broken in (False, True):
                with self.subTest(broken=broken):
                    port = root / ("broken" if broken else "port")
                    spec = fifo.make_system(fair=False)
                    if broken:
                        spec = Specification(
                            fifo.State,
                            fifo.init,
                            any_action(fifo.ssend, fifo.buf_rcv, drop_rest, fifo.rrcv),
                        )
                    artifacts = export(spec, output_dir=port, module="Port")
                    result = graph(
                        self.run_dump(port, "Port", artifacts.cfg.name, java, jar),
                        port_state,
                    )
                    if broken:
                        self.assertNotEqual(result[2], reference[2])
                    else:
                        self.assertEqual(result, reference)


if __name__ == "__main__":
    unittest.main()
