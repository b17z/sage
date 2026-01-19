"""Tests for error handling and Result types."""

import pytest

from sage.errors import (
    Err,
    Ok,
    Result,
    SageError,
    api_error,
    api_key_missing,
    err,
    file_error,
    format_error,
    map_error,
    map_result,
    ok,
    skill_exists,
    skill_not_found,
    unwrap,
    unwrap_or,
)


class TestSageError:
    """Tests for SageError dataclass."""

    def test_error_with_all_fields(self):
        """SageError stores all fields."""
        error = SageError(
            code="test_error",
            message="Test message",
            suggestion="Try this instead",
            context={"key": "value"},
        )
        assert error.code == "test_error"
        assert error.message == "Test message"
        assert error.suggestion == "Try this instead"
        assert error.context == {"key": "value"}

    def test_error_with_defaults(self):
        """SageError has sensible defaults."""
        error = SageError(code="test", message="msg")
        assert error.suggestion is None
        assert error.context is None

    def test_error_is_frozen(self):
        """SageError is immutable."""
        error = SageError(code="test", message="msg")
        with pytest.raises(AttributeError):
            error.code = "changed"


class TestOkResult:
    """Tests for Ok result type."""

    def test_ok_stores_value(self):
        """Ok stores the value."""
        result = Ok(42)
        assert result.value == 42

    def test_ok_property(self):
        """ok property returns True."""
        result = Ok("value")
        assert result.ok is True

    def test_is_ok(self):
        """is_ok returns True."""
        result = Ok("value")
        assert result.is_ok() is True

    def test_is_err(self):
        """is_err returns False."""
        result = Ok("value")
        assert result.is_err() is False

    def test_unwrap_returns_value(self):
        """unwrap returns the value."""
        result = Ok("hello")
        assert result.unwrap() == "hello"

    def test_unwrap_err_raises(self):
        """unwrap_err raises on Ok."""
        result = Ok("value")
        with pytest.raises(ValueError, match="Cannot unwrap_err on Ok"):
            result.unwrap_err()

    def test_ok_is_frozen(self):
        """Ok is immutable."""
        result = Ok(42)
        with pytest.raises(AttributeError):
            result.value = 99


class TestErrResult:
    """Tests for Err result type."""

    def test_err_stores_error(self):
        """Err stores the error."""
        error = SageError(code="test", message="msg")
        result = Err(error)
        assert result.error == error

    def test_ok_property(self):
        """ok property returns False."""
        result = Err("error")
        assert result.ok is False

    def test_is_ok(self):
        """is_ok returns False."""
        result = Err("error")
        assert result.is_ok() is False

    def test_is_err(self):
        """is_err returns True."""
        result = Err("error")
        assert result.is_err() is True

    def test_unwrap_raises(self):
        """unwrap raises on Err."""
        result = Err("some error")
        with pytest.raises(ValueError, match="Cannot unwrap on Err"):
            result.unwrap()

    def test_unwrap_err_returns_error(self):
        """unwrap_err returns the error."""
        error = SageError(code="test", message="msg")
        result = Err(error)
        assert result.unwrap_err() == error

    def test_err_is_frozen(self):
        """Err is immutable."""
        result = Err("error")
        with pytest.raises(AttributeError):
            result.error = "changed"


class TestConstructors:
    """Tests for ok() and err() constructors."""

    def test_ok_constructor(self):
        """ok() creates Ok result."""
        result = ok(42)
        assert isinstance(result, Ok)
        assert result.value == 42

    def test_err_constructor(self):
        """err() creates Err result."""
        error = SageError(code="test", message="msg")
        result = err(error)
        assert isinstance(result, Err)
        assert result.error == error


class TestCombinators:
    """Tests for Result combinators."""

    def test_unwrap_on_ok(self):
        """unwrap returns value from Ok."""
        result: Result[int, str] = ok(42)
        assert unwrap(result) == 42

    def test_unwrap_on_err(self):
        """unwrap raises on Err."""
        result: Result[int, str] = err("error")
        with pytest.raises(ValueError, match="Cannot unwrap error"):
            unwrap(result)

    def test_unwrap_or_on_ok(self):
        """unwrap_or returns value from Ok."""
        result: Result[int, str] = ok(42)
        assert unwrap_or(result, 0) == 42

    def test_unwrap_or_on_err(self):
        """unwrap_or returns default on Err."""
        result: Result[int, str] = err("error")
        assert unwrap_or(result, 99) == 99

    def test_map_result_on_ok(self):
        """map_result applies function to Ok value."""
        result: Result[int, str] = ok(10)
        mapped = map_result(result, lambda x: x * 2)
        assert mapped.is_ok()
        assert mapped.unwrap() == 20

    def test_map_result_on_err(self):
        """map_result passes through Err."""
        result: Result[int, str] = err("error")
        mapped = map_result(result, lambda x: x * 2)
        assert mapped.is_err()
        assert mapped.unwrap_err() == "error"

    def test_map_error_on_ok(self):
        """map_error passes through Ok."""
        result: Result[int, str] = ok(42)
        mapped = map_error(result, lambda e: f"wrapped: {e}")
        assert mapped.is_ok()
        assert mapped.unwrap() == 42

    def test_map_error_on_err(self):
        """map_error applies function to Err."""
        result: Result[int, str] = err("error")
        mapped = map_error(result, lambda e: f"wrapped: {e}")
        assert mapped.is_err()
        assert mapped.unwrap_err() == "wrapped: error"


class TestErrorConstructors:
    """Tests for common error constructors."""

    def test_skill_not_found_basic(self):
        """skill_not_found creates proper error."""
        error = skill_not_found("my-skill")
        assert error.code == "skill_not_found"
        assert "my-skill" in error.message
        assert "sage list" in error.suggestion

    def test_skill_not_found_with_similar(self):
        """skill_not_found suggests similar skills."""
        error = skill_not_found("my-skil", similar=["my-skill", "my-skill-2"])
        assert "Did you mean" in error.suggestion
        assert "my-skill" in error.suggestion

    def test_skill_exists(self):
        """skill_exists creates proper error."""
        error = skill_exists("my-skill")
        assert error.code == "skill_exists"
        assert "my-skill" in error.message
        assert "sage context" in error.suggestion

    def test_api_key_missing(self):
        """api_key_missing creates proper error."""
        error = api_key_missing()
        assert error.code == "api_key_missing"
        assert "API key" in error.message
        assert "sage init" in error.suggestion or "ANTHROPIC_API_KEY" in error.suggestion

    def test_api_error(self):
        """api_error creates proper error."""
        error = api_error("Rate limited")
        assert error.code == "api_error"
        assert error.message == "Rate limited"
        assert error.suggestion is None

    def test_file_error(self):
        """file_error creates proper error."""
        error = file_error("/path/to/file", "Permission denied")
        assert error.code == "file_error"
        assert "/path/to/file" in error.message
        assert "Permission denied" in error.message


class TestFormatError:
    """Tests for format_error function."""

    def test_format_basic_error(self):
        """format_error formats message only."""
        error = SageError(code="test", message="Something went wrong")
        formatted = format_error(error)
        assert "Error: Something went wrong" in formatted
        assert "\n" not in formatted  # No suggestion line

    def test_format_error_with_suggestion(self):
        """format_error includes suggestion."""
        error = SageError(
            code="test",
            message="Something went wrong",
            suggestion="Try again later",
        )
        formatted = format_error(error)
        assert "Error: Something went wrong" in formatted
        assert "Try again later" in formatted
        assert "\n" in formatted  # Has suggestion on new line
