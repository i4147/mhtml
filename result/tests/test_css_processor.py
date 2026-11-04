"""
Tests for CSS Processor

Tests combining features from all existing implementations.
"""

import pytest

from converter.config import ConverterConfig
from converter.css_processor import CSSProcessor
from converter.parser import Resource, ResourceType


class TestCSSProcessor:
    """Test CSS processor functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = ConverterConfig()
        self.processor = CSSProcessor(self.config)

    def test_rewrite_css_urls(self):
        """Test CSS URL rewriting."""
        css = """
        body {
            background: url('background.png');
            background-image: url(icon.svg);
            background: url("image.jpg");
        }
        """

        resource_map = {
            "http://example.com/background.png": Resource(
                url="http://example.com/background.png",
                content_type="image/png",
                content=b"png content",
                resource_type=ResourceType.IMAGE,
            ),
            "http://example.com/icon.svg": Resource(
                url="http://example.com/icon.svg",
                content_type="image/svg+xml",
                content=b"svg content",
                resource_type=ResourceType.IMAGE,
            ),
            "http://example.com/image.jpg": Resource(
                url="http://example.com/image.jpg",
                content_type="image/jpeg",
                content=b"jpg content",
                resource_type=ResourceType.IMAGE,
            ),
        }

        # Rewrite with inline resources
        self.config.resource_handling = "inline"
        result = self.processor.rewrite_css(css, "http://example.com/", resource_map)

        # Check that URLs are converted to data URIs
        assert "data:image/png;base64," in result
        assert "data:image/svg+xml;base64," in result
        assert "data:image/jpeg;base64," in result

    def test_rewrite_css_imports(self):
        """Test CSS import rewriting."""
        css = """
        @import url("imported.css");
        @import 'another.css';
        @import url(third.css);
        body { color: red; }
        """

        resource_map = {
            "http://example.com/imported.css": Resource(
                url="http://example.com/imported.css",
                content_type="text/css",
                content=b"h1 { color: blue; }",
                resource_type=ResourceType.CSS,
            ),
            "http://example.com/another.css": Resource(
                url="http://example.com/another.css",
                content_type="text/css",
                content=b"p { margin: 0; }",
                resource_type=ResourceType.CSS,
            ),
            "http://example.com/third.css": Resource(
                url="http://example.com/third.css",
                content_type="text/css",
                content=b"div { padding: 10px; }",
                resource_type=ResourceType.CSS,
            ),
        }

        # Rewrite with inline resources
        self.config.resource_handling = "inline"
        result = self.processor.rewrite_css(css, "http://example.com/", resource_map)

        # Check that imports are converted to data URIs
        assert "data:text/css;base64," in result
        assert "@import url(" in result

    def test_comment_removal(self):
        """Test CSS comment removal."""
        css = """
        /* Comment 1 */
        body { color: red; } /* Comment 2 */
        /* Comment 3
           Multi-line */
        p { margin: 0; }
        """

        result = self.processor.rewrite_css(css, "http://example.com/", {})

        # Comments should be removed
        assert "Comment 1" not in result
        assert "Comment 2" not in result
        assert "Comment 3" not in result

        # Content should remain
        assert "body { color: red; }" in result
        assert "p { margin: 0; }" in result


if __name__ == "__main__":
    pytest.main([__file__])
