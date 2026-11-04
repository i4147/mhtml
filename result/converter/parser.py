"""MIME/MHTML parsing, text decoding, resource extraction, and URL discovery."""

from __future__ import annotations

import base64
import binascii
import quopri
import re
import urllib.parse
from dataclasses import dataclass, field
from email import policy
from email.header import decode_header
from email.message import Message
from email.parser import BytesParser
from enum import Enum
from typing import Any

from .config import ConverterConfig


class ResourceType(str, Enum):
    """High-level category of an extracted MIME resource."""

    HTML = "html"
    CSS = "css"
    IMAGE = "image"
    SCRIPT = "script"
    FONT = "font"
    OTHER = "other"


def classify_resource_type(content_type: str) -> ResourceType:
    """Map a MIME content type to the converter's resource categories."""
    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    if media_type in {"text/html", "text/htm", "application/xhtml+xml"}:
        return ResourceType.HTML
    if media_type == "text/css":
        return ResourceType.CSS
    if media_type in {
        "application/javascript",
        "application/x-javascript",
        "text/javascript",
        "text/ecmascript",
        "application/ecmascript",
    }:
        return ResourceType.SCRIPT
    if media_type.startswith("image/"):
        return ResourceType.IMAGE
    if media_type.startswith("font/") or media_type in {
        "application/font-woff",
        "application/font-woff2",
        "application/vnd.ms-fontobject",
    }:
        return ResourceType.FONT
    return ResourceType.OTHER


def resource_to_data_uri(resource: Resource) -> str:
    """Encode a resource as a base64 data URI using its MIME media type."""
    content = (
        resource.content
        if isinstance(resource.content, bytes)
        else resource.content.encode("utf-8")
    )
    media_type = resource.content_type.split(";", maxsplit=1)[0].strip()
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


# A resource carries MIME, URL, content, and lookup metadata by design.
# pylint: disable=too-many-instance-attributes
@dataclass(slots=True)
class Resource:
    """A MIME part and the URL by which HTML/CSS refers to it."""

    url: str
    content_type: str
    content: bytes | str
    resource_type: ResourceType
    encoding: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    original_url: str | None = None
    size: int = 0

    def __post_init__(self) -> None:
        """Compute byte size and ensure each resource owns its header mapping."""
        if isinstance(self.content, bytes):
            self.size = len(self.content)
        else:
            self.size = len(self.content.encode("utf-8"))
        if self.original_url is None:
            self.original_url = self.url


def resolve_resource_url(
    url: str,
    base_url: str,
    resource_map: dict[str, Resource],
    config: ConverterConfig,
) -> str:
    """Normalize an asset URL and inline a mapped resource when configured."""
    value = url.strip()
    if not value or value.lower().startswith("data:"):
        return value
    normalized = urllib.parse.urldefrag(urllib.parse.urljoin(base_url, value))[0]
    resource = resource_map.get(normalized) or resource_map.get(value)
    if (
        resource is not None
        and config.resource_handling in {"inline", "mixed"}
        and resource.size <= config.max_resource_size
    ):
        return resource_to_data_uri(resource)
    return normalized


class MHTMLParser:
    """Parse MHTML data using Python's MIME parser plus compatibility helpers."""

    BOUNDARY_RE = re.compile(
        r"boundary\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s;]+))",
        re.IGNORECASE,
    )
    CHARSET_RE = re.compile(r"charset\s*=\s*['\"]?([^\s;'\"]+)", re.IGNORECASE)
    HTML_URL_RE = re.compile(
        r"\b(?:src|href|poster|background|action|data|xlink:href)\s*=\s*"
        r"(?P<quote>[\"'])(?P<url>.*?)(?P=quote)",
        re.IGNORECASE | re.DOTALL,
    )
    CSS_URL_RE = re.compile(
        r"url\(\s*(?:(?P<quote>[\"'])(?P<quoted>.*?)(?P=quote)|(?P<plain>[^)]*?))\s*\)",
        re.IGNORECASE | re.DOTALL,
    )
    CSS_IMPORT_RE = re.compile(
        r"@import\s+(?:url\(\s*)?(?:\"([^\"]*)\"|'([^']*)'|([^\s)]+))",
        re.IGNORECASE,
    )
    SRCSET_RE = re.compile(r"(?:^|,)\s*([^\s,]+)(?:\s+[^,]+)?")

    BOM_UTF8 = b"\xef\xbb\xbf"
    BOM_UTF16BE = b"\xfe\xff"
    BOM_UTF16LE = b"\xff\xfe"

    def __init__(self, config: ConverterConfig | None = None) -> None:
        """Create a parser using the supplied configuration."""
        self.config = config or ConverterConfig()
        self.parser = BytesParser(policy=policy.default)

    def _detect_encoding(
        self, content: bytes, content_type: str = ""
    ) -> tuple[str, bytes]:
        """Detect a BOM or MIME charset and return the charset and BOM-free bytes."""
        if content.startswith(self.BOM_UTF8):
            return "utf-8", content[len(self.BOM_UTF8) :]
        if content.startswith(self.BOM_UTF16BE):
            return "utf-16-be", content[len(self.BOM_UTF16BE) :]
        if content.startswith(self.BOM_UTF16LE):
            return "utf-16-le", content[len(self.BOM_UTF16LE) :]

        charset_match = self.CHARSET_RE.search(content_type)
        charset = charset_match.group(1) if charset_match else self.config.encoding
        try:
            content.decode(charset)
        except (LookupError, UnicodeDecodeError):
            return "utf-8", content
        return charset, content

    def decode_text(self, content: bytes | str, content_type: str = "") -> str:
        """Decode text with BOM/charset detection and a replacement fallback."""
        if isinstance(content, str):
            return content.removeprefix("\ufeff")
        charset, data = self._detect_encoding(content, content_type)
        try:
            return data.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            return data.decode(self.config.encoding, errors="replace")

    def _decode_content(
        self,
        content: bytes,
        content_type: str,
        encoding: str,
    ) -> bytes:
        """Decode MIME transfer encodings while preserving text as raw bytes."""
        if not content:
            return b""
        transfer_encoding = encoding.strip().lower()
        if transfer_encoding in {"base64", "b64"}:
            compact = re.sub(rb"\s+", b"", content)
            try:
                return base64.b64decode(compact, validate=False)
            except (binascii.Error, ValueError):
                return content
        if transfer_encoding in {"quoted-printable", "qp"}:
            return quopri.decodestring(content)
        # 7bit/8bit/binary parts already contain their transfer-decoded bytes.
        del content_type
        return content

    @staticmethod
    def _get_resource_type(content_type: str) -> ResourceType:
        """Compatibility wrapper for MIME resource classification."""
        return classify_resource_type(content_type)

    def parse_mhtml(
        self,
        raw_data: bytes,
    ) -> tuple[Resource, dict[str, Resource], dict[str, Any]]:
        """Parse a full MHTML message into its main part, assets, and metadata.

        Raises:
            ValueError: If the input is empty or has no MIME content-type header.
        """
        if not raw_data.strip() or b"content-type:" not in raw_data.lower():
            raise ValueError("Invalid MHTML data: missing MIME Content-Type header")
        if len(raw_data) > self.config.max_input_size:
            raise ValueError(
                f"MHTML input exceeds the {self.config.max_input_size}-byte limit"
            )

        message = self.parser.parsebytes(raw_data)
        main_part = self._find_main_part(message)
        main_resource = self._resource_from_part(main_part)
        resources = self._extract_resources(message, main_part)
        metadata = self._extract_metadata(message, main_resource, resources)
        return main_resource, resources, metadata

    @staticmethod
    def _find_main_part(message: Message) -> Message:
        """Select the first HTML part, or the first leaf if no HTML part exists."""
        if not message.is_multipart():
            return message
        parts = list(message.walk())
        for part in parts:
            if part.get_content_type().lower() in {
                "text/html",
                "text/htm",
                "application/xhtml+xml",
            }:
                return part
        return next((part for part in parts if not part.is_multipart()), message)

    def _resource_from_part(self, part: Message) -> Resource:
        """Build a resource from one MIME part, honoring its own MIME headers."""
        payload = part.get_payload(decode=False)
        if isinstance(payload, bytes):
            raw_content = payload
        elif isinstance(payload, str):
            raw_content = payload.encode("utf-8", errors="replace")
        else:
            raw_content = b""

        transfer_encoding = str(part.get("Content-Transfer-Encoding", "7bit"))
        content = self._decode_content(
            raw_content,
            str(part.get("Content-Type", part.get_content_type())),
            transfer_encoding,
        )
        url = str(part.get("Content-Location", "") or part.get("Content-ID", ""))
        if url.startswith("<") and url.endswith(">"):
            url = url[1:-1]

        return Resource(
            url=url,
            content_type=part.get_content_type(),
            content=content,
            resource_type=self._get_resource_type(part.get_content_type()),
            encoding=transfer_encoding,
            headers={str(key): str(value) for key, value in part.items()},
            original_url=url,
        )

    def _extract_resources(
        self,
        message: Message,
        main_part: Message,
    ) -> dict[str, Resource]:
        """Extract all non-main MIME parts and index Content-ID aliases."""
        resources: dict[str, Resource] = {}
        if not message.is_multipart():
            return resources

        for part in message.walk():
            if part is message or part is main_part or part.is_multipart():
                continue
            resource = self._resource_from_part(part)
            if not resource.url:
                continue
            resources[resource.url] = resource
            content_id = str(part.get("Content-ID", "")).strip()
            if content_id.startswith("<") and content_id.endswith(">"):
                content_id = content_id[1:-1]
            if content_id:
                resources[f"cid:{content_id}"] = resource
        return resources

    def _extract_metadata(
        self,
        message: Message,
        main_resource: Resource,
        resources: dict[str, Resource],
    ) -> dict[str, Any]:
        """Extract MIME headers, structural details, and lightweight asset metadata."""
        metadata: dict[str, Any] = {
            "content_type": message.get_content_type(),
            "boundary": self._extract_boundary(message),
            "part_count": sum(1 for part in message.walk() if not part.is_multipart()),
            "main_resource_type": main_resource.resource_type.value,
            "resource_count": len({id(resource) for resource in resources.values()}),
        }
        if self.config.metadata_extraction:
            metadata.update(
                {
                    "subject": self._decode_header_value(message.get("Subject", "")),
                    "from": self._decode_header_value(message.get("From", "")),
                    "to": self._decode_header_value(message.get("To", "")),
                    "date": self._decode_header_value(message.get("Date", "")),
                    "content_location": main_resource.url,
                    "resources": [
                        {
                            "url": resource.url,
                            "content_type": resource.content_type,
                            "resource_type": resource.resource_type.value,
                            "size": resource.size,
                        }
                        for resource in self._unique_resources(resources.values())
                    ],
                }
            )
        return metadata

    @staticmethod
    def _unique_resources(resources: Any) -> list[Resource]:
        """Return a stable unique list, accounting for CID aliases."""
        result: list[Resource] = []
        seen: set[int] = set()
        for resource in resources:
            identity = id(resource)
            if identity not in seen:
                result.append(resource)
                seen.add(identity)
        return result

    @staticmethod
    def _decode_header_value(value: Any) -> str:
        """Decode RFC 2047 encoded MIME headers into Unicode text."""
        if not value:
            return ""
        pieces: list[str] = []
        for chunk, charset in decode_header(str(value)):
            if isinstance(chunk, bytes):
                pieces.append(chunk.decode(charset or "utf-8", errors="replace"))
            else:
                pieces.append(chunk)
        return "".join(pieces)

    def _extract_boundary(self, message: Message) -> str | None:
        """Extract the MIME boundary from a real or compatible message object."""
        content_type = str(message.get("Content-Type", ""))
        match = self.BOUNDARY_RE.search(content_type)
        if match is None:
            return None
        return next((value for value in match.groups() if value), None)

    def extract_urls_from_content(
        self,
        content: bytes | str,
        content_type: str,
    ) -> set[str]:
        """Find URL references in HTML and CSS, including srcset and CSS imports."""
        text = self.decode_text(content, content_type)
        urls: set[str] = set()
        media_type = content_type.split(";", maxsplit=1)[0].lower()
        if "html" in media_type or media_type.endswith("xhtml+xml"):
            urls.update(
                match.group("url").strip()
                for match in self.HTML_URL_RE.finditer(text)
                if match.group("url").strip()
            )
            for match in re.finditer(
                r"\bsrcset\s*=\s*([\"'])(.*?)\1",
                text,
                re.IGNORECASE | re.DOTALL,
            ):
                urls.update(
                    item.group(1).strip()
                    for item in self.SRCSET_RE.finditer(match.group(2))
                    if item.group(1).strip()
                )
        if "css" in media_type or "html" in media_type:
            for match in self.CSS_URL_RE.finditer(text):
                url = (
                    (match.group("quoted") or match.group("plain") or "")
                    .strip()
                    .strip("\"'")
                )
                if url:
                    urls.add(url)
        if "css" in media_type:
            for match in self.CSS_IMPORT_RE.finditer(text):
                url = next((value for value in match.groups() if value), "").strip(
                    "\"'"
                )
                if url:
                    urls.add(url)
        return urls


__all__ = [
    "MHTMLParser",
    "Resource",
    "ResourceType",
    "classify_resource_type",
    "resolve_resource_url",
    "resource_to_data_uri",
]
