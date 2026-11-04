"""
Tests for Resource Manager

Tests combining features from all existing implementations.
"""

import base64

import pytest

from converter.config import ConverterConfig
from converter.parser import Resource, ResourceType
from converter.resource_manager import ResourceCache, ResourceManager


class TestResourceCache:
    """Test resource cache functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cache = ResourceCache(max_size=5)

    def test_cache_put_get(self):
        """Test cache put and get operations."""
        resource = Resource(
            url="http://example.com/test.png",
            content_type="image/png",
            content=b"test content",
            resource_type=ResourceType.IMAGE,
        )

        # Put in cache
        self.cache.put("http://example.com/test.png", resource)

        # Get from cache
        cached = self.cache.get("http://example.com/test.png")
        assert cached is not None
        assert cached.content == b"test content"
        assert cached.url == "http://example.com/test.png"

    def test_cache_eviction(self):
        """Test cache eviction when full."""
        # Fill cache
        for i in range(5):
            resource = Resource(
                url=f"http://example.com/test{i}.png",
                content_type="image/png",
                content=f"content{i}".encode(),
                resource_type=ResourceType.IMAGE,
            )
            self.cache.put(f"http://example.com/test{i}.png", resource)

        # Add one more (should evict oldest)
        resource6 = Resource(
            url="http://example.com/test6.png",
            content_type="image/png",
            content=b"content6",
            resource_type=ResourceType.IMAGE,
        )
        self.cache.put("http://example.com/test6.png", resource6)

        # First resource should be evicted
        assert self.cache.get("http://example.com/test0.png") is None
        # Last resource should be present
        assert self.cache.get("http://example.com/test6.png") is not None


class TestResourceManager:
    """Test resource manager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = ConverterConfig()
        self.manager = ResourceManager(self.config)

    def test_normalize_url(self):
        """Test URL normalization."""
        # Relative URL
        normalized = self.manager._normalize_url(
            "style.css", "http://example.com/index.html"
        )
        assert normalized == "http://example.com/style.css"

        # Absolute URL
        normalized = self.manager._normalize_url(
            "http://other.com/style.css", "http://example.com/index.html"
        )
        assert normalized == "http://other.com/style.css"

        # Data URI (should remain unchanged)
        normalized = self.manager._normalize_url(
            "data:text/css;base64,...", "http://example.com/"
        )
        assert normalized == "data:text/css;base64,..."

        # CID reference
        normalized = self.manager._normalize_url("cid:image123", "http://example.com/")
        assert normalized == "cid:image123"

    def test_convert_to_data_uri(self):
        """Test conversion to data URI."""
        resource = Resource(
            url="http://example.com/test.png",
            content_type="image/png",
            content=b"test content",
            resource_type=ResourceType.IMAGE,
        )

        data_uri = self.manager._convert_to_data_uri(resource)

        assert data_uri.startswith("data:image/png;base64,")
        expected_b64 = base64.b64encode(b"test content").decode("ascii")
        assert data_uri.endswith(expected_b64)

    def test_guess_content_type(self):
        """Test content type guessing."""
        # From URL extension
        content_type = self.manager._guess_content_type(
            "http://example.com/style.css", b""
        )
        assert content_type == "text/css"

        # From content inspection
        content_type = self.manager._guess_content_type(
            "http://example.com/unknown", b"<html><body>Test</body></html>"
        )
        assert content_type == "text/html"

        # Fallback
        content_type = self.manager._guess_content_type(
            "http://example.com/unknown", b"unknown content"
        )
        assert content_type == "application/octet-stream"


if __name__ == "__main__":
    pytest.main([__file__])
