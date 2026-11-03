import base64
import binascii
import email.utils
import glob as globlib
import json
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import lxml.etree
import lxml.html
import tinycss2
CRLF = 0x0D
LF = 0x0A
HYPHEN_MINUS = 0x2D
SPACE = 0x20
HORIZONTAL_TAB = 0x09
EQUAL_SIGN = 0x3D
LESS_THAN_SIGN = 0x3C
NUL = 0x00
UTF8_CHARSET = "utf-8"
UTF16LE_CHARSET = "utf-16le"
UTF16BE_CHARSET = "utf-16be"
REPLACEMENT_CHARACTER = "\ufffd"
BASE64_ENCODING = "base64"
QUOTED_PRINTABLE_ENCODING = "quoted-printable"
BINARY_ENCODING = "binary"
CONTENT_TYPE_HEADER = "content-type"
CONTENT_TRANSFER_ENCODING_HEADER = "content-transfer-encoding"
CONTENT_ID_HEADER = "content-id"
CONTENT_LOCATION_HEADER = "content-location"
TEXT_HTML_CONTENT_TYPE = "text/html"
JSON_LD_CONTENT_TYPE = "application/ld+json"
APPLICATION_OCTET_STREAM_CONTENT_TYPE = "application/octet-stream"
CID_PROTOCOL = "cid:"
DATA_PROTOCOL = "data:"
HTTP_PROTOCOL = "http:"
HTTPS_PROTOCOL = "https:"
URN_PROTOCOL = "urn:"
INDEX_PAGE_NOT_FOUND_ERROR = "Index page not found"
MISLABELED_DOCUMENT_ANOMALY = "document-mislabeled-as-archive"
UNUSED_BOUNDARY_ANOMALY = "declared-boundary-unused"
MISSING_DELIMITERS_ANOMALY = "multipart-without-delimiters"
UNDECODABLE_BASE64_ANOMALY = "base64-left-encoded"
SYNTHESIZED_INDEX_ANOMALY = "index-synthesized"
DEFAULT_CSP = (
    "default-src 'none'; connect-src 'self' data:; "
    "font-src 'self' data:; img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline' data:; frame-src 'self' data:; "
    "media-src 'self' data:; object-src 'self' data:; "
)
JS_ENABLED_CSP = "script-src 'self' 'unsafe-inline' data:;"
JS_DISABLED_CSP = "script-src 'none';"
ORIGINAL_URL_ATTRIBUTE_PREFIX = "data-original-"
ORIGINAL_URL_FUNCTION_NAME = "--mhtml-to-html-url"
SUBJECT_HEADER = "subject"
DATE_HEADER = "date"
FROM_HEADER = "from"
JSON_LD_PAGE_INFO = {
    "@context": "https://schema.org",
    "@type": "WebPage",
    "additionalProperty": {
        "@type": "PropertyValue",
        "name": "savedBy",
    },
}
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_PARALLEL_REQUESTS = 16
RETRY_BASE_DELAY = 500
MAX_RETRY_DELAY = 5000
TOO_MANY_REQUESTS_STATUS = 429
SERVER_ERROR_STATUS = 500
SERVER_ERROR_MAX_STATUS = 599
URN_ERROR_REGEXP = re.compile(r"^urn:[^:]+:(.+)$")
CID_REGEXP = re.compile(r"^<.+>$")
CHARSET_REGEXP = re.compile(r"charset=([^;]+)", re.IGNORECASE)
QUOTED_PARAMETER_REGEXP = re.compile(r"^([^=]+)=\s*\"([^\"]*)\"\s*$")
HEADER_NAME_REGEXP = re.compile(r"^[!-9;-~]+:")
HEADER_CONTINUATION_REGEXP = re.compile(r"^[ \t]")
REL_REMOVED_VALUES_REGEXP = re.compile(
    r"(preconnect|prerender|dns-prefetch|preload|prefetch|manifest|modulepreload)", re.IGNORECASE
)
REL_SEPARATOR_REGEXP = re.compile(r"\s+")
EVENT_HANDLER_ATTRIBUTES = frozenset((
    "onafterprint",
    "onbeforeprint",
    "onbeforeunload",
    "onhashchange",
    "onlanguagechange",
    "onmessage",
    "onmessageerror",
    "onoffline",
    "ononline",
    "onpagehide",
    "onpageshow",
    "onpopstate",
    "onrejectionhandled",
    "onstorage",
    "onunhandledrejection",
    "onunload",
    "ongamepadconnected",
    "ongamepaddisconnected",
    "onabort",
    "onblur",
    "onfocus",
    "oncancel",
    "onauxclick",
    "onbeforeinput",
    "onbeforetoggle",
    "oncanplay",
    "oncanplaythrough",
    "onchange",
    "onclick",
    "onclose",
    "oncontentvisibilityautostatechange",
    "oncontextlost",
    "oncontextmenu",
    "oncontextrestored",
    "oncopy",
    "oncuechange",
    "oncut",
    "ondblclick",
    "ondrag",
    "ondragend",
    "ondragenter",
    "ondragleave",
    "ondragover",
    "ondragstart",
    "ondrop",
    "ondurationchange",
    "onemptied",
    "onended",
    "onformdata",
    "oninput",
    "oninvalid",
    "onkeydown",
    "onkeypress",
    "onkeyup",
    "onload",
    "onloadeddata",
    "onloadedmetadata",
    "onloadstart",
    "onmousedown",
    "onmouseenter",
    "onmouseleave",
    "onmousemove",
    "onmouseout",
    "onmouseover",
    "onmouseup",
    "onwheel",
    "onpaste",
    "onpause",
    "onplay",
    "onplaying",
    "onprogress",
    "onratechange",
    "onreset",
    "onresize",
    "onscroll",
    "onscrollend",
    "onsecuritypolicyviolation",
    "onseeked",
    "onseeking",
    "onselect",
    "onslotchange",
    "onstalled",
    "onsubmit",
    "onsuspend",
    "ontimeupdate",
    "onvolumechange",
    "onwaiting",
    "onselectstart",
    "onselectionchange",
    "ontoggle",
    "onpointercancel",
    "onpointerdown",
    "onpointerup",
    "onpointermove",
    "onpointerout",
    "onpointerover",
    "onpointerenter",
    "onpointerleave",
    "ongotpointercapture",
    "onlostpointercapture",
    "onanimationcancel",
    "onanimationend",
    "onanimationiteration",
    "onanimationstart",
    "ontransitioncancel",
    "ontransitionend",
    "ontransitionrun",
    "ontransitionstart",
    "onerror",
    "onfullscreenchange",
    "onfullscreenerror",
))
VOID_TAG_NAMES = frozenset((
    "area",
    "base",
    "basefont",
    "bgsound",
    "br",
    "col",
    "command",
    "embed",
    "frame",
    "hr",
    "img",
    "input",
    "keygen",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
))
RAW_TEXT_NODE_TAG_NAMES = frozenset((
    "style",
    "script",
    "xmp",
    "iframe",
    "noembed",
    "noframes",
    "plaintext",
    "noscript",
))
JAVASCRIPT_MIME_TYPE = "text/javascript"
TEXT_ESCAPE_ENTITIES = {"&": "&amp;", "\xa0": "&nbsp;", "<": "&lt;", ">": "&gt;"}
ATTRIBUTE_ESCAPE_ENTITIES = {"&": "&amp;", "\xa0": "&nbsp;", '"': "&quot;"}
INVALID_TAG_NAME_REGEXP = re.compile(r"[\"'>/=]")
CLOSING_TAG_MARKER_REGEXP = re.compile(r"</", re.IGNORECASE)
SELF_CLOSING_TAG_MARKER_REGEXP = re.compile(r"(?<!\\)/>", re.IGNORECASE)
CHARSET_ALIASES = {
    "ks_c_5601-1987": "cp949",
    "ks_c_5601": "cp949",
    "iso-8859-8-i": "iso-8859-8",
    "unicode-1-1-utf-8": "utf-8",
    "unicodefffe": "utf-16be",
    "unicodefeff": "utf-8",
}
_SPECIAL_SCHEMES = frozenset(("http", "https", "ws", "wss", "ftp", "file"))
_DEFAULT_PORTS = {"http": "80", "https": "443", "ws": "80", "wss": "443", "ftp": "21"}
_SVG_ATTRIBUTE_ADJUSTMENTS = {
    "attributename": "attributeName",
    "attributetype": "attributeType",
    "basefrequency": "baseFrequency",
    "baseprofile": "baseProfile",
    "calcmode": "calcMode",
    "clippathunits": "clipPathUnits",
    "diffuseconstant": "diffuseConstant",
    "edgemode": "edgeMode",
    "filterunits": "filterUnits",
    "glyphref": "glyphRef",
    "gradienttransform": "gradientTransform",
    "gradientunits": "gradientUnits",
    "kernelmatrix": "kernelMatrix",
    "kernelunitlength": "kernelUnitLength",
    "keypoints": "keyPoints",
    "keysplines": "keySplines",
    "keytimes": "keyTimes",
    "lengthadjust": "lengthAdjust",
    "limitingconeangle": "limitingConeAngle",
    "markerheight": "markerHeight",
    "markerunits": "markerUnits",
    "markerwidth": "markerWidth",
    "maskcontentunits": "maskContentUnits",
    "maskunits": "maskUnits",
    "numoctaves": "numOctaves",
    "pathlength": "pathLength",
    "patterncontentunits": "patternContentUnits",
    "patterntransform": "patternTransform",
    "patternunits": "patternUnits",
    "pointsatx": "pointsAtX",
    "pointsaty": "pointsAtY",
    "pointsatz": "pointsAtZ",
    "preservealpha": "preserveAlpha",
    "preserveaspectratio": "preserveAspectRatio",
    "primitiveunits": "primitiveUnits",
    "refx": "refX",
    "refy": "refY",
    "repeatcount": "repeatCount",
    "repeatdur": "repeatDur",
    "requiredextensions": "requiredExtensions",
    "requiredfeatures": "requiredFeatures",
    "specularconstant": "specularConstant",
    "specularexponent": "specularExponent",
    "spreadmethod": "spreadMethod",
    "startoffset": "startOffset",
    "stddeviation": "stdDeviation",
    "stitchtiles": "stitchTiles",
    "surfacescale": "surfaceScale",
    "systemlanguage": "systemLanguage",
    "tablevalues": "tableValues",
    "targetx": "targetX",
    "targety": "targetY",
    "textlength": "textLength",
    "viewbox": "viewBox",
    "viewtarget": "viewTarget",
    "xchannelselector": "xChannelSelector",
    "ychannelselector": "yChannelSelector",
    "zoomandpan": "zoomAndPan",
}
def _decode_quoted_printable(data: bytes) -> bytes:
    if 0x3D not in data:
        return data
    result = bytearray()
    length = len(data)
    i = 0
    while i < length:
        if data[i] == 0x3D and i + 2 < length and _is_hex(data[i + 1]) and _is_hex(data[i + 2]):
            result.append(int(data[i + 1 : i + 3], 16))
            i += 3
        else:
            result.append(data[i])
            i += 1
    return bytes(result)
def _is_hex(byte: int) -> bool:
    return 0x30 <= byte <= 0x39 or 0x41 <= byte <= 0x46 or 0x61 <= byte <= 0x66
def _decode_binary(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
def _decode_base64_bytes(value: str) -> bytes | None:
    data = "".join(value.split())
    if len(data) % 4 == 1:
        return None
    data = data.rstrip("=")
    data += "=" * (-len(data) % 4)
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None
def _decode_base64(value: str, charset: str | None) -> str:
    decoded = _decode_base64_bytes(value)
    if decoded is None:
        return value
    return _decode_string(decoded, charset)
def _decode_string(data: bytes, charset: str | None = None) -> str:
    if charset is not None:
        codec = CHARSET_ALIASES.get(charset.strip().lower(), charset.strip())
        try:
            text = data.decode(codec, errors="replace")
        except (LookupError, UnicodeError):
            text = data.decode("utf-8", errors="replace")
        if text.startswith("\ufeff") and _bom_matches(data, charset):
            text = text[1:]
        return text
    text = data.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text
def _bom_matches(data: bytes, charset: str | None) -> bool:
    if charset is None:
        return data.startswith(b"\xef\xbb\xbf")
    charset = charset.strip().lower()
    if charset in ("utf-8", "utf8", "unicode-1-1-utf-8"):
        return data.startswith(b"\xef\xbb\xbf")
    if charset in ("utf-16le", "utf-16"):
        return data.startswith(b"\xff\xfe")
    if charset == "utf-16be":
        return data.startswith(b"\xfe\xff")
    return False
def _decode_mime_header(header: str | None) -> str:
    if not header:
        return ""
    parts = []
    index = 0
    pending_charset = None
    pending_chunks: list[bytes] = []
    def flush_pending():
        nonlocal pending_charset, pending_chunks
        if pending_charset is not None:
            parts.append(_decode_string(b"".join(pending_chunks), pending_charset))
        pending_charset = None
        pending_chunks = []
    while index < len(header):
        start = header.find("=?", index)
        if start == -1:
            break
        text = header[index:start]
        encoded_word = _decode_encoded_word(header, start)
        if encoded_word is None:
            flush_pending()
            parts.append(text + "=?")
            index = start + 2
        else:
            if text and (pending_charset is None or text.strip()):
                flush_pending()
                parts.append(text)
            if pending_charset is not None and pending_charset != encoded_word[0]:
                flush_pending()
            if pending_charset is None:
                pending_charset = encoded_word[0]
                pending_chunks = []
            pending_chunks.append(encoded_word[1])
            index = encoded_word[2]
    flush_pending()
    parts.append(header[index:])
    return "".join(parts)
def _decode_encoded_word(header: str, start: int) -> tuple[str, bytes, int] | None:
    end_charset = header.find("?", start + 2)
    if end_charset == -1:
        return None
    end_encoding = header.find("?", end_charset + 1)
    if end_encoding == -1:
        return None
    end_value = header.find("?=", end_encoding + 1)
    if end_value == -1:
        return None
    charset = header[start + 2 : end_charset].lower()
    encoding = header[end_charset + 1 : end_encoding].lower()
    value = header[end_encoding + 1 : end_value]
    end = end_value + 2
    if encoding == "q":
        return charset, _decode_quoted_printable(value.replace("_", " ").encode("utf-8")), end
    if encoding == "b":
        decoded = _decode_base64_bytes(value)
        return charset, decoded if decoded is not None else value.encode("utf-8"), end
    return None
def _get_charset(content_type: str | None) -> str | None:
    if not content_type:
        return None
    match = CHARSET_REGEXP.search(content_type)
    if match:
        return _remove_quotes(match.group(1)).strip().lower()
    return None
def _get_bom_charset(data: bytes) -> str | None:
    if len(data) >= 3 and data[0] == 0xEF and data[1] == 0xBB and data[2] == 0xBF:
        return UTF8_CHARSET
    if len(data) >= 2 and data[0] == 0xFF and data[1] == 0xFE:
        return UTF16LE_CHARSET
    if len(data) >= 2 and data[0] == 0xFE and data[1] == 0xFF:
        return UTF16BE_CHARSET
    return None
def _remove_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1]
    return value
def _replace_charset(content_type: str, charset: str) -> str:
    return CHARSET_REGEXP.sub(f"charset={charset}", content_type, count=1)
def _is_document(content_type: str | None) -> bool:
    return _test_content_type(content_type, "text/html") or _test_content_type(content_type, "application/xhtml+xml")
def _is_stylesheet(content_type: str | None) -> bool:
    return _test_content_type(content_type, "text/css")
def _is_text(content_type: str | None) -> bool:
    return _test_content_type(content_type, "text/")
def _is_image(content_type: str | None) -> bool:
    return _test_content_type(content_type, "image/")
def _is_plain_text(content_type: str | None) -> bool:
    return _test_content_type(content_type, "text/plain")
def _is_media(content_type: str | None) -> bool:
    return (
        _test_content_type(content_type, "image/")
        or _test_content_type(content_type, "audio/")
        or _test_content_type(content_type, "video/")
        or _test_content_type(content_type, "font/")
    )
def _is_multipart(content_type: str | None) -> bool:
    return _test_content_type(content_type, "multipart/")
def _is_multipart_alternative(content_type: str | None) -> bool:
    return _test_content_type(content_type, "multipart/alternative")
def _test_content_type(content_type: str | None, type_: str) -> bool:
    return bool(content_type) and content_type.lower().startswith(type_)
def _get_boundary(content_type: str) -> str | None:
    params = content_type.split(";")[1:]
    for param in params:
        param = param.strip()
        if param.startswith("boundary="):
            return _remove_quotes(param[9:]).strip()
    return None
def _is_line_feed(line: bytes) -> bool:
    if len(line) == 2:
        return line[0] == CRLF and line[1] == LF
    if len(line) == 1:
        return line[0] == LF
    return False
def _ends_with_crlf(data: bytes) -> bool:
    if len(data) >= 2:
        return data[-2] == CRLF and data[-1] == LF
    if len(data) >= 1:
        return data[-1] == CRLF
    return False
def _ends_with_lf(data: bytes) -> bool:
    return len(data) >= 1 and data[-1] == LF
def _starts_with_boundary(data: bytes) -> bool:
    return len(data) >= 2 and data[0] == HYPHEN_MINUS and data[1] == HYPHEN_MINUS
def _get_media_type(content_type: str | None) -> str | None:
    if not content_type:
        return content_type
    return ";".join(QUOTED_PARAMETER_REGEXP.sub(r"\1=\2", parameter.strip()) for parameter in content_type.split(";"))
def _get_resource_uri(resource: "Resource") -> str:
    media_type = _get_media_type(resource.content_type)
    if media_type is None:
        media_type = "undefined"
    if resource.transfer_encoding == BASE64_ENCODING:
        payload = resource.data if isinstance(resource.data, str) else _decode_binary(resource.data)
    else:
        data = resource.data if isinstance(resource.data, (bytes, bytearray)) else str(resource.data).encode("utf-8")
        payload = _decode_binary(bytes(data))
    return f"data:{media_type};base64,{payload}"
def _remove_dot_segments(path: str) -> str:
    segments = path.split("/")
    output: list[str] = []
    for segment in segments:
        if segment == ".":
            continue
        if segment == "..":
            while output and output[-1] not in ("", ".."):
                output.pop()
            continue
        output.append(segment)
    result = "/".join(output)
    if path.startswith("/") and not result.startswith("/"):
        result = "/" + result
    return result
def _percent_encode(value: str, extra: str) -> str:
    out = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "%":
            if index + 2 < len(value) and _is_hex(ord(value[index + 1])) and _is_hex(ord(value[index + 2])):
                out.append("%")
                index += 1
                continue
            out.append("%25")
            index += 1
            continue
        code = ord(char)
        if code <= 0x20 or code == 0x7F or char in extra or code > 0x7E:
            for byte in char.encode("utf-8"):
                out.append(f"%{byte:02X}")
            index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)
def _encode_path(path: str) -> str:
    return _percent_encode(path, '"<>`?{}')
def _encode_query(query: str) -> str:
    return _percent_encode(query, '"#<>')
def _encode_fragment(fragment: str) -> str:
    return _percent_encode(fragment, '"<>`')
def _normalize_url(url: str, base: str | None = None) -> str:
    if base:
        url = urllib.parse.urljoin(base, url)
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        raise
    if not parts.scheme and not parts.netloc:
        raise ValueError(f"not an absolute URL: {url!r}")
    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    if port is not None and _DEFAULT_PORTS.get(scheme) != str(port):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    if parts.username is not None or parts.password is not None:
        netloc = f"{parts.username or ''}:{parts.password or ''}@{netloc}"
    path = _remove_dot_segments(parts.path)
    if scheme and not parts.netloc and scheme not in _SPECIAL_SCHEMES:
        return f"{scheme}:{_percent_encode(parts.path, '"<>`?#{}')}"
    if scheme in _SPECIAL_SCHEMES and not path and not parts.query and not parts.fragment and scheme != "file":
        path = "/"
    path = _encode_path(path) if path else path
    result = f"{scheme}://{netloc}{path}" if scheme or netloc else path
    if parts.query is not None and "?" in url:
        result += "?" + _encode_query(parts.query)
    if parts.fragment is not None and "#" in url:
        result += "#" + _encode_fragment(parts.fragment)
    return result
def _split_url_fragment(url: str, base: str | None = None) -> tuple[str, str]:
    full = _normalize_url(url, base)
    parts = urllib.parse.urlsplit(full)
    if parts.fragment:
        without = full[: len(full) - len(parts.fragment) - 1]
        return without, f"#{parts.fragment}"
    return full, ""
def normalize_location(value: str) -> str:
    try:
        return _normalize_url(value)
    except ValueError:
        return value
def _resolve_path(path: str, base: str | None) -> str:
    if base and not path.startswith(DATA_PROTOCOL):
        try:
            return _normalize_url(path, base)
        except ValueError:
            if path.startswith("//"):
                match = re.match(r"^[^:]+", base)
                if match:
                    return f"{match.group(0)}:{path}"
                return path
            return path
    return path
class Resource:
    __slots__ = (
        "id",
        "transfer_encoding",
        "content_type",
        "content_id",
        "data",
        "used",
        "raw_data",
        "not_found",
        "_dom",
        "_dom_data",
    )
    def __init__(
        self,
        id: str,
        transfer_encoding: str | None = None,
        content_type: str | None = None,
        content_id: str | None = None,
    ):
        self.id = id
        self.transfer_encoding = transfer_encoding
        self.content_type = content_type
        self.content_id = content_id
        self.data: bytes | bytearray | str | _ChunkBuffer = _ChunkBuffer()
        self.used = False
        self.raw_data: bytes | None = None
        self.not_found = False
        self._dom = None
        self._dom_data = None
class _ChunkBuffer:
    __slots__ = ("chunks", "length")
    def __init__(self):
        self.chunks: list[bytes] = []
        self.length = 0
    def append(self, chunk: bytes) -> None:
        if len(chunk):
            self.chunks.append(bytes(chunk))
            self.length += len(chunk)
    def byte_from_end(self, offset: int) -> int | None:
        for chunk in reversed(self.chunks):
            if len(chunk) >= offset:
                return chunk[-offset]
            offset -= len(chunk)
        return None
    def truncate(self, count: int) -> None:
        self.length -= count
        remaining = count
        while remaining:
            chunk = self.chunks[-1]
            if len(chunk) > remaining:
                self.chunks[-1] = chunk[: len(chunk) - remaining]
                remaining = 0
            else:
                self.chunks.pop()
                remaining -= len(chunk)
    def flatten(self) -> bytes:
        return b"".join(self.chunks)
class _Document:
    __slots__ = ("root", "doctype")
    def __init__(self, root, doctype: str | None):
        self.root = root
        self.doctype = doctype
    def serialize(self) -> str:
        result = ""
        if self.doctype:
            result += self.doctype + "\n"
        result += _serialize_node(self.root)
        return result
def _serialize_doctype(name: str | None, public_id: str | None, system_id: str | None) -> str:
    result = f"<!DOCTYPE {(name or 'html').lower()}"
    if public_id:
        result += f' PUBLIC "{public_id}"'
    if system_id:
        result += f' "{system_id}"'
    return result + ">"
DOCTYPE_DECLARATION_REGEXP = re.compile(r"<!doctype", re.IGNORECASE)
AFTER_HTML_END_REGEXP = re.compile(r"(?i)</html[^>]*>")
def _append_after_html_text(root, asset: str) -> None:
    last_match = None
    for match in AFTER_HTML_END_REGEXP.finditer(asset):
        last_match = match
    if last_match is None:
        return
    trailing = asset[last_match.end() :]
    if not trailing or "<" in trailing:
        return
    body = root.find("body")
    if body is None:
        body = root.find("frameset")
        if body is None:
            return
    trailing = trailing.replace("\r\n", "\n").replace("\r", "\n")
    if len(body):
        last_child = body[-1]
        last_child.tail = (last_child.tail or "") + trailing
    else:
        body.text = (body.text or "") + trailing
def _parse_dom(asset: str) -> _Document:
    root = None
    tree = None
    if asset:
        try:
            root = lxml.html.document_fromstring(asset)
            tree = root.getroottree()
        except Exception:
            root = None
    if root is None or not isinstance(root.tag, str) or root.tag != "html":
        root = lxml.etree.Element("html")
        tree = lxml.etree.ElementTree(root)
    _ensure_head_body(root)
    doctype = None
    if (
        tree is not None
        and tree.docinfo is not None
        and tree.docinfo.doctype
        and DOCTYPE_DECLARATION_REGEXP.search(asset or "")
    ):
        doctype = _serialize_doctype(tree.docinfo.root_name, tree.docinfo.public_id, tree.docinfo.system_url)
    _append_after_html_text(root, asset)
    _fix_svg_attribute_case(root)
    return _Document(root, doctype)
def _ensure_head_body(root) -> None:
    head = root.find("head")
    if head is None:
        head = _make_element(root, "head")
        root.insert(0, head)
    body = root.find("body")
    frameset = root.find("frameset")
    if body is None and frameset is None:
        body = _make_element(root, "body")
        head.addnext(body)
    elif body is not None and frameset is not None and not len(body) and not body.text:
        _remove_element(body)
def _make_element(parent, tag: str):
    return parent.makeelement(tag, {})
def _remove_element(element) -> None:
    parent = element.getparent()
    if parent is None:
        return
    tail = element.tail
    if tail:
        previous = element.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    parent.remove(element)
def _replace_element(old, new) -> None:
    new.tail = old.tail
    old.getparent().replace(old, new)
def _prepend_element(parent, element) -> None:
    if parent.text:
        element.tail = parent.text + element.tail if element.tail else parent.text
        parent.text = None
    parent.insert(0, element)
def _fix_svg_attribute_case(root) -> None:
    for svg in root.iter("svg"):
        for element in svg.iter():
            adjusted_items = [
                (_SVG_ATTRIBUTE_ADJUSTMENTS.get(name, name), value) for name, value in element.attrib.items()
            ]
            if adjusted_items != list(element.attrib.items()):
                element.attrib.clear()
                element.attrib.update(adjusted_items)
def _escape_text(value: str) -> str:
    return "".join(TEXT_ESCAPE_ENTITIES.get(char, char) for char in value)
def _escape_attribute_value(value: str) -> str:
    return "".join(ATTRIBUTE_ESCAPE_ENTITIES.get(char, char) for char in value)
def _escape_raw_text(value: str) -> str:
    value = value.replace("</", "<\\/")
    return SELF_CLOSING_TAG_MARKER_REGEXP.sub("\\/>", value)
def _serialize_node(node) -> str:
    if isinstance(node.tag, str):
        return _serialize_element(node)
    if node.tag is lxml.etree.Comment:
        return f"<!--{node.text}-->"
    if node.tag is lxml.etree.ProcessingInstruction:
        return f"<?{node.text}>"
    return ""
def _serialize_element(element) -> str:
    tag = element.tag
    html = f"<{tag}"
    attributes = _serialize_attributes(element)
    if attributes:
        html += " " + attributes
    html += ">"
    html += _serialize_children(element)
    if tag not in VOID_TAG_NAMES:
        html += f"</{tag}>"
    return html
def _serialize_children(element) -> str:
    parts = []
    if element.text:
        parts.append(_serialize_text(element.text, element))
    for child in element:
        parts.append(_serialize_node(child))
        if child.tail:
            parts.append(_serialize_text(child.tail, element))
    return "".join(parts)
def _serialize_text(text: str, parent) -> str:
    if _should_escape_entities(parent):
        return _escape_text(text)
    if _should_escape_raw_text(parent):
        return _escape_raw_text(text)
    return text
def _should_escape_entities(parent) -> bool:
    return parent.tag not in RAW_TEXT_NODE_TAG_NAMES
def _should_escape_raw_text(parent) -> bool:
    parent_type = parent.get("type")
    return parent.tag == "style" or (
        parent.tag == "script" and (not parent_type or parent_type == JAVASCRIPT_MIME_TYPE)
    )
def _serialize_attributes(element) -> str:
    parts = []
    for name, value in element.attrib.items():
        if INVALID_TAG_NAME_REGEXP.search(name):
            continue
        parts.append(f'{name}="{_escape_attribute_value(value)}"')
    return " ".join(parts)
def _get_resource_dom(resource: Resource, content_type: str | None) -> _Document:
    if resource._dom is None or resource._dom_data != resource.data:
        dom = _parse_dom(resource.data if isinstance(resource.data, str) else "")
        _cache_resource_dom(resource, dom)
    return resource._dom
def _cache_resource_dom(resource: Resource, dom: _Document) -> None:
    resource._dom = dom
    resource._dom_data = resource.data
def _release_resource_dom(resource: Resource) -> None:
    resource._dom = None
    resource._dom_data = None
class _RawCss:
    __slots__ = ("text",)
    type = "raw"
    def __init__(self, text: str):
        self.text = text
class _CssBail(Exception):
    pass
_CSS_IDENT = 1
_CSS_FUNCTION = 2
_CSS_AT_KEYWORD = 3
_CSS_HASH = 4
_CSS_STRING = 5
_CSS_URL = 7
_CSS_DELIM = 9
_CSS_NUMBER = 10
_CSS_PERCENTAGE = 11
_CSS_DIMENSION = 12
_CSS_CDC = 15
_CSS_COLON = 16
_CSS_SEMICOLON = 17
_CSS_LEFT_SQUARE_BRACKET = 19
_CSS_RIGHT_SQUARE_BRACKET = 20
_CSS_LEFT_PARENTHESIS = 21
_CSS_RIGHT_PARENTHESIS = 22
_CSS_LEFT_CURLY_BRACKET = 23
_CSS_RIGHT_CURLY_BRACKET = 24
_LITERAL_TOKEN_TYPES = {
    ":": _CSS_COLON,
    ";": _CSS_SEMICOLON,
    "(": _CSS_LEFT_PARENTHESIS,
    ")": _CSS_RIGHT_PARENTHESIS,
    "[": _CSS_LEFT_SQUARE_BRACKET,
    "]": _CSS_RIGHT_SQUARE_BRACKET,
    "{": _CSS_LEFT_CURLY_BRACKET,
    "}": _CSS_RIGHT_CURLY_BRACKET,
}
def _css_code(value) -> int:
    return value if isinstance(value, int) else ord(value) << 8
_SAFE_SEPARATOR_PAIRS = frozenset(
    (_css_code(previous) << 16) | _css_code(next_)
    for previous, next_ in (
        (1, 1),
        (1, 2),
        (1, 7),
        (1, 8),
        (1, "-"),
        (1, 10),
        (1, 11),
        (1, 12),
        (1, 15),
        (1, 21),
        (3, 1),
        (3, 2),
        (3, 7),
        (3, 8),
        (3, "-"),
        (3, 10),
        (3, 11),
        (3, 12),
        (3, 15),
        (4, 1),
        (4, 2),
        (4, 7),
        (4, 8),
        (4, "-"),
        (4, 10),
        (4, 11),
        (4, 12),
        (4, 15),
        (12, 1),
        (12, 2),
        (12, 7),
        (12, 8),
        (12, "-"),
        (12, 10),
        (12, 11),
        (12, 12),
        (12, 15),
        ("#", 1),
        ("#", 2),
        ("#", 7),
        ("#", 8),
        ("#", "-"),
        ("#", 10),
        ("#", 11),
        ("#", 12),
        ("#", 15),
        ("-", 1),
        ("-", 2),
        ("-", 7),
        ("-", 8),
        ("-", "-"),
        ("-", 10),
        ("-", 11),
        ("-", 12),
        ("-", 15),
        (10, 1),
        (10, 2),
        (10, 7),
        (10, 8),
        (10, 10),
        (10, 11),
        (10, 12),
        (10, "%"),
        (10, 15),
        ("@", 1),
        ("@", 2),
        ("@", 7),
        ("@", 8),
        ("@", "-"),
        ("@", 15),
        (".", 10),
        (".", 11),
        (".", 12),
        ("+", 10),
        ("+", 11),
        ("+", 12),
        ("/", "*"),
        (1, 4),
        (12, 4),
        (4, 4),
        (3, 21),
        (3, 5),
        (3, 16),
        (11, 11),
        (11, 12),
        (11, 2),
        (11, "-"),
        (22, 1),
        (22, 2),
        (22, 11),
        (22, 12),
        (22, 4),
        (22, "-"),
    )
)
_UNQUOTED_URL_SAFE = re.compile(r"[\x21-\x7e]+\Z")
def _serialize_url_token(value: str) -> str:
    if (
        value
        and _UNQUOTED_URL_SAFE.fullmatch(value)
        and '"' not in value
        and "'" not in value
        and "(" not in value
        and ")" not in value
        and "\\" not in value
    ):
        return f"url({value})"
    return f'url("{_escape_css_string(value)}")'
def _escape_css_string(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\a ")
        .replace("\r", "\\d ")
        .replace("\f", "\\c ")
    )
def _flatten_tokens(tokens):
    for token in tokens:
        token_type = token.type
        if token_type in ("whitespace", "comment"):
            continue
        if token_type == "parse-error":
            raise _CssBail(token.message)
        if token_type == "raw":
            yield _CSS_URL, token.text
        elif token_type == "ident":
            yield _CSS_IDENT, token.value
        elif token_type == "at-keyword":
            yield _CSS_AT_KEYWORD, "@" + token.value
        elif token_type == "hash":
            yield _CSS_HASH, "#" + token.value
        elif token_type == "string":
            yield _CSS_STRING, '"' + _escape_css_string(token.value) + '"'
        elif token_type == "url":
            yield _CSS_URL, _serialize_url_token(token.value)
        elif token_type == "number":
            yield _CSS_NUMBER, token.representation
        elif token_type == "percentage":
            yield _CSS_PERCENTAGE, token.representation + "%"
        elif token_type == "dimension":
            yield _CSS_DIMENSION, token.representation + token.unit
        elif token_type == "literal":
            value = token.value
            yield _LITERAL_TOKEN_TYPES.get(value, _CSS_DELIM), value
        elif token_type == "unicode-range":
            yield _CSS_IDENT, token.value if isinstance(token.value, str) else str(token.value)
        elif token_type == "function":
            yield _CSS_FUNCTION, token.lower_name + "("
            yield from _flatten_tokens(token.arguments)
            yield _CSS_RIGHT_PARENTHESIS, ")"
        elif token_type == "() block":
            yield _CSS_LEFT_PARENTHESIS, "("
            yield from _flatten_tokens(token.content)
            yield _CSS_RIGHT_PARENTHESIS, ")"
        elif token_type == "[] block":
            yield _CSS_LEFT_SQUARE_BRACKET, "["
            yield from _flatten_tokens(token.content)
            yield _CSS_RIGHT_SQUARE_BRACKET, "]"
        elif token_type == "{} block":
            yield _CSS_LEFT_CURLY_BRACKET, "{"
            yield from _block_pairs(token.content)
            yield _CSS_RIGHT_CURLY_BRACKET, "}"
        else:
            raise _CssBail(f"unserializable token: {token_type}")
def _block_pairs(tokens):
    pairs = list(_flatten_tokens(tokens))
    while pairs and pairs[-1][1] == ";":
        pairs.pop()
    return pairs
def _join_token_pairs(pairs) -> str:
    parts: list[str] = []
    previous_code = 0
    for type_code, text in pairs:
        code = (ord(text[0]) << 8) if type_code == _CSS_DELIM else type_code
        first = text[0] if text else ""
        if (first == "-" and type_code not in (_CSS_IDENT, _CSS_FUNCTION, _CSS_CDC)) or first == "+":
            needs_space = (previous_code << 16) | (ord(first) << 8) in _SAFE_SEPARATOR_PAIRS
        else:
            needs_space = (previous_code << 16) | code in _SAFE_SEPARATOR_PAIRS
        if needs_space:
            parts.append(" ")
        parts.append(text)
        previous_code = code
    return "".join(parts)
def serialize_css(nodes) -> str:
    pairs: list[tuple[int, str]] = []
    saw_declaration = False
    for node in nodes:
        node_type = node.type
        if node_type == "whitespace":
            continue
        if node_type == "declaration":
            if saw_declaration:
                pairs.append((_CSS_SEMICOLON, ";"))
            saw_declaration = True
            pairs.append((_CSS_IDENT, node.name))
            pairs.append((_CSS_COLON, ":"))
            pairs.extend(_flatten_tokens(node.value))
            if node.important:
                pairs.append((_CSS_DELIM, "!"))
                pairs.append((_CSS_IDENT, "important"))
        elif node_type == "qualified-rule":
            pairs.extend(_flatten_tokens(node.prelude))
            pairs.append((_CSS_LEFT_CURLY_BRACKET, "{"))
            pairs.extend(_block_pairs(node.content))
            pairs.append((_CSS_RIGHT_CURLY_BRACKET, "}"))
        elif node_type == "at-rule":
            pairs.append((_CSS_AT_KEYWORD, "@" + node.at_keyword))
            pairs.extend(_flatten_tokens(node.prelude))
            if node.content is None:
                pairs.append((_CSS_SEMICOLON, ";"))
            else:
                pairs.append((_CSS_LEFT_CURLY_BRACKET, "{"))
                pairs.extend(_block_pairs(node.content))
                pairs.append((_CSS_RIGHT_CURLY_BRACKET, "}"))
        else:
            pairs.extend(_flatten_tokens([node]))
    return _join_token_pairs(pairs)
STYLESHEET_CONTEXT = "stylesheet"
DECLARATION_LIST_CONTEXT = "declarationList"
def _get_original_url_comment(id_: str, resource_uri: str | None = None) -> str:
    return f"/* original URL: {id_} */ url({resource_uri if resource_uri is not None else id_})"
def _quoted_url_value(node) -> str | None:
    arguments = [token for token in node.arguments if token.type != "whitespace"]
    if len(arguments) == 1 and arguments[0].type == "string":
        return arguments[0].value
    return None
def _rewrite_css_urls(nodes, resources, base, stylesheets, missing_resources, unfound_resources) -> None:
    for index, node in enumerate(nodes):
        node_type = node.type
        quoted_url = _quoted_url_value(node) if node_type == "function" and node.lower_name == "url" else None
        if node_type == "url" or quoted_url is not None:
            path = node.value if node_type == "url" else quoted_url
            if path and not path.startswith(DATA_PROTOCOL) and not path.startswith(ORIGINAL_URL_FUNCTION_NAME):
                id_ = _resolve_path(path, base)
                def found(resource, id_=id_, index=index):
                    if _is_stylesheet(resource.content_type):
                        resource.data = _replace_stylesheet_urls(
                            resources,
                            resource.id,
                            resource,
                            STYLESHEET_CONTEXT,
                            stylesheets,
                            missing_resources,
                            unfound_resources,
                        )
                    nodes[index] = _RawCss(_get_original_url_comment(id_, _get_resource_uri(resource)))
                def not_found(id_=id_, index=index):
                    nodes[index] = _RawCss(_get_original_url_comment(id_))
                _resolve_reference(
                    resources,
                    missing_resources,
                    unfound_resources,
                    {
                        "id": id_,
                        "raw_id": path,
                        "encoding": BASE64_ENCODING,
                        "found": found,
                        "not_found": not_found,
                    },
                )
        elif node_type == "at-rule":
            if node.at_keyword.lower() == "import":
                prelude = node.prelude
                import_index = None
                import_node = None
                for i, token in enumerate(prelude):
                    if token.type != "whitespace":
                        import_index = i
                        import_node = token
                        break
                if import_node is not None and import_node.type in ("url", "string"):
                    path = import_node.value
                    if path and not path.startswith(DATA_PROTOCOL) and not path.startswith(ORIGINAL_URL_FUNCTION_NAME):
                        id_ = _resolve_path(path, base)
                        def descend(resource):
                            resource.data = _replace_stylesheet_urls(
                                resources,
                                resource.id,
                                resource,
                                STYLESHEET_CONTEXT,
                                stylesheets,
                                missing_resources,
                                unfound_resources,
                            )
                        def found(resource, id_=id_, import_index=import_index, prelude=prelude):
                            prelude[import_index] = _RawCss(_get_original_url_comment(id_, _get_resource_uri(resource)))
                        def not_found(id_=id_, import_index=import_index, prelude=prelude):
                            prelude[import_index] = _RawCss(_get_original_url_comment(id_))
                        _resolve_reference(
                            resources,
                            missing_resources,
                            unfound_resources,
                            {
                                "id": id_,
                                "raw_id": path,
                                "descend": descend,
                                "found": found,
                                "not_found": not_found,
                            },
                        )
            _rewrite_css_urls(node.prelude, resources, base, stylesheets, missing_resources, unfound_resources)
            if node.content is not None:
                _rewrite_css_urls(node.content, resources, base, stylesheets, missing_resources, unfound_resources)
        elif node_type == "qualified-rule":
            _rewrite_css_urls(node.prelude, resources, base, stylesheets, missing_resources, unfound_resources)
            _rewrite_css_urls(node.content, resources, base, stylesheets, missing_resources, unfound_resources)
        elif node_type == "declaration":
            _rewrite_css_urls(node.value, resources, base, stylesheets, missing_resources, unfound_resources)
        elif node_type == "function":
            _rewrite_css_urls(node.arguments, resources, base, stylesheets, missing_resources, unfound_resources)
        elif node_type in ("() block", "[] block", "{} block"):
            _rewrite_css_urls(node.content, resources, base, stylesheets, missing_resources, unfound_resources)
def _replace_stylesheet_urls(
    resources, base, resource, context, stylesheets, missing_resources, unfound_resources
) -> str:
    if isinstance(resource, dict):
        data = resource["data"]
        resource_id = None
    else:
        resource_id = getattr(resource, "id", None)
        data = resource.data
        if not isinstance(data, str):
            data = "" if data is None else str(data)
    if resource_id is not None:
        stylesheet = stylesheets.get(resource_id)
        if stylesheet is not None:
            return data if stylesheet.get("data") is None else stylesheet["data"]
        stylesheets[resource_id] = {}
    try:
        if context == DECLARATION_LIST_CONTEXT:
            nodes = tinycss2.parse_declaration_list(data, skip_comments=True, skip_whitespace=True)
        else:
            nodes = tinycss2.parse_stylesheet(data, skip_comments=True, skip_whitespace=True)
    except Exception:
        nodes = None
    if nodes is None:
        return data
    if _contains_parse_error(nodes):
        return data
    _rewrite_css_urls(nodes, resources, base, stylesheets, missing_resources, unfound_resources)
    try:
        result = serialize_css(nodes)
    except Exception:
        return data
    if resource_id is not None:
        stylesheets[resource_id]["data"] = result
    return result
def _contains_parse_error(nodes) -> bool:
    for node in nodes:
        node_type = node.type
        if node_type == "parse-error":
            return True
        if node_type == "qualified-rule":
            if _tokens_have_error(node.prelude) or _contains_parse_error(node.content):
                return True
        elif node_type == "at-rule":
            if _tokens_have_error(node.prelude):
                return True
            if node.content is not None and _contains_parse_error(node.content):
                return True
        elif node_type == "declaration":
            if _tokens_have_error(node.value):
                return True
        elif node_type == "function":
            if _tokens_have_error(node.arguments):
                return True
        elif node_type in ("() block", "[] block", "{} block"):
            if _tokens_have_error(node.content):
                return True
    return False
def _tokens_have_error(tokens) -> bool:
    for token in tokens:
        if token.type == "parse-error":
            return True
        if token.type == "function":
            if _tokens_have_error(token.arguments):
                return True
        elif token.type in ("() block", "[] block", "{} block"):
            if _tokens_have_error(token.content):
                return True
    return False
_SRCSET_SPACES = frozenset(" \t\n\r\f")
_REGEX_LEADING_COMMAS_OR_SPACES = re.compile(r"[, \t\n\r\f]+")
_REGEX_LEADING_NOT_SPACES = re.compile(r"[^ \t\n\r\f]+")
_REGEX_TRAILING_COMMAS = re.compile(r",+$")
_REGEX_NON_NEGATIVE_INTEGER = re.compile(r"^\d+$")
_REGEX_FLOATING_POINT = re.compile(r"^-?(?:[0-9]+|[0-9]*\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")
def parse_srcset(input_value: str) -> list[dict]:
    input_length = len(input_value)
    candidates: list[dict] = []
    pos = 0
    def collect_characters(regex) -> str:
        nonlocal pos
        match = regex.match(input_value, pos)
        if match:
            chars = match.group(0)
            pos += len(chars)
            return chars
        return ""
    def parse_descriptors(url, descriptors):
        p_error = False
        w = d = h = None
        for descriptor in descriptors:
            last_char = descriptor[-1] if descriptor else ""
            value = descriptor[:-1]
            if _REGEX_NON_NEGATIVE_INTEGER.match(value) and last_char == "w":
                if w or d is not None:
                    p_error = True
                int_value = int(value) if value.isdigit() else 0
                if int_value == 0:
                    p_error = True
                else:
                    w = int_value
            elif _REGEX_FLOATING_POINT.match(value) and last_char == "x":
                if w or d is not None or h:
                    p_error = True
                float_value = float(value) if value else 0.0
                if float_value < 0:
                    p_error = True
                else:
                    d = float_value
            elif _REGEX_NON_NEGATIVE_INTEGER.match(value) and last_char == "h":
                if h or d is not None:
                    p_error = True
                int_value = int(value) if value.isdigit() else 0
                if int_value == 0:
                    p_error = True
                else:
                    h = int_value
            else:
                p_error = True
        candidate = {"url": url}
        if p_error:
            candidate["descriptors"] = list(descriptors)
        else:
            if w:
                candidate["w"] = w
            if d is not None:
                candidate["d"] = d
            if h:
                candidate["h"] = h
        candidates.append(candidate)
    def tokenize(url, descriptors):
        nonlocal pos
        collect_characters(re.compile(r"[ \t\n\r\f]+"))
        current_descriptor = ""
        state = "in descriptor"
        while True:
            c = input_value[pos] if pos < input_length else ""
            if state == "in descriptor":
                if c in _SRCSET_SPACES:
                    if current_descriptor:
                        descriptors.append(current_descriptor)
                        current_descriptor = ""
                        state = "after descriptor"
                elif c == ",":
                    pos += 1
                    if current_descriptor:
                        descriptors.append(current_descriptor)
                    parse_descriptors(url, descriptors)
                    return
                elif c == "(":
                    current_descriptor += c
                    state = "in parens"
                elif c == "":
                    if current_descriptor:
                        descriptors.append(current_descriptor)
                    parse_descriptors(url, descriptors)
                    return
                else:
                    current_descriptor += c
            elif state == "in parens":
                if c == ")":
                    current_descriptor += c
                    state = "in descriptor"
                elif c == "":
                    descriptors.append(current_descriptor)
                    parse_descriptors(url, descriptors)
                    return
                else:
                    current_descriptor += c
            elif state == "after descriptor":
                if c in _SRCSET_SPACES:
                    pass
                elif c == "":
                    parse_descriptors(url, descriptors)
                    return
                else:
                    state = "in descriptor"
                    pos -= 1
            pos += 1
    while True:
        collect_characters(_REGEX_LEADING_COMMAS_OR_SPACES)
        if pos >= input_length:
            return candidates
        url = collect_characters(_REGEX_LEADING_NOT_SPACES)
        descriptors: list[str] = []
        if url.endswith(","):
            url = _REGEX_TRAILING_COMMAS.sub("", url)
            parse_descriptors(url, descriptors)
        else:
            tokenize(url, descriptors)
def _js_number(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
def serialize_srcset(srcset: list[dict]) -> str:
    parts = []
    for candidate in srcset:
        descriptors = list(candidate.get("descriptors") or ())
        if candidate.get("w"):
            descriptors.append(f"{candidate['w']}w")
        if candidate.get("h"):
            descriptors.append(f"{candidate['h']}h")
        if candidate.get("d") is not None:
            descriptors.append(f"{_js_number(candidate['d'])}x")
        parts.append(" ".join([candidate["url"]] + descriptors))
    return ", ".join(parts)
MHTML_HEADERS = 0
MHTML_CONTENT = 1
MHTML_DATA = 2
MHTML_END = 3
GENERATED_ID_PREFIX = "_"
class _MhtmlParser:
    def __init__(self, mhtml: bytes, context: dict | None = None):
        if isinstance(mhtml, str):
            mhtml = mhtml.encode("utf-8")
        self.mhtml = mhtml
        context = context if context is not None else {}
        self.context = context
        self.resources: dict[str, Resource] = context.setdefault("resources", {})
        self.frames: dict[str, Resource] = context.setdefault("frames", {})
        self.anomalies: list[dict] = context.setdefault("anomalies", [])
        self.headers: dict[str, str] = {}
        self.raw_header_lines: list[bytes] = []
        self.content: dict[str, str] = {}
        self.header_key: str | None = None
        self.transfer_encoding: str | None = None
        self.content_id: str | None = None
        self.resource: Resource | None = None
        self.boundary: str | None = None
        self.boundary_bytes: bytes | None = None
        self.declared_boundary_unused = False
        self.index_mhtml = 0
        self.index_generated_id = 0
        self.index_start_embedded_mhtml: int | None = None
    def parse(self) -> dict:
        mhtml = self.mhtml
        if _starts_with_markup(mhtml):
            self.anomalies.append({"type": MISLABELED_DOCUMENT_ANOMALY})
            self.headers[CONTENT_TYPE_HEADER] = TEXT_HTML_CONTENT_TYPE
            self._init_resource(self.headers)
            self._append_data(self.resource.data, mhtml)
            self._process_resource()
            return self._result()
        state = MHTML_HEADERS
        while state != MHTML_END and (self.index_mhtml < len(mhtml) or state == MHTML_DATA):
            if state == MHTML_HEADERS:
                next_line = self._get_line()
                if not _is_line_feed(next_line):
                    self.raw_header_lines.append(next_line)
                    self._split_headers(next_line, self.headers)
                else:
                    if self.headers.get(CONTENT_TYPE_HEADER):
                        self._set_boundary(_get_boundary(self.headers[CONTENT_TYPE_HEADER]))
                    if self.boundary is not None:
                        index_start_body = self.index_mhtml
                        while (
                            _find_boundary_delimiter(next_line, self.boundary_bytes) == -1
                            and self.index_mhtml < len(mhtml) - 1
                        ):
                            next_line = self._get_line()
                        if _find_boundary_delimiter(next_line, self.boundary_bytes) == -1:
                            self.index_mhtml = index_start_body
                            self._set_boundary(None)
                            self.declared_boundary_unused = True
                    if self.boundary is None:
                        previous_index = self.index_mhtml
                        next_line = self._get_line(self.transfer_encoding)
                        if _starts_with_boundary(next_line):
                            self._set_boundary(_decode_string(next_line)[2:].rstrip())
                            if self.declared_boundary_unused:
                                self.anomalies.append({"type": UNUSED_BOUNDARY_ANOMALY})
                        else:
                            self.index_mhtml = previous_index
                    self.content = {}
                    state = MHTML_CONTENT
            elif state == MHTML_CONTENT:
                if self.boundary is not None:
                    if self.index_start_embedded_mhtml is None:
                        self.index_start_embedded_mhtml = self.index_mhtml
                    next_line = self._get_line()
                    if not _is_line_feed(next_line):
                        self._split_headers(next_line, self.content)
                    else:
                        self._init_resource(self.content)
                        if not self.resource.content_type or not _is_multipart_alternative(self.resource.content_type):
                            self.index_start_embedded_mhtml = None
                        state = MHTML_DATA
                else:
                    missing_delimiters = _is_multipart(self.headers.get(CONTENT_TYPE_HEADER))
                    if missing_delimiters:
                        self.anomalies.append({"type": MISSING_DELIMITERS_ANOMALY})
                    self._init_resource(self._read_body_headers() if missing_delimiters else self.headers)
                    state = MHTML_DATA
            elif state == MHTML_DATA:
                index_end_data = self._parse_resource_data()
                if self.index_start_embedded_mhtml is not None and index_end_data is not None:
                    self.resource.data = self._flatten(self.resource.data)
                    self.resource.used = True
                    self.context["index"] = self._convert_embedded_mhtml(index_end_data)
                else:
                    self._process_resource()
                state = MHTML_END if self.index_mhtml >= len(mhtml) - 1 else MHTML_CONTENT
        return self._result()
    def _result(self) -> dict:
        return {
            "headers": self.headers,
            "frames": self.frames,
            "resources": self.resources,
            "index": self.context.get("index"),
            "anomalies": self.anomalies,
        }
    def _set_boundary(self, value: str | None) -> None:
        self.boundary = value
        self.boundary_bytes = value.encode("utf-8") if value is not None else None
    def _get_line(self, transfer_encoding: str | None = None) -> bytes:
        index_start = self.index_mhtml
        index_line_feed = self.mhtml.find(b"\n", index_start)
        if index_line_feed == -1:
            self.index_mhtml = len(self.mhtml) + 1
            end = len(self.mhtml)
        else:
            self.index_mhtml = index_line_feed + 1
            end = self.index_mhtml
        line = self.mhtml[index_start:end]
        if transfer_encoding == QUOTED_PRINTABLE_ENCODING:
            line = _decode_quoted_printable(line)
        return line
    def _split_headers(self, line: bytes, obj: dict) -> None:
        self.header_key = _parse_header_line(_decode_string(line), obj, self.header_key)
    def _decode_raw_headers(self, charset: str | None) -> None:
        if charset is None or charset == UTF8_CHARSET:
            return
        if not any(REPLACEMENT_CHARACTER in value for value in self.headers.values()):
            return
        decoded_headers: dict[str, str] = {}
        decoded_header_key = None
        for line in self.raw_header_lines:
            decoded_header_key = _parse_header_line(_decode_string(line, charset), decoded_headers, decoded_header_key)
        for name, value in self.headers.items():
            if REPLACEMENT_CHARACTER in value and name in decoded_headers:
                self.headers[name] = decoded_headers[name]
    def _read_body_headers(self) -> dict[str, str]:
        index_start_body = self.index_mhtml
        if _starts_with_markup(self.mhtml[index_start_body:]):
            return {CONTENT_TYPE_HEADER: TEXT_HTML_CONTENT_TYPE}
        body_headers: dict[str, str] = {}
        self.header_key = None
        index_before_line = self.index_mhtml
        next_line = self._get_line()
        while len(next_line) and not _is_line_feed(next_line) and _is_header_line(next_line, len(body_headers)):
            self._split_headers(next_line, body_headers)
            index_before_line = self.index_mhtml
            next_line = self._get_line()
        if body_headers.get(CONTENT_TYPE_HEADER) is None:
            self.index_mhtml = index_start_body
            return self.headers
        if not _is_line_feed(next_line):
            self.index_mhtml = index_before_line
        return body_headers
    def _init_resource(self, resource_data: dict) -> None:
        self.transfer_encoding = resource_data.get(CONTENT_TRANSFER_ENCODING_HEADER)
        content_type = resource_data.get(CONTENT_TYPE_HEADER)
        self.content_id = resource_data.get(CONTENT_ID_HEADER)
        id_ = resource_data.get(CONTENT_LOCATION_HEADER)
        if self.transfer_encoding:
            self.transfer_encoding = self.transfer_encoding.lower()
        resource = Resource(
            id=id_ if id_ is not None else "",
            transfer_encoding=self.transfer_encoding,
            content_type=content_type,
            content_id=self.content_id,
        )
        if id_ is None:
            if self.content_id is not None:
                id_ = self.content_id
            else:
                while True:
                    id_ = GENERATED_ID_PREFIX + str(self.index_generated_id)
                    self.index_generated_id += 1
                    if id_ not in self.resources:
                        break
        written_id = id_
        id_ = normalize_location(id_)
        resource.id = id_
        if self.context.get("index") is None and _is_document(content_type):
            self.context["index"] = id_
        if self.content_id is not None:
            self.frames[self.content_id] = resource
            if self.content_id not in self.resources:
                self.resources[self.content_id] = resource
        if id_ not in self.resources:
            self.resources[id_] = resource
        if written_id != id_ and written_id not in self.resources:
            self.resources[written_id] = resource
        self.resource = resource
        self.content = {}
        self.header_key = None
    def _parse_resource_data(self) -> int | None:
        resource = self.resource
        next_line = self._get_line(self.transfer_encoding)
        index_end_data = None
        boundary_found = False
        while not boundary_found and len(next_line):
            index_end_data = self.index_mhtml
            index_boundary = _find_boundary_delimiter(next_line, self.boundary_bytes)
            if index_boundary != -1:
                index_end_data = index_end_data - len(next_line) + index_boundary - 2
                if index_boundary > 2:
                    next_line = next_line[: index_boundary - 2]
                else:
                    next_line = b""
                boundary_found = True
            if resource.transfer_encoding == QUOTED_PRINTABLE_ENCODING:
                data = resource.data
                if data.length > 2 and data.byte_from_end(3) == EQUAL_SIGN and _ends_with_crlf(next_line):
                    data.truncate(3)
                elif data.length > 1 and data.byte_from_end(2) == EQUAL_SIGN and _ends_with_lf(next_line):
                    data.truncate(2)
            elif resource.transfer_encoding == BASE64_ENCODING:
                if _ends_with_crlf(next_line):
                    next_line = next_line[: len(next_line) - 2]
                elif _ends_with_lf(next_line):
                    next_line = next_line[: len(next_line) - 1]
            self._append_data(resource.data, next_line)
            if not boundary_found:
                next_line = self._get_line(self.transfer_encoding)
        self._truncate_data_line_terminator(resource.data)
        if not boundary_found and self.boundary is not None:
            index_end_data = self.index_mhtml
        return index_end_data
    def _convert_embedded_mhtml(self, index_end: int) -> str | None:
        context = {"resources": self.resources, "frames": self.frames, "anomalies": self.anomalies}
        embedded = self.mhtml[self.index_start_embedded_mhtml : index_end]
        if _ends_with_crlf(embedded):
            index_end -= 2
        elif _ends_with_lf(embedded):
            index_end -= 1
        _MhtmlParser(self.mhtml[self.index_start_embedded_mhtml : index_end], context).parse()
        return context.get("index")
    def _process_resource(self) -> None:
        resource = self.resource
        data = resource.data
        if isinstance(data, _ChunkBuffer):
            resource.data = resource.raw_data = data.flatten()
        else:
            resource.raw_data = bytes(data)
        declared_charset = _get_charset(resource.content_type) if resource.content_type else None
        if (
            resource.transfer_encoding == BASE64_ENCODING
            and resource.content_type
            and (
                resource.id == self.context.get("index")
                or (self.content_id is not None and _is_document(resource.content_type))
                or _is_stylesheet(resource.content_type)
            )
        ):
            decoded_data = _decode_base64_bytes(_decode_string(resource.data))
            if decoded_data is not None:
                resource.transfer_encoding = None
                resource.data = resource.raw_data = decoded_data
            else:
                self.anomalies.append({"type": UNDECODABLE_BASE64_ANOMALY, "id": resource.id})
        bom_charset = _get_bom_charset(resource.data)
        charset = bom_charset or declared_charset
        if resource.transfer_encoding == BINARY_ENCODING and (
            not resource.content_type or not _is_text(resource.content_type)
        ):
            resource.transfer_encoding = BASE64_ENCODING
            resource.data = _decode_binary(resource.data)
        else:
            resource.data = _decode_string(resource.data, charset)
        if resource.content_type:
            if resource.transfer_encoding != BASE64_ENCODING:
                resource.content_type = _replace_charset(resource.content_type, UTF8_CHARSET)
            if _is_stylesheet(resource.content_type):
                self._process_stylesheet_charset(charset, bom_charset)
            elif _is_document(resource.content_type):
                document_charset = self._process_document_charset(charset, bom_charset)
                if resource.id == self.context.get("index"):
                    self._decode_raw_headers(document_charset)
        resource.raw_data = None
    def _process_stylesheet_charset(self, charset: str | None, bom_charset: str | None) -> None:
        resource = self.resource
        try:
            rules = tinycss2.parse_stylesheet(resource.data, skip_comments=True, skip_whitespace=True)
            if rules and rules[0].type == "at-rule" and rules[0].at_keyword.lower() == "charset":
                prelude = [token for token in rules[0].prelude if token.type != "whitespace"]
                if prelude and hasattr(prelude[0], "value"):
                    css_charset = str(prelude[0].value).lower()
                    if bom_charset is None and css_charset != UTF8_CHARSET and css_charset != charset:
                        resource.data = _decode_string(resource.raw_data, css_charset)
                        rules = tinycss2.parse_stylesheet(resource.data, skip_comments=True, skip_whitespace=True)
                rules.pop(0)
                resource.data = serialize_css(rules)
        except Exception:
            pass
    def _process_document_charset(self, charset: str | None, bom_charset: str | None) -> str | None:
        resource = self.resource
        document_charset = charset
        modified = False
        dom = _get_resource_dom(resource, None)
        root = dom.root
        charset_meta_elements = _get_meta_charset_elements(root)
        if charset_meta_elements:
            html_charset = charset_meta_elements[0].get("charset")
            if html_charset:
                html_charset = html_charset.lower()
                if bom_charset is None and html_charset != UTF8_CHARSET and html_charset != charset:
                    resource.data = _decode_string(resource.raw_data, html_charset)
                    document_charset = html_charset
                    dom = _get_resource_dom(resource, None)
                    root = dom.root
                    charset_meta_elements = _get_meta_charset_elements(root)
            for meta_element in charset_meta_elements:
                _remove_element(meta_element)
            modified = True
        meta_elements = _get_meta_content_type_elements(root)
        if meta_elements:
            content_value = meta_elements[0].get("content")
            html_charset = _get_charset(content_value)
            if (
                bom_charset is None
                and html_charset
                and html_charset != UTF8_CHARSET
                and html_charset != document_charset
            ):
                resource.data = _decode_string(resource.raw_data, html_charset)
                document_charset = html_charset
                dom = _get_resource_dom(resource, None)
                root = dom.root
                meta_elements = _get_meta_content_type_elements(root)
                for meta_element in _get_meta_charset_elements(root):
                    _remove_element(meta_element)
            for meta_element in meta_elements:
                _remove_element(meta_element)
            modified = True
        if modified:
            resource.data = dom.serialize()
            dom = _get_resource_dom(resource, None)
        _cache_resource_dom(resource, dom)
        return document_charset
    def _append_data(self, data, chunk: bytes) -> None:
        if len(chunk):
            data.append(chunk)
    def _flatten(self, data):
        if isinstance(data, _ChunkBuffer):
            return data.flatten()
        return data
    def _truncate_data_line_terminator(self, data) -> None:
        if data.length > 1 and data.byte_from_end(2) == CRLF and data.byte_from_end(1) == LF:
            data.truncate(2)
        elif data.length > 0 and data.byte_from_end(1) == LF:
            data.truncate(1)
def _parse_header_line(line_string: str, obj: dict, header_key: str | None) -> str | None:
    index_column = line_string.find(":")
    if index_column > -1:
        header_key = line_string[:index_column].strip().lower()
        obj[header_key] = line_string[index_column + 1 :].strip()
    elif header_key is not None and obj.get(header_key) is not None:
        obj[header_key] += line_string.strip()
    return header_key
def _is_header_line(line: bytes, count_headers: int) -> bool:
    value = _decode_string(line)
    return bool(HEADER_NAME_REGEXP.match(value)) or (
        count_headers > 0 and bool(HEADER_CONTINUATION_REGEXP.match(value))
    )
def _find_boundary_delimiter(line: bytes, boundary_bytes: bytes | None) -> int:
    if not boundary_bytes or not len(boundary_bytes):
        return -1
    index_boundary = line.find(boundary_bytes)
    if index_boundary >= 2 and line[index_boundary - 2] == HYPHEN_MINUS and line[index_boundary - 1] == HYPHEN_MINUS:
        index = index_boundary + len(boundary_bytes)
        if line[index : index + 2] == b"--":
            index += 2
        while index < len(line) and line[index] in (SPACE, HORIZONTAL_TAB):
            index += 1
        if index >= len(line) or line[index] in (CRLF, LF):
            return index_boundary
    return -1
def _starts_with_markup(array: bytes) -> bool:
    bom_charset = _get_bom_charset(array)
    index = 0
    skip_nul = False
    if bom_charset == UTF8_CHARSET:
        index = 3
    elif bom_charset is not None:
        index = 2
        skip_nul = True
    length = len(array)
    while index < length:
        byte = array[index]
        if byte == LESS_THAN_SIGN:
            return True
        if skip_nul and byte == NUL:
            index += 1
            continue
        if byte not in (SPACE, HORIZONTAL_TAB, CRLF, LF):
            return False
        index += 1
    return False
def _get_meta_charset_elements(root) -> list:
    return [element for element in root.iter("meta") if element.get("charset")]
def _get_meta_content_type_elements(root) -> list:
    return [
        element
        for element in root.iter("meta")
        if element.get("http-equiv") and element.get("http-equiv").lower() == CONTENT_TYPE_HEADER
    ]
def _set_attribute(element, attribute: str, new_value: str | None = None) -> None:
    value = element.get(attribute)
    if value and not value.startswith(DATA_PROTOCOL) and value != new_value:
        element.set(ORIGINAL_URL_ATTRIBUTE_PREFIX + attribute, value)
    if new_value is not None:
        element.set(attribute, new_value)
def _escape_plain_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;")
def _create_document(resources: dict[str, Resource]) -> Resource | None:
    for resource in resources.values():
        content_type = resource.content_type
        if _is_image(content_type):
            synthesized = Resource(
                id=resource.id,
                transfer_encoding=None,
                content_type=TEXT_HTML_CONTENT_TYPE,
                content_id=resource.content_id,
            )
            synthesized.data = f'<html><body><img src="{_get_resource_uri(resource)}"></body></html>'
            return synthesized
        if _is_plain_text(content_type):
            text = (
                _decode_base64(str(resource.data), _get_charset(content_type))
                if resource.transfer_encoding == BASE64_ENCODING
                else str(resource.data)
            )
            synthesized = Resource(
                id=resource.id,
                transfer_encoding=None,
                content_type=TEXT_HTML_CONTENT_TYPE,
                content_id=resource.content_id,
            )
            synthesized.data = f"<html><body><pre>{_escape_plain_text(text)}</pre></body></html>"
            return synthesized
    return None
def _get_page_info(headers: dict[str, str], index: str) -> dict:
    page_info = {
        **JSON_LD_PAGE_INFO,
        "url": index,
        "name": _decode_mime_header(headers.get(SUBJECT_HEADER)),
        "additionalProperty": {
            **JSON_LD_PAGE_INFO["additionalProperty"],
            "value": _decode_mime_header(headers.get(FROM_HEADER)),
        },
    }
    if headers.get(DATE_HEADER) is not None:
        page_info["dateCreated"] = headers[DATE_HEADER]
    return page_info
def _get_resource(resources: dict[str, Resource], id_: str | None, raw_id: str | None) -> Resource | None:
    resource = resources.get(id_) if id_ is not None else None
    if resource is None and raw_id is not None:
        resource = resources.get(raw_id)
    if resource is None and id_ and id_.startswith(CID_PROTOCOL):
        resource = resources.get(f"<{id_[len(CID_PROTOCOL) :]}>")
    return resource
def _add_missing_resource(missing_resources: list, id_: str, transfer_encoding: str | None) -> None:
    if (id_.startswith(HTTP_PROTOCOL) or id_.startswith(HTTPS_PROTOCOL) or id_.startswith(URN_PROTOCOL)) and not any(
        resource["id"] == id_ for resource in missing_resources
    ):
        missing_resources.append({"id": id_, "transferEncoding": transfer_encoding})
def _resolve_reference(resources, missing_resources, unfound_resources, reference) -> None:
    resource = (
        reference["resource"]
        if "resource" in reference
        else _get_resource(resources, reference.get("id"), reference.get("raw_id"))
    )
    if resource is not None:
        if reference.get("descend"):
            reference["descend"](resource)
        if missing_resources is None:
            resource.used = True
            reference["found"](resource)
    elif missing_resources is not None:
        _add_missing_resource(missing_resources, reference["id"], reference.get("encoding"))
    else:
        unfound_resources.add(reference["id"])
        reference["not_found"]()
def _convert(mhtml: dict, config: dict):
    enable_scripts = bool(config.get("enableScripts") or config.get("enable_scripts"))
    fetch_missing_resources = bool(config.get("fetchMissingResources") or config.get("fetch_missing_resources"))
    headers = mhtml.get("headers")
    frames = mhtml.get("frames") or {}
    resources: dict[str, Resource] = mhtml.get("resources") or {}
    unfound_resources = mhtml.get("unfoundResources")
    if unfound_resources is None:
        unfound_resources = set()
        mhtml["unfoundResources"] = unfound_resources
    index = mhtml.get("index")
    id_ = mhtml.get("id")
    anomalies = mhtml.get("anomalies") or []
    resource = resources.get(index) if index is not None else None
    if resource is None:
        resource = _create_document(resources)
        if resource is None:
            raise ValueError(INDEX_PAGE_NOT_FOUND_ERROR)
        index = resource.id
        if not fetch_missing_resources:
            anomalies = [*anomalies, {"type": SYNTHESIZED_INDEX_ANOMALY, "id": index}]
    base = resource.id
    if resource.transfer_encoding == BASE64_ENCODING:
        resource.transfer_encoding = None
        resource.data = _decode_base64(str(resource.data), _get_charset(resource.content_type))
    dom = _get_resource_dom(resource, None)
    root = dom.root
    if not fetch_missing_resources:
        _release_resource_dom(resource)
    head = root.find("head")
    nodes = [root]
    base_element = next(iter(root.iter("base")), None)
    if base_element is not None:
        href = base_element.get("href")
        if href:
            base = _resolve_path(href, base)
        if not fetch_missing_resources:
            _remove_element(base_element)
    if not fetch_missing_resources:
        resource.used = True
    canonical_link_element = None
    stylesheets: dict[str, dict] = {}
    missing_resources: list | None = [] if fetch_missing_resources else None
    removed_nodes = []
    favicons: list[dict] = []
    title: str | None = None
    index_node = 0
    while index_node < len(nodes):
        child_node = nodes[index_node]
        index_node += 1
        parent_tag_name = child_node.tag
        for child in list(child_node):
            if not isinstance(child.tag, str):
                continue
            tag_name = child.tag
            href = child.get("href")
            if href:
                href = _resolve_path(href, base)
            src = child.get("src")
            if src:
                src = _resolve_path(src, base)
            style = child.get("style")
            if style is not None:
                declarations = _replace_stylesheet_urls(
                    resources,
                    base,
                    {"data": style},
                    DECLARATION_LIST_CONTEXT,
                    stylesheets,
                    missing_resources,
                    unfound_resources,
                )
                if not fetch_missing_resources:
                    child.set("style", declarations)
            integrity = child.get("integrity")
            if integrity is not None:
                del child.attrib["integrity"]
            if not enable_scripts:
                for attribute_name in list(child.attrib):
                    if attribute_name.lower() in EVENT_HANDLER_ATTRIBUTES:
                        del child.attrib[attribute_name]
            if tag_name == "link" and href:
                rel = child.get("rel")
                if rel:
                    rel = rel.lower()
                    rel_tokens = rel.strip().split()
                    if "stylesheet" in rel_tokens:
                        stylesheet_value: list = []
                        def descend(resource, base=base, index=index, id_=id_):
                            descend_base = resource.id
                            if descend_base.startswith(CID_PROTOCOL):
                                if index is not None and CID_REGEXP.match(str(index)):
                                    descend_base = id_
                                else:
                                    descend_base = index
                            stylesheet_value.append(
                                _replace_stylesheet_urls(
                                    resources,
                                    descend_base,
                                    resource,
                                    STYLESHEET_CONTEXT,
                                    stylesheets,
                                    missing_resources,
                                    unfound_resources,
                                )
                            )
                        def found(resource, child=child, rel_tokens=rel_tokens, href=href):
                            resource.data = stylesheet_value[0] if stylesheet_value else resource.data
                            media = child.get("media")
                            if child.get("title") or "alternate" in rel_tokens:
                                _set_attribute(child, "href", _get_resource_uri(resource))
                            else:
                                style_element = _make_element(child, "style")
                                if media:
                                    style_element.set("media", media)
                                if not href.startswith(DATA_PROTOCOL):
                                    style_element.set(ORIGINAL_URL_ATTRIBUTE_PREFIX + "href", href)
                                style_element.text = (
                                    resource.data if isinstance(resource.data, str) else str(resource.data)
                                )
                                _replace_element(child, style_element)
                        def not_found(child=child, href=href):
                            _set_attribute(child, "href", href)
                        _resolve_reference(
                            resources,
                            missing_resources,
                            unfound_resources,
                            {
                                "id": href,
                                "raw_id": child.get("href"),
                                "descend": descend,
                                "found": found,
                                "not_found": not_found,
                            },
                        )
                    elif "icon" in rel:
                        media = child.get("media")
                        type_ = child.get("type")
                        sizes = child.get("sizes")
                        def found(resource, child=child, href=href, media=media, type_=type_, sizes=sizes):
                            resource_uri = _get_resource_uri(resource)
                            _set_attribute(child, "href", resource_uri)
                            favicons.append({
                                "href": resource_uri,
                                "media": media,
                                "type": type_,
                                "sizes": sizes,
                                "originalHref": href,
                            })
                        def not_found(child=child, href=href, media=media, type_=type_, sizes=sizes):
                            _set_attribute(child, "href", href)
                            favicons.append({"href": href, "media": media, "type": type_, "sizes": sizes})
                        _resolve_reference(
                            resources,
                            missing_resources,
                            unfound_resources,
                            {
                                "id": href,
                                "raw_id": child.get("href"),
                                "encoding": BASE64_ENCODING,
                                "found": found,
                                "not_found": not_found,
                            },
                        )
                    elif rel == "canonical" and not fetch_missing_resources:
                        canonical_link_element = child
                    if not fetch_missing_resources:
                        rel_value = REL_REMOVED_VALUES_REGEXP.sub("", rel).strip()
                        if rel_value:
                            child.set("rel", rel_value)
                        else:
                            removed_nodes.append(child)
            elif tag_name == "style":
                style_text = child.text_content()
                style = _replace_stylesheet_urls(
                    resources,
                    base,
                    {"data": style_text},
                    STYLESHEET_CONTEXT,
                    stylesheets,
                    missing_resources,
                    unfound_resources,
                )
                if not fetch_missing_resources:
                    style_element = _make_element(child, "style")
                    media = child.get("media")
                    if media:
                        style_element.set("media", media)
                    style_title = child.get("title")
                    if style_title:
                        style_element.set("title", style_title)
                    style_element.text = style
                    _replace_element(child, style_element)
            elif tag_name in ("img", "audio", "video", "source", "script"):
                if src:
                    def found(resource, child=child):
                        _set_attribute(child, "src", _get_resource_uri(resource))
                    def not_found(child=child, src=src):
                        _set_attribute(child, "src", src)
                    _resolve_reference(
                        resources,
                        missing_resources,
                        unfound_resources,
                        {
                            "id": src,
                            "raw_id": child.get("src"),
                            "encoding": BASE64_ENCODING,
                            "found": found,
                            "not_found": not_found,
                        },
                    )
                if tag_name in ("img", "source"):
                    srcset = child.get("srcset")
                    if srcset:
                        srcset_data = parse_srcset(srcset)
                        for data in srcset_data:
                            candidate_src = _resolve_path(data["url"], base)
                            def found(resource, data=data):
                                data["url"] = _get_resource_uri(resource)
                            def not_found(data=data, candidate_src=candidate_src):
                                data["url"] = candidate_src
                            _resolve_reference(
                                resources,
                                missing_resources,
                                unfound_resources,
                                {
                                    "id": candidate_src,
                                    "raw_id": data["url"],
                                    "encoding": BASE64_ENCODING,
                                    "found": found,
                                    "not_found": not_found,
                                },
                            )
                        if not fetch_missing_resources:
                            _set_attribute(child, "srcset", serialize_srcset(srcset_data))
                elif tag_name == "script" and not fetch_missing_resources:
                    type_ = child.get("type")
                    if type_:
                        type_ = type_.lower()
                    if not enable_scripts and (not type_ or type_ != JSON_LD_CONTENT_TYPE):
                        removed_nodes.append(child)
            elif tag_name in ("body", "table", "td", "th"):
                background = child.get("background")
                if background and not background.startswith(DATA_PROTOCOL):
                    resolved_background = _resolve_path(background, base)
                    def found(resource, child=child):
                        _set_attribute(child, "background", _get_resource_uri(resource))
                    def not_found(child=child, resolved_background=resolved_background):
                        _set_attribute(child, "background", resolved_background)
                    _resolve_reference(
                        resources,
                        missing_resources,
                        unfound_resources,
                        {
                            "id": resolved_background,
                            "raw_id": background,
                            "encoding": BASE64_ENCODING,
                            "found": found,
                            "not_found": not_found,
                        },
                    )
            elif tag_name == "input":
                type_ = child.get("type")
                if type_ and type_.lower() == "image" and src:
                    def found(resource, child=child):
                        _set_attribute(child, "src", _get_resource_uri(resource))
                    def not_found(child=child, src=src):
                        _set_attribute(child, "src", src)
                    _resolve_reference(
                        resources,
                        missing_resources,
                        unfound_resources,
                        {
                            "id": src,
                            "raw_id": child.get("src"),
                            "encoding": BASE64_ENCODING,
                            "found": found,
                            "not_found": not_found,
                        },
                    )
            elif tag_name in ("iframe", "frame", "embed", "object"):
                attribute = "data" if tag_name == "object" else "src"
                if tag_name == "object":
                    src = child.get("data")
                    if src:
                        src = _resolve_path(src, base)
                if src:
                    frame_resource = None
                    if src.startswith(CID_PROTOCOL):
                        frame_id = f"<{src[len(CID_PROTOCOL) :]}>"
                        frame_resource = frames.get(frame_id)
                    else:
                        frame_id = src
                        frame_resource = _get_resource(resources, src, child.get(attribute))
                    if frame_resource is not None and not (
                        tag_name in ("embed", "object") or _is_media(frame_resource.content_type)
                    ):
                        result = _convert(
                            {
                                "resources": {**resources, frame_id: frame_resource},
                                "unfoundResources": unfound_resources,
                                "frames": frames,
                                "index": frame_id,
                                "id": frame_resource.id,
                            },
                            config,
                        )
                        if fetch_missing_resources:
                            for missing_resource in result:
                                if not any(resource["id"] == missing_resource["id"] for resource in missing_resources):
                                    missing_resources.append(missing_resource)
                        else:
                            frame_resource.used = True
                            if tag_name == "iframe":
                                _set_attribute(child, "src")
                                if "src" in child.attrib:
                                    del child.attrib["src"]
                                child.set("srcdoc", result["data"])
                            else:
                                _set_attribute(
                                    child,
                                    attribute,
                                    DATA_PROTOCOL
                                    + TEXT_HTML_CONTENT_TYPE
                                    + ","
                                    + urllib.parse.quote(result["data"], safe="!~*'()"),
                                )
                    else:
                        def found(resource, child=child, attribute=attribute):
                            _set_attribute(child, attribute, _get_resource_uri(resource))
                        def not_found(child=child, attribute=attribute, src=src):
                            _set_attribute(child, attribute, src)
                        _resolve_reference(
                            resources,
                            missing_resources,
                            unfound_resources,
                            {
                                "id": src,
                                "resource": frame_resource,
                                "found": found,
                                "not_found": not_found,
                            },
                        )
            elif tag_name in ("a", "area") and not fetch_missing_resources:
                if href:
                    try:
                        url_without_fragment, hash_fragment = _split_url_fragment(child.get("href"), base)
                        if url_without_fragment == base and hash_fragment:
                            child.set("href", hash_fragment)
                        else:
                            child.set("href", href)
                    except ValueError:
                        child.set("href", href)
                if "ping" in child.attrib:
                    del child.attrib["ping"]
            elif tag_name == "meta" and not fetch_missing_resources:
                http_equiv = child.get("http-equiv")
                if http_equiv:
                    http_equiv = http_equiv.lower()
                    if http_equiv in ("refresh", "content-security-policy"):
                        removed_nodes.append(child)
            elif tag_name == "template" and not fetch_missing_resources:
                shadow_mode_attribute = child.get("shadowmode")
                if shadow_mode_attribute:
                    del child.attrib["shadowmode"]
                    child.set("shadowrootmode", shadow_mode_attribute)
            elif (
                tag_name == "title"
                and not fetch_missing_resources
                and parent_tag_name == "head"
                and title is None
                and child.text_content()
            ):
                title = child.text_content()
            nodes.append(child)
    if fetch_missing_resources:
        return missing_resources
    for node in removed_nodes:
        _remove_element(node)
    if canonical_link_element is None:
        link_element = _make_element(head, "link")
        link_element.set("rel", "canonical")
        link_element.set("href", index)
        head.append(link_element)
    csp = DEFAULT_CSP + (JS_ENABLED_CSP if enable_scripts else JS_DISABLED_CSP)
    meta_element = _make_element(head, "meta")
    meta_element.set("http-equiv", "content-security-policy")
    meta_element.set("content", csp)
    if head.text or len(head):
        _prepend_element(head, meta_element)
    else:
        head.append(meta_element)
    meta_element = _make_element(head, "meta")
    meta_element.set("charset", UTF8_CHARSET)
    _prepend_element(head, meta_element)
    if headers:
        page_info_element = _make_element(head, "script")
        page_info_element.set("type", JSON_LD_CONTENT_TYPE)
        page_info_element.text = json.dumps(_get_page_info(headers, index), indent=2, ensure_ascii=False)
        if len(head):
            head[0].addnext(page_info_element)
        else:
            head.append(page_info_element)
    unfound_resource_ids = []
    if unfound_resources:
        for unfound_id in unfound_resources:
            if not unfound_id.startswith(DATA_PROTOCOL):
                placeholder = Resource(id=unfound_id)
                placeholder.not_found = True
                placeholder.used = True
                resources[unfound_id] = placeholder
                unfound_resource_ids.append(unfound_id)
    return {
        "title": title,
        "favicons": favicons,
        "unfoundResources": unfound_resource_ids,
        "anomalies": anomalies,
        "data": dom.serialize(),
    }
class _FetchResponse:
    __slots__ = ("status", "headers", "_bytes")
    def __init__(self, status: int, headers, payload: bytes):
        self.status = status
        self.headers = headers
        self._bytes = payload
    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300
    def bytes(self) -> bytes:
        return self._bytes
    def text(self) -> str:
        return self._bytes.decode("utf-8", errors="replace")
def _default_fetch(url: str) -> _FetchResponse:
    request = urllib.request.Request(url, headers={"Accept": "*/*"})
    try:
        with urllib.request.urlopen(request) as response:
            return _FetchResponse(response.status, response.headers, response.read())
    except urllib.error.HTTPError as error:
        payload = error.read() if hasattr(error, "read") else b""
        return _FetchResponse(error.code, error.headers, payload)
def _is_transient_status(status: int) -> bool:
    return status == TOO_MANY_REQUESTS_STATUS or SERVER_ERROR_STATUS <= status <= SERVER_ERROR_MAX_STATUS
def _get_retry_delay(response, index_attempt: int) -> float | None:
    retry_after = None
    if response.headers is not None:
        retry_after = response.headers.get("Retry-After")
    if retry_after:
        delay = _parse_retry_after(retry_after)
        return None if delay is None or delay > MAX_RETRY_DELAY else delay
    return _get_backoff_delay(index_attempt)
def _parse_retry_after(retry_after: str) -> float | None:
    try:
        return max(0.0, float(retry_after) * 1000.0)
    except ValueError:
        pass
    try:
        date = email.utils.parsedate_to_datetime(retry_after)
        return max(0.0, (date.timestamp() - time.time()) * 1000.0)
    except (TypeError, ValueError, OverflowError):
        return None
def _get_backoff_delay(index_attempt: int) -> float:
    return min(RETRY_BASE_DELAY * (2**index_attempt), MAX_RETRY_DELAY)
def _fetch_resources(missing_resources: list, mhtml: dict, config: dict, failed_resources: list) -> None:
    fetch = config.get("fetch") or _default_fetch
    max_parallel_requests = config.get("maxParallelRequests", DEFAULT_MAX_PARALLEL_REQUESTS)
    count_workers = max(1, min(max_parallel_requests, len(missing_resources)))
    chunks = [missing_resources[i::count_workers] for i in range(count_workers)]
    def worker(chunk):
        for resource in chunk:
            if _fetch_resource(resource, fetch, config):
                mhtml["resources"][resource["id"]] = _resource_from_missing(resource)
            elif resource["id"] not in failed_resources:
                failed_resources.append(resource["id"])
    if count_workers <= 1:
        worker(chunks[0])
    else:
        with ThreadPoolExecutor(max_workers=count_workers) as pool:
            list(pool.map(worker, chunks))
def _resource_from_missing(missing: dict) -> Resource:
    resource = Resource(
        id=missing["id"],
        transfer_encoding=missing.get("transferEncoding"),
        content_type=missing.get("contentType"),
        content_id=missing.get("contentId"),
    )
    resource.data = missing.get("data", "")
    resource.used = False
    return resource
def _fetch_resource(resource: dict, fetch, config: dict) -> bool:
    max_retries = config.get("maxRetries", DEFAULT_MAX_RETRIES)
    transfer_encoding = resource.get("transferEncoding")
    url = resource["id"]
    urn_error_match = URN_ERROR_REGEXP.match(url)
    if urn_error_match:
        url = urn_error_match.group(1)
    index_attempt = 0
    while True:
        delay = None
        try:
            response = fetch(url)
            if response.ok:
                resource["contentType"] = response.headers.get("Content-Type") or APPLICATION_OCTET_STREAM_CONTENT_TYPE
                if transfer_encoding == BASE64_ENCODING:
                    resource["data"] = _decode_binary(response.bytes())
                else:
                    resource["data"] = response.text()
                return True
            if not _is_transient_status(response.status):
                return False
            delay = _get_retry_delay(response, index_attempt)
        except Exception:
            delay = _get_backoff_delay(index_attempt)
        if delay is None or index_attempt >= max_retries:
            return False
        time.sleep(delay / 1000.0)
        index_attempt += 1
def _fetch_and_convert(mhtml: dict, config: dict, failed_resources: list | None = None) -> dict:
    if config.get("fetchMissingResources") or config.get("fetch_missing_resources"):
        failed = failed_resources if failed_resources is not None else []
        missing_resources = _convert(mhtml, config)
        missing_resources = [resource for resource in missing_resources if resource["id"] not in failed]
        if missing_resources:
            _fetch_resources(missing_resources, mhtml, config, failed)
            return _fetch_and_convert(mhtml, config, failed)
        config = {**config, "fetchMissingResources": False, "fetch_missing_resources": False}
        return _convert(mhtml, config)
    return _convert(mhtml, config)
def parse(data: bytes | bytearray | str, config: dict | None = None) -> dict:
    return _MhtmlParser(bytes(data) if not isinstance(data, str) else data.encode("utf-8")).parse()
def convert(mhtml, config: dict | None = None) -> dict:
    config = dict(config) if config else {}
    if isinstance(mhtml, (str, bytes, bytearray)):
        mhtml = parse(mhtml, config)
    return _fetch_and_convert(mhtml, config)
USAGE = """Usage: mhtml-to-html <input>... [--output <output>] [--help] [--enable-scripts] [--fetch-missing-resources] [--version]
 Arguments:
  <input>: The input MHTML file, wildcards are supported
 Options:
  --output <output>: The output HTML file (default: input file with .html extension), only used when a single input file is provided
  --help: Show this help message
  --enable-scripts: Enable scripts (default: disabled)
  --fetch-missing-resources: Fetch missing resources (default: disabled)
  --version: Show the version number
Examples:
 mhtml-to-html file.mht
 mhtml-to-html file1.mht file2.mht
 mhtml-to-html file.mht --output output_file.html
 mhtml-to-html *.mht
 mhtml-to-html *.mht *.mhtml
 mhtml-to-html *.mht --enable-scripts"""
def _is_glob(pattern: str) -> bool:
    files = globlib.glob(pattern, recursive=True)
    return len(files) > 1 or (len(files) == 1 and files[0] != pattern)
def _expand_glob(pattern: str) -> list[str]:
    return sorted(globlib.glob(pattern, recursive=True))
def _convert_file(
    input_path: str, output: str | None, config: dict, read_file=None, write_file=None, log_error=None
) -> None:
    output = output or re.sub(r"\.[^.]+$", ".html", input_path, count=1)
    if not output.endswith(".html"):
        output += ".html"
    read_file = read_file or (lambda path: open(path, "rb").read())
    write_file = write_file or _write_text_file
    log_error = log_error or _log_conversion_error
    try:
        mhtml = read_file(input_path)
        result = convert(mhtml, config)
        write_file(output, result["data"])
    except Exception as error:
        log_error(input_path, error)
def _write_text_file(path: str, data: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as file:
        file.write(data)
def _log_conversion_error(input_path: str, error: Exception) -> None:
    print(f"Error processing {input_path}: {error}", file=sys.stderr)
    traceback.print_exc()
def main(args: list[str] | None = None) -> int:
    positionals = list(sys.argv[1:]) if args is None else list(args)
    if "--output" in positionals:
        index_output = positionals.index("--output")
        next_value = positionals[index_output + 1] if index_output + 1 < len(positionals) else None
        output = next_value if next_value else ""
    else:
        output = None
    input_values = [
        arg
        for arg in positionals
        if arg != "--output" and arg != output and arg != "--enable-scripts" and arg != "--fetch-missing-resources"
    ]
    input_value = input_values[0] if input_values else ""
    enable_scripts = "--enable-scripts" in positionals
    fetch_missing_resources = "--fetch-missing-resources" in positionals
    version = "--version" in positionals
    help_requested = "--help" in positionals
    if input_value == "" or output == "" or help_requested:
        print(USAGE)
        return 1
    if version:
        print(__version__)
        return 0
    config = {"enableScripts": enable_scripts, "fetchMissingResources": fetch_missing_resources}
    if len(input_values) == 1 and not _is_glob(input_value):
        _convert_file(input_value, output, config)
    else:
        for value in input_values:
            if _is_glob(value):
                for path in _expand_glob(value):
                    _convert_file(path, None, config)
            else:
                _convert_file(value, None, config)
    return 0
if __name__ == "__main__":
    sys.exit(main())
