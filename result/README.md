# MHTML to HTML converter

A Python 3.11+ converter that combines MIME parsing, resource extraction, CSS and HTML rewriting, and security controls from the four original implementations in this repository. The implementation is available both as an importable package (`converter/`) and as a standalone, consolidated script (`mhtml_converter_consolidated.py`).

## Features

- Parses MHTML/MIME with Python's email parser, including multipart boundaries, transfer encodings, character sets, BOMs, and encoded headers.
- Selects the main HTML part and indexes related assets by `Content-Location` and `Content-ID` (`cid:`).
- Rewrites HTML resource attributes, `srcset`, inline styles, CSS `url()` values, and CSS `@import` references with `lxml` and `tinycss2`.
- Inlines resources as data URIs by default; can retain external URLs or use mixed handling.
- Supports optional external HTTP(S) fetching. Fetching is **disabled by default**; enabled fetches are size-bounded, restricted to public IP addresses, checked on redirects, and subject to optional domain allow/block lists.
- Includes a bounded LRU resource cache, optional disk persistence, retry and timeout controls, and thread-pool resource fetching.
- Provides HTML sanitization, script/style controls, HTML/CSS validation diagnostics, and graceful recovery for malformed input.
- Offers progress callbacks, Loguru logging, configurable conversion profiles, custom resource handlers, and plugin hooks.
- Supports HTML5/XHTML output, conservative minification, file conversion, chunked output APIs, and a single-file command-line tool.

> `convert_stream()` and `iter_convert()` write/yield output incrementally, but the MIME parser still buffers the complete input message (up to `max_input_size`) to resolve related parts correctly. They are not constant-memory streaming parsers. The `compress_output` option enables compact HTML serialization; it does not gzip the output.

## Install

From this directory, install the runtime and test dependencies:

```bash
python -m pip install -r requirements.txt
```

The runtime dependencies are Loguru, lxml, lxml-html-clean, and tinycss2. Pytest is included for running the test suite.

## Quick start: Python API

```python
from pathlib import Path

from converter import ConverterConfig, MHTMLConverter

source = Path("message.mhtml")
with MHTMLConverter(ConverterConfig()) as converter:
    output_path, metadata = converter.convert_file(source)

print(f"Saved {metadata['output_size']} bytes to {output_path}")
```

`convert_file()` writes `message.html` beside `message.mhtml` when no output path is supplied. For in-memory conversion:

```python
from converter import MHTMLConverter

with MHTMLConverter() as converter:
    html_bytes, metadata = converter.convert(mhtml_bytes)
html_text = html_bytes.decode("utf-8")
```

A converter can also be used with `convert_stream(input_stream, output_stream)` or `iter_convert(mhtml_bytes)` when the caller wants to consume output in chunks. All APIs return conversion metadata where applicable, including byte counts, selected MIME type, extracted MIME metadata, profile, and validation results.

## Single-file command line

The consolidated script has no dependency on the package directory and saves the `.html` file beside the input by default:

```bash
python result/mhtml_converter_consolidated.py archives/message.mhtml
# Creates archives/message.html
```

Specify an output path or select a profile as needed:

```bash
python result/mhtml_converter_consolidated.py message.mhtml --output converted/page.html
python result/mhtml_converter_consolidated.py message.mhtml --profile secure --minify
python result/mhtml_converter_consolidated.py message.mhtml --fetch-external --allow-domain example.com
```

`--fetch-external` opts into network access. Domain allow/block flags can be repeated. The `secure` profile disables external fetching and removes scripts and styles; this is the recommended preset for untrusted MHTML. The `standard` profile preserves content according to its configured script/style settings, so enabling `sanitize_html` alone should not be treated as a substitute for choosing a restrictive profile.

The package-based example CLI is also available:

```bash
cd result
python -m examples.cli_demo message.mhtml
```

## Configuration profiles

`ConverterConfig` accepts a `ConversionProfile` enum or its string value:

| Profile | Intended use | Defaults of note |
| --- | --- | --- |
| `minimal` | Small, simple output | Minification on; no external fetching, scripts, or styles |
| `standard` | General conversion | External fetching off; related resources are inlined |
| `full` | Broad resource capture | External fetching on; mixed resource handling and debug logging |
| `secure` | Restrictive conversion | External fetching, scripts, and styles disabled; minification on |
| `optimized` | Compact output | Minification on; external fetching off; parallel resource handling available |

Profiles provide starting values; instantiate `ConverterConfig` and then change individual options if needed. For example:

```python
from converter import ConversionProfile, ConverterConfig

config = ConverterConfig(profile=ConversionProfile.SECURE)
config.max_input_size = 32 * 1024 * 1024
config.validation = True
```

External fetching is a security-sensitive choice. The fetcher rejects non-HTTP(S), credentials in URLs, local/reserved IPs, disallowed hosts, and unsafe redirects, and enforces configured size limits. For particularly sensitive environments, keep fetching disabled and use an allowlist if it must be enabled.

## Customization

A `ConverterPlugin` can transform input bytes, extracted resources, or final output. `ConverterConfig.custom_handlers` maps a MIME type, resource type, or wildcard such as `image/*` to a resource handler. Progress reporting is available through either the config or a per-call callback:

```python
from converter import ConverterConfig, MHTMLConverter


def show_progress(message: str, value: float) -> None:
    print(f"{value:5.0%} {message}")


config = ConverterConfig(progress_callback=show_progress)
with MHTMLConverter(config) as converter:
    html_bytes, metadata = converter.convert(mhtml_bytes)
```

See `examples/advanced_usage.py` for a plugin example.

## Examples

Run examples as modules from this directory so Python can import `converter`:

```bash
cd result
python -m examples.basic_usage
python -m examples.advanced_usage
python -m examples.cli_demo --help
```

The first two demos write output files beside their scripts.

## Tests and quality checks

Run the test suite from this directory:

```bash
cd result
python -m pytest -q
```

The package is also checked with Ruff, strict mypy, Ty, and Pylint. Example commands (install the checkers separately if needed):

```bash
ruff check converter examples tests mhtml_converter_consolidated.py
mypy --strict --ignore-missing-imports --disable-error-code=import-untyped converter
pylint --extension-pkg-allow-list=lxml.etree converter
# Ty's Python interpreter option may be set to the interpreter used for this environment.
ty check converter
```

`arena/consolidated_converter.py` is the original repository helper. The current standalone deliverable is `mhtml_converter_consolidated.py`; when changing converter behavior, keep the package and standalone copy aligned.
