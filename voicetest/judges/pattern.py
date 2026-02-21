"""Pattern matching engine abstraction.

Supports two engines controlled by the pattern_engine run setting:

  "fnmatch" (default) — shell-style wildcards (*, ?, [abc]).
      Safe against ReDoS. No extra dependencies.

  "re2" — full regular expressions via google-re2 (linear-time guarantee).
      Requires: uv add voicetest[re2]

Both engines do case-insensitive, unanchored (partial) matching against
transcript text.
"""

import fnmatch
import re


def compile_pattern(pattern: str, engine: str = "fnmatch") -> re.Pattern:
    """Compile a user-supplied pattern into a regex Pattern object.

    For fnmatch: escapes regex metacharacters, then restores wildcard
    semantics (*, ?, []) so the result is a safe, non-backtracking regex.

    For re2: delegates to google-re2 which guarantees linear-time matching.

    Returns a compiled pattern with a .search() method.
    """
    if engine == "re2":
        return _compile_re2(pattern)
    return _compile_fnmatch(pattern)


def _compile_fnmatch(pattern: str) -> re.Pattern:
    """Convert a glob/wildcard pattern to a case-insensitive partial-match regex.

    fnmatch.translate() produces an anchored regex (\\A...\\Z). We strip the
    anchors so the pattern matches anywhere in the text, consistent with how
    re.search() behaves.
    """
    translated = fnmatch.translate(pattern)

    # fnmatch.translate wraps output in (?s:\\A...\\Z) — strip anchors
    # to allow partial matching
    if translated.startswith("(?s:") and translated.endswith(")\\Z"):
        inner = translated[4:-3]
        if inner.startswith("\\A"):
            inner = inner[2:]
        translated = inner
    elif translated.startswith("\\A") or translated.endswith("\\Z"):
        translated = translated.removeprefix("\\A").removesuffix("\\Z")

    return re.compile(translated, re.IGNORECASE)


def _compile_re2(pattern: str) -> re.Pattern:
    """Compile a regex pattern using google-re2 for linear-time matching.

    Uses inline (?i) flag for case-insensitivity since google-re2
    does not expose module-level flag constants like re.IGNORECASE.
    """
    try:
        import re2  # noqa:PLC0415
    except ImportError:
        raise ImportError(
            "google-re2 is required for pattern_engine='re2'. Install with: uv add voicetest[re2]"
        ) from None

    return re2.compile(f"(?i){pattern}")
