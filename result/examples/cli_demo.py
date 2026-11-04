"""Example CLI for converting an MHTML file with the Python package."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from converter import ConversionProfile, ConverterConfig, MHTMLConverter


def build_argument_parser() -> argparse.ArgumentParser:
    """Build arguments for the package-based example command."""
    parser = argparse.ArgumentParser(description="Convert an MHTML file to HTML")
    parser.add_argument("input", type=Path, help="Input .mhtml or .mht file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path (default: input path with a .html suffix)",
    )
    parser.add_argument(
        "--profile",
        choices=[profile.value for profile in ConversionProfile],
        default=ConversionProfile.STANDARD.value,
    )
    parser.add_argument(
        "--fetch-external",
        action="store_true",
        help="Allow fetching referenced public HTTP(S) resources",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print conversion progress to standard error",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Convert the requested file and report its output path."""
    arguments = build_argument_parser().parse_args(argv)
    config = ConverterConfig(profile=ConversionProfile(arguments.profile))
    config.fetch_external = arguments.fetch_external or config.fetch_external
    if arguments.progress:
        config.progress_callback = lambda message, value: print(
            f"{value:6.1%} {message}", file=sys.stderr
        )

    try:
        with MHTMLConverter(config) as converter:
            output_path, metadata = converter.convert_file(
                arguments.input,
                output_path=arguments.output,
            )
    except (OSError, ValueError) as error:
        print(f"mhtml-converter: {error}", file=sys.stderr)
        return 2

    print(
        f"Saved {metadata['output_size']} bytes to {output_path} "
        f"({metadata['resource_count']} embedded or resolved resources)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
