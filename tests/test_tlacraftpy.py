import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from enum import Enum, IntEnum, auto
from pathlib import Path
from unittest.mock import patch

from tlacraftpy import (
    ConfigurationError,
    Specification,
    SpecificationError,
    Status,
    TLCError,
    UnconstrainedWarning,
    action,
    any_action,
    check,
    compile_spec,
    export,
    initial,
    leads_to,
    state,
    temporal,
    unconstrained,
    unchanged,
    weak_fairness,
)
from tlacraftpy.runner import classify, parse_trace, resolve_tools

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from request_response import (  # noqa: E402
    Phase,
    State,
    every_request_gets_response,
    init,
    make_system,
    request,
    respond,
)


class Flag(Enum):
    Off = auto()
    On = auto()


@state
class TwoFields:
    phase: Phase
    flag: Flag


@initial
def two_init(s):
    return s.phase == Phase.Idle and s.flag == Flag.Off


@action
def missing(s, t):
    return s.phase == Phase.Idle and t.phase == Phase.Requested


@action
def keep(s, t):
    return t.phase == Phase.Requested and unchanged(s.flag)


@action
def allow(s, t):
    return t.phase == Phase.Requested and unconstrained(s.flag)


@action
def branch_missing(s, t):
    return (t.phase == Phase.Requested and unchanged(s.flag)) or t.phase == Phase.Idle


@action
def assign(s, t):
    x = Phase.Requested
    return t.phase == x


@action
def arbitrary_call(s, t):
    return print("MUST NOT EXECUTE")


@action
def wrong_domain(s, t):
    return t.phase == Flag.On


@action
def wrong_field(s, t):
    return t.typo == Phase.Idle


@action
def ordering(s, t):
    return s.phase < t.phase


@action
def bad_frame(s, t):
    return unchanged(t.phase)


@action
def bad_temporal(s, t):
    return leads_to(s.phase == Phase.Idle, t.phase == Phase.Requested)


@temporal
def nested_temporal(s):
    return leads_to(leads_to(s.phase == Phase.Idle, s.phase == Phase.Requested), True)


@initial
def bare_enum(s):
    return s.phase


@initial
def wrong_arguments(s, t):
    return True


@temporal
def not_temporal(s):
    return s.phase == Phase.Idle


@temporal
def logical_property(s):
    return not leads_to(s.phase != Phase.Idle, s.phase == Phase.Responded)


@temporal
def flag_returns_off(s):
    return leads_to(s.flag == Flag.On, s.flag == Flag.Off)


def two_spec(a):
    return Specification(TwoFields, two_init, any_action(a))


SUCCESS = """@!@!@STARTMSG 2193:0 @!@!@
Model checking completed. No error has been found.
@!@!@ENDMSG 2193 @!@!@
"""
# Protocol fixtures, not claimed to be captured from a real TLC invocation.
STUTTER = """@!@!@STARTMSG 2116:1 @!@!@
Temporal properties were violated.
@!@!@ENDMSG 2116 @!@!@
@!@!@STARTMSG 2217:4 @!@!@
1: <Initial predicate>
v0 = E0M0
@!@!@ENDMSG 2217 @!@!@
@!@!@STARTMSG 2217:4 @!@!@
2: <A0 line 12, col 1 to line 12, col 50 of module Model>
v0 = E0M1
@!@!@ENDMSG 2217 @!@!@
@!@!@STARTMSG 2218:4 @!@!@
3: Stuttering
@!@!@ENDMSG 2218 @!@!@
"""


class CompilerTests(unittest.TestCase):
    def test_fair_request_response(self):
        compiled = compile_spec(make_system(), properties=[every_request_gets_response])
        self.assertIn("WF_vars(A1)", compiled.tla)
        self.assertIn("[][Next]_vars", compiled.tla)
        self.assertIn("~>", compiled.tla)
        self.assertIn("v0' \\in {E0M0, E0M1, E0M2}", compiled.tla)
        self.assertIn("PROPERTIES\n    P0", compiled.cfg)
        self.assertIn("E0M1 = E0M1", compiled.cfg)
        self.assertEqual(compiled.mapping["values"]["E0M1"], "Phase.Requested")
        self.assertNotIn("WF_vars", compile_spec(make_system(fair=False)).tla)

    def test_missing_field_warns_and_keeps_domain(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            compiled = compile_spec(two_spec(missing))
        self.assertEqual(len(caught), 1)
        self.assertIs(caught[0].category, UnconstrainedWarning)
        self.assertIn("'flag'", str(caught[0].message))
        self.assertIn("v1 \\in {E1M0, E1M1}", compiled.tla)
        self.assertIn("v1' \\in {E1M0, E1M1}", compiled.tla)

    def test_frames_and_explicit_unconstrained(self):
        for a, expected in [(keep, "UNCHANGED v1"), (allow, "(TRUE)")]:
            with self.subTest(a=a.name), warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                compiled = compile_spec(two_spec(a))
            self.assertEqual(caught, [])
            self.assertIn(expected, compiled.tla)

    def test_branch_specific_warning(self):
        with self.assertWarns(UnconstrainedWarning):
            compile_spec(two_spec(branch_missing))

    def test_unsupported_source_never_executes(self):
        for a in (
            assign,
            arbitrary_call,
            wrong_domain,
            wrong_field,
            ordering,
            bad_frame,
            bad_temporal,
        ):
            with (
                self.subTest(a=a.name),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                with self.assertRaises(SpecificationError) as error:
                    compile_spec(Specification(State, init, any_action(a)))
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("test_tlacraftpy.py:", str(error.exception))

    def test_bad_initial_and_temporal_levels(self):
        for definition in (bare_enum, wrong_arguments):
            with (
                self.subTest(definition=definition.name),
                self.assertRaises(SpecificationError),
            ):
                compile_spec(Specification(State, definition, any_action(request)))
        for prop in (nested_temporal, not_temporal):
            with self.subTest(prop=prop.name), self.assertRaises(SpecificationError):
                compile_spec(make_system(), properties=[prop])
        self.assertIn(
            "~(", compile_spec(make_system(), properties=[logical_property]).tla
        )

    def test_bad_declarations(self):
        with self.assertRaises(SpecificationError):
            state(type("Bad", (), {"__annotations__": {"x": int}}))
        with self.assertRaises(SpecificationError):
            any_action(init)
        with self.assertRaises(SpecificationError):
            Specification(State, init, any_action(request), [weak_fairness(respond)])
        with self.assertRaises(SpecificationError):
            compile_spec(make_system(), module="Bad\nINJECTION")

    def test_source_required(self):
        with self.assertRaises(SpecificationError):
            compile_spec(
                Specification(
                    State, initial(eval("lambda s: True")), any_action(request)
                )
            )

    def test_numeric_enum_domains_do_not_alias(self):
        # IntEnum members in different domains compare equal as Python values.
        class First(IntEnum):
            One = 1

        class Second(IntEnum):
            One = 1

        # Build a local source definition to also exercise closure resolution.
        @state
        class Numeric:
            left: First
            right: Second

        @initial
        def numeric_init(s):
            return s.left == First.One and s.right == Second.One

        @action
        def numeric_next(s, t):
            return unchanged(s.left) and unchanged(s.right)

        compiled = compile_spec(
            Specification(Numeric, numeric_init, any_action(numeric_next))
        )
        self.assertEqual(len(compiled.mapping["values"]), 2)
        self.assertIn("v0 \\in {E0M0}", compiled.tla)
        self.assertIn("v1 \\in {E1M0}", compiled.tla)

    def test_export_and_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = export(
                make_system(),
                properties=[every_request_gets_response],
                output_dir=directory,
            )
            self.assertEqual(artifacts.tla.read_text(), artifacts.compiled.tla)
            self.assertEqual(artifacts.cfg.read_text(), artifacts.compiled.cfg)
            self.assertIn("Phase.Requested", artifacts.mapping.read_text())


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.artifacts = export(
            make_system(fair=False),
            properties=[every_request_gets_response],
            output_dir=self.tmp.name,
        )

    def test_results_and_stuttering_trace(self):
        result = classify(STUTTER, 13, self.artifacts)
        self.assertEqual(result.status, Status.Violated)
        self.assertEqual(result.property_name, "every_request_gets_response")
        self.assertEqual(result.counterexample.loop_start, 2)
        self.assertTrue(result.counterexample.stuttering)
        self.assertEqual(
            result.counterexample.states[1].values, {"phase": "Phase.Requested"}
        )
        self.assertIn("request", result.counterexample.states[1].label)
        self.assertEqual(classify(SUCCESS, 0, self.artifacts).status, Status.Passed)

    def test_loop_trace(self):
        for back in ("Back to state 1: <A1>", "3: Back to state: 1"):
            output = STUTTER.replace("3: Stuttering", back)
            trace = parse_trace(output, self.artifacts.compiled.mapping)
            self.assertEqual(trace.loop_start, 1)
            self.assertFalse(trace.stuttering)

    def test_unknown_error_and_malformed_trace_fail_closed(self):
        outputs = ["", "Parsing failed", SUCCESS.replace("No error", "An error")]
        for output in outputs:
            with self.subTest(output=output), self.assertRaises(TLCError):
                classify(output, 0, self.artifacts)
        with self.assertRaises(TLCError):
            classify(SUCCESS, 1, self.artifacts)
        for output in (
            STUTTER.replace("E0M1", "UNKNOWN"),
            STUTTER.replace("v0 = E0M0", ""),
            STUTTER.replace("3: Stuttering", ""),
        ):
            with self.subTest(output=output), self.assertRaises(TLCError):
                classify(output, 13, self.artifacts)

    def test_timeout_is_incomplete_and_logged(self):
        with (
            patch(
                "tlacraftpy.runner.resolve_tools",
                return_value=("java", Path("/fake/tlc.jar")),
            ),
            patch(
                "tlacraftpy.runner.subprocess.run",
                side_effect=subprocess.TimeoutExpired("java", 1, b"partial"),
            ),
        ):
            result = check(
                make_system(), output_dir=self.tmp.name, timeout=1, verbose=False
            )
        self.assertEqual(result.status, Status.Incomplete)
        self.assertEqual(result.artifacts.log.read_text(), "partial")

    def test_invocation_and_log(self):
        with (
            patch(
                "tlacraftpy.runner.resolve_tools",
                return_value=("java", Path("/fake/a b.jar")),
            ),
            patch(
                "tlacraftpy.runner.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, SUCCESS),
            ) as run,
        ):
            result = check(make_system(), output_dir=self.tmp.name, verbose=False)
        self.assertEqual(result.status, Status.Passed)
        self.assertIn("/fake/a b.jar", run.call_args.args[0])
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(result.artifacts.log.read_text(), SUCCESS)

    def test_launch_error(self):
        with (
            patch(
                "tlacraftpy.runner.resolve_tools",
                return_value=("java", Path("/fake/tlc.jar")),
            ),
            patch("tlacraftpy.runner.subprocess.run", side_effect=OSError("denied")),
        ):
            with self.assertRaises(TLCError):
                check(make_system(), output_dir=self.tmp.name, verbose=False)

    def test_java_path_precedes_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jar = root / "tlc.jar"
            jar.touch()
            (root / "pyproject.toml").write_text(
                '[tool.tlacraftpy]\njava="missing"\ntlc_jar="tlc.jar"\n'
            )
            source = root / "spec.py"
            with patch("tlacraftpy.runner.shutil.which", return_value="/usr/bin/java"):
                self.assertEqual(resolve_tools(source), ("/usr/bin/java", jar))
            with patch("tlacraftpy.runner.shutil.which", return_value=None):
                with self.assertRaises(ConfigurationError):
                    resolve_tools(source)
            executable = root / "java"
            executable.touch()
            executable.chmod(0o755)
            (root / "pyproject.toml").write_text(
                '[tool.tlacraftpy]\njava="java"\ntlc_jar="tlc.jar"\n'
            )
            with patch("tlacraftpy.runner.shutil.which", return_value=None):
                self.assertEqual(resolve_tools(source), (str(executable), jar))

    def test_missing_jar_is_configuration_error_no_download(self):
        with patch("tlacraftpy.runner.shutil.which", return_value="/usr/bin/java"):
            with self.assertRaises(ConfigurationError):
                resolve_tools(Path(self.tmp.name) / "spec.py")


@unittest.skipUnless(
    os.environ.get("TLACRAFTPY_TLC_JAR"), "set TLACRAFTPY_TLC_JAR to run real TLC tests"
)
class TLCIntegrationTests(unittest.TestCase):
    def run_tlc(self, system, prop, directory):
        try:
            return check(
                system,
                properties=[prop],
                tlc_jar=os.environ["TLACRAFTPY_TLC_JAR"],
                output_dir=directory,
                timeout=30,
                verbose=False,
            )
        except TLCError as exc:
            log = Path(directory) / "tlc.log"
            self.fail(f"{exc}\n{log.read_text() if log.exists() else ''}")

    def test_fairness_changes_liveness_result(self):
        for fair, expected in ((True, Status.Passed), (False, Status.Violated)):
            with self.subTest(fair=fair), tempfile.TemporaryDirectory() as directory:
                result = self.run_tlc(
                    make_system(fair=fair), every_request_gets_response, directory
                )
                self.assertEqual(result.status, expected)
                if not fair:
                    self.assertIsNotNone(result.counterexample.loop_start)
                    self.assertEqual(
                        result.counterexample.states[-1].values["phase"],
                        "Phase.Requested",
                    )

    def test_frame_conditions_with_multiple_enum_domains(self):
        for a, expected in ((keep, Status.Passed), (allow, Status.Violated)):
            with (
                self.subTest(action=a.name),
                tempfile.TemporaryDirectory() as directory,
            ):
                result = self.run_tlc(two_spec(a), flag_returns_off, directory)
                self.assertEqual(result.status, expected)
                if a is allow:
                    self.assertEqual(
                        result.counterexample.states[-1].values["flag"], "Flag.On"
                    )


if __name__ == "__main__":
    unittest.main()
