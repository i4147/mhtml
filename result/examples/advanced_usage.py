"""Demonstrate profiles, progress callbacks, and a converter plugin."""

from pathlib import Path
from typing import Any

from converter import (
    ConversionProfile,
    ConverterConfig,
    ConverterPlugin,
    MHTMLConverter,
)

SAMPLE_MHTML = b"""Subject: Advanced MHTML example
MIME-Version: 1.0
Content-Type: multipart/related; boundary=advanced-boundary

--advanced-boundary
Content-Type: text/html; charset=utf-8
Content-Location: https://example.test/page.html

<!doctype html>
<html><head><title>Advanced example</title></head>
<body><h1>Profile and plugin demo</h1><p>Embedded content is retained.</p></body></html>
--advanced-boundary--
"""


class ConversionNotePlugin(ConverterPlugin):
    """Append a small HTML comment after a successful conversion."""

    def after_convert(self, output: bytes, metadata: dict[str, Any]) -> bytes:
        """Append a fixed demonstration note to the generated HTML."""
        del metadata
        return output + b"\n<!-- Added by the advanced-usage plugin. -->\n"


def report_progress(message: str, progress: float) -> None:
    """Print progress milestones emitted by the converter."""
    print(f"{progress:>5.0%}  {message}")


def main() -> None:
    """Run the secure profile with a progress callback and a plugin."""
    output_path = Path(__file__).with_name("advanced_output.html")
    config = ConverterConfig(
        profile=ConversionProfile.SECURE,
        progress_callback=report_progress,
        plugins=[ConversionNotePlugin()],
    )

    with MHTMLConverter(config) as converter:
        html_bytes, metadata = converter.convert(SAMPLE_MHTML)

    output_path.write_bytes(html_bytes)
    print(f"Profile: {metadata['profile']}")
    print(f"Validation: {metadata['validation']['valid']}")
    print(f"Saved output to {output_path}")


if __name__ == "__main__":
    main()
