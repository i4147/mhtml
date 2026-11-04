"""
Tests for MHTML Converter

Integration tests combining features from all existing implementations.
"""

import pytest

from converter.config import ConversionProfile, ConverterConfig
from converter.converter import MHTMLConverter


class TestMHTMLConverter:
    """Test main converter functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = ConverterConfig()
        self.converter = MHTMLConverter(self.config)

    def test_convert_basic(self, sample_mhtml_data):
        """Test basic conversion."""
        result, metadata = self.converter.convert(sample_mhtml_data)

        # Check result
        assert isinstance(result, bytes)
        assert len(result) > 0

        # Check metadata
        assert "original_size" in metadata
        assert "output_size" in metadata
        assert "resource_count" in metadata
        assert "main_resource_type" in metadata
        assert "content_type" in metadata
        assert "profile" in metadata
        assert "metadata" in metadata
        assert "config" in metadata

        # Check content
        result_str = result.decode("utf-8", errors="ignore")
        assert "Hello World" in result_str

    def test_convert_with_profile(self, sample_mhtml_data):
        """Test conversion with different profiles."""
        # Minimal profile
        config = ConverterConfig()
        config.apply_profile(ConversionProfile.MINIMAL)
        converter = MHTMLConverter(config)

        result, metadata = converter.convert(sample_mhtml_data)
        assert len(result) > 0
        assert metadata["profile"] == "minimal"

        # Secure profile
        config = ConverterConfig()
        config.apply_profile(ConversionProfile.SECURE)
        converter = MHTMLConverter(config)

        result, metadata = converter.convert(sample_mhtml_data)
        assert len(result) > 0
        assert metadata["profile"] == "secure"

    def test_convert_with_progress_callback(self, sample_mhtml_data):
        """Test conversion with progress callback."""
        progress_log = []

        def progress_callback(message, progress):
            progress_log.append((message, progress))

        self.converter.convert(sample_mhtml_data, progress_callback=progress_callback)

        # Check that progress callback was called
        assert len(progress_log) > 0

        # Check progress values
        progress_values = [p[1] for p in progress_log]
        assert all(0.0 <= p <= 1.0 for p in progress_values)

    def test_fallback_conversion(self):
        """Test fallback conversion on error."""
        # Create invalid MHTML data
        invalid_data = b"Invalid MHTML data without proper structure"

        # Should use fallback conversion
        result, metadata = self.converter.convert(invalid_data)

        assert isinstance(result, bytes)
        assert "error" in metadata

    def test_config_integration(self):
        """Test configuration integration."""
        config = ConverterConfig()
        config.minify_html = True
        config.compress_output = True
        config.fetch_external = False

        converter = MHTMLConverter(config)

        # Check that config is passed correctly
        assert converter.config.minify_html is True
        assert converter.config.compress_output is True
        assert converter.config.fetch_external is False


if __name__ == "__main__":
    pytest.main([__file__])
