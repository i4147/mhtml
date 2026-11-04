"""CSS URL extraction, safe rewriting, import handling, and comment removal."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any, cast

import tinycss2
from tinycss2.ast import StringToken

from .config import ConverterConfig
from .parser import Resource, resolve_resource_url


class CSSProcessor:
    """Rewrite CSS asset references with tinycss2 while preserving valid syntax."""

    def __init__(self, config: ConverterConfig | None = None) -> None:
        """Create a CSS processor bound to a converter configuration."""
        self.config = config or ConverterConfig()

    def rewrite_css(
        self,
        content: str,
        base_url: str,
        resource_map: dict[str, Resource],
        depth: int = 0,
    ) -> str:
        """Resolve CSS ``url()`` and ``@import`` references against resources.

        Comments are removed when ``strip_css_comments`` is enabled. At or past
        ``max_import_depth``, imports are left as normalized references and are
        not expanded further.
        """
        if depth > self.config.max_import_depth:
            return content
        rules = tinycss2.parse_stylesheet(
            content,
            skip_comments=self.config.strip_css_comments,
            skip_whitespace=False,
        )
        self._rewrite_tokens(rules, base_url, resource_map, depth)
        result = cast(str, tinycss2.serialize(rules))
        if self.config.minify_css:
            result = self._conservative_minify(result)
        return result

    def extract_urls(self, content: str) -> set[str]:
        """Return URL tokens and string-form ``@import`` references in CSS."""
        rules = tinycss2.parse_stylesheet(
            content, skip_comments=True, skip_whitespace=False
        )
        urls: set[str] = set()
        self._collect_urls(rules, urls)
        return urls

    @staticmethod
    def parse_css(content: str) -> list[Any]:
        """Parse a stylesheet and expose tinycss2 error tokens for validation."""
        return cast(
            list[Any],
            tinycss2.parse_stylesheet(
                content, skip_comments=False, skip_whitespace=False
            ),
        )

    def _rewrite_tokens(
        self,
        tokens: list[Any],
        base_url: str,
        resource_map: dict[str, Resource],
        depth: int,
    ) -> None:
        """Mutate tinycss2 tokens recursively, rewriting nested URL values."""
        for token in tokens:
            token_type = getattr(token, "type", "")
            if token_type == "url":
                token.value = self._rewrite_url(token.value, base_url, resource_map)
                token.representation = self._url_representation(token.value)
            elif token_type == "function" and token.name.lower() == "url":
                url = self._function_url_value(token)
                rewritten = self._rewrite_url(url, base_url, resource_map)
                token.arguments = [
                    StringToken(
                        token.source_line,
                        token.source_column,
                        rewritten,
                        self._string_representation(rewritten),
                    )
                ]
            elif token_type == "at-rule":
                if token.lower_at_keyword == "import":
                    self._rewrite_import(token, base_url, resource_map, depth)
                else:
                    self._rewrite_tokens(token.prelude, base_url, resource_map, depth)
                if token.content is not None:
                    self._rewrite_tokens(token.content, base_url, resource_map, depth)
            else:
                nested = getattr(token, "content", None)
                if isinstance(nested, list):
                    self._rewrite_tokens(nested, base_url, resource_map, depth)
                prelude = getattr(token, "prelude", None)
                if isinstance(prelude, list):
                    self._rewrite_tokens(prelude, base_url, resource_map, depth)
                arguments = getattr(token, "arguments", None)
                if isinstance(arguments, list) and token_type != "function":
                    self._rewrite_tokens(arguments, base_url, resource_map, depth)

    def _rewrite_import(
        self,
        token: Any,
        base_url: str,
        resource_map: dict[str, Resource],
        depth: int,
    ) -> None:
        """Rewrite the first URL in an ``@import`` prelude."""
        if depth >= self.config.max_import_depth:
            return
        for item in token.prelude:
            if item.type in {"whitespace", "comment"}:
                continue
            if item.type == "string":
                rewritten = self._rewrite_url(item.value, base_url, resource_map)
                item.value = rewritten
                item.representation = self._string_representation(rewritten)
            elif item.type == "url":
                item.value = self._rewrite_url(item.value, base_url, resource_map)
                item.representation = self._url_representation(item.value)
            elif item.type == "function" and item.name.lower() == "url":
                url = self._function_url_value(item)
                rewritten = self._rewrite_url(url, base_url, resource_map)
                item.arguments = [
                    StringToken(
                        item.source_line,
                        item.source_column,
                        rewritten,
                        self._string_representation(rewritten),
                    )
                ]
            break

    def _rewrite_url(
        self,
        url: str,
        base_url: str,
        resource_map: dict[str, Resource],
    ) -> str:
        """Return an inlined URI or normalized safe URL for one asset reference."""
        value = url.strip().strip("\"'")
        if not value or value.lower().startswith("data:"):
            return value
        scheme = urllib.parse.urlsplit(value).scheme.lower()
        if scheme in {"javascript", "vbscript"}:
            return ""
        return resolve_resource_url(value, base_url, resource_map, self.config)

    @staticmethod
    def _function_url_value(token: Any) -> str:
        """Extract the unquoted URL from a parsed ``url(...)`` function token."""
        if len(token.arguments) == 1 and hasattr(token.arguments[0], "value"):
            return str(token.arguments[0].value)
        serialized = cast(str, tinycss2.serialize(token.arguments))
        return serialized.strip().strip("\"'")

    @staticmethod
    def _string_representation(value: str) -> str:
        """Quote a CSS string, escaping delimiters and backslashes."""
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\a ")
        return f'"{escaped}"'

    @classmethod
    def _url_representation(cls, value: str) -> str:
        """Serialize a URL token without allowing its value to break CSS syntax."""
        return f"url({cls._string_representation(value)})"

    def _collect_urls(self, tokens: list[Any], urls: set[str]) -> None:
        """Walk a tinycss2 token tree and collect URLs and import strings."""
        for token in tokens:
            self._collect_token_urls(token, urls)

    def _collect_token_urls(self, token: Any, urls: set[str]) -> None:
        """Collect direct URL values and recursively visit a token's children."""
        token_type = getattr(token, "type", "")
        if token_type == "url" and token.value:
            urls.add(token.value)
        elif token_type == "function" and token.name.lower() == "url":
            url = self._function_url_value(token)
            if url:
                urls.add(url)
        elif token_type == "at-rule" and token.lower_at_keyword == "import":
            self._collect_import_url(token.prelude, urls)
        self._collect_nested_urls(token, urls)

    def _collect_import_url(self, prelude: list[Any], urls: set[str]) -> None:
        """Collect the URL-like first item of an ``@import`` prelude."""
        for item in prelude:
            if item.type in {"whitespace", "comment"}:
                continue
            if item.type in {"string", "url"} and item.value:
                urls.add(item.value)
            elif item.type == "function" and item.name.lower() == "url":
                url = self._function_url_value(item)
                if url:
                    urls.add(url)
            return

    def _collect_nested_urls(self, token: Any, urls: set[str]) -> None:
        """Recursively inspect nested component values, rules, and function args."""
        for name in ("content", "prelude", "arguments"):
            nested = getattr(token, name, None)
            if isinstance(nested, list):
                self._collect_urls(nested, urls)

    def _conservative_minify(self, content: str) -> str:
        """Reduce redundant spaces only around punctuation safe in CSS syntax."""
        result = re.sub(r"\s*([{}:;,>])\s*", r"\1", content)
        return result.strip()

    def _rewrite_with_regex_fallback(
        self,
        content: str,
        base_url: str,
        resource_map: dict[str, Resource],
    ) -> str:
        """Compatibility helper for consumers that need a regex-only fallback."""
        url_pattern = re.compile(
            r"url\(\s*(?P<quote>[\"']?)(?P<url>[^)\"']+)(?P=quote)\s*\)",
            re.IGNORECASE,
        )

        def replace(match: re.Match[str]) -> str:
            original = match.group(0)
            rewritten = self._rewrite_url(match.group("url"), base_url, resource_map)
            return (
                f"url({self._string_representation(rewritten)})"
                if rewritten
                else original
            )

        stripped = (
            re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
            if self.config.strip_css_comments
            else content
        )
        return url_pattern.sub(replace, stripped)


__all__ = ["CSSProcessor"]
