"""Explicit Java/TLC invocation and conservative result classification."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .compiler import Artifacts, _NameMapping, export, project_root
from .model import ConfigurationError, Definition, Specification, TLCError


class Status(Enum):
    """Identify the outcome of a completed or interrupted verification attempt.

    Args:
        value: Serialized outcome: ``"passed"``, ``"violated"``, or ``"incomplete"``.

    Attributes:
        Passed: TLC completed model checking and all requested properties held.
        Violated: TLC produced a counterexample to an invariant or temporal property.
        Incomplete: Verification reached its timeout or TLC reported interruption.

    Raises:
        ValueError: If constructing ``Status(value)`` with an unknown value.
    """

    Passed = "passed"
    Violated = "violated"
    Incomplete = "incomplete"


@dataclass(frozen=True)
class TraceState:
    """Describe one state in a counterexample using Python-side names.

    Args:
        number: TLC's one-based state number within the counterexample.
        values: Mapping of Python field names to display values such as
            ``{"phase": "Phase.Requested", "q": "(Message.A, Message.B)"}``.
        label: TLC transition or initial-predicate label with generated names
            replaced by their Python-side equivalents where available.
    """

    number: int
    values: dict[str, str]
    label: str


@dataclass(frozen=True)
class Counterexample:
    """Represent a counterexample prefix and its repeating suffix.

    Args:
        states: Ordered tuple of states forming the displayed finite prefix.
        loop_start: One-based state number that follows the last displayed state
            when execution repeats. ``None`` represents a trace without a loop.
        stuttering: Whether the repetition preserves the last state's field
            values. Defaults to ``False``.

    ``str(counterexample)`` formats the states and the repetition target for
    display. Temporal counterexamples returned by ``check`` include a loop.
    """

    states: tuple[TraceState, ...]
    loop_start: int | None = None  # TLC's 1-based state number
    stuttering: bool = False

    def __str__(self) -> str:
        """Format state values and the repeating suffix as readable text.

        Returns:
            str: Numbered states followed by the loop target, when present.
        """
        lines = [
            f"{s.number}. " + ", ".join(f"{k} = {v}" for k, v in s.values.items())
            for s in self.states
        ]
        if self.loop_start is not None:
            suffix = " (stuttering)" if self.stuttering else ""
            lines.append(f"   -> repeat from state {self.loop_start}{suffix}")
        return "\n".join(lines)


@dataclass(frozen=True)
class CheckResult:
    """Collect a verification outcome, output files, and any counterexample.

    Args:
        status: ``Passed``, ``Violated``, or ``Incomplete`` verification outcome.
        artifacts: Generated specification, configuration, mapping, and log paths.
        counterexample: Trace supplied for an invariant or temporal-property violation;
            defaults to ``None``.
        property_name: Python name of the violated invariant, or the violated
            temporal property when exactly one was checked. ``None`` means the
            name is unspecified.
        reason: Explanation of an interruption or timeout, when applicable.

    ``str(result)`` formats the outcome, property name, reason, and trace for
    display. ``check`` raises exceptions for configuration and execution errors.
    """

    status: Status
    artifacts: Artifacts
    counterexample: Counterexample | None = None
    property_name: str | None = None
    reason: str | None = None

    def __str__(self) -> str:
        """Format the verification outcome and associated diagnostic details.

        Returns:
            str: Outcome followed by the property, reason, and trace when present.
        """
        name = f" ({self.property_name})" if self.property_name else ""
        text = f"TLC: {self.status.value}{name}"
        if self.reason:
            text += f" — {self.reason}"
        if self.counterexample:
            text += "\n" + str(self.counterexample)
        return text


def _replace_names(text: str, mapping: _NameMapping) -> str:
    replacements = {}
    for category in ("variables", "values", "actions", "properties", "invariants"):
        replacements.update(mapping.get(category, {}))
    return re.sub(
        r"\b[A-Za-z][A-Za-z0-9_]*\b", lambda m: replacements.get(m[0], m[0]), text
    )


def _decode_value(raw: str, mapping: _NameMapping) -> str:
    tokens = re.findall(r"<<|>>|,|[A-Za-z][A-Za-z0-9_]*", raw)
    if "".join(tokens) != re.sub(r"\s+", "", raw):
        raise TLCError("Unsupported value in TLC counterexample; see tlc.log")

    def parse(index: int) -> tuple[str, int]:
        if index >= len(tokens):
            raise TLCError("Truncated sequence in TLC counterexample; see tlc.log")
        token = tokens[index]
        if token == "<<":
            values = []
            index += 1
            if index < len(tokens) and tokens[index] == ">>":
                return "()", index + 1
            while True:
                value, index = parse(index)
                values.append(value)
                if index < len(tokens) and tokens[index] == ">>":
                    suffix = "," if len(values) == 1 else ""
                    return "(" + ", ".join(values) + suffix + ")", index + 1
                if index >= len(tokens) or tokens[index] != ",":
                    raise TLCError(
                        "Malformed sequence in TLC counterexample; see tlc.log"
                    )
                index += 1
        if token not in mapping["values"]:
            raise TLCError("Unknown value in TLC counterexample; see tlc.log")
        return mapping["values"][token], index + 1

    value, end = parse(0)
    if end != len(tokens):
        raise TLCError("Trailing value in TLC counterexample; see tlc.log")
    return value


def parse_trace(output: str, mapping: _NameMapping) -> Counterexample:
    """Decode TLC's counterexample messages using generated name mappings.

    Args:
        output: TLC text output, including optional ``-tool`` message markers.
        mapping: Generated-to-Python mapping from ``Compiled.mapping``.

    Returns:
        Counterexample: Numbered states and any loop or stuttering target.

    Raises:
        TLCError: If state values, state numbering, or the repetition target are
            malformed or cannot be interpreted.
        KeyError: If a required mapping category is absent.
    """
    # -tool decorates normal TLC messages with STARTMSG/ENDMSG records.
    lines = [line for line in output.splitlines() if not line.startswith("@!@!@")]
    states: list[TraceState] = []
    current_number: int | None = None
    label = ""
    values: dict[str, str] = {}
    loop_start: int | None = None
    stuttering = False
    active_field: str | None = None

    def flush() -> None:
        nonlocal current_number, values, active_field
        if current_number is not None:
            if set(values) != set(mapping["variables"].values()):
                raise TLCError(
                    "Incomplete or unsupported TLC counterexample; see tlc.log"
                )
            states.append(
                TraceState(
                    current_number,
                    {name: _decode_value(raw, mapping) for name, raw in values.items()},
                    label,
                )
            )
            current_number, values = None, {}
            active_field = None

    for line in lines:
        stripped = line.strip()
        if re.match(r"^Invariant I\d+ is violated by the initial state:", stripped):
            flush()
            current_number, label = 1, "<Initial predicate>"
            continue
        back = re.match(r"^(?:\d+:\s*)?Back to state\s*:?\s*(\d+)", stripped, re.I)
        if back:
            flush()
            loop_start = int(back[1])
            continue
        header = re.match(r"^(?:State\s+)?(\d+):\s*(.*)$", stripped)
        if header:
            flush()
            if "stuttering" in header[2].lower():
                if not states:
                    raise TLCError("Invalid stuttering trace; see tlc.log")
                loop_start, stuttering = states[-1].number, True
            else:
                current_number = int(header[1])
                label = _replace_names(header[2], mapping)
            continue
        assignment = re.match(r"^(?:/\\\s*)?(v\d+)\s*=\s*(.+?)\s*$", stripped)
        if assignment and current_number is not None:
            var, value = assignment.groups()
            if var not in mapping["variables"]:
                raise TLCError("Unknown value in TLC counterexample; see tlc.log")
            active_field = mapping["variables"][var]
            values[active_field] = value
        elif current_number is not None and active_field is not None:
            raw = values[active_field]
            if raw.count("<<") > raw.count(">>"):
                values[active_field] += " " + stripped
    flush()
    if not states or [s.number for s in states] != list(range(1, len(states) + 1)):
        raise TLCError("Missing or malformed TLC counterexample; see tlc.log")
    if loop_start is not None and loop_start not in {s.number for s in states}:
        raise TLCError("Invalid counterexample loop target; see tlc.log")
    return Counterexample(tuple(states), loop_start, stuttering)


def classify(output: str, returncode: int, artifacts: Artifacts) -> CheckResult:
    """Interpret a TLC process's output and exit code as a verification result.

    Args:
        output: Combined standard output and standard error from TLC.
        returncode: Process exit code.
        artifacts: Generated files and name mappings for this invocation.

    Returns:
        CheckResult: Passed for successful completion, Violated for an invariant
        or temporal counterexample, or Incomplete for a reported interruption.

    Raises:
        TLCError: If TLC reports an execution error, its result is unrecognized,
            or a temporal counterexample cannot be decoded with a loop.
    """
    violated = "Temporal properties were violated" in output
    invariant_match = re.search(r"\bInvariant (I\d+) is violated\b", output)
    if invariant_match:
        name = artifacts.compiled.mapping.get("invariants", {}).get(invariant_match[1])
        if name is None:
            raise TLCError("Unknown invariant in TLC output; see tlc.log")
        return CheckResult(
            Status.Violated,
            artifacts,
            parse_trace(output, artifacts.compiled.mapping),
            name,
        )
    if violated:
        trace = parse_trace(output, artifacts.compiled.mapping)
        if trace.loop_start is None:
            raise TLCError("Temporal counterexample has no loop; see tlc.log")
        properties = artifacts.compiled.mapping["properties"]
        # Report the property name when exactly one property is being checked.
        name = next(iter(properties.values())) if len(properties) == 1 else None
        return CheckResult(Status.Violated, artifacts, trace, name)
    if (
        returncode == 0
        and "Model checking completed. No error has been found." in output
    ):
        return CheckResult(Status.Passed, artifacts)
    if "TLC was interrupted" in output or "TLC execution was canceled" in output:
        return CheckResult(Status.Incomplete, artifacts, reason="TLC was interrupted")
    raise TLCError(
        f"TLC did not produce a recognized verification result (exit {returncode}); "
        f"see {artifacts.log}"
    )


def _configuration(source: Path) -> tuple[Path, dict[str, object]]:
    root = project_root(source)
    config = root / "pyproject.toml"
    try:
        data = (
            tomllib.loads(config.read_text(encoding="utf-8"))
            if config.is_file()
            else {}
        )
        settings = data.get("tool", {}).get("tlacraftpy", {})
        if not isinstance(settings, dict):
            raise ConfigurationError("[tool.tlacraftpy] must be a TOML table")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Cannot read {config}: {exc}") from exc
    return root, settings


def _path(value: object, root: Path, name: str) -> Path:
    if not isinstance(value, (str, os.PathLike)) or not str(value):
        raise ConfigurationError(f"{name} must be a nonempty filesystem path")
    path = Path(value).expanduser()
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def resolve_tools(
    source: Path, tlc_jar: str | os.PathLike[str] | None = None
) -> tuple[str, Path]:
    """Locate Java and the TLC JAR for a specification's project.

    Args:
        source: Path to the initial predicate's source file, used to locate the
            nearest enclosing ``pyproject.toml`` and ``[tool.tlacraftpy]`` table.
        tlc_jar: Explicit JAR path, taking precedence over ``tlc_jar`` in project
            configuration. Explicit relative paths use the working directory;
            configured relative paths use the project root. Defaults to ``None``.

    Returns:
        tuple[str, Path]: Java executable and absolute TLC JAR path. Java is
        resolved from PATH first, then from the configured ``java`` path.

    Raises:
        ConfigurationError: If configuration cannot be parsed, Java cannot be
            located or executed, or the TLC JAR path is missing or invalid.
    """
    root, settings = _configuration(source)
    java = shutil.which("java")
    if java is None:
        configured = settings.get("java")
        if configured is None:
            raise ConfigurationError(
                "Java not found on PATH; set [tool.tlacraftpy].java in pyproject.toml"
            )
        executable = _path(configured, root, "java")
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ConfigurationError(f"Configured Java is not executable: {executable}")
        java = str(executable)
    jar = tlc_jar if tlc_jar is not None else settings.get("tlc_jar")
    if jar is None:
        raise ConfigurationError(
            "TLC is not configured; pass tlc_jar= or set [tool.tlacraftpy].tlc_jar. "
            "No Java or TLC is downloaded automatically."
        )
    # Explicit arguments are relative to the caller's cwd; config paths to project root.
    jar_path = _path(jar, Path.cwd() if tlc_jar is not None else root, "tlc_jar")
    if not jar_path.is_file():
        raise ConfigurationError(f"TLC JAR does not exist: {jar_path}")
    return java, jar_path


def check(
    spec: Specification,
    *,
    properties: Iterable[Definition] = (),
    invariants: Iterable[Definition] = (),
    tlc_jar: str | os.PathLike[str] | None = None,
    output_dir: str | os.PathLike[str] | None = None,
    module: str = "Model",
    timeout: float | None = None,
    verbose: bool = True,
) -> CheckResult:
    """Export a specification, run TLC, and return its verification outcome.

    Args:
        spec: ``Specification`` defining the finite-state model to verify.
        properties: Iterable of ``@temporal`` definitions to check.
        invariants: Iterable of ``@invariant`` state predicates to check in all
            reachable states. Violations return a finite counterexample.
        tlc_jar: TLC JAR path overriding ``[tool.tlacraftpy].tlc_jar``. Explicit
            relative paths use the working directory; configuration paths use
            the project root. Defaults to the project configuration.
        output_dir: Directory for the TLA+ module, TLC configuration, name
            mappings, TLC log, and state files. Relative paths use the working
            directory. The default is ``.tlacraftpy/<source stem>/`` beneath the
            project root located from the initial predicate's source file.
        module: TLA+ module name and generated file stem. Defaults to ``"Model"``.
        timeout: Positive time limit in seconds for the TLC process. ``None``
            waits for completion. Defaults to ``None``.
        verbose: Print the result and artifact directory when ``True``.
            Defaults to ``True``.

    Returns:
        CheckResult: Verification status, generated file paths, and any
        counterexample. Timeouts and reported interruptions produce Incomplete;
        invariant violations produce a finite trace and temporal-property
        violations produce a repeating trace, both with status Violated.
        Existing generated files and the TLC log at the output paths are replaced.

    Raises:
        SpecificationError: If the specification, invariant, or temporal property fails
            source compilation, or the module name is invalid.
        ConfigurationError: If Java, the TLC JAR, or project settings are invalid.
        TLCError: If Java cannot start, TLC reports an execution error, or its
            output or counterexample cannot be interpreted.
        ValueError: If ``timeout`` is zero or negative.
        OSError: If output directories, generated files, or logs cannot be written.

    Warns:
        UnconstrainedWarning: An action may leave a next-state field implicit.

    Examples:
        >>> result = check(system, properties=[responds], timeout=30)
        >>> if result.status is Status.Violated:
        ...     print(result.counterexample)
    """
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be positive or None")
    artifacts = export(
        spec,
        properties=properties,
        invariants=invariants,
        output_dir=output_dir,
        module=module,
    )
    java, jar = resolve_tools(artifacts.compiled.source, tlc_jar)
    meta = tempfile.mkdtemp(prefix="states-", dir=artifacts.directory)
    command = [
        java,
        "-Xmx512m",
        "-cp",
        str(jar),
        "tlc2.TLC",
        "-tool",
        "-workers",
        "1",
        "-metadir",
        meta,
        "-config",
        artifacts.cfg.name,
        module,
    ]
    try:
        run = subprocess.run(
            command,
            cwd=artifacts.directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        artifacts.log.write_text(output, encoding="utf-8")
        result = CheckResult(
            Status.Incomplete, artifacts, reason=f"timeout after {timeout}s"
        )
    except OSError as exc:
        artifacts.log.write_text(str(exc), encoding="utf-8")
        raise TLCError(f"Could not start Java: {exc}; see {artifacts.log}") from exc
    else:
        artifacts.log.write_text(run.stdout, encoding="utf-8")
        result = classify(run.stdout, run.returncode, artifacts)
    if verbose:
        print(result)
        print(f"Artifacts: {artifacts.directory}")
    return result
