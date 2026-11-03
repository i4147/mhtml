import argparse
import base64
import logging
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Iterable
LOG = logging.getLogger("mhtml_to_html")
MHTML_EXTENSIONS = {".mht", ".mhtml"}
URL_RE = re.compile(
    r"""(?P<prefix>\b(?:src|href|poster|background|action|data)\s*=\s*)"""
    r"""(?P<quote>["'])(?P<url>.*?)(?P=quote)"""
    r"""|"""
    r"""(?P<cssprefix>\burl\(\s*)"""
    r"""(?P<cssquote>["']?)(?P<cssurl>[^)'"]*)"""
    r"""(?P=cssquote)(?P<csssuffix>\s*\))""",
    re.IGNORECASE | re.DOTALL,
)
SCRIPT_RE = re.compile(
    r"<script\b[^>]*>.*?</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
EVENT_RE = re.compile(
    r"""\s+on[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""",
    re.IGNORECASE,
)
JAVASCRIPT_URL_RE = re.compile(
    r"""(["'])\s*javascript:[^"']*\1""",
    re.IGNORECASE,
)
def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    url = urllib.parse.unquote(url)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() in {"http", "https"}:
        return urllib.parse.urlunsplit((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.query,
            "",
        ))
    return url
def get_content_type(part) -> str:
    return part.get_content_type().lower()
def make_data_uri(content_type: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{encoded}"
def get_part_bytes(part) -> bytes:
    payload = part.get_payload(decode=True)
    if payload is not None:
        return payload
    raw = part.get_payload()
    if isinstance(raw, str):
        charset = part.get_content_charset() or "utf-8"
        return raw.encode(charset, errors="replace")
    if isinstance(raw, bytes):
        return raw
    return b""
def get_part_text(part) -> str:
    data = get_part_bytes(part)
    charset = part.get_content_charset() or "utf-8"
    try:
        return data.decode(charset)
    except (LookupError, UnicodeDecodeError):
        return data.decode("utf-8", errors="replace")
def get_part_locations(part) -> set[str]:
    locations: set[str] = set()
    content_id = part.get("Content-ID")
    if content_id:
        content_id = str(content_id).strip().strip("<>")
        if content_id:
            locations.add("cid:" + content_id)
            locations.add("cid:" + content_id.lower())
    content_location = part.get("Content-Location")
    if content_location:
        location = str(content_location).strip()
        if location:
            locations.add(location)
            locations.add(normalize_url(location))
    return locations
def extract_html_root(message):
    parts = list(message.walk())
    start = message.get_param("start", header="Content-Type")
    if start:
        start = str(start).strip().strip("<>")
        for part in parts:
            content_id = part.get("Content-ID")
            if content_id and str(content_id).strip().strip("<>") == start:
                if get_content_type(part) == "text/html":
                    return part
    for part in parts:
        if get_content_type(part) == "text/html":
            return part
    raise ValueError("No text/html document found in the MHTML archive")
def parse_mhtml(path: Path):
    with path.open("rb") as file:
        message = BytesParser(policy=policy.default).parse(file)
    root = extract_html_root(message)
    return message, root
def build_resource_map(message, root) -> dict[str, str]:
    resources: dict[str, str] = {}
    for part in message.walk():
        if part.is_multipart() or part is root:
            continue
        content_type = get_content_type(part)
        data = get_part_bytes(part)
        if not data:
            continue
        uri = make_data_uri(content_type, data)
        for location in get_part_locations(part):
            resources[location] = uri
            resources[normalize_url(location)] = uri
            if location.lower().startswith("cid:"):
                resources[location.lower()] = uri
    return resources
def resolve_resource(
    url: str,
    resources: dict[str, str],
    base_url: str = "",
) -> str | None:
    url = url.strip()
    if not url:
        return None
    if url.startswith("#"):
        return None
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() in {
        "data",
        "javascript",
        "mailto",
        "tel",
        "blob",
    }:
        return None
    if url in resources:
        return resources[url]
    normalized = normalize_url(url)
    if normalized in resources:
        return resources[normalized]
    if url.lower().startswith("cid:"):
        cid = url[4:].strip().strip("<>")
        for key in (f"cid:{cid}", f"cid:{cid}".lower()):
            if key in resources:
                return resources[key]
    if base_url:
        absolute = urllib.parse.urljoin(base_url, url)
        if absolute in resources:
            return resources[absolute]
        normalized = normalize_url(absolute)
        if normalized in resources:
            return resources[normalized]
    return None
def fetch_resource(url: str, timeout: float = 10.0) -> str | None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Python-MHTML-Converter/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            data = response.read()
        return make_data_uri(content_type, data)
    except (
        OSError,
        ValueError,
        urllib.error.URLError,
    ) as exc:
        LOG.debug("Unable to fetch %s: %s", url, exc)
        return None
def rewrite_css(
    css: str,
    resources: dict[str, str],
    base_url: str = "",
    fetch_missing: bool = False,
) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group("prefix") is not None:
            prefix = match.group("prefix")
            quote = match.group("quote")
            url = match.group("url")
            replacement = resolve_resource(url, resources, base_url)
            if replacement is None and fetch_missing:
                absolute = urllib.parse.urljoin(base_url, url)
                replacement = fetch_resource(absolute)
            if replacement is None:
                return match.group(0)
            return f"{prefix}{quote}{replacement}{quote}"
        prefix = match.group("cssprefix")
        quote = match.group("cssquote")
        url = match.group("cssurl")
        suffix = match.group("csssuffix")
        replacement = resolve_resource(url, resources, base_url)
        if replacement is None and fetch_missing:
            absolute = urllib.parse.urljoin(base_url, url)
            replacement = fetch_resource(absolute)
        if replacement is None:
            return match.group(0)
        return f"{prefix}{quote}{replacement}{quote}{suffix}"
    return URL_RE.sub(replace, css)
def rewrite_html(
    html: str,
    resources: dict[str, str],
    base_url: str = "",
    enable_scripts: bool = False,
    fetch_missing: bool = False,
) -> str:
    if not enable_scripts:
        html = SCRIPT_RE.sub("", html)
        html = EVENT_RE.sub("", html)
        html = JAVASCRIPT_URL_RE.sub(r"\1#\1", html)
    def replace(match: re.Match[str]) -> str:
        if match.group("prefix") is not None:
            prefix = match.group("prefix")
            quote = match.group("quote")
            url = match.group("url")
            replacement = resolve_resource(url, resources, base_url)
            if replacement is None and fetch_missing:
                absolute = urllib.parse.urljoin(base_url, url)
                replacement = fetch_resource(absolute)
            if replacement is None:
                return match.group(0)
            return f"{prefix}{quote}{replacement}{quote}"
        prefix = match.group("cssprefix")
        quote = match.group("cssquote")
        url = match.group("cssurl")
        suffix = match.group("csssuffix")
        replacement = resolve_resource(url, resources, base_url)
        if replacement is None and fetch_missing:
            absolute = urllib.parse.urljoin(base_url, url)
            replacement = fetch_resource(absolute)
        if replacement is None:
            return match.group(0)
        return f"{prefix}{quote}{replacement}{quote}{suffix}"
    html = URL_RE.sub(replace, html)
    style_element_re = re.compile(
        r"(<style\b[^>]*>)(.*?)(</style\s*>)",
        re.IGNORECASE | re.DOTALL,
    )
    html = style_element_re.sub(
        lambda match: (
            match.group(1)
            + rewrite_css(
                match.group(2),
                resources,
                base_url,
                fetch_missing,
            )
            + match.group(3)
        ),
        html,
    )
    style_attribute_re = re.compile(
        r"""(\bstyle\s*=\s*)(["'])(.*?)(\2)""",
        re.IGNORECASE | re.DOTALL,
    )
    html = style_attribute_re.sub(
        lambda match: (
            match.group(1)
            + match.group(2)
            + rewrite_css(
                match.group(3),
                resources,
                base_url,
                fetch_missing,
            )
            + match.group(4)
        ),
        html,
    )
    return html
def convert_file(
    source: Path,
    destination: Path | None = None,
    *,
    enable_scripts: bool = False,
    fetch_missing: bool = False,
) -> Path:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Input file not found: {source}")
    destination = destination.expanduser().resolve() if destination is not None else source.with_suffix(".html")
    if source == destination:
        raise ValueError("Input and output paths must be different")
    message, root = parse_mhtml(source)
    resources = build_resource_map(message, root)
    html = get_part_text(root)
    base_url = str(root.get("Content-Location", ""))
    html = rewrite_html(
        html,
        resources,
        base_url,
        enable_scripts,
        fetch_missing,
    )
    if not re.search(r"<meta\b[^>]*charset\s*=", html, re.I):
        charset_tag = '<meta charset="utf-8">'
        if re.search(r"<head\b[^>]*>", html, re.I):
            html = re.sub(
                r"(<head\b[^>]*>)",
                lambda match: match.group(1) + charset_tag,
                html,
                count=1,
                flags=re.I,
            )
        else:
            html = "<!doctype html><html><head>" + charset_tag + "</head><body>" + html + "</body></html>"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    LOG.info("%s -> %s", source, destination)
    return destination
def discover_inputs(inputs: Iterable[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for argument in inputs:
        path = Path(argument).expanduser()
        if any(char in argument for char in "*?["):
            matches = sorted(path.parent.glob(path.name))
        else:
            matches = [path]
        for match in matches:
            if match.is_dir():
                candidates = (p for p in match.rglob("*") if p.is_file() and p.suffix.lower() in MHTML_EXTENSIONS)
            elif match.is_file():
                candidates = (match,)
            else:
                LOG.warning("Input not found: %s", match)
                continue
            for candidate in candidates:
                if candidate.suffix.lower() not in MHTML_EXTENSIONS:
                    continue
                resolved = candidate.resolve()
                found[str(resolved)] = resolved
    return sorted(found.values())
def main() -> int:
    parser = argparse.ArgumentParser(description="Convert MHTML/MHT archives to standalone HTML.")
    parser.add_argument(
        "input",
        nargs="*",
        help="MHTML files, wildcard patterns or directories",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output HTML path; only valid with one input file",
    )
    parser.add_argument(
        "--enable-scripts",
        action="store_true",
        help="Preserve JavaScript (disabled by default)",
    )
    parser.add_argument(
        "--fetch-missing-resources",
        action="store_true",
        help="Fetch missing HTTP/HTTPS resources",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    inputs = discover_inputs(args.input or ["."])
    if not inputs:
        LOG.error("No MHTML files found.")
        return 1
    if args.output is not None and len(inputs) != 1:
        parser.error("--output requires exactly one input file")
    failures = 0
    for source in inputs:
        destination = args.output if args.output else None
        try:
            convert_file(
                source,
                destination,
                enable_scripts=args.enable_scripts,
                fetch_missing=args.fetch_missing_resources,
            )
        except Exception:
            failures += 1
            LOG.exception("Failed to convert %s", source)
    LOG.info(
        "Finished: %d succeeded, %d failed",
        len(inputs) - failures,
        failures,
    )
    return 1 if failures else 0
if __name__ == "__main__":
    sys.exit(main())
