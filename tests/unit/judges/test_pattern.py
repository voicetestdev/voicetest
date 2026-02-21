"""Tests for voicetest.judges.pattern module."""

import pytest

from voicetest.judges.pattern import compile_pattern


class TestFnmatchEngine:
    """Tests for the fnmatch pattern engine."""

    def test_wildcard_star(self):
        pattern = compile_pattern("*billing*")
        assert pattern.search("Ask about billing inquiry")
        assert not pattern.search("Ask about payment")

    def test_wildcard_question(self):
        pattern = compile_pattern("hel?o")
        assert pattern.search("say hello world")
        assert not pattern.search("say help world")

    def test_char_class(self):
        pattern = compile_pattern("REF-[A-Z]*")
        assert pattern.search("Your code is REF-ABC")
        assert not pattern.search("Your code is REF-123")

    def test_negated_char_class(self):
        pattern = compile_pattern("REF-[!0-9]*")
        assert pattern.search("code REF-ABC")
        assert not pattern.search("code REF-123")

    def test_case_insensitive(self):
        pattern = compile_pattern("*HELLO*")
        assert pattern.search("say hello to the user")

    def test_partial_match(self):
        """Patterns match anywhere in the text, not just the full string."""
        pattern = compile_pattern("*billing*")
        assert pattern.search("USER: I have a billing question\nASSISTANT: Sure!")

    def test_literal_characters(self):
        """Regex metacharacters are treated as literals."""
        pattern = compile_pattern("price is $100")
        assert pattern.search("the price is $100 total")

    def test_empty_pattern(self):
        pattern = compile_pattern("*")
        assert pattern.search("anything matches")
        assert pattern.search("")


class TestRe2Engine:
    """Tests for the re2 pattern engine (requires google-re2)."""

    @pytest.fixture(autouse=True)
    def _skip_without_re2(self):
        pytest.importorskip("re2", reason="google-re2 not installed")

    def test_regex_pattern(self):
        pattern = compile_pattern(r"REF-[A-Z0-9]+", engine="re2")
        assert pattern.search("Your code is REF-ABC123")

    def test_regex_no_match(self):
        pattern = compile_pattern(r"TICKET-\d+", engine="re2")
        assert not pattern.search("Your code is REF-ABC123")

    def test_case_insensitive(self):
        pattern = compile_pattern(r"hello", engine="re2")
        assert pattern.search("HELLO WORLD")


class TestRe2ImportError:
    """Test error handling when re2 is not installed."""

    def test_import_error_message(self, monkeypatch):
        """Attempting re2 engine without the package gives a clear error."""
        import importlib

        # Force re2 to be unavailable
        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else None

        def mock_import(name, *args, **kwargs):
            if name == "re2":
                raise ImportError("No module named 're2'")
            if original_import:
                return original_import(name, *args, **kwargs)
            return importlib.__import__(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        with pytest.raises(ImportError, match="google-re2 is required"):
            compile_pattern("test", engine="re2")
