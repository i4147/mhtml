"""Demonstrate in-memory MHTML conversion and writing an HTML file."""

from pathlib import Path

from converter import ConverterConfig, MHTMLConverter

SAMPLE_MHTML = b"""Subject: Basic MHTML example
MIME-Version: 1.0
Content-Type: multipart/related; boundary=basic-boundary

--basic-boundary
Content-Type: text/html; charset=utf-8
Content-Location: https://example.test/index.html

<!doctype html>
<html><head><title>Basic example</title></head>
<body><h1>Hello from MHTML</h1><p>The converter keeps this text.</p></body></html>
--basic-boundary--
"""


def main() -> None:
    """Convert a small in-memory message and save the resulting HTML."""
    output_path = Path(__file__).with_name("basic_output.html")
    with MHTMLConverter(ConverterConfig()) as converter:
        html_bytes, metadata = converter.convert(SAMPLE_MHTML)

    output_path.write_bytes(html_bytes)
    print(f"Converted {metadata['original_size']} input bytes")
    print(f"Wrote {metadata['output_size']} HTML bytes to {output_path}")
    print(f"Main MIME type: {metadata['content_type']}")


if __name__ == "__main__":
    main()
