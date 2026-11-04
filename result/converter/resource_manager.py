"""Safe resource resolution, concurrent fetching, and bounded LRU caching."""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import mimetypes
import re
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.client import HTTPMessage
from pathlib import Path
from typing import IO

from loguru import logger

from .config import ConverterConfig
from .parser import (
    Resource,
    ResourceType,
    classify_resource_type,
    resource_to_data_uri,
)


class ResourceCache:
    """Thread-safe, bounded LRU cache with optional persistent disk storage."""

    def __init__(self, max_size: int = 100, cache_dir: Path | None = None) -> None:
        """Create a cache holding at most ``max_size`` in-memory resources."""
        self.max_size = max_size
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._entries: OrderedDict[str, Resource] = OrderedDict()
        self._lock = threading.RLock()

    def put(self, key: str, resource: Resource) -> None:
        """Insert or replace a resource, persisting it when configured."""
        if self.max_size == 0:
            return
        with self._lock:
            self._entries.pop(key, None)
            self._entries[key] = resource
            while len(self._entries) > self.max_size:
                self._entries.popitem(last=False)
        self._write_disk(key, resource)

    def get(self, key: str) -> Resource | None:
        """Retrieve a resource and update its LRU position."""
        with self._lock:
            resource = self._entries.pop(key, None)
            if resource is not None:
                self._entries[key] = resource
                return resource
        resource = self._read_disk(key)
        if resource is not None:
            with self._lock:
                self._entries[key] = resource
                while len(self._entries) > self.max_size:
                    self._entries.popitem(last=False)
        return resource

    def clear(self, *, clear_disk: bool = False) -> None:
        """Clear memory entries and optionally remove persisted cache files."""
        with self._lock:
            self._entries.clear()
        if clear_disk and self.cache_dir is not None and self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink(missing_ok=True)
                cache_file.with_suffix(".bin").unlink(missing_ok=True)

    def _cache_paths(self, key: str) -> tuple[Path, Path] | None:
        if self.cache_dir is None:
            return None
        filename = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{filename}.json", self.cache_dir / f"{filename}.bin"

    def _write_disk(self, key: str, resource: Resource) -> None:
        """Write one resource atomically to the optional disk cache."""
        paths = self._cache_paths(key)
        cache_dir = self.cache_dir
        if paths is None or cache_dir is None:
            return
        metadata_path, content_path = paths
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            is_text = isinstance(resource.content, str)
            content = (
                resource.content.encode("utf-8")
                if isinstance(resource.content, str)
                else resource.content
            )
            metadata = {
                "url": resource.url,
                "content_type": resource.content_type,
                "resource_type": resource.resource_type.value,
                "encoding": resource.encoding,
                "headers": resource.headers,
                "original_url": resource.original_url,
                "is_text": is_text,
            }
            content_tmp = content_path.with_suffix(".tmp")
            metadata_tmp = metadata_path.with_suffix(".tmp")
            content_tmp.write_bytes(content)
            metadata_tmp.write_text(json.dumps(metadata), encoding="utf-8")
            content_tmp.replace(content_path)
            metadata_tmp.replace(metadata_path)
        except OSError as error:
            logger.warning("Unable to persist resource cache entry {}: {}", key, error)

    def _read_disk(self, key: str) -> Resource | None:
        """Read and validate one resource from the optional disk cache."""
        paths = self._cache_paths(key)
        if paths is None:
            return None
        metadata_path, content_path = paths
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            raw_content = content_path.read_bytes()
            content: bytes | str = raw_content
            if metadata.get("is_text"):
                content = raw_content.decode("utf-8", errors="replace")
            return Resource(
                url=metadata["url"],
                content_type=metadata["content_type"],
                content=content,
                resource_type=ResourceType(metadata["resource_type"]),
                encoding=metadata.get("encoding"),
                headers=metadata.get("headers", {}),
                original_url=metadata.get("original_url"),
            )
        except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
            return None


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects to URLs outside the resource manager's policy."""

    def __init__(self, is_allowed: Callable[[str], bool]) -> None:
        super().__init__()
        self._is_allowed = is_allowed

    # Signature is fixed by urllib.request.HTTPRedirectHandler.
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        if not self._is_allowed(newurl):
            raise urllib.error.HTTPError(
                newurl,
                code,
                "Redirect target rejected by resource security policy",
                headers,
                fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ResourceManager:
    """Resolve URLs against MHTML resources and optionally fetch public assets."""

    def __init__(self, config: ConverterConfig | None = None) -> None:
        """Set up cache and fetch settings from the converter configuration."""
        self.config = config or ConverterConfig()
        cache_dir = self.config.cache_dir if self.config.cache_enabled else None
        cache_size = self.config.cache_size if self.config.cache_enabled else 0
        self.cache = ResourceCache(cache_size, cache_dir)
        self._opener = urllib.request.build_opener(
            _SafeRedirectHandler(self._is_safe_external_url)
        )

    @staticmethod
    def normalize_url(url: str, base_url: str) -> str:
        """Resolve relative URLs and discard fragments for asset lookup."""
        value = url.strip()
        if value.lower().startswith(("data:", "cid:")):
            return value
        normalized = urllib.parse.urljoin(base_url, value)
        return urllib.parse.urldefrag(normalized)[0]

    @staticmethod
    def _normalize_url(url: str, base_url: str) -> str:
        """Backwards-compatible alias for :meth:`normalize_url`."""
        return ResourceManager.normalize_url(url, base_url)

    @staticmethod
    def _convert_to_data_uri(resource: Resource) -> str:
        """Encode a resource as an RFC 2397 base64 data URI."""
        return resource_to_data_uri(resource)

    @staticmethod
    # Ordered signature checks make the MIME fallback straightforward to review.
    # pylint: disable=too-many-return-statements
    def _guess_content_type(url: str, content: bytes) -> str:
        """Guess MIME type from URL extension or a few common file signatures."""
        path = urllib.parse.urlsplit(url).path
        content_type, _ = mimetypes.guess_type(path)
        if content_type:
            return content_type
        if content.lstrip().lower().startswith((b"<html", b"<!doctype html")):
            return "text/html"
        if content.lstrip().startswith((b"body {", b"@import", b"@media")):
            return "text/css"
        if content.lstrip().startswith((b"function", b"console", b"const ", b"let ")):
            return "application/javascript"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            return "image/webp"
        return "application/octet-stream"

    def process_resources_parallel(
        self,
        urls: list[str],
        base_url: str,
    ) -> dict[str, Resource | None]:
        """Resolve the unique URLs in parallel where enabled, using the cache."""
        normalized_urls = list(
            dict.fromkeys(self.normalize_url(url, base_url) for url in urls)
        )
        result: dict[str, Resource | None] = {}
        pending: list[str] = []
        for url in normalized_urls:
            cached = self.cache.get(url)
            if cached is None:
                pending.append(url)
            else:
                result[url] = cached

        if self.config.parallel_processing and len(pending) > 1:
            with ThreadPoolExecutor(
                max_workers=min(self.config.max_workers, len(pending))
            ) as pool:
                futures = {
                    pool.submit(self._fetch_resource, url, base_url): url
                    for url in pending
                }
                for future in as_completed(futures):
                    url = futures[future]
                    try:
                        result[url] = future.result()
                    except (OSError, ValueError, urllib.error.URLError) as error:
                        logger.debug("Resource fetch failed for {}: {}", url, error)
                        result[url] = None
        else:
            for url in pending:
                try:
                    result[url] = self._fetch_resource(url, base_url)
                except (OSError, ValueError, urllib.error.URLError) as error:
                    logger.debug("Resource fetch failed for {}: {}", url, error)
                    result[url] = None
        return result

    # Explicit guard clauses keep network limits and security policy obvious.
    # pylint: disable=too-many-return-statements
    def _fetch_resource(self, url: str, base_url: str) -> Resource | None:
        """Fetch a data URI or permitted public HTTP(S) asset within size limits."""
        normalized_url = self.normalize_url(url, base_url)
        if normalized_url.lower().startswith("data:"):
            return self._parse_data_uri(normalized_url)
        if normalized_url.lower().startswith("cid:") or not self.config.fetch_external:
            return None
        if not self._is_safe_external_url(normalized_url):
            logger.warning("Refusing unsafe external resource URL: {}", normalized_url)
            return None

        request = urllib.request.Request(
            normalized_url,
            headers={"User-Agent": "MHTML-Converter/1.0"},
        )
        for attempt in range(self.config.max_fetch_retries + 1):
            try:
                with self._opener.open(
                    request, timeout=self.config.fetch_timeout
                ) as response:
                    final_url = response.geturl()
                    if not self._is_safe_external_url(final_url):
                        logger.warning("Refusing unsafe redirect target: {}", final_url)
                        return None
                    content_length = response.headers.get("Content-Length")
                    if (
                        content_length
                        and int(content_length) > self.config.max_resource_size
                    ):
                        logger.warning(
                            "Resource exceeds configured size limit: {}", final_url
                        )
                        return None
                    content = response.read(self.config.max_resource_size + 1)
                    if len(content) > self.config.max_resource_size:
                        logger.warning(
                            "Resource exceeds configured size limit: {}", final_url
                        )
                        return None
                    content_type = response.headers.get_content_type()
                    resource = Resource(
                        url=final_url,
                        content_type=content_type
                        or self._guess_content_type(final_url, content),
                        content=content,
                        resource_type=self._get_resource_type(content_type),
                        encoding=response.headers.get("Content-Transfer-Encoding"),
                        headers=dict(response.headers.items()),
                        original_url=url,
                    )
                    transformed = self.transform_resource(resource)
                    self.cache.put(normalized_url, transformed)
                    return transformed
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
                if attempt >= self.config.max_fetch_retries:
                    logger.debug("Could not fetch {}: {}", normalized_url, error)
                    return None
        return None

    # Early returns make the URL policy easy to audit as a sequence of checks.
    # pylint: disable=too-many-return-statements
    def _is_safe_external_url(self, url: str) -> bool:
        """Allow public HTTP(S) hosts that satisfy the configured domain policy."""
        parts = urllib.parse.urlsplit(url)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return False
        if parts.username is not None or parts.password is not None:
            return False
        host = parts.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(
            (".localhost", ".local", ".internal")
        ):
            return False
        if self._domain_matches(host, self.config.blocked_domains):
            return False
        if self.config.allowed_domains and not self._domain_matches(
            host, self.config.allowed_domains
        ):
            return False

        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            try:
                addresses = [
                    ipaddress.ip_address(result[4][0])
                    for result in socket.getaddrinfo(
                        host, parts.port or 80, type=socket.SOCK_STREAM
                    )
                ]
            except (OSError, ValueError):
                return False
        return bool(addresses) and all(address.is_global for address in addresses)

    @staticmethod
    def _domain_matches(host: str, domains: list[str]) -> bool:
        """Match an exact hostname or a subdomain of a configured domain."""
        return any(host == domain or host.endswith(f".{domain}") for domain in domains)

    # Each malformed data-URI condition returns safely without extra nesting.
    # pylint: disable=too-many-return-statements
    def _parse_data_uri(self, data_uri: str) -> Resource | None:
        """Decode a data URI, rejecting malformed or oversized payloads."""
        if not data_uri.lower().startswith("data:"):
            return None
        header, separator, data = data_uri[5:].partition(",")
        if not separator:
            return None
        header_parts = header.split(";")
        content_type = header_parts[0] or "text/plain"
        is_base64 = any(part.lower() == "base64" for part in header_parts[1:])
        try:
            if is_base64:
                content = base64.b64decode(re.sub(r"\s+", "", data), validate=False)
            else:
                content = urllib.parse.unquote_to_bytes(data)
        except (ValueError, binascii.Error):
            return None
        if len(content) > self.config.max_resource_size:
            return None
        resource = Resource(
            url=data_uri,
            content_type=content_type,
            content=content,
            resource_type=self._get_resource_type(content_type),
            encoding="base64" if is_base64 else "7bit",
            original_url=data_uri,
        )
        return self.transform_resource(resource)

    @staticmethod
    def _get_resource_type(content_type: str) -> ResourceType:
        """Compatibility wrapper for shared MIME resource classification."""
        return classify_resource_type(content_type)

    def transform_resource(self, resource: Resource) -> Resource:
        """Apply the first matching user handler to a resource."""
        media_type = resource.content_type.split(";", maxsplit=1)[0].lower()
        handler = next(
            (
                candidate
                for key, candidate in self.config.custom_handlers.items()
                if key.lower()
                in {
                    media_type,
                    resource.resource_type.value,
                    f"{media_type.split('/')[0]}/*",
                }
            ),
            None,
        )
        if handler is None:
            return resource
        transformed = handler(resource)
        if transformed is None:
            return resource
        if isinstance(transformed, Resource):
            return transformed
        return Resource(
            url=resource.url,
            content_type=resource.content_type,
            content=transformed,
            resource_type=resource.resource_type,
            encoding=resource.encoding,
            headers=resource.headers.copy(),
            original_url=resource.original_url,
        )


__all__ = ["ResourceCache", "ResourceManager"]
