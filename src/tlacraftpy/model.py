"""Declare state domains, specification expressions, actions, and fairness."""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, get_type_hints


class SpecificationError(ValueError):
    """Report an error in a declaration or specification expression.

    Args:
        *args: Error message and context, stored in ``args`` by ``ValueError``.

    Source compilation includes the function name, filename, and line number
    in the message when that information is available.
    """


class ConfigurationError(RuntimeError):
    """Report a problem with Java, the TLC JAR, or project configuration.

    Args:
        *args: Error message and context, stored in ``args`` by ``RuntimeError``.

    Raised while resolving ``[tool.tlacraftpy]`` settings and executable paths.
    """


class TLCError(RuntimeError):
    """Report a TLC launch, execution, or output interpretation error.

    Args:
        *args: Error message and context, stored in ``args`` by ``RuntimeError``.

    The message identifies the TLC log when an invocation has produced one.
    Property violations and time limits are represented by ``CheckResult``.
    """


class UnconstrainedWarning(UserWarning):
    """Identify an action field whose next-state value may vary freely.

    Args:
        *args: Diagnostic message and context, stored in ``args`` by ``UserWarning``.

    Compilation emits this warning for fields with an implicit next-state
    choice. ``unchanged`` and ``unconstrained`` document the intended choice.
    """


@dataclass(frozen=True)
class Definition:
    """Store a specification function and its expression category.

    Args:
        fn: Python function whose source supplies the specification expression.
        kind: Expression category: ``"initial"``, ``"action"``, or ``"temporal"``.

    Decorators create these records. ``compile_spec`` validates the function's
    source and raises ``SpecificationError`` for invalid definitions.
    """

    fn: Callable
    kind: str

    @property
    def name(self):
        """Return the registered Python function's name.

        Returns:
            str: Function name used in diagnostics and generated name mappings.
        """
        return self.fn.__name__


def initial(fn):
    """Register a predicate describing the allowed initial states.

    Args:
        fn: Function with one current-state parameter and a single Boolean
            return expression, defined in a ``.py`` file.

    Returns:
        Definition: Initial-state predicate for ``Specification.init``.

    Source validation occurs in ``compile_spec``, ``export``, or ``check``;
    those calls raise ``SpecificationError`` for an invalid predicate.

    Examples:
        >>> @initial
        ... def init(s):
        ...     return s.phase == Phase.Idle
    """
    return Definition(fn, "initial")


def action(fn):
    """Register a relation between the current state and the next state.

    Args:
        fn: Function with two positional parameters, current state first and
            next state second, and a single Boolean return expression.
            The function must be defined in a ``.py`` file.

    Returns:
        Definition: Action for ``any_action`` and ``weak_fairness``.

    Source validation occurs in ``compile_spec``, ``export``, or ``check``;
    those calls raise ``SpecificationError`` for an invalid action.

    Examples:
        >>> @action
        ... def respond(s, t):
        ...     return s.phase == Phase.Requested and t.phase == Phase.Responded
    """
    return Definition(fn, "action")


def temporal(fn):
    """Register a property about an infinite sequence of states.

    Args:
        fn: Function with one current-state parameter whose return expression
            contains ``leads_to``. The function must be defined in a ``.py`` file.

    Returns:
        Definition: Temporal property accepted by ``properties`` in compilation,
        export, and verification calls.

    Source validation occurs in ``compile_spec``, ``export``, or ``check``;
    those calls raise ``SpecificationError`` for an invalid temporal property.

    Examples:
        >>> @temporal
        ... def responds(s):
        ...     return leads_to(s.phase == Phase.Requested, s.phase == Phase.Responded)
    """
    return Definition(fn, "temporal")


def state(cls):
    """Declare state fields and their finite Enum domains.

    Args:
        cls: Class whose annotated fields each name a nonempty ``Enum`` type.
            Each Enum member represents a distinct specification value.

    Returns:
        type: The class, annotated with the field domains for compilation.

    Raises:
        SpecificationError: If annotations cannot be resolved, there are no
            annotated fields, or a field's domain is not a nonempty Enum.

    Examples:
        >>> @state
        ... class State:
        ...     phase: Phase
    """
    try:
        fields = get_type_hints(cls)
    except Exception as exc:
        raise SpecificationError(f"Cannot resolve state annotations: {exc}") from exc
    if not fields:
        raise SpecificationError("A state must declare at least one Enum field")
    for name, domain in fields.items():
        if (
            not isinstance(domain, type)
            or not issubclass(domain, Enum)
            or not list(domain)
        ):
            raise SpecificationError(f"{name}: expected a nonempty Enum domain")
    cls.__tlacraftpy_fields__ = dict(fields)
    return cls


def _syntax_only(*args, **kwargs):
    raise SpecificationError("DSL operators may only occur in specification source")


def unchanged(*args):
    """Express that an action preserves a current-state field's value.

    The compiler interprets this call in an ``@action`` return expression as
    equality between the field's current and next values.

    Args:
        *args: Exactly one current-state field reference, such as ``s.phase``.

    Raises:
        SpecificationError: If called directly as Python code. Compilation also
            raises this exception for an invalid argument or expression context.

    Examples:
        >>> @action
        ... def wait(s, t):
        ...     return unchanged(s.phase)
    """
    return _syntax_only(*args)


def unconstrained(*args):
    """Express an intentional choice from a field's entire next-state domain.

    In an ``@action`` return expression, this marker contributes ``TRUE`` and
    suppresses the implicit-choice warning for the specified field. The Enum
    domain still bounds the possible values.

    Args:
        *args: Exactly one current-state field reference, such as ``s.phase``.

    Raises:
        SpecificationError: If called directly as Python code. Compilation also
            raises this exception for an invalid argument or expression context.

    Examples:
        >>> @action
        ... def choose_phase(s, t):
        ...     return unconstrained(s.phase)
    """
    return _syntax_only(*args)


def leads_to(*args):
    """Express that each occurrence of a condition eventually gets a response.

    In ``@temporal`` source, ``leads_to(P, Q)`` means that whenever ``P`` holds,
    ``Q`` holds at the same position or at some later position in the execution.

    Args:
        *args: Exactly two Boolean state predicates: the triggering condition
            ``P`` followed by the eventual condition ``Q``.

    Raises:
        SpecificationError: If called directly as Python code. Compilation also
            raises this exception for arguments other than two state predicates
            or for use outside a temporal property.
    """
    return _syntax_only(*args)


def any_action(*actions):
    """Combine actions as alternatives for the next state.

    Args:
        *actions: One or more definitions produced by ``@action``.

    Returns:
        tuple[Definition, ...]: Actions whose relations are combined by logical
        disjunction when compiling ``Specification.next``.

    Raises:
        SpecificationError: If no actions are provided or an argument is not an
            action definition.
    """
    if not actions or any(
        not isinstance(a, Definition) or a.kind != "action" for a in actions
    ):
        raise SpecificationError("any_action requires at least one @action")
    return tuple(actions)


@dataclass(frozen=True)
class WeakFairness:
    """Represent weak fairness for a particular action.

    Args:
        action: Definition of the action subject to weak fairness. Use
            ``weak_fairness`` to validate the definition when constructing it.

    ``Specification`` raises ``SpecificationError`` if this action is not one of
    its next-state alternatives.
    """

    action: Definition


def weak_fairness(a):
    """Require progress for a continuously enabled non-stuttering action.

    If, from some point on, the action remains enabled for a state-changing
    step, such steps must occur infinitely often. Compilation uses TLA+'s
    ``WF_vars`` operator over the complete state-variable tuple.

    Args:
        a: Action definition produced by ``@action``.

    Returns:
        WeakFairness: Fairness assumption for ``Specification.fairness``.

    Raises:
        SpecificationError: If ``a`` is not an action definition.
    """
    if not isinstance(a, Definition) or a.kind != "action":
        raise SpecificationError("weak_fairness requires an @action")
    return WeakFairness(a)


@dataclass(frozen=True)
class Specification:
    """Describe initial states, next-state alternatives, and fairness assumptions.

    Args:
        state: Class decorated with ``@state`` that defines the state fields.
        init: Definition produced by ``@initial`` for the initial-state predicate.
        next: Iterable containing at least one distinct action definition,
            normally built with ``any_action``. Stored as a tuple.
        fairness: Iterable of ``WeakFairness`` assumptions referring to the same
            action objects as ``next``. Defaults to an empty tuple.

    Raises:
        SpecificationError: If declarations have the wrong category, actions
            repeat, or a fairness assumption refers to an action outside ``next``.
        TypeError: If ``next`` or ``fairness`` cannot be converted to a tuple.

    Compilation allows stuttering steps that preserve all fields and restricts
    each field to its declared Enum domain.
    """

    state: type
    init: Definition
    next: tuple[Definition, ...]
    fairness: tuple[WeakFairness, ...] = ()

    def __post_init__(self):
        """Normalize iterables and validate the registered declarations.

        Raises:
            SpecificationError: If a declaration category, action identity, or
                fairness target is invalid.
            TypeError: If next-state alternatives or fairness assumptions cannot
                be converted to tuples.
        """
        if not hasattr(self.state, "__tlacraftpy_fields__"):
            raise SpecificationError("state must be an @state class")
        if not isinstance(self.init, Definition) or self.init.kind != "initial":
            raise SpecificationError("init must be an @initial definition")
        object.__setattr__(self, "next", tuple(self.next))
        object.__setattr__(self, "fairness", tuple(self.fairness))
        any_action(*self.next)
        if len({id(a) for a in self.next}) != len(self.next):
            raise SpecificationError("Duplicate next action")
        for fair in self.fairness:
            if not isinstance(fair, WeakFairness) or not any(
                fair.action is a for a in self.next
            ):
                raise SpecificationError("Fairness must refer to an action in next")
