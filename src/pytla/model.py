"""Declarations only: specification function bodies are never executed."""
from dataclasses import dataclass
from enum import Enum
from typing import Callable, get_type_hints


class SpecificationError(ValueError):
    """Invalid or unsupported source specification."""


class ConfigurationError(RuntimeError):
    """Java/TLC configuration is missing or invalid."""


class TLCError(RuntimeError):
    """TLC could not run or reported a tool/specification error."""


class UnconstrainedWarning(UserWarning):
    """An action may leave a next-state variable unspecified."""


@dataclass(frozen=True)
class Definition:
    fn: Callable
    kind: str

    @property
    def name(self):
        return self.fn.__name__


def initial(fn):
    return Definition(fn, "initial")


def action(fn):
    return Definition(fn, "action")


def temporal(fn):
    return Definition(fn, "temporal")


def state(cls):
    try:
        fields = get_type_hints(cls)
    except Exception as exc:
        raise SpecificationError(f"Cannot resolve state annotations: {exc}") from exc
    if not fields:
        raise SpecificationError("A state must declare at least one Enum field")
    for name, domain in fields.items():
        if not isinstance(domain, type) or not issubclass(domain, Enum) or not list(domain):
            raise SpecificationError(f"{name}: expected a nonempty Enum domain")
    cls.__pytla_fields__ = dict(fields)
    return cls


def _syntax_only(*args, **kwargs):
    raise SpecificationError("DSL operators may only occur in specification source")


def unchanged(*args):
    return _syntax_only(*args)


def unconstrained(*args):
    return _syntax_only(*args)


def leads_to(*args):
    return _syntax_only(*args)


def any_action(*actions):
    if not actions or any(not isinstance(a, Definition) or a.kind != "action" for a in actions):
        raise SpecificationError("any_action requires at least one @action")
    return tuple(actions)


@dataclass(frozen=True)
class WeakFairness:
    action: Definition


def weak_fairness(a):
    if not isinstance(a, Definition) or a.kind != "action":
        raise SpecificationError("weak_fairness requires an @action")
    return WeakFairness(a)


@dataclass(frozen=True)
class Specification:
    state: type
    init: Definition
    next: tuple[Definition, ...]
    fairness: tuple[WeakFairness, ...] = ()

    def __post_init__(self):
        if not hasattr(self.state, "__pytla_fields__"):
            raise SpecificationError("state must be an @state class")
        if not isinstance(self.init, Definition) or self.init.kind != "initial":
            raise SpecificationError("init must be an @initial definition")
        object.__setattr__(self, "next", tuple(self.next))
        object.__setattr__(self, "fairness", tuple(self.fairness))
        any_action(*self.next)
        if len({id(a) for a in self.next}) != len(self.next):
            raise SpecificationError("Duplicate next action")
        for fair in self.fairness:
            if not isinstance(fair, WeakFairness) or not any(fair.action is a for a in self.next):
                raise SpecificationError("Fairness must refer to an action in next")
