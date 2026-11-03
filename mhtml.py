import argparse
import base64
import codecs
import contextlib
import glob
import mimetypes
import multiprocessing as mp
import re
import sys
from email.parser import BytesParser
from email.policy import compat32
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Sequence
from urllib.parse import unquote, urljoin
from urllib.request import Request, urlopen
from loguru import logger
from lxml import html as lh
if TYPE_CHECKING:
    import os
MHTML_SUFFIXES: frozenset[str] = frozenset({".mht", ".mhtml"})
POOL_METHODS: tuple[str, ...] = (
    "map",
    "imap",
    "imap_unordered",
    "starmap",
    "apply",
    "apply_async",
)
_UA = "Mozilla/5.0 (compatible; mhtml-to-html)"
_HTML_MIMES = frozenset({"text/html", "application/xhtml+xml"})
_SKIP_PREFIXES = ("data:", "about:", "blob:", "javascript:", "mailto:", "tel:")
_ICON_RELS = frozenset({
    "icon",
    "shortcut",
    "apple-touch-icon",
    "apple-touch-icon-precomposed",
    "mask-icon",
})
_DROP_RELS = frozenset({"preload", "prefetch", "modulepreload", "dns-prefetch", "preconnect", "prerender"})
_DROP_HTTP_EQUIV = frozenset({"content-type", "refresh", "content-security-policy"})
_URL_ATTRS: dict[str, tuple[str, ...]] = {
    "img": ("src",),
    "source": ("src",),
    "video": ("src", "poster"),
    "audio": ("src",),
    "track": ("src",),
    "embed": ("src",),
    "object": ("data",),
    "input": ("src",),
    "body": ("background",),
    "image": ("href", "xlink:href"),
}
_SRCSET_TAGS = frozenset({"img", "source"})
_CSS_URL = re.compile(r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s'"]*))\s*\)""", re.IGNORECASE)
_CSS_IMPORT = re.compile(
    r"""@import\s+(?:url\(\s*)?(?:"([^"]+)"|'([^']+)'|([^)\s;'"]+))\s*\)?\s*([^;]*);""",
    re.IGNORECASE,
)
_CSS_CHARSET = re.compile(rb"""^@charset\s+["']([^"']+)["']""", re.IGNORECASE)
_CLOSING_TAG = re.compile(r"</(style|script)", re.IGNORECASE)
_SRCSET_SPLIT = re.compile(r"\s*,\s+")
_XPATH_EVENT_ATTRS = "//*[@*[starts-with(name(), 'on')]]"
class Resource(NamedTuple):
    mime: str
    charset: Optional[str]
    data: bytes
def _safe(text: str) -> str:
    return _CLOSING_TAG.sub(r"<\\/\1", text)
def _decode(res: Resource) -> str:
    enc = res.charset
    if not enc and res.mime == "text/css":
        m = _CSS_CHARSET.match(res.data)
        enc = m.group(1).decode("ascii", "ignore") if m else None
    try:
        return res.data.decode(enc or "utf-8-sig", "replace")
    except LookupError:
        return res.data.decode("utf-8-sig", "replace")
def _data_uri(res: Resource, url: str) -> str:
    mime = res.mime
    if not mime or mime == "application/octet-stream":
        mime = mimetypes.guess_type(url)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(res.data).decode('ascii')}"
def parse_mhtml(raw: bytes) -> tuple[Resource, str, dict[str, Optional[Resource]]]:
    msg = BytesParser(policy=compat32).parsebytes(raw)
    resources: dict[str, Optional[Resource]] = {}
    root: Optional[Resource] = None
    root_url = ""
    for part in msg.walk():
        if part.is_multipart():
            continue
        res = Resource(
            part.get_content_type(),
            part.get_content_charset(),
            part.get_payload(decode=True) or b"",
        )
        url = "".join(str(part.get("Content-Location", "")).split())
        cid = str(part.get("Content-ID", "")).strip().strip("<>")
        if url:
            resources.setdefault(url, res)
        if cid:
            resources.setdefault("cid:" + cid, res)
        if root is None and res.mime in _HTML_MIMES:
            root = res
            root_url = url or "".join(str(msg.get("Snapshot-Content-Location", "")).split())
    if root is None:
        msg_0 = "no HTML part found in MHTML archive"
        raise ValueError(msg_0)
    return root, root_url, resources
class _Converter:
    __slots__ = ("fetch", "res", "scripts", "stack", "timeout", "uris")
    def __init__(
        self,
        resources: dict[str, Optional[Resource]],
        scripts: bool,
        fetch: bool,
        timeout: float,
    ) -> None:
        self.res = resources
        self.scripts = scripts
        self.fetch = fetch
        self.timeout = timeout
        self.uris: dict[str, str] = {}
        self.stack: set[str] = set()
    def download(self, url: str) -> Optional[Resource]:
        res: Optional[Resource] = None
        try:
            with urlopen(Request(url, headers={"User-Agent": _UA}), timeout=self.timeout) as r:
                head = r.headers
                res = Resource(head.get_content_type(), head.get_content_charset(), r.read())
        except Exception as e:
            logger.warning("fetch failed {}: {}", url, e)
        self.res[url] = res
        return res
    def lookup(self, url: str) -> Optional[Resource]:
        url = url.partition("#")[0]
        if url in self.res:
            return self.res[url]
        alt = unquote(url)
        if alt in self.res:
            return self.res[alt]
        if self.fetch and url.startswith(("http://", "https://")):
            return self.download(url)
        return None
    def inline(self, ref: str, base: str) -> str:
        ref = ref.strip()
        if not ref or ref[0] == "#" or ref.lower().startswith(_SKIP_PREFIXES):
            return ref
        url = urljoin(base, ref)
        bare, _, frag = url.partition("#")
        uri = self.uris.get(bare)
        if uri is None:
            res = self.lookup(bare)
            if res is None:
                return url
            uri = self.uris[bare] = _data_uri(res, bare)
        return f"{uri}#{frag}" if frag else uri
    def srcset(self, value: str, base: str) -> str:
        out: list[str] = []
        for item in _SRCSET_SPLIT.split(value.strip()):
            bits = item.split(None, 1)
            if bits:
                out.append(" ".join([self.inline(bits[0].rstrip(","), base), *bits[1:]]))
        return ", ".join(out)
    def css(self, text: str, base: str, depth: int = 0) -> str:
        if depth < 8 and "@import" in text.lower():
            text = _CSS_IMPORT.sub(lambda m: self._css_import(m, base, depth), text)
        return _CSS_URL.sub(lambda m: self._css_url(m, base), text)
    def _css_import(self, m: re.Match[str], base: str, depth: int) -> str:
        ref = m.group(1) or m.group(2) or m.group(3)
        media = m.group(4).strip()
        url = urljoin(base, ref)
        res = self.lookup(url)
        if res is None:
            return f'@import url("{url}"){" " + media if media else ""};'
        body = self.css(_decode(res), url, depth + 1)
        return f"@media {media}{{{body}}}" if media else body
    def _css_url(self, m: re.Match[str], base: str) -> str:
        ref = m.group(1) or m.group(2) or m.group(3) or ""
        new = self.inline(ref, base)
        if new == ref:
            return m.group(0)
        return 'url("%s")' % new.replace('"', "%22")
    def document(self, res: Resource, base: str) -> bytes:
        enc = res.charset or "utf-8"
        try:
            codecs.lookup(enc)
        except LookupError:
            enc = "utf-8"
        parser = lh.HTMLParser(encoding=enc, huge_tree=True)
        doc = lh.document_fromstring(res.data, parser=parser)
        for b in doc.xpath("//base"):
            href = b.attrib.pop("href", None)
            if href:
                base = urljoin(base, href)
            if not b.attrib:
                b.drop_tree()
        drops: list[Any] = []
        has_charset = False
        scripts = self.scripts
        for el in doc.iter():
            tag = el.tag
            if not isinstance(tag, str):
                continue
            attrs = el.attrib
            style = attrs.get("style")
            if style and "url(" in style.lower():
                attrs["style"] = self.css(style, base)
            if tag in {"a", "area"}:
                href = attrs.get("href")
                if href:
                    low = href.lstrip().lower()
                    if low.startswith("javascript:"):
                        if not scripts:
                            del attrs["href"]
                    elif low and low[0] != "#" and not low.startswith(_SKIP_PREFIXES):
                        attrs["href"] = urljoin(base, href.strip())
            elif tag == "link":
                href = attrs.get("href")
                if not href:
                    continue
                rel = set(attrs.get("rel", "").lower().split())
                if "stylesheet" in rel:
                    if "alternate" in rel:
                        drops.append(el)
                        continue
                    url = urljoin(base, href.strip())
                    found = self.lookup(url)
                    if found is None:
                        attrs["href"] = url
                        attrs.pop("integrity", None)
                        attrs.pop("crossorigin", None)
                    else:
                        media = attrs.get("media")
                        attrs.clear()
                        if media:
                            attrs["media"] = media
                        el.tag = "style"
                        el.text = _safe(self.css(_decode(found), url))
                elif rel & _DROP_RELS:
                    drops.append(el)
                elif rel & _ICON_RELS:
                    attrs["href"] = self.inline(href, base)
                    attrs.pop("integrity", None)
                    attrs.pop("crossorigin", None)
            elif tag == "style":
                if el.text:
                    el.text = _safe(self.css(el.text, base))
            elif tag == "script":
                if not scripts:
                    drops.append(el)
                    continue
                src = attrs.get("src")
                if src:
                    url = urljoin(base, src.strip())
                    found = self.lookup(url)
                    if found is None:
                        attrs["src"] = url
                    else:
                        del attrs["src"]
                        el.text = _safe(_decode(found))
                for k in ("integrity", "crossorigin", "nonce"):
                    attrs.pop(k, None)
            elif tag in {"iframe", "frame"}:
                src = attrs.get("src")
                if not src or "srcdoc" in attrs:
                    continue
                url = urljoin(base, src.strip())
                found = self.lookup(url)
                if found is None:
                    attrs["src"] = url
                elif found.mime in _HTML_MIMES and url not in self.stack:
                    self.stack.add(url)
                    try:
                        inner = self.document(found, url)
                    except Exception as e:
                        logger.warning("frame failed {}: {}", url, e)
                        attrs["src"] = url
                    else:
                        if tag == "iframe":
                            del attrs["src"]
                            attrs["srcdoc"] = inner.decode("utf-8")
                        else:
                            attrs["src"] = "data:text/html;charset=utf-8;base64," + base64.b64encode(inner).decode(
                                "ascii"
                            )
                    finally:
                        self.stack.discard(url)
                else:
                    attrs["src"] = _data_uri(found, url)
            elif tag == "meta":
                if "charset" in attrs:
                    attrs["charset"] = "utf-8"
                    has_charset = True
                elif attrs.get("http-equiv", "").strip().lower() in _DROP_HTTP_EQUIV:
                    drops.append(el)
            else:
                names = _URL_ATTRS.get(tag)
                if names is None:
                    continue
                for name in names:
                    value = attrs.get(name)
                    if value:
                        attrs[name] = self.inline(value, base)
                if tag in _SRCSET_TAGS:
                    value = attrs.get("srcset")
                    if value:
                        attrs["srcset"] = self.srcset(value, base)
        for el in drops:
            el.drop_tree()
        if not scripts:
            for el in doc.xpath(_XPATH_EVENT_ATTRS):
                for k in [k for k in el.attrib if k.startswith("on")]:
                    del el.attrib[k]
        if not has_charset:
            head = doc.find("head")
            if head is None:
                head = doc.makeelement("head")
                doc.insert(0, head)
            head.insert(0, doc.makeelement("meta", charset="utf-8"))
        doctype = doc.getroottree().docinfo.doctype
        return lh.tostring(doc, encoding="utf-8", method="html", doctype=doctype or "<!DOCTYPE html>")
def _convert(raw: bytes, scripts: bool, fetch: bool, timeout: float) -> bytes:
    root, url, resources = parse_mhtml(raw)
    converter = _Converter(resources, scripts, fetch, timeout)
    converter.stack.add(url)
    return converter.document(root, url)
def convert(
    mhtml: "bytes | str | os.PathLike[str]",
    *,
    enable_scripts: bool = False,
    fetch_missing_resources: bool = False,
    timeout: float = 15.0,
) -> str:
    raw = mhtml if isinstance(mhtml, bytes) else Path(mhtml).read_bytes()
    return _convert(raw, enable_scripts, fetch_missing_resources, timeout).decode("utf-8")
def convert_file(
    src: "str | os.PathLike[str]",
    out: "str | os.PathLike[str] | None" = None,
    enable_scripts: bool = False,
    fetch_missing_resources: bool = False,
    timeout: float = 15.0,
    remove: bool = False,
    skip_existing: bool = False,
) -> bool:
    src = Path(src)
    dst = Path(out) if out else src.with_suffix(".html")
    tmp = dst.with_name(dst.name + ".tmp")
    try:
        if dst.absolute() == src.absolute():
            msg = "input and output are the same file"
            raise ValueError(msg)
        if skip_existing and dst.exists():
            logger.info("skipped (exists) {}", dst)
            return True
        data = _convert(src.read_bytes(), enable_scripts, fetch_missing_resources, timeout)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        tmp.replace(dst)
        if remove:
            src.unlink()
        logger.info("{} -> {}", src, dst)
        return True
    except Exception as e:
        logger.error("{}: {}: {}", src, type(e).__name__, e)
        logger.opt(exception=True).debug("traceback for {}", src)
        with contextlib.suppress(OSError):
            tmp.unlink()
        return False
def _run(job: Sequence[Any]) -> bool:
    return convert_file(*job)
def _init_worker(worker_logger: Any) -> None:
    global logger
    logger = worker_logger
def collect(inputs: Sequence[str]) -> list[Path]:
    found: dict[Path, None] = {}
    def add_file(p: Path) -> None:
        found.setdefault(p.absolute(), None)
    def add_dir(p: Path) -> None:
        for f in p.rglob("*"):
            if f.suffix.lower() in MHTML_SUFFIXES and f.is_file():
                add_file(f)
    for item in inputs or ["."]:
        p = Path(item)
        if p.is_dir():
            add_dir(p)
        elif p.is_file():
            add_file(p)
        else:
            hits = glob.glob(item, recursive=True)
            if not hits:
                logger.error("not found: {}", item)
            for hit in hits:
                hp = Path(hit)
                if hp.is_dir():
                    add_dir(hp)
                elif hp.is_file():
                    add_file(hp)
    return list(found)
def run_jobs(jobs: Sequence[tuple[Any, ...]], workers: int, method: str) -> list[bool]:
    if not jobs:
        return []
    workers = max(1, min(workers, len(jobs)))
    if workers == 1:
        return [_run(j) for j in jobs]
    chunk = max(1, len(jobs) // (workers * 4))
    with mp.Pool(workers, initializer=_init_worker, initargs=(logger,)) as pool:
        if method == "map":
            return pool.map(_run, jobs, chunk)
        if method == "imap":
            return list(pool.imap(_run, jobs, chunk))
        if method == "imap_unordered":
            return list(pool.imap_unordered(_run, jobs, chunk))
        if method == "starmap":
            return pool.starmap(convert_file, jobs, chunk)
        if method == "apply":
            return [pool.apply(convert_file, j) for j in jobs]
        pending = [pool.apply_async(convert_file, j) for j in jobs]
        return [r.get() for r in pending]
def _setup_logging(verbose: bool, quiet: bool, log_file: Optional[Path]) -> None:
    logger.remove()
    level = "DEBUG" if verbose else ("ERROR" if quiet else "INFO")
    logger.add(
        sys.stderr,
        level=level,
        enqueue=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}",
    )
    if log_file:
        logger.add(log_file, level="DEBUG", enqueue=True, rotation="10 MB", encoding="utf-8")
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mhtml-to-html",
        description="Convert MHTML files to single HTML files. "
        "Without input, converts all .mht/.mhtml files in the current directory recursively.",
    )
    p.add_argument(
        "inputs",
        nargs="*",
        metavar="input",
        help="MHTML files, directories or wildcards",
    )
    p.add_argument("-o", "--output", type=Path, help="output HTML file (single input only)")
    p.add_argument("--enable-scripts", action="store_true", help="keep scripts (default: removed)")
    p.add_argument(
        "--fetch-missing-resources",
        action="store_true",
        help="download resources absent from the archive",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "-r",
        "--remove",
        action="store_true",
        help="delete original after successful conversion",
    )
    p.add_argument("-w", "--workers", type=int, default=4, help="worker processes (default: 4)")
    p.add_argument(
        "--pool-method",
        choices=POOL_METHODS,
        default="map",
        help="multiprocessing pool method (default: map)",
    )
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="skip files whose .html already exists",
    )
    p.add_argument("--timeout", type=float, default=15.0, help="network timeout in seconds")
    p.add_argument("--log-file", type=Path, help="also write logs to this file")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging with tracebacks")
    p.add_argument("-q", "--quiet", action="store_true", help="only log errors")
    return p
def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose, args.quiet, args.log_file)
    files = collect(args.inputs)
    if not files:
        logger.warning("no MHTML files found")
        logger.complete()
        return 0
    if args.output and len(files) > 1:
        logger.warning("--output ignored: multiple inputs")
        args.output = None
    jobs = [
        (
            f,
            args.output or None,
            args.enable_scripts,
            args.fetch_missing_resources,
            args.timeout,
            args.remove,
            args.skip_existing,
        )
        for f in files
    ]
    results = run_jobs(jobs, args.workers, args.pool_method)
    ok = sum(results)
    logger.info("{}/{} converted", ok, len(jobs))
    logger.complete()
    return 0 if ok == len(jobs) else 1
if __name__ == "__main__":
    raise SystemExit(main())
