"""
Test Configuration

Pytest configuration for MHTML converter tests.
"""

import pytest

from converter.config import ConversionProfile, ConverterConfig


@pytest.fixture
def default_config() -> ConverterConfig:
    """Fixture for default configuration."""
    return ConverterConfig()


@pytest.fixture
def minimal_config() -> ConverterConfig:
    """Fixture for minimal configuration."""
    config = ConverterConfig()
    config.apply_profile(ConversionProfile.MINIMAL)
    return config


@pytest.fixture
def secure_config() -> ConverterConfig:
    """Fixture for secure configuration."""
    config = ConverterConfig()
    config.apply_profile(ConversionProfile.SECURE)
    return config


@pytest.fixture
def sample_mhtml_data() -> bytes:
    """Fixture for sample MHTML data."""
    # Simple MHTML structure for testing
    return b"""Subject: Test MHTML
MIME-Version: 1.0
Content-Type: multipart/related; boundary="boundary123"

--boundary123
Content-Type: text/html
Content-Location: http://example.com/index.html

<html>
<head>
    <title>Test Page</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <h1>Hello World</h1>
    <img src="image.png" alt="Test Image">
    <script src="script.js"></script>
</body>
</html>

--boundary123
Content-Type: text/css
Content-Location: http://example.com/style.css
Content-Transfer-Encoding: base64

Ym9keSB7IGJhY2tncm91bmQ6ICNmZmY7IH0=

--boundary123
Content-Type: image/png
Content-Location: http://example.com/image.png
Content-Transfer-Encoding: base64

iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==

--boundary123
Content-Type: application/javascript
Content-Location: http://example.com/script.js
Content-Transfer-Encoding: base64

Y29uc29sZS5sb2coIkhlbGxvIFdvcmxkISIpOw==

--boundary123--
"""


@pytest.fixture
def sample_mhtml_file(tmp_path, sample_mhtml_data) -> str:
    """Fixture for sample MHTML file."""
    file_path = tmp_path / "test.mhtml"
    file_path.write_bytes(sample_mhtml_data)
    return str(file_path)
