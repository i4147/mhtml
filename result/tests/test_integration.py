"""
Integration Tests for MHTML Converter

End-to-end tests combining all features.
"""

import pytest

from converter.config import ConversionProfile, ConverterConfig
from converter.converter import MHTMLConverter


class TestIntegration:
    """Integration tests for the complete conversion process."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = ConverterConfig()
        self.converter = MHTMLConverter(self.config)

    def test_complete_conversion_pipeline(self, sample_mhtml_data):
        """Test the complete conversion pipeline."""
        # Convert MHTML to HTML
        result, metadata = self.converter.convert(sample_mhtml_data)

        # Verify result structure
        assert isinstance(result, bytes)
        assert len(result) > 0

        # Verify metadata structure
        assert metadata["original_size"] > 0
        assert metadata["output_size"] > 0
        assert metadata["resource_count"] >= 3
        assert metadata["main_resource_type"] == "html"
        assert metadata["content_type"] == "text/html"
        assert metadata["profile"] == "standard"

        # Verify content
        result_str = result.decode("utf-8", errors="ignore")

        # Check that main content is preserved
        assert "Hello World" in result_str

        # Check that resources are processed (depending on profile)
        if self.config.resource_handling == "inline":
            # Should contain data URIs
            assert (
                "data:text/css;base64," in result_str
                or "data:image/png;base64," in result_str
            )

    def test_different_configurations(self, sample_mhtml_data):
        """Test conversion with different configurations."""
        configurations = [
            ConverterConfig(),  # Standard
            ConverterConfig(profile=ConversionProfile.MINIMAL),
            ConverterConfig(profile=ConversionProfile.SECURE),
            ConverterConfig(profile=ConversionProfile.OPTIMIZED),
            ConverterConfig(profile=ConversionProfile.FULL),
        ]

        for config in configurations:
            converter = MHTMLConverter(config)
            result, metadata = converter.convert(sample_mhtml_data)

            assert isinstance(result, bytes)
            assert len(result) > 0
            assert metadata["profile"] == config.profile.value

    def test_error_recovery(self, sample_mhtml_data):
        """Test error recovery functionality."""
        # Create converter with error recovery enabled
        config = ConverterConfig(error_recovery=True)
        converter = MHTMLConverter(config)

        # Test with invalid data
        invalid_data = b"Invalid data that will cause parsing errors"

        result, metadata = converter.convert(invalid_data)

        # Should still return result due to fallback
        assert isinstance(result, bytes)
        assert "error" in metadata


if __name__ == "__main__":
    pytest.main([__file__])
