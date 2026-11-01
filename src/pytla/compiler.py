"""Translate specification ASTs into typed expressions and TLA+."""

import ast
import inspect
import json
import re
import textwrap
import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .model import (
    Definition,
    Specification,
    SpecificationError,
    UnconstrainedWarning,
    leads_to,
    unchanged,
    unconstrained,
)


@dataclass(frozen=True)
class Expression:
    text: str
    type: object
    level: int = 0  # constant=0, state=1, action=2, temporal=3
    covered: frozenset[str] = frozenset()


class Parser:
    def __init__(self, definition, fields, variables, atoms):
        self.definition = definition
        self.fields = fields
        self.variables = variables
        self.atoms = atoms
        fn = definition.fn
        self.filename = inspect.getsourcefile(fn)
        if (
            not self.filename
            or Path(self.filename).suffix != ".py"
            or not Path(self.filename).is_file()
        ):
            raise SpecificationError(f"{definition.name}: source must be in a .py file")
        try:
            source, self.start = inspect.getsourcelines(fn)
            tree = ast.parse(textwrap.dedent("".join(source)))
        except (OSError, TypeError, SyntaxError) as exc:
            raise SpecificationError(
                f"{definition.name}: source unavailable: {exc}"
            ) from exc
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            raise SpecificationError(
                f"{definition.name}: expected a synchronous function"
            )
        self.node = tree.body[0]
        args = self.node.args
        count = 2 if definition.kind == "action" else 1
        if (
            len(args.posonlyargs) + len(args.args) != count
            or args.vararg
            or args.kwarg
            or args.kwonlyargs
            or args.defaults
        ):
            self.fail(
                self.node, f"expected exactly {count} positional state parameter(s)"
            )
        self.params = [a.arg for a in args.posonlyargs + args.args]
        self.env = dict(fn.__globals__)
        try:
            self.env.update(inspect.getclosurevars(fn).nonlocals)
        except TypeError:
            pass
        body = self.node.body
        if (
            len(body) != 1
            or not isinstance(body[0], ast.Return)
            or body[0].value is None
        ):
            self.fail(self.node, "only a single return expression is supported")
        self.body = body[0].value

    def fail(self, node, message):
        line = self.start + getattr(node, "lineno", 1) - 1
        raise SpecificationError(
            f"{self.filename}:{line}: {self.definition.name}: {message}"
        )

    def field(self, node, current_only=False):
        if (
            not isinstance(node, ast.Attribute)
            or not isinstance(node.value, ast.Name)
            or node.value.id not in self.params
        ):
            self.fail(node, "expected a state field such as s.phase")
        if node.attr not in self.fields:
            self.fail(node, f"unknown state field {node.attr!r}")
        index = self.params.index(node.value.id)
        if current_only and index != 0:
            self.fail(node, "expected a current-state field")
        return node.attr, index

    def boolean(self, expr, node):
        if expr.type is not bool:
            self.fail(node, "expected a Boolean expression")

    def parse(self):
        expr = self.expr(self.body)
        self.boolean(expr, self.body)
        if self.definition.kind == "temporal" and expr.level != 3:
            self.fail(self.body, "@temporal requires a temporal expression (leads_to)")
        return expr

    def expr(self, node):
        if isinstance(node, ast.Constant) and type(node.value) is bool:
            return Expression("TRUE" if node.value else "FALSE", bool)
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id in self.params:
                name, index = self.field(node)
                return Expression(
                    self.variables[name] + ("'" if index else ""),
                    self.fields[name],
                    2 if index else 1,
                    frozenset({name}) if index else frozenset(),
                )
            if isinstance(node.value, ast.Name):
                enum = self.env.get(node.value.id)
                if isinstance(enum, type) and issubclass(enum, Enum):
                    member = enum.__members__.get(node.attr)
                    if member is not None and (enum, member.name) in self.atoms:
                        return Expression(self.atoms[enum, member.name], enum)
            self.fail(node, "expected a state field or a declared Enum member")
        if isinstance(node, ast.Compare):
            values = [self.expr(n) for n in [node.left, *node.comparators]]
            pieces = []
            for left, op, right in zip(values, node.ops, values[1:]):
                if left.type is not right.type:
                    self.fail(node, "comparison requires values from the same domain")
                if not isinstance(op, (ast.Eq, ast.NotEq)):
                    self.fail(node, "only == and != comparisons are supported")
                if max(left.level, right.level) == 3:
                    self.fail(node, "temporal expressions cannot be compared")
                operator = "=" if isinstance(op, ast.Eq) else "#"
                pieces.append(f"({left.text} {operator} {right.text})")
            return Expression(
                "(" + " /\\ ".join(pieces) + ")",
                bool,
                max(v.level for v in values),
                frozenset().union(*(v.covered for v in values)),
            )
        if isinstance(node, ast.BoolOp):
            values = [self.expr(n) for n in node.values]
            for value in values:
                self.boolean(value, node)
            if isinstance(node.op, ast.And):
                operator = " /\\ "
                covered = frozenset().union(*(v.covered for v in values))
            else:
                operator = " \\/ "
                covered = values[0].covered.intersection(
                    *(v.covered for v in values[1:])
                )
            return Expression(
                "(" + operator.join(v.text for v in values) + ")",
                bool,
                max(v.level for v in values),
                covered,
            )
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            value = self.expr(node.operand)
            self.boolean(value, node)
            return Expression(f"~({value.text})", bool, value.level, value.covered)
        if isinstance(node, ast.Call):
            operator = (
                self.env.get(node.func.id)
                if isinstance(node.func, ast.Name) and node.func.id not in self.params
                else None
            )
            if node.keywords:
                self.fail(
                    node, "keyword arguments are not supported in DSL expressions"
                )
            if operator is leads_to:
                if self.definition.kind != "temporal" or len(node.args) != 2:
                    self.fail(
                        node, "leads_to requires two state predicates in @temporal"
                    )
                left, right = [self.expr(n) for n in node.args]
                for value in (left, right):
                    self.boolean(value, node)
                    if value.level > 1:
                        self.fail(node, "leads_to arguments must be state predicates")
                return Expression(f"({left.text} ~> {right.text})", bool, 3)
            if operator is unchanged or operator is unconstrained:
                if self.definition.kind != "action" or len(node.args) != 1:
                    self.fail(
                        node, "unchanged/unconstrained requires one field in @action"
                    )
                name, _ = self.field(node.args[0], current_only=True)
                text = (
                    f"UNCHANGED {self.variables[name]}"
                    if operator is unchanged
                    else "TRUE"
                )
                return Expression(f"({text})", bool, 2, frozenset({name}))
            self.fail(
                node, "unsupported call (only declared DSL operators are allowed)"
            )
        self.fail(node, f"unsupported syntax: {type(node).__name__}")


@dataclass(frozen=True)
class Compiled:
    module: str
    tla: str
    cfg: str
    mapping: dict
    source: Path


@dataclass(frozen=True)
class Artifacts:
    directory: Path
    tla: Path
    cfg: Path
    mapping: Path
    log: Path
    compiled: Compiled


def compile_spec(spec: Specification, *, properties=(), module="Model"):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", module):
        raise SpecificationError("module must be an ASCII TLA+ identifier")
    properties = tuple(properties)
    if any(not isinstance(p, Definition) or p.kind != "temporal" for p in properties):
        raise SpecificationError("properties must be @temporal definitions")
    fields = spec.state.__pytla_fields__
    variables = {name: f"v{i}" for i, name in enumerate(fields)}
    domains = list(dict.fromkeys(fields.values()))
    atoms = {
        (domain, member.name): f"E{i}M{j}"
        for i, domain in enumerate(domains)
        for j, member in enumerate(domain)
    }
    init_parser = Parser(spec.init, fields, variables, atoms)
    init = init_parser.parse()
    action_exprs = []
    for definition in spec.next:
        parser = Parser(definition, fields, variables, atoms)
        expression = parser.parse()
        for name in fields:
            if name in expression.covered:
                continue
            warnings.warn_explicit(
                f"{definition.name}: next-state field {name!r} may be unconstrained; "
                f"use unchanged({parser.params[0]}.{name}) or "
                f"unconstrained({parser.params[0]}.{name}) to document intent",
                UnconstrainedWarning,
                parser.filename,
                parser.start + parser.body.lineno - 1,
            )
        action_exprs.append(expression)
    prop_exprs = [Parser(p, fields, variables, atoms).parse() for p in properties]
    type_ok = " /\\ ".join(
        f"({variables[name]} \\in {{{', '.join(atoms[domain, m.name] for m in domain)}}})"
        for name, domain in fields.items()
    )
    next_domains = " /\\ ".join(
        f"({variables[name]}' \\in {{{', '.join(atoms[domain, m.name] for m in domain)}}})"
        for name, domain in fields.items()
    )
    lines = [
        f"---- MODULE {module} ----",
        "",
        "CONSTANTS " + ", ".join(atoms.values()),
        "VARIABLES " + ", ".join(variables.values()),
        "",
        "vars == <<" + ", ".join(variables.values()) + ">>",
        f"TypeOK == {type_ok}",
        f"Init == TypeOK /\\ {init.text}",
        "",
    ]
    for i, (definition, expression) in enumerate(zip(spec.next, action_exprs)):
        lines.extend(
            [
                f"\\* Python action: {definition.name}",
                f"A{i} == {next_domains} /\\ {expression.text}",
                "",
            ]
        )
    lines.append("Next == " + " \\/ ".join(f"A{i}" for i in range(len(spec.next))))
    spec_text = "Init /\\ [][Next]_vars"
    for fair in spec.fairness:
        index = next(i for i, a in enumerate(spec.next) if a is fair.action)
        spec_text += f" /\\ WF_vars(A{index})"
    lines.extend([f"Spec == {spec_text}", ""])
    for i, (prop, expression) in enumerate(zip(properties, prop_exprs)):
        lines.extend(
            [f"\\* Python property: {prop.name}", f"P{i} == {expression.text}", ""]
        )
    lines.append("====")
    cfg = ["SPECIFICATION Spec", "CHECK_DEADLOCK FALSE", "CONSTANTS"]
    cfg.extend(f"    {atom} = {atom}" for atom in atoms.values())
    if properties:
        cfg.append("PROPERTIES")
        cfg.extend(f"    P{i}" for i in range(len(properties)))
    mapping = {
        "variables": {symbol: name for name, symbol in variables.items()},
        "values": {
            symbol: f"{domain.__name__}.{name}"
            for (domain, name), symbol in atoms.items()
        },
        "actions": {f"A{i}": a.name for i, a in enumerate(spec.next)},
        "properties": {f"P{i}": p.name for i, p in enumerate(properties)},
    }
    return Compiled(
        module,
        "\n".join(lines) + "\n",
        "\n".join(cfg) + "\n",
        mapping,
        Path(init_parser.filename).resolve(),
    )


def project_root(source: Path):
    for directory in source.parent, *source.parent.parents:
        if (directory / "pyproject.toml").is_file():
            return directory
    return source.parent


def export(spec, *, properties=(), output_dir=None, module="Model"):
    compiled = compile_spec(spec, properties=properties, module=module)
    directory = (
        Path(output_dir)
        if output_dir is not None
        else project_root(compiled.source) / ".pytla" / compiled.source.stem
    ).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    tla, cfg = directory / f"{module}.tla", directory / f"{module}.cfg"
    mapping = directory / "mapping.json"
    tla.write_text(compiled.tla, encoding="utf-8")
    cfg.write_text(compiled.cfg, encoding="utf-8")
    mapping.write_text(
        json.dumps(compiled.mapping, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return Artifacts(directory, tla, cfg, mapping, directory / "tlc.log", compiled)
