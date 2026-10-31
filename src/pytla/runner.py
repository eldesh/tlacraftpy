"""Explicit Java/TLC invocation and conservative result classification."""
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .compiler import Artifacts, export, project_root
from .model import ConfigurationError, TLCError


class Status(Enum):
    Passed = "passed"
    Violated = "violated"
    Incomplete = "incomplete"


@dataclass(frozen=True)
class TraceState:
    number: int
    values: dict[str, str]
    label: str


@dataclass(frozen=True)
class Counterexample:
    states: tuple[TraceState, ...]
    loop_start: int | None = None  # TLC's 1-based state number
    stuttering: bool = False

    def __str__(self):
        lines = [f"{s.number}. " + ", ".join(f"{k} = {v}" for k, v in s.values.items())
                 for s in self.states]
        if self.loop_start is not None:
            suffix = " (stuttering)" if self.stuttering else ""
            lines.append(f"   -> repeat from state {self.loop_start}{suffix}")
        return "\n".join(lines)


@dataclass(frozen=True)
class CheckResult:
    status: Status
    artifacts: Artifacts
    counterexample: Counterexample | None = None
    property_name: str | None = None
    reason: str | None = None

    def __str__(self):
        name = f" ({self.property_name})" if self.property_name else ""
        text = f"TLC: {self.status.value}{name}"
        if self.reason:
            text += f" — {self.reason}"
        if self.counterexample:
            text += "\n" + str(self.counterexample)
        return text


def _replace_names(text, mapping):
    replacements = {}
    for category in ("variables", "values", "actions", "properties"):
        replacements.update(mapping[category])
    return re.sub(r"\b[A-Za-z][A-Za-z0-9_]*\b", lambda m: replacements.get(m[0], m[0]), text)


def parse_trace(output, mapping):
    # -tool decorates normal TLC messages with STARTMSG/ENDMSG records.
    lines = [line for line in output.splitlines() if not line.startswith("@!@!@")]
    states = []
    current_number, label, values = None, "", {}
    loop_start, stuttering = None, False

    def flush():
        nonlocal current_number, values
        if current_number is not None:
            if set(values) != set(mapping["variables"].values()):
                raise TLCError("Incomplete or unsupported TLC counterexample; see tlc.log")
            states.append(TraceState(current_number, dict(values), label))
            current_number, values = None, {}

    for line in lines:
        stripped = line.strip()
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
        assignment = re.match(r"^(?:/\\\s*)?(v\d+)\s*=\s*(\S+)\s*$", stripped)
        if assignment and current_number is not None:
            var, value = assignment.groups()
            if var not in mapping["variables"] or value not in mapping["values"]:
                raise TLCError("Unknown value in TLC counterexample; see tlc.log")
            values[mapping["variables"][var]] = mapping["values"][value]
    flush()
    if not states or [s.number for s in states] != list(range(1, len(states) + 1)):
        raise TLCError("Missing or malformed TLC counterexample; see tlc.log")
    if loop_start is not None and loop_start not in {s.number for s in states}:
        raise TLCError("Invalid counterexample loop target; see tlc.log")
    return Counterexample(tuple(states), loop_start, stuttering)


def classify(output, returncode, artifacts):
    violated = "Temporal properties were violated" in output
    if violated:
        trace = parse_trace(output, artifacts.compiled.mapping)
        if trace.loop_start is None:
            raise TLCError("Temporal counterexample has no loop; see tlc.log")
        properties = artifacts.compiled.mapping["properties"]
        # TLC may not identify which of multiple temporal properties failed.
        name = next(iter(properties.values())) if len(properties) == 1 else None
        return CheckResult(Status.Violated, artifacts, trace, name)
    if returncode == 0 and "Model checking completed. No error has been found." in output:
        return CheckResult(Status.Passed, artifacts)
    if "TLC was interrupted" in output or "TLC execution was canceled" in output:
        return CheckResult(Status.Incomplete, artifacts, reason="TLC was interrupted")
    raise TLCError(f"TLC did not produce a recognized verification result (exit {returncode}); "
                   f"see {artifacts.log}")


def _configuration(source):
    root = project_root(source)
    config = root / "pyproject.toml"
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8")) if config.is_file() else {}
        settings = data.get("tool", {}).get("pytla", {})
        if not isinstance(settings, dict):
            raise ConfigurationError("[tool.pytla] must be a TOML table")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Cannot read {config}: {exc}") from exc
    return root, settings


def _path(value, root, name):
    if not isinstance(value, (str, os.PathLike)) or not str(value):
        raise ConfigurationError(f"{name} must be a nonempty filesystem path")
    path = Path(value).expanduser()
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def resolve_tools(source, tlc_jar=None):
    root, settings = _configuration(source)
    java = shutil.which("java")
    if java is None:
        configured = settings.get("java")
        if configured is None:
            raise ConfigurationError("Java not found on PATH; set [tool.pytla].java in pyproject.toml")
        executable = _path(configured, root, "java")
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ConfigurationError(f"Configured Java is not executable: {executable}")
        java = str(executable)
    jar = tlc_jar if tlc_jar is not None else settings.get("tlc_jar")
    if jar is None:
        raise ConfigurationError("TLC is not configured; pass tlc_jar= or set [tool.pytla].tlc_jar. "
                                 "No Java or TLC is downloaded automatically.")
    # Explicit arguments are relative to the caller's cwd; config paths to project root.
    jar_path = _path(jar, Path.cwd() if tlc_jar is not None else root, "tlc_jar")
    if not jar_path.is_file():
        raise ConfigurationError(f"TLC JAR does not exist: {jar_path}")
    return java, jar_path


def check(spec, *, properties=(), tlc_jar=None, output_dir=None, module="Model",
          timeout=None, verbose=True):
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be positive or None")
    artifacts = export(spec, properties=properties, output_dir=output_dir, module=module)
    java, jar = resolve_tools(artifacts.compiled.source, tlc_jar)
    meta = tempfile.mkdtemp(prefix="states-", dir=artifacts.directory)
    command = [java, "-Xmx512m", "-cp", str(jar), "tlc2.TLC", "-tool", "-workers", "1",
               "-metadir", meta, "-config", artifacts.cfg.name, module]
    try:
        run = subprocess.run(command, cwd=artifacts.directory, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                             errors="replace", timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        artifacts.log.write_text(output, encoding="utf-8")
        result = CheckResult(Status.Incomplete, artifacts, reason=f"timeout after {timeout}s")
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
