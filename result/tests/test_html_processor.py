"""
Tests for HTML Processor

Tests combining features from all existing implementations.
"""

import pytest

from converter.config import ConverterConfig
from converter.html_processor import HTMLNode, HTMLProcessor, HTMLTreeParser
from converter.parser import Resource, ResourceType


class TestHTMLTreeParser:
    """Test HTML tree parser functionality."""

    def test_parse_basic_html(self):
        """Test basic HTML parsing."""
        parser = HTMLTreeParser()
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test</title>
        </head>
        <body>
            <h1>Hello World</h1>
            <p>Paragraph text</p>
            <!-- Comment -->
        </body>
        </html>
        """

        parser.feed(html)

        # Check root
        assert parser.root.is_doctype is False
        assert len(parser.root.children) == 1

        # Check HTML tag
        html_node = parser.root.children[0]
        assert html_node.tag == "html"
        assert len(html_node.children) == 2  # head, body

        # Check head
        head_node = html_node.children[0]
        assert head_node.tag == "head"
        assert len(head_node.children) == 1

        # Check title
        title_node = head_node.children[0]
        assert title_node.tag == "title"
        assert len(title_node.children) == 1
        assert title_node.children[0].is_text is True
        assert title_node.children[0].text == "Test"

        # Check body
        body_node = html_node.children[1]
        assert body_node.tag == "body"
        assert len(body_node.children) == 3  # h1, p, comment

        # Check h1
        h1_node = body_node.children[0]
        assert h1_node.tag == "h1"
        assert h1_node.children[0].text == "Hello World"

        # Check p
        p_node = body_node.children[1]
        assert p_node.tag == "p"
        assert p_node.children[0].text == "Paragraph text"

        # Check comment
        comment_node = body_node.children[2]
        assert comment_node.is_comment is True
        assert comment_node.text == " Comment "

    def test_to_string(self):
        """Test node to string conversion."""
        # Create simple tree
        root = HTMLNode()

        html_node = HTMLNode(tag="html")
        root.add_child(html_node)

        head_node = HTMLNode(tag="head")
        html_node.add_child(head_node)

        title_node = HTMLNode(tag="title")
        head_node.add_child(title_node)

        title_text = HTMLNode(is_text=True, text="Test")
        title_node.add_child(title_text)

        body_node = HTMLNode(tag="body")
        html_node.add_child(body_node)

        h1_node = HTMLNode(tag="h1")
        body_node.add_child(h1_node)

        h1_text = HTMLNode(is_text=True, text="Hello")
        h1_node.add_child(h1_text)

        # Convert to string
        result = root.to_string()

        expected = (
            "<html><head><title>Test</title></head><body><h1>Hello</h1></body></html>"
        )
        assert result == expected


class TestHTMLProcessor:
    """Test HTML processor functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = ConverterConfig()
        self.processor = HTMLProcessor(self.config)

    def test_rewrite_html_basic(self):
        """Test basic HTML rewriting."""
        html = """
        <html>
        <head>
            <link rel="stylesheet" href="style.css">
        </head>
        <body>
            <img src="image.png" alt="Test">
            <script src="script.js"></script>
            <a href="http://example.com">Link</a>
        </body>
        </html>
        """

        # Create resource map
        resource_map = {
            "http://example.com/style.css": Resource(
                url="http://example.com/style.css",
                content_type="text/css",
                content=b"body { background: #fff; }",
                resource_type=ResourceType.CSS,
            ),
            "http://example.com/image.png": Resource(
                url="http://example.com/image.png",
                content_type="image/png",
                content=b"image content",
                resource_type=ResourceType.IMAGE,
            ),
            "http://example.com/script.js": Resource(
                url="http://example.com/script.js",
                content_type="application/javascript",
                content=b"console.log('Hello');",
                resource_type=ResourceType.SCRIPT,
            ),
        }

        # Rewrite with inline resources
        self.config.resource_handling = "inline"
        result = self.processor.rewrite_html(html, "http://example.com/", resource_map)

        # Check that URLs are converted to data URIs
        assert "data:text/css;base64," in result
        assert "data:image/png;base64," in result
        assert "data:application/javascript;base64," in result

    def test_sanitizes_scriptable_urls_and_unsafe_svg_data_uris(self):
        """Remove active URL schemes but preserve ordinary raster images."""
        content = """<html><body>
        <a href="java&#x73;cript:alert(1)">unsafe</a>
        <img src="data:image/svg+xml;base64,PHN2Zz4=" alt="svg">
        <img src="data:image/png;base64,aW1hZ2U=" alt="png">
        </body></html>"""

        result = self.processor.rewrite_html(content, "https://example.test/", {})

        assert "javascript:" not in result.lower()
        assert "data:image/svg+xml" not in result.lower()
        assert "data:image/png;base64,aW1hZ2U=" in result

    def test_rewrite_with_regex_fallback(self):
        """Test regex fallback rewriting."""
        # Create processor with broken parser simulation
        processor = HTMLProcessor(self.config)

        html = '<img src="image.png">'
        resource_map = {
            "http://example.com/image.png": Resource(
                url="http://example.com/image.png",
                content_type="image/png",
                content=b"image content",
                resource_type=ResourceType.IMAGE,
            )
        }

        # Rewrite
        self.config.resource_handling = "inline"
        result = processor._rewrite_with_regex(
            html, "http://example.com/", resource_map
        )

        assert "data:image/png;base64," in result


if __name__ == "__main__":
    pytest.main([__file__])
