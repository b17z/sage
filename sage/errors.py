"""Error handling and Result types for Sage.

Uses functional approach: errors as values, not exceptions.
Result types force explicit handling of both success and failure cases.
"""

from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True)
class SageError:
    """Immutable error information."""

    code: str
    message: str
    suggestion: str | None = None


@dataclass(frozen=True)
class Ok[T]:
    """Successful result."""

    value: T

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class Err[E]:
    """Failed result."""

    error: E

    @property
    def ok(self) -> bool:
        return False


type Result[T, E] = Ok[T] | Err[E]


# Constructors
def ok[T](value: T) -> Ok[T]:
    """Create a successful result."""
    return Ok(value)


def err[E](error: E) -> Err[E]:
    """Create a failed result."""
    return Err(error)


# Combinators
def unwrap[T, E](result: Result[T, E]) -> T:
    """Get value or raise. Use sparingly."""
    match result:
        case Ok(value):
            return value
        case Err(error):
            raise ValueError(f"Cannot unwrap error: {error}")


def unwrap_or[T, E](result: Result[T, E], default: T) -> T:
    """Get value or default."""
    match result:
        case Ok(value):
            return value
        case Err():
            return default


def map_result[T, U, E](result: Result[T, E], fn) -> Result[U, E]:
    """Map the value if successful."""
    match result:
        case Ok(value):
            return ok(fn(value))
        case Err() as e:
            return e


def map_error[T, E, F](result: Result[T, E], fn) -> Result[T, F]:
    """Map the error if failed."""
    match result:
        case Ok() as o:
            return o
        case Err(error):
            return err(fn(error))


# Common error constructors
def skill_not_found(skill_name: str, similar: list[str] | None = None) -> SageError:
    """Error for missing skill."""
    suggestion = f"Did you mean: {', '.join(similar)}?" if similar else "Use 'sage list' to see available skills."
    return SageError(
        code="skill_not_found",
        message=f"Skill '{skill_name}' not found",
        suggestion=suggestion,
    )


def skill_exists(skill_name: str) -> SageError:
    """Error for skill that already exists."""
    return SageError(
        code="skill_exists",
        message=f"Skill '{skill_name}' already exists",
        suggestion=f"Use 'sage context {skill_name}' to inspect it.",
    )


def api_key_missing() -> SageError:
    """Error for missing API key."""
    return SageError(
        code="api_key_missing",
        message="Anthropic API key not configured",
        suggestion="Run 'sage init' or set ANTHROPIC_API_KEY environment variable.",
    )


def api_error(message: str) -> SageError:
    """Error from API call."""
    return SageError(
        code="api_error",
        message=message,
    )


def file_error(path: str, message: str) -> SageError:
    """Error for file operations."""
    return SageError(
        code="file_error",
        message=f"{path}: {message}",
    )


def format_error(error: SageError) -> str:
    """Format error for display."""
    result = f"Error: {error.message}"
    if error.suggestion:
        result += f"\n  {error.suggestion}"
    return result
