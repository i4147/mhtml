"""HTML tree parsing, MIME asset rewriting, and security sanitization."""

from __future__ import annotations

import html as html_stdlib
import re
import urllib.parse
from typing import Any, ClassVar, cast

from lxml import etree
from lxml import html as lxml_html
from lxml_html_clean import Cleaner

from .config import ConverterConfig
from .css_processor import CSSProcessor
from .parser import Resource, resolve_resource_url

_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_SAFE_EXTRA_ATTRIBUTES = frozenset(
    {
        "style",
        "srcset",
        "sizes",
        "loading",
        "decoding",
        "fetchpriority",
        "crossorigin",
        "integrity",
        "referrerpolicy",
        "download",
        "poster",
        "background",
        "data",
        "form",
        "formaction",
        "formenctype",
        "formmethod",
        "formnovalidate",
        "formtarget",
        "placeholder",
        "pattern",
        "minlength",
        "maxlength",
        "autocomplete",
        "autofocus",
        "required",
        "multiple",
        "novalidate",
        "step",
        "min",
        "max",
        "controls",
        "loop",
        "muted",
        "autoplay",
        "preload",
        "sandbox",
        "allowfullscreen",
        "frameborder",
        "scrolling",
        "marginwidth",
        "marginheight",
        "xlink:href",
    }
)


# This compatibility model mirrors the legacy public node constructor.
# pylint: disable=too-many-instance-attributes,too-many-arguments,too-many-positional-arguments
class HTMLNode:
    """Small mutable HTML node model retained for the legacy tree API."""

    def __init__(
        self,
        tag: str = "",
        is_text: bool = False,
        text: str = "",
        is_comment: bool = False,
        comment: str = "",
        is_doctype: bool = False,
        attributes: dict[str, str] | None = None,
    ) -> None:
        """Initialize a node and its relationship fields."""
        self.tag = tag
        self.is_text = is_text
        self.text = text
        self.is_comment = is_comment
        self.comment = comment
        self.is_doctype = is_doctype
        self.attributes = attributes.copy() if attributes else {}
        self.children: list[HTMLNode] = []
        self.parent: HTMLNode | None = None

    def add_child(self, child: HTMLNode) -> None:
        """Append a child and update its parent pointer."""
        child.parent = self
        self.children.append(child)

    def to_string(self) -> str:
        """Serialize this node with text/attribute escaping."""
        if self.is_doctype:
            return ""
        if self.is_comment:
            safe_comment = self.comment.replace("--", "- -")
            return f"<!--{safe_comment}-->"
        if self.is_text:
            return html_stdlib.escape(self.text, quote=False)
        if not self.tag:
            return "".join(child.to_string() for child in self.children)

        attributes = "".join(
            f' {name}="{html_stdlib.escape(value, quote=True)}"'
            for name, value in self.attributes.items()
        )
        children = "".join(child.to_string() for child in self.children)
        if self.tag.lower() in _VOID_TAGS:
            return f"<{self.tag}{attributes} />"
        return f"<{self.tag}{attributes}>{children}</{self.tag}>"


# Maintains the old API shape while exposing one public ``feed`` operation.
# pylint: disable=too-few-public-methods
class HTMLTreeParser:
    """Compatibility tree parser that exposes :class:`HTMLNode` instances."""

    def __init__(self) -> None:
        """Initialize an empty document root."""
        self.root = HTMLNode()
        self.current = self.root

    def feed(self, html_content: str) -> None:
        """Parse an HTML document, retaining comments and meaningful text."""
        parser = lxml_html.HTMLParser(recover=True, remove_comments=False)
        try:
            tree = lxml_html.fromstring(html_content, parser=parser)
        except (ValueError, etree.LxmlError):
            self.root = HTMLNode()
            self.root.add_child(HTMLNode(tag="html"))
            self.current = self.root
            return
        self.root = HTMLNode()
        self.root.add_child(self._convert_lxml_to_node(tree))
        self.current = self.root

    def _convert_lxml_to_node(self, element: Any) -> HTMLNode:
        """Copy an lxml element and its mixed text content into HTMLNode form."""
        if isinstance(element, lxml_html.HtmlComment):
            comment_text = element.text or ""
            return HTMLNode(is_comment=True, comment=comment_text, text=comment_text)

        node = HTMLNode(tag=str(element.tag), attributes=dict(element.attrib))
        if element.text and element.text.strip():
            node.add_child(HTMLNode(is_text=True, text=element.text))
        for child in element:
            node.add_child(self._convert_lxml_to_node(child))
            if child.tail and child.tail.strip():
                node.add_child(HTMLNode(is_text=True, text=child.tail))
        return node


class _MHTMLCleaner(Cleaner):
    """Preserve opted-in inlined assets while filtering active URL schemes."""

    safe_attrs: frozenset[str]

    def __init__(
        self,
        allow_inline_scripts: bool,
        allow_inline_styles: bool,
        allow_external_stylesheets: bool,
        **options: Any,
    ) -> None:
        self.allow_inline_scripts = allow_inline_scripts
        self.allow_inline_styles = allow_inline_styles
        self.allow_external_stylesheets = allow_external_stylesheets
        super().__init__(**options)

    @staticmethod
    def _data_uri_media_type(url: str) -> str:
        """Return a data URI media type, ignoring parameters."""
        if not url.lower().startswith("data:"):
            return ""
        return url[5:].split(",", maxsplit=1)[0].split(";", maxsplit=1)[0].lower()

    def sanitize_url(self, link: str) -> str:
        """Reject scriptable URL schemes and allow intended data resources."""
        compact = re.sub(
            r"[\s\x00-\x20]+", "", urllib.parse.unquote(link).strip()
        ).lower()
        media_type = self._data_uri_media_type(compact)
        if compact.startswith("data:"):
            allowed_media_type = (
                (
                    self.allow_inline_scripts
                    and media_type
                    in {
                        "application/javascript",
                        "application/x-javascript",
                        "text/javascript",
                    }
                )
                or (self.allow_inline_styles and media_type == "text/css")
                or (media_type.startswith("image/") and media_type != "image/svg+xml")
                or media_type in {"font/woff", "font/woff2", "application/font-woff"}
            )
            return link if allowed_media_type else ""
        scheme = urllib.parse.urlsplit(compact).scheme
        return (
            ""
            if scheme in {"javascript", "vbscript", "file", "filesystem", "blob"}
            else link
        )

    def _remove_javascript_link(self, link: str) -> str:
        """Adapt lxml's callback to the public URL sanitizer."""
        return self.sanitize_url(link)

    def allow_element(self, el: Any) -> bool:
        """Keep only enabled stylesheets when lxml checks embedded links."""
        if el.tag == "link" and "stylesheet" in el.get("rel", "").lower():
            href = el.get("href", "")
            media_type = self._data_uri_media_type(href)
            if self.allow_inline_styles and media_type == "text/css":
                return True
            if self.allow_external_stylesheets:
                return urllib.parse.urlsplit(href).scheme.lower() in {"http", "https"}
        return False


class HTMLProcessor:
    """Parse, validate, rewrite, and sanitize HTML content."""

    URL_ATTRIBUTES: ClassVar[tuple[str, ...]] = (
        "src",
        "href",
        "poster",
        "background",
        "action",
        "formaction",
        "data",
        "xlink:href",
    )
    RESOURCE_TAGS: ClassVar[dict[str, frozenset[str]]] = {
        "img": frozenset({"src", "srcset"}),
        "script": frozenset({"src"}),
        "link": frozenset({"href"}),
        "source": frozenset({"src", "srcset"}),
        "video": frozenset({"src", "poster"}),
        "audio": frozenset({"src"}),
        "track": frozenset({"src"}),
        "iframe": frozenset({"src"}),
        "embed": frozenset({"src"}),
        "object": frozenset({"data"}),
        "body": frozenset({"background"}),
        "table": frozenset({"background"}),
        "td": frozenset({"background"}),
        "th": frozenset({"background"}),
        "input": frozenset({"src"}),
    }

    def __init__(self, config: ConverterConfig | None = None) -> None:
        """Create an HTML processor and its CSS rewriter."""
        self.config = config or ConverterConfig()
        self.css_processor = CSSProcessor(self.config)
        self.cleaner = _MHTMLCleaner(
            allow_inline_scripts=self.config.include_scripts
            and not self.config.remove_scripts,
            allow_inline_styles=self.config.include_styles,
            allow_external_stylesheets=(
                self.config.resource_handling in {"external", "mixed"}
            ),
            safe_attrs_only=True,
            safe_attrs=frozenset(getattr(Cleaner, "safe_attrs", frozenset()))
            | _SAFE_EXTRA_ATTRIBUTES,
            scripts=not self.config.include_scripts or self.config.remove_scripts,
            style=not self.config.include_styles,
            links=False,
            meta=False,
            page_structure=False,
            forms=False,
            kill_tags=("base",),
            remove_unknown_tags=False,
        )

    def parse_basic_html(self, content: str) -> Any:
        """Parse an HTML fragment or document with error recovery enabled."""
        parser = lxml_html.HTMLParser(recover=True, remove_comments=False)
        if not content.strip():
            return lxml_html.fromstring("<html><body></body></html>", parser=parser)
        return lxml_html.fromstring(content, parser=parser)

    def to_string(self, element: Any) -> str:
        """Serialize an lxml element using the configured HTML/XHTML method."""
        method = "xml" if self.config.output_format == "xhtml" else "html"
        return cast(str, lxml_html.tostring(element, encoding="unicode", method=method))

    def extract_resource_urls(self, content: str) -> set[str]:
        """Find fetchable assets in HTML, excluding ordinary anchor navigation."""
        try:
            tree = self.parse_basic_html(content)
        except (ValueError, etree.LxmlError):
            return set()
        urls: set[str] = set()
        for element in tree.iter():
            tag = str(element.tag).lower()
            attributes: set[str] = set(self.RESOURCE_TAGS.get(tag, frozenset()))
            if tag == "script" and (
                not self.config.include_scripts or self.config.remove_scripts
            ):
                attributes = set()
            if tag == "link":
                rel = element.get("rel", "").lower().split()
                allowed_rel = {"icon", "preload", "modulepreload", "manifest"}
                if self.config.include_styles:
                    allowed_rel.add("stylesheet")
                if not allowed_rel.intersection(rel):
                    attributes = set()
            for name in attributes:
                value = element.get(name)
                if not value:
                    continue
                if name == "srcset":
                    urls.update(url for url, _ in self._parse_srcset(value))
                else:
                    urls.add(value.strip())
            style = element.get("style")
            if style:
                urls.update(self.css_processor.extract_urls(f"x{{{style}}}"))
            if tag == "style" and element.text:
                urls.update(self.css_processor.extract_urls(element.text))
        return {url for url in urls if url and not url.lower().startswith("data:")}

    def rewrite_html(
        self,
        content: str,
        base_url: str,
        resource_map: dict[str, Resource],
    ) -> str:
        """Rewrite assets in HTML and sanitize the result when configured."""
        try:
            tree = self.parse_basic_html(content)
        except (ValueError, etree.LxmlError):
            return self._rewrite_with_regex_fallback(content, base_url, resource_map)

        for element in tree.iter():
            for attribute in self.URL_ATTRIBUTES:
                if attribute in element.attrib:
                    element.attrib[attribute] = self._rewrite_url(
                        element.attrib[attribute], base_url, resource_map
                    )
            if "srcset" in element.attrib:
                candidates = self._parse_srcset(element.attrib["srcset"])
                element.attrib["srcset"] = ", ".join(
                    f"{self._rewrite_url(url, base_url, resource_map)}{descriptor}"
                    for url, descriptor in candidates
                )
            if self.config.include_styles and "style" in element.attrib:
                declaration = element.attrib["style"]
                rewritten = self.css_processor.rewrite_css(
                    f"mhtml-inline{{{declaration}}}", base_url, resource_map
                )
                element.attrib["style"] = self._extract_rule_body(rewritten)
            if (
                self.config.include_styles
                and str(element.tag).lower() == "style"
                and element.text
            ):
                element.text = self.css_processor.rewrite_css(
                    element.text, base_url, resource_map
                )

        if self.config.sanitize_html:
            self._extend_safe_attributes(tree)
            tree = self.cleaner.clean_html(tree)
        return self.to_string(tree)

    def validate_html(self, content: str) -> list[str]:
        """Return parser diagnostics for an HTML document or fragment."""
        parser = lxml_html.HTMLParser(recover=True, remove_comments=False)
        try:
            lxml_html.fromstring(content or "<html></html>", parser=parser)
        except (ValueError, etree.LxmlError) as error:
            return [str(error)]
        return [str(entry) for entry in parser.error_log]

    def minify_html(self, content: str) -> str:
        """Remove comments and serialize compactly while preserving text spacing."""
        parser = lxml_html.HTMLParser(recover=True, remove_comments=True)
        try:
            tree = lxml_html.fromstring(content or "<html></html>", parser=parser)
        except (ValueError, etree.LxmlError):
            return content
        method = "xml" if self.config.output_format == "xhtml" else "html"
        return cast(str, lxml_html.tostring(tree, encoding="unicode", method=method))

    def _extend_safe_attributes(self, tree: Any) -> None:
        """Preserve data-/ARIA attributes while dropping event-handler attributes."""
        safe_attributes = set(getattr(self.cleaner, "safe_attrs", frozenset()))
        for element in tree.iter():
            for name in tuple(element.attrib):
                normalized = name.lower()
                if normalized.startswith(("data-", "aria-")):
                    safe_attributes.add(name)
        self.cleaner.safe_attrs = frozenset(safe_attributes)

    @staticmethod
    def _extract_rule_body(css: str) -> str:
        """Extract the declaration block from a temporary selector wrapper."""
        opening = css.find("{")
        closing = css.rfind("}")
        if opening < 0 or closing < opening:
            return css
        return css[opening + 1 : closing].strip()

    @staticmethod
    def _parse_srcset(value: str) -> list[tuple[str, str]]:
        """Parse basic srcset candidates without splitting commas inside data URLs."""
        candidates: list[tuple[str, str]] = []
        length = len(value)
        cursor = 0
        while cursor < length:
            while cursor < length and (value[cursor].isspace() or value[cursor] == ","):
                cursor += 1
            start = cursor
            while cursor < length and not value[cursor].isspace():
                cursor += 1
            url = value[start:cursor].rstrip(",")
            if not url:
                continue
            descriptor_start = cursor
            while cursor < length and value[cursor] != ",":
                cursor += 1
            descriptor = value[descriptor_start:cursor].strip()
            candidates.append((url, f" {descriptor}" if descriptor else ""))
            cursor += cursor < length
        return candidates

    def _rewrite_url(
        self,
        url: str,
        base_url: str,
        resource_map: dict[str, Resource],
    ) -> str:
        """Return an inlined data URI or a normalized URL for an HTML attribute."""
        value = url.strip()
        if not value:
            return value
        if self.config.sanitize_html and not self.cleaner.sanitize_url(value):
            return ""
        return resolve_resource_url(value, base_url, resource_map, self.config)

    def _rewrite_with_regex(
        self,
        content: str,
        base_url: str,
        resource_map: dict[str, Resource],
    ) -> str:
        """Regex-only URL rewrite retained for compatibility and parse recovery."""
        pattern = re.compile(
            r"(?P<prefix>\b(?:src|href|poster|background|action|data)\s*=\s*)"
            r"(?P<quote>[\"'])(?P<url>.*?)(?P=quote)",
            re.IGNORECASE | re.DOTALL,
        )
        return pattern.sub(
            lambda match: (
                f"{match.group('prefix')}{match.group('quote')}"
                f"{self._rewrite_url(match.group('url'), base_url, resource_map)}"
                f"{match.group('quote')}"
            ),
            content,
        )

    def _rewrite_with_regex_fallback(
        self,
        content: str,
        base_url: str,
        resource_map: dict[str, Resource],
    ) -> str:
        """Alias kept for backwards compatibility with the original scripts."""
        rewritten = self._rewrite_with_regex(content, base_url, resource_map)
        if not self.config.sanitize_html:
            return rewritten
        rewritten = re.sub(
            r"\s+on[a-z]+\s*=\s*([\"']).*?\1",
            "",
            rewritten,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return re.sub(
            r"\b(href|src|action)\s*=\s*([\"'])\s*(?:javascript|vbscript):.*?\2",
            r'\1=""',
            rewritten,
            flags=re.IGNORECASE | re.DOTALL,
        )


__all__ = ["HTMLNode", "HTMLProcessor", "HTMLTreeParser"]
