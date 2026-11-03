import base64
import html
import quopri
import re
import sys
import traceback
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from multiprocessing import Pool
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
BOM_UTF16BE = b"\xfe\xff"
BOM_UTF16LE = b"\xff\xfe"
BOM_UTF8 = b"\xef\xbb\xbf"
BOUNDARY_RE = re.compile("boundary\\s*=\\s*(?:\"([^\"]+)\"|\\'([^\\']+)\\'|([^\\s;]+))", re.IGNORECASE)
CHARSET_RE = re.compile('charset\\s*=\\s*"?([^";\\s]+)"?', re.IGNORECASE)
CSS_IMPORT_RE = re.compile(
    "@import\\s+(?:url\\(\\s*(?:\"([^\"]*)\"|\\'([^\\']*)\\'|([^)\\s]+))\\s*\\)|\"([^\"]*)\"|\\'([^\\']*)\\')",
    re.IGNORECASE,
)
CSS_URL_RE = re.compile("url\\(\\s*(?:\"([^\"]*)\"|\\'([^\\']*)\\'|([^)\\s\\'\"]+))\\s*\\)", re.IGNORECASE)
EVENT_HANDLER_ATTRS = {
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
}
HEADER_CONT_RE = re.compile("^[ \\t]")
HEADER_NAME_RE = re.compile("^[!-9;-~]+:")
HELP_TEXT = "Usage: mhtml_to_html <input>... [--output <output>] [--help] [--enable-scripts] [--fetch-missing-resources] [--version]\n Arguments:\n  <input>: The input MHTML file, wildcards are supported\n Options:\n  --output <output>: The output HTML file (default: input file with .html extension), only used when a single input file is provided\n  --help: Show this help message\n  --enable-scripts: Enable scripts (default: disabled)\n  --fetch-missing-resources: Fetch missing resources (default: disabled)\n  --version: Show the version number\n\nExamples:\n mhtml_to_html file.mht\n mhtml_to_html file1.mht file2.mht\n mhtml_to_html file.mht --output output_file.html\n mhtml_to_html *.mht\n mhtml_to_html *.mht *.mhtml\n mhtml_to_html *.mht --enable-scripts\n"
RAW_TEXT_ELEMENTS = {"style", "script", "xmp", "iframe", "noembed", "noframes", "plaintext", "noscript"}
REL_REMOVED = {"preconnect", "prerender", "dns-prefetch", "preload", "prefetch", "manifest", "modulepreload"}
SRCSET_RE = re.compile("\\s*,\\s*")
TEXT_HTML = "text/html"
UTF8_CHARSET = "utf-8"
VOID_ELEMENTS = {
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
}
WORKERS = 4
class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "is_text", "text", "is_comment", "is_doctype")
    def __init__(self, tag=None, attrs=None, parent=None, is_text=False, text="", is_comment=False, is_doctype=False):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.parent = parent
        self.is_text = is_text
        self.text = text
        self.is_comment = is_comment
        self.is_doctype = is_doctype
class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node(tag="document")
        self.current = self.root
        self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr_dict = {}
        for k, v in attrs:
            if v is None:
                v = ""
            attr_dict[k.lower()] = v
        node = Node(tag=tag, attrs=attr_dict, parent=self.current)
        self.current.children.append(node)
        if tag not in VOID_ELEMENTS:
            self.stack.append(node)
            self.current = node
    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                self.current = self.stack[-1]
                break
    def handle_data(self, data):
        if data is None:
            return
        node = Node(is_text=True, text=data, parent=self.current)
        self.current.children.append(node)
    def handle_comment(self, data):
        node = Node(tag="#comment", text=data, parent=self.current, is_comment=True)
        self.current.children.append(node)
    def handle_decl(self, decl):
        node = Node(tag="#doctype", text=decl, parent=self.current, is_doctype=True)
        self.current.children.append(node)
    def handle_pi(self, data):
        node = Node(tag="#comment", text=data, parent=self.current, is_comment=True)
        self.current.children.append(node)
def convert(mhtml_data, config=None):
    if isinstance(mhtml_data, dict) and "resources" in mhtml_data:
        parsed = mhtml_data
    elif isinstance(mhtml_data, str):
        parsed = parse_mhtml_bytes(mhtml_data.encode("utf-8"))
    elif isinstance(mhtml_data, (bytes, bytearray)):
        parsed = parse_mhtml_bytes(bytes(mhtml_data))
    else:
        raise TypeError("mhtml_data must be bytes, str, or parsed dict")
    if config and config.get("fetchMissingResources"):
        failed = set()
        import time
        import urllib.error
        import urllib.request
        max_retries = config.get("maxRetries", 2)
        max_parallel = config.get("maxParallelRequests", 16)
        while True:
            missing = (
                convert_mhtml(parsed, {**config, "fetchMissingResources": False, "_collect": True}) if False else None
            )
            missing_list = convert_mhtml(parsed, {**config, "fetchMissingResources": True})
            missing_list = [r for r in missing_list if r["id"] not in failed]
            if not missing_list:
                break
            for res_info in missing_list:
                url = res_info["id"]
                if url.startswith("urn:"):
                    m = re.match("^urn:[^:]+:(.+)$", url)
                    if m:
                        url = m.group(1)
                success = False
                for attempt in range(max_retries + 1):
                    try:
                        req = urllib.request.Request(url, headers={"User-Agent": "mhtml_to_html Python"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            if (
                                resp.status == 200
                                or (hasattr(resp, "getcode") and resp.getcode() == 200)
                                or resp.status is None
                            ):
                                data_bytes = resp.read()
                                ct = resp.headers.get("Content-Type", "application/octet-stream")
                                parsed["resources"][res_info["id"]] = {
                                    "id": res_info["id"],
                                    "contentType": ct,
                                    "data": data_bytes,
                                    "data_bytes": data_bytes,
                                    "transferEncoding": res_info.get("transferEncoding"),
                                }
                                success = True
                                break
                            else:
                                status = resp.status
                                if status == 429 or 500 <= status <= 599:
                                    delay = min(0.5 * 2**attempt, 5)
                                    time.sleep(delay)
                                    continue
                                else:
                                    break
                    except urllib.error.HTTPError as e:
                        if e.code == 429 or 500 <= e.code <= 599:
                            delay = min(0.5 * 2**attempt, 5)
                            time.sleep(delay)
                            continue
                        else:
                            break
                    except Exception:
                        delay = min(0.5 * 2**attempt, 5)
                        if attempt < max_retries:
                            time.sleep(delay)
                            continue
                        else:
                            break
                if not success:
                    failed.add(res_info["id"])
        return convert_mhtml(parsed, {**config, "fetchMissingResources": False})
    else:
        return convert_mhtml(parsed, config)
def convert_file(input_path, output_path, config):
    try:
        print(f"processing ...{input_path.name}")
        input_path = Path(input_path)
        if output_path is None:
            if input_path.suffix:
                out = input_path.with_suffix(".html")
            else:
                out = Path(str(input_path) + ".html")
            if not str(out).endswith(".html"):
                out = Path(str(out) + ".html")
        else:
            out = Path(output_path)
        data = input_path.read_bytes()
        result = convert(data, config)
        html_content = result["data"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_content, encoding="utf-8")
        return (str(input_path), str(out), True, None)
    except Exception as e:
        tb = traceback.format_exc()
        return (str(input_path), str(output_path) if output_path else None, False, f"{e}\n{tb}")
def convert_mhtml(parsed, config=None):
    if config is None:
        config = {}
    enable_scripts = config.get("enableScripts", False)
    fetch_missing = config.get("fetchMissingResources", False)
    headers = parsed.get("headers", {})
    frames = parsed.get("frames", {})
    resources = parsed.get("resources", {})
    index = parsed.get("index")
    anomalies = parsed.get("anomalies", [])
    unfound_resources = set()
    if not index:
        for res in resources.values():
            ct = res.get("contentTypeShort") or res.get("contentType", "")
            ct = ct.lower() if ct else ""
            if ct.startswith("image/"):
                uri = get_resource_uri(res)
                html_data = f'<html><body><img src="{uri}"></body></html>'
                res_id = "_synthesized"
                resources[res_id] = {
                    "id": res_id,
                    "contentType": "text/html",
                    "data": html_data,
                    "data_bytes": html_data.encode("utf-8"),
                }
                index = res_id
                anomalies = anomalies + [{"type": "index-synthesized", "id": index}]
                break
            elif ct.startswith("text/plain"):
                data = res.get("data")
                if isinstance(data, bytes):
                    try:
                        data = data.decode("utf-8", errors="replace")
                    except:
                        data = data.decode("latin-1", errors="replace")
                esc = html.escape(data)
                html_data = f"<html><body><pre>{esc}</pre></body></html>"
                res_id = "_synthesized"
                resources[res_id] = {
                    "id": res_id,
                    "contentType": "text/html",
                    "data": html_data,
                    "data_bytes": html_data.encode("utf-8"),
                }
                index = res_id
                anomalies = anomalies + [{"type": "index-synthesized", "id": index}]
                break
        if not index:
            raise ValueError("Index page not found")
    resource = resources.get(index)
    if not resource:
        for r in resources.values():
            if r["id"] == index:
                resource = r
                break
        if not resource:
            raise ValueError("Index page not found")
    html_data = resource.get("data")
    if isinstance(html_data, bytes):
        charset = get_charset(resource.get("contentType", "")) or "utf-8"
        try:
            html_data = html_data.decode(charset, errors="replace")
        except:
            html_data = html_data.decode("utf-8", errors="replace")
    if fetch_missing:
        missing_resources = []
        builder = TreeBuilder()
        try:
            builder.feed(html_data)
        except Exception:
            pass
        root = builder.root
        base = index
        base_elements = find_elements(root, "base")
        if base_elements:
            href = base_elements[0].attrs.get("href")
            if href:
                base = resolve_path(href, base)
        stylesheets_cache = {}
        def collect_walk(node, current_base):
            if node.is_text or node.is_comment or node.is_doctype:
                return
            if node.tag == "document":
                for child in node.children:
                    collect_walk(child, current_base)
                return
            tag = node.tag
            style_attr = node.attrs.get("style")
            if style_attr:
                replace_stylesheet_urls(
                    style_attr,
                    current_base,
                    resources,
                    stylesheets_cache,
                    missing_resources,
                    unfound_resources,
                    fetch_mode=True,
                )
            if tag == "link":
                href = node.attrs.get("href")
                rel = (node.attrs.get("rel") or "").lower()
                if href and "stylesheet" in rel:
                    resolved = resolve_path(href, current_base)
                    res = get_resource(resources, resolved, href)
                    if res:
                        css = res.get("data")
                        if isinstance(css, bytes):
                            try:
                                css = css.decode("utf-8", errors="replace")
                            except:
                                css = css.decode("latin-1", errors="replace")
                        replace_stylesheet_urls(
                            css,
                            res["id"],
                            resources,
                            stylesheets_cache,
                            missing_resources,
                            unfound_resources,
                            fetch_mode=True,
                        )
                    elif resolved.startswith("http://") or resolved.startswith("https://"):
                        if not any((r["id"] == resolved for r in missing_resources)):
                            missing_resources.append({"id": resolved, "transferEncoding": "base64"})
                elif href and "icon" in rel:
                    resolved = resolve_path(href, current_base)
                    res = get_resource(resources, resolved, href)
                    if not res:
                        if resolved.startswith("http://") or resolved.startswith("https://"):
                            if not any((r["id"] == resolved for r in missing_resources)):
                                missing_resources.append({"id": resolved, "transferEncoding": "base64"})
            elif tag == "style":
                css_text = "".join((child.text for child in node.children if child.is_text))
                replace_stylesheet_urls(
                    css_text,
                    current_base,
                    resources,
                    stylesheets_cache,
                    missing_resources,
                    unfound_resources,
                    fetch_mode=True,
                )
            elif tag in ("img", "audio", "video", "source", "script", "input", "iframe", "frame", "embed", "object"):
                src = node.attrs.get("src") or node.attrs.get("data")
                attr_name = "src" if tag != "object" else "data"
                src_val = node.attrs.get(attr_name)
                if src_val:
                    resolved = resolve_path(src_val, current_base)
                    if tag in ("iframe", "frame") and resolved:
                        res = get_resource(resources, resolved, src_val)
                        if res and is_document_content_type(
                            res.get("contentType", "") or res.get("contentTypeShort", "")
                        ):
                            frame_html = res.get("data")
                            if isinstance(frame_html, bytes):
                                try:
                                    frame_html = frame_html.decode("utf-8", errors="replace")
                                except:
                                    frame_html = frame_html.decode("latin-1", errors="replace")
                            fb = TreeBuilder()
                            try:
                                fb.feed(frame_html)
                                collect_walk(fb.root, res["id"])
                            except:
                                pass
                        elif not res and (resolved.startswith("http://") or resolved.startswith("https://")):
                            if not any((r["id"] == resolved for r in missing_resources)):
                                missing_resources.append({"id": resolved, "transferEncoding": "base64"})
                    else:
                        res = get_resource(resources, resolved, src_val)
                        if not res and (resolved.startswith("http://") or resolved.startswith("https://")):
                            if not any((r["id"] == resolved for r in missing_resources)):
                                missing_resources.append({"id": resolved, "transferEncoding": "base64"})
                srcset = node.attrs.get("srcset")
                if srcset:
                    for candidate in srcset.split(","):
                        candidate = candidate.strip()
                        if not candidate:
                            continue
                        parts = candidate.split()
                        if parts:
                            url = parts[0]
                            resolved = resolve_path(url, current_base)
                            res = get_resource(resources, resolved, url)
                            if not res and (resolved.startswith("http://") or resolved.startswith("https://")):
                                if not any((r["id"] == resolved for r in missing_resources)):
                                    missing_resources.append({"id": resolved, "transferEncoding": "base64"})
            for child in node.children:
                if not child.is_text and (not child.is_comment) and (not child.is_doctype):
                    collect_walk(child, current_base)
        collect_walk(root, base)
        return missing_resources
    builder = TreeBuilder()
    try:
        builder.feed(html_data)
    except Exception as e:
        pass
    root = builder.root
    base = index
    base_elements = find_elements(root, "base")
    base_href = None
    if base_elements:
        href = base_elements[0].attrs.get("href")
        if href:
            base_href = href
            base = resolve_path(href, base)
    canonical_element = None
    favicons = []
    title = None
    removed_nodes = []
    stylesheets_cache = {}
    def set_attribute_with_original(element, attr, new_val):
        old_val = element.attrs.get(attr)
        if old_val and (not old_val.startswith("data:")) and (old_val != new_val):
            element.attrs[f"data-original-{attr}"] = old_val
        if new_val is not None:
            element.attrs[attr] = new_val
    def walk(node, current_base):
        nonlocal canonical_element, title
        if node.is_text or node.is_comment or node.is_doctype:
            return
        if node.tag == "document":
            for child in list(node.children):
                walk(child, current_base)
            return
        tag = node.tag
        style_val = node.attrs.get("style")
        if style_val:
            new_style = replace_stylesheet_urls(
                style_val, current_base, resources, stylesheets_cache, [], unfound_resources, fetch_mode=False
            )
            if new_style != style_val:
                node.attrs["style"] = new_style
        if "integrity" in node.attrs:
            del node.attrs["integrity"]
        if not enable_scripts:
            to_remove = [k for k in node.attrs.keys() if k.lower() in EVENT_HANDLER_ATTRS]
            for k in to_remove:
                del node.attrs[k]
        if tag == "link":
            href = node.attrs.get("href")
            rel = (node.attrs.get("rel") or "").lower()
            if href:
                resolved_href = resolve_path(href, current_base)
                rel_tokens = rel.split()
                if "stylesheet" in rel_tokens:
                    res = get_resource(resources, resolved_href, href)
                    if res:
                        css_data = res.get("data")
                        if isinstance(css_data, bytes):
                            try:
                                css_data = css_data.decode("utf-8", errors="replace")
                            except:
                                css_data = css_data.decode("latin-1", errors="replace")
                        processed_css = replace_stylesheet_urls(
                            css_data, res["id"], resources, stylesheets_cache, [], unfound_resources, fetch_mode=False
                        )
                        has_title = "title" in node.attrs
                        is_alternate = "alternate" in rel_tokens
                        if has_title or is_alternate:
                            res["data"] = processed_css
                            res["data_bytes"] = processed_css.encode("utf-8")
                            uri = get_resource_uri(res)
                            set_attribute_with_original(node, "href", uri)
                        else:
                            style_elem = create_element("style")
                            media = node.attrs.get("media")
                            if media:
                                style_elem.attrs["media"] = media
                            text_node = Node(is_text=True, text=processed_css, parent=style_elem)
                            style_elem.children.append(text_node)
                            if node.parent:
                                idx = node.parent.children.index(node)
                                node.parent.children[idx] = style_elem
                                style_elem.parent = node.parent
                                res["used"] = True
                                return
                    else:
                        set_attribute_with_original(node, "href", resolved_href)
                        unfound_resources.add(resolved_href)
                elif "icon" in rel:
                    media = node.attrs.get("media")
                    type_attr = node.attrs.get("type")
                    sizes = node.attrs.get("sizes")
                    res = get_resource(resources, resolved_href, href)
                    if res:
                        uri = get_resource_uri(res)
                        set_attribute_with_original(node, "href", uri)
                        favicons.append({
                            "href": uri,
                            "media": media,
                            "type": type_attr,
                            "sizes": sizes,
                            "originalHref": resolved_href,
                        })
                        res["used"] = True
                    else:
                        set_attribute_with_original(node, "href", resolved_href)
                        favicons.append({"href": resolved_href, "media": media, "type": type_attr, "sizes": sizes})
                        unfound_resources.add(resolved_href)
                elif rel.strip() == "canonical":
                    if canonical_element is None:
                        canonical_element = node
                if rel_tokens:
                    filtered = [t for t in rel_tokens if t not in REL_REMOVED]
                    if filtered:
                        node.attrs["rel"] = " ".join(filtered)
                    else:
                        removed_nodes.append(node)
        elif tag == "style":
            css_text = "".join((child.text for child in node.children if child.is_text))
            processed = replace_stylesheet_urls(
                css_text, current_base, resources, stylesheets_cache, [], unfound_resources, fetch_mode=False
            )
            node.children = []
            new_text = Node(is_text=True, text=processed, parent=node)
            node.children.append(new_text)
        elif tag in ("img", "audio", "video", "source", "script", "input", "iframe", "frame", "embed", "object"):
            if tag == "object":
                attr_name = "data"
            else:
                attr_name = "src"
            src_val = node.attrs.get(attr_name)
            if src_val:
                resolved = resolve_path(src_val, current_base)
                if tag in ("iframe", "frame", "embed", "object"):
                    res = None
                    if resolved.startswith("cid:"):
                        cid = f"<{resolved[4:]}>"
                        res = frames.get(cid) or resources.get(cid)
                    else:
                        res = get_resource(resources, resolved, src_val)
                    if res and (
                        not (
                            tag in ("embed", "object")
                            and (
                                res.get("contentType", "").lower().startswith("image/")
                                or res.get("contentType", "").lower().startswith("audio/")
                                or res.get("contentType", "").lower().startswith("video/")
                                or res.get("contentType", "").lower().startswith("font/")
                            )
                        )
                    ):
                        ct = res.get("contentTypeShort") or res.get("contentType", "")
                        if is_document_content_type(ct) or (
                            not ct
                            and res.get("data")
                            and isinstance(res.get("data"), str)
                            and ("<html" in res.get("data").lower())
                        ):
                            try:
                                frame_result = convert_mhtml(
                                    {
                                        "headers": headers,
                                        "frames": frames,
                                        "resources": dict(resources),
                                        "index": res["id"],
                                        "anomalies": anomalies,
                                    },
                                    config,
                                )
                                if isinstance(frame_result, dict):
                                    converted_html = frame_result["data"]
                                    if tag == "iframe":
                                        if "src" in node.attrs:
                                            set_attribute_with_original(node, "src", None)
                                            if None in [node.attrs.get("src")]:
                                                if "src" in node.attrs:
                                                    del node.attrs["src"]
                                        node.attrs["srcdoc"] = converted_html
                                    else:
                                        data_uri = (
                                            f"data:text/html,{__import__('urllib.parse').parse.quote(converted_html)}"
                                        )
                                        set_attribute_with_original(node, attr_name, data_uri)
                                    res["used"] = True
                                else:
                                    pass
                            except Exception as e:
                                res_uri = get_resource_uri(res)
                                set_attribute_with_original(node, attr_name, res_uri)
                        elif res:
                            uri = get_resource_uri(res)
                            set_attribute_with_original(node, attr_name, uri)
                            res["used"] = True
                        else:
                            set_attribute_with_original(node, attr_name, resolved)
                            unfound_resources.add(resolved)
                    else:
                        res = get_resource(resources, resolved, src_val)
                        if res:
                            uri = get_resource_uri(res)
                            set_attribute_with_original(node, attr_name, uri)
                            res["used"] = True
                        else:
                            set_attribute_with_original(node, attr_name, resolved)
                            unfound_resources.add(resolved)
                else:
                    res = get_resource(resources, resolved, src_val)
                    if res:
                        uri = get_resource_uri(res)
                        set_attribute_with_original(node, attr_name, uri)
                        res["used"] = True
                    else:
                        set_attribute_with_original(node, attr_name, resolved)
                        unfound_resources.add(resolved)
            if tag in ("img", "source"):
                srcset = node.attrs.get("srcset")
                if srcset:
                    candidates = []
                    for part in srcset.split(","):
                        part = part.strip()
                        if not part:
                            continue
                        tokens = part.split()
                        if not tokens:
                            continue
                        url = tokens[0]
                        desc = " ".join(tokens[1:])
                        resolved = resolve_path(url, current_base)
                        res = get_resource(resources, resolved, url)
                        if res:
                            uri = get_resource_uri(res)
                            res["used"] = True
                            if desc:
                                candidates.append(f"{uri} {desc}")
                            else:
                                candidates.append(uri)
                        else:
                            if desc:
                                candidates.append(f"{resolved} {desc}")
                            else:
                                candidates.append(resolved)
                            unfound_resources.add(resolved)
                    new_srcset = ", ".join(candidates)
                    set_attribute_with_original(node, "srcset", new_srcset)
            if tag == "script" and (not enable_scripts):
                type_attr = node.attrs.get("type")
                if type_attr:
                    type_attr = type_attr.lower()
                if not type_attr or type_attr != "application/ld+json":
                    removed_nodes.append(node)
                    return
        elif tag in ("body", "table", "td", "th"):
            bg = node.attrs.get("background")
            if bg and (not bg.startswith("data:")):
                resolved = resolve_path(bg, current_base)
                res = get_resource(resources, resolved, bg)
                if res:
                    uri = get_resource_uri(res)
                    set_attribute_with_original(node, "background", uri)
                    res["used"] = True
                else:
                    set_attribute_with_original(node, "background", resolved)
                    unfound_resources.add(resolved)
        elif tag == "input":
            type_attr = node.attrs.get("type")
            if type_attr and type_attr.lower() == "image":
                src_val = node.attrs.get("src")
                if src_val:
                    resolved = resolve_path(src_val, current_base)
                    res = get_resource(resources, resolved, src_val)
                    if res:
                        uri = get_resource_uri(res)
                        set_attribute_with_original(node, "src", uri)
                        res["used"] = True
                    else:
                        set_attribute_with_original(node, "src", resolved)
                        unfound_resources.add(resolved)
        elif tag in ("a", "area"):
            href = node.attrs.get("href")
            if href:
                resolved = resolve_path(href, current_base)
                try:
                    from urllib.parse import urlparse as up
                    parsed_base = up(current_base)
                    parsed_href = up(href)
                    from urllib.parse import urldefrag, urljoin
                    abs_href = urljoin(current_base, href)
                    defrag, frag = urldefrag(abs_href)
                    if defrag == current_base and frag:
                        node.attrs["href"] = f"#{frag}"
                    else:
                        set_attribute_with_original(node, "href", resolved)
                except Exception:
                    set_attribute_with_original(node, "href", resolved)
            if "ping" in node.attrs:
                del node.attrs["ping"]
        elif tag == "meta":
            http_equiv = (node.attrs.get("http-equiv") or "").lower()
            if http_equiv in ("refresh", "content-security-policy"):
                removed_nodes.append(node)
                return
        elif tag == "template":
            shadowmode = node.attrs.get("shadowmode")
            if shadowmode:
                del node.attrs["shadowmode"]
                node.attrs["shadowrootmode"] = shadowmode
        elif tag == "title":
            parent_tag = node.parent.tag if node.parent else ""
            if parent_tag == "head" and title is None:
                text_content = "".join((child.text for child in node.children if child.is_text))
                if text_content:
                    title = text_content
        for child in list(node.children):
            if not child.is_text and (not child.is_comment) and (not child.is_doctype):
                walk(child, current_base)
    walk(root, base)
    for n in removed_nodes:
        if n.parent and n in n.parent.children:
            n.parent.children.remove(n)
    for be in base_elements:
        if be.parent and be in be.parent.children:
            be.parent.children.remove(be)
    head = find_head(root)
    if not head:
        html_node = find_first(root, "html")
        if not html_node:
            html_node = create_element("html")
            root.children.insert(0, html_node)
        head = create_element("head")
        html_node.children.insert(0, head)
        head.parent = html_node
    if not canonical_element:
        link_elem = create_element("link", {"rel": "canonical", "href": index})
        head.children.append(link_elem)
        link_elem.parent = head
    csp_meta = create_element("meta", {"http-equiv": "Content-Security-Policy"})
    csp = "default-src 'none'; connect-src 'self' data:; font-src 'self' data:; img-src 'self' data:; style-src 'self' 'unsafe-inline' data:; frame-src 'self' data:; media-src 'self' data:; object-src 'self' data:; "
    if enable_scripts:
        csp += "script-src 'self' 'unsafe-inline' data:;"
    else:
        csp += "script-src 'none';"
    csp_meta.attrs["content"] = csp
    if head.children:
        head.children.insert(0, csp_meta)
        csp_meta.parent = head
    else:
        head.children.append(csp_meta)
        csp_meta.parent = head
    charset_meta = create_element("meta", {"charset": "utf-8"})
    head.children.insert(0, charset_meta)
    charset_meta.parent = head
    if headers:
        subject = headers.get("subject", "")
        date = headers.get("date", "")
        from_header = headers.get("from", "")
        page_info = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "additionalProperty": {"@type": "PropertyValue", "name": "savedBy"},
        }
        if subject or date or from_header:
            page_info["name"] = subject
            page_info["datePublished"] = date
            page_info["author"] = from_header
        import json
        script_elem = create_element("script", {"type": "application/ld+json"})
        text_node = Node(is_text=True, text=json.dumps(page_info, indent=2), parent=script_elem)
        script_elem.children.append(text_node)
        if len(head.children) > 1:
            head.children.insert(1, script_elem)
        else:
            head.children.append(script_elem)
        script_elem.parent = head
    final_html = serialize_node(root)
    unfound_list = [u for u in unfound_resources if not u.startswith("data:")]
    if index in resources:
        resources[index]["used"] = True
    return {
        "title": title,
        "favicons": favicons,
        "unfoundResources": unfound_list,
        "anomalies": anomalies,
        "data": final_html,
    }
def convert_mhtml_wrapper(mhtml_bytes, config=None):
    return convert(mhtml_bytes, config)
def create_element(tag, attrs=None, parent=None):
    return Node(tag=tag, attrs=attrs or {}, parent=parent)
def decode_base64_bytes(data_str: str):
    try:
        cleaned = "".join(data_str.split())
        missing = len(cleaned) % 4
        if missing:
            cleaned += "=" * (4 - missing)
        return base64.b64decode(cleaned, validate=False)
    except Exception:
        return None
def decode_quoted_printable_bytes(data: bytes) -> bytes:
    try:
        return quopri.decodestring(data)
    except Exception:
        return data
def escape_attr(val):
    return html.escape(val, quote=True)
def escape_text(val):
    return html.escape(val, quote=False)
def expand_glob(pattern: str):
    p = Path(pattern)
    if p.is_absolute():
        try:
            base = Path(p.anchor)
            rel_pattern = str(p.relative_to(base))
            if not is_glob_pattern(rel_pattern):
                if p.exists():
                    return [p]
                else:
                    return []
            matched = list(base.glob(rel_pattern))
            return [m for m in matched if m.is_file()]
        except Exception:
            if p.exists():
                return [p]
            return []
    else:
        if not is_glob_pattern(pattern):
            fp = Path(pattern)
            if fp.exists() and fp.is_file():
                return [fp]
            return []
        cwd = Path.cwd()
        try:
            matched = list(cwd.glob(pattern))
            files = [m for m in matched if m.is_file()]
            return files
        except Exception:
            return []
def find_elements(root, tag_name):
    result = []
    def dfs(node):
        if node.tag == tag_name:
            result.append(node)
        for child in node.children:
            if not child.is_text and (not child.is_comment) and (not child.is_doctype):
                dfs(child)
    dfs(root)
    return result
def find_first(root, tag_name):
    stack = [root]
    while stack:
        node = stack.pop(0)
        if node.tag == tag_name:
            return node
        for child in reversed(node.children):
            if not child.is_text and (not child.is_comment) and (not child.is_doctype):
                stack.append(child)
    return None
def find_head(root):
    html_node = find_first(root, "html")
    if html_node:
        for child in html_node.children:
            if child.tag == "head":
                return child
    head = find_first(root, "head")
    return head
def flatten_chunks(chunks):
    if not chunks:
        return b""
    if len(chunks) == 1:
        return chunks[0]
    total = sum((len(c) for c in chunks))
    out = bytearray(total)
    off = 0
    for c in chunks:
        out[off : off + len(c)] = c
        off += len(c)
    return bytes(out)
def get_bom_charset(data: bytes):
    if data.startswith(BOM_UTF8):
        return ("utf-8", 3)
    if data.startswith(BOM_UTF16LE):
        return ("utf-16le", 2)
    if data.startswith(BOM_UTF16BE):
        return ("utf-16be", 2)
    return (None, 0)
def get_boundary(content_type: str):
    if not content_type:
        return None
    m = BOUNDARY_RE.search(content_type)
    if m:
        return m.group(1) or m.group(2) or m.group(3)
    return None
def get_charset(content_type: str):
    if not content_type:
        return None
    m = CHARSET_RE.search(content_type)
    if m:
        return (m.group(1) or "").strip(" \"'").lower()
    return None
def get_media_type(content_type):
    if not content_type:
        return "application/octet-stream"
    parts = content_type.split(";")
    media = parts[0].strip()
    cleaned_params = []
    for p in parts[1:]:
        p = p.strip()
        if "=" in p:
            k, v = p.split("=", 1)
            v = v.strip().strip('"').strip("'").strip()
            cleaned_params.append(f"{k.strip()}={v}")
        else:
            cleaned_params.append(p)
    if cleaned_params:
        return media + ";" + ";".join(cleaned_params)
    return media
def get_resource(resources, res_id, raw_id=None):
    if not res_id:
        return None
    if res_id in resources:
        return resources[res_id]
    if raw_id and raw_id in resources:
        return resources[raw_id]
    if res_id.startswith("cid:"):
        cid = f"<{res_id[4:]}>"
        if cid in resources:
            return resources[cid]
        if res_id[4:] in resources:
            return resources[res_id[4:]]
    norm = normalize_location(res_id)
    if norm != res_id and norm in resources:
        return resources[norm]
    return None
def get_resource_uri(resource):
    content_type = resource.get("contentType") or resource.get("contentTypeShort") or "application/octet-stream"
    media_type = get_media_type(content_type)
    media_type = media_type.replace(" ", "")
    data_bytes = resource.get("data_bytes")
    if data_bytes is None:
        data = resource.get("data")
        if isinstance(data, bytes):
            data_bytes = data
        elif isinstance(data, str):
            data_bytes = data.encode("utf-8")
        else:
            data_bytes = b""
    b64 = base64.b64encode(data_bytes).decode("ascii")
    return f"data:{media_type};base64,{b64}"
def is_document_content_type(ct: str) -> bool:
    if not ct:
        return False
    ct = ct.lower().split(";")[0].strip()
    return ct == "text/html" or ct == "application/xhtml+xml"
def is_glob(pattern: str) -> bool:
    if not is_glob_pattern(pattern):
        return False
    expanded = expand_glob(pattern)
    if len(expanded) > 1:
        return True
    if len(expanded) == 1:
        exp_str = str(expanded[0])
        return (
            exp_str != pattern
            and Path(exp_str).name != pattern
            and (str(Path(exp_str).resolve()) != str(Path(pattern).resolve()))
        )
    return False
def is_glob_pattern(pattern: str) -> bool:
    glob_chars = set("*?[]{}!")
    return any((c in pattern for c in glob_chars))
def is_stylesheet_content_type(ct: str) -> bool:
    if not ct:
        return False
    return ct.lower().split(";")[0].strip() == "text/css"
def is_text_content_type(ct: str) -> bool:
    if not ct:
        return False
    ct = ct.lower()
    return ct.startswith("text/")
def main_cli(args=None):
    if args is None:
        args = sys.argv[1:]
    if not args or "--help" in args:
        print(HELP_TEXT)
        sys.exit(1)
    if "--version" in args:
        print(__version__)
        return
    output = None
    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output = args[idx + 1]
        else:
            print(HELP_TEXT)
            print("\nError: --output requires a value")
            sys.exit(1)
    enable_scripts = "--enable-scripts" in args
    fetch_missing = "--fetch-missing-resources" in args
    input_values = []
    skip_next = False
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == "--output":
            skip_next = True
            continue
        if arg in ("--enable-scripts", "--fetch-missing-resources", "--version", "--help"):
            continue
        if output is not None and arg == output:
            if i > 0 and args[i - 1] == "--output":
                continue
        input_values.append(arg)
    if not input_values:
        print(HELP_TEXT)
        sys.exit(1)
    if output == "":
        print(HELP_TEXT)
        sys.exit(1)
    config = {"enableScripts": enable_scripts, "fetchMissingResources": fetch_missing}
    if len(input_values) == 1 and (not is_glob(input_values[0])) and (not is_glob_pattern(input_values[0])):
        inp = input_values[0]
        p = Path(inp)
        if not p.exists():
            print(f"Error: Input file not found: {inp}", file=sys.stderr)
            sys.exit(1)
        result = convert_file(p, output, config)
        if not result[2]:
            print(f"Error processing {result[0]}: {result[3]}", file=sys.stderr)
        return
    all_files = []
    for pattern in input_values:
        if is_glob_pattern(pattern):
            expanded = expand_glob(pattern)
            if expanded:
                all_files.extend(expanded)
            else:
                p = Path(pattern)
                if p.exists():
                    all_files.append(p)
                else:
                    print(f"Warning: No files matched pattern: {pattern}", file=sys.stderr)
        else:
            p = Path(pattern)
            if p.exists():
                all_files.append(p)
            else:
                print(f"Warning: File not found: {pattern}", file=sys.stderr)
    seen = set()
    unique_files = []
    for f in all_files:
        try:
            rp = f.resolve()
        except:
            rp = f
        if rp not in seen:
            seen.add(rp)
            unique_files.append(f)
    if not unique_files:
        print("No input files found.", file=sys.stderr)
        sys.exit(1)
    if output is not None and len(unique_files) > 1:
        print("Warning: --output is ignored when multiple input files are provided", file=sys.stderr)
        output = None
    if len(unique_files) > 1:
        with Pool(processes=8) as pool:
            async_results = []
            for f in unique_files:
                async_res = pool.apply_async(convert_file, args=(f, None, config))
                async_results.append(async_res)
            for ar in async_results:
                try:
                    inp, out, success, err = ar.get()
                    if not success:
                        print(f"Error processing {inp}: {err}", file=sys.stderr)
                    else:
                        print(f"Converted {inp} -> {out}")
                except Exception as e:
                    print(f"Error in worker: {e}", file=sys.stderr)
    else:
        f = unique_files[0]
        inp, out, success, err = convert_file(f, output, config)
        if not success:
            print(f"Error processing {inp}: {err}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Converted {inp} -> {out}")
def manual_parse_mhtml(data: bytes):
    resources = {}
    frames = {}
    anomalies = []
    headers = {}
    index = None
    generated_id = 0
    def find_header_end(d):
        idx = d.find(b"\r\n\r\n")
        if idx != -1:
            return (idx + 4, 2)
        idx = d.find(b"\n\n")
        if idx != -1:
            return (idx + 2, 1)
        return (None, None)
    header_end, _ = find_header_end(data)
    if header_end is None:
        if starts_with_markup(data):
            content_type = TEXT_HTML
            bom_charset, bom_off = get_bom_charset(data)
            charset = bom_charset or "utf-8"
            try:
                text = data[bom_off:].decode(charset, errors="replace")
            except:
                text = data.decode("utf-8", errors="replace")
            res_id = "_0"
            resources[res_id] = {
                "id": res_id,
                "contentType": content_type,
                "data": text,
                "data_bytes": data,
                "transferEncoding": None,
                "contentId": None,
            }
            index = res_id
            return {
                "headers": {},
                "frames": {},
                "resources": resources,
                "index": index,
                "anomalies": [{"type": "document-mislabeled-as-archive"}],
            }
        else:
            return {"headers": {}, "frames": {}, "resources": {}, "index": None, "anomalies": []}
    top_header_bytes = data[:header_end]
    headers = parse_headers_from_bytes(top_header_bytes)
    body = data[header_end:]
    ct = headers.get("content-type", "")
    boundary = get_boundary(ct)
    if not boundary:
        for line in body.splitlines()[:20]:
            if line.startswith(b"--"):
                cand = line[2:].strip()
                if cand.endswith(b"--"):
                    cand = cand[:-2]
                try:
                    cand_str = cand.decode("utf-8", errors="ignore").strip()
                    if cand_str:
                        boundary = cand_str
                        break
                except:
                    pass
        if not boundary:
            b_header_end, _ = find_header_end(body)
            if b_header_end:
                part_headers = parse_headers_from_bytes(body[:b_header_end])
                part_body = body[b_header_end:]
                content_type = part_headers.get("content-type", TEXT_HTML)
                content_location = part_headers.get("content-location")
                content_id = part_headers.get("content-id")
                transfer_enc = part_headers.get("content-transfer-encoding", "").lower()
                res_id = content_location or content_id or f"_{generated_id}"
                if not content_location and (not content_id):
                    generated_id += 1
                norm_id = normalize_location(res_id)
                data_bytes = part_body
                if transfer_enc == "base64":
                    decoded = decode_base64_bytes(data_bytes.decode("utf-8", errors="ignore"))
                    if decoded is not None:
                        data_bytes = decoded
                elif transfer_enc == "quoted-printable":
                    data_bytes = decode_quoted_printable_bytes(data_bytes)
                charset = get_charset(content_type) or "utf-8"
                try:
                    text_data = data_bytes.decode(charset, errors="replace")
                except:
                    try:
                        text_data = data_bytes.decode("utf-8", errors="replace")
                    except:
                        text_data = data_bytes.decode("latin-1", errors="replace")
                resources[norm_id] = {
                    "id": norm_id,
                    "contentType": content_type,
                    "data": text_data,
                    "data_bytes": data_bytes,
                    "transferEncoding": transfer_enc,
                    "contentId": content_id,
                    "contentLocation": content_location,
                }
                if content_id:
                    frames[content_id] = resources[norm_id]
                if content_location and normalize_location(content_location) != norm_id:
                    resources[content_location] = resources[norm_id]
                index = norm_id
                return {
                    "headers": headers,
                    "frames": frames,
                    "resources": resources,
                    "index": index,
                    "anomalies": [{"type": "multipart-without-delimiters"}] if "multipart" in ct.lower() else [],
                }
            else:
                charset = get_charset(ct) or "utf-8"
                try:
                    text_data = body.decode(charset, errors="replace")
                except:
                    text_data = body.decode("utf-8", errors="replace")
                res_id = headers.get("content-location") or headers.get("content-id") or f"_{generated_id}"
                norm_id = normalize_location(res_id)
                resources[norm_id] = {
                    "id": norm_id,
                    "contentType": ct or TEXT_HTML,
                    "data": text_data,
                    "data_bytes": body,
                    "transferEncoding": headers.get("content-transfer-encoding", "").lower(),
                    "contentId": headers.get("content-id"),
                    "contentLocation": headers.get("content-location"),
                }
                index = norm_id
                return {"headers": headers, "frames": frames, "resources": resources, "index": index, "anomalies": []}
    boundary_bytes = boundary.encode("utf-8", errors="ignore")
    delimiter = b"--" + boundary_bytes
    parts_raw = body.split(delimiter)
    for part_raw in parts_raw[1:]:
        if part_raw.startswith(b"--"):
            break
        if part_raw.startswith(b"\r\n"):
            part_raw = part_raw[2:]
        elif part_raw.startswith(b"\n"):
            part_raw = part_raw[1:]
        h_end, _ = find_header_end(part_raw)
        if h_end is None:
            continue
        part_header_bytes = part_raw[:h_end]
        part_body_bytes = part_raw[h_end:]
        if part_body_bytes.endswith(b"\r\n"):
            part_body_bytes = part_body_bytes[:-2]
        elif part_body_bytes.endswith(b"\n"):
            part_body_bytes = part_body_bytes[:-1]
        part_headers = parse_headers_from_bytes(part_header_bytes)
        content_type = part_headers.get("content-type", "")
        content_location = part_headers.get("content-location")
        content_id = part_headers.get("content-id")
        transfer_enc = part_headers.get("content-transfer-encoding", "").lower()
        data_bytes = part_body_bytes
        if transfer_enc == "base64":
            try:
                text_b64 = data_bytes.decode("utf-8", errors="ignore")
                decoded = decode_base64_bytes(text_b64)
                if decoded is not None:
                    data_bytes = decoded
                else:
                    anomalies.append({"type": "base64-left-encoded", "id": content_location or content_id})
            except Exception:
                pass
        elif transfer_enc == "quoted-printable":
            data_bytes = decode_quoted_printable_bytes(data_bytes)
        res_id_raw = content_location or content_id
        if not res_id_raw:
            res_id_raw = f"_{generated_id}"
            generated_id += 1
        norm_id = normalize_location(res_id_raw)
        charset = get_charset(content_type)
        bom_charset, bom_off = get_bom_charset(data_bytes)
        used_charset = bom_charset or charset or "utf-8"
        try:
            text_data = (
                data_bytes[bom_off:].decode(used_charset, errors="replace")
                if bom_charset
                else data_bytes.decode(used_charset, errors="replace")
            )
        except Exception:
            try:
                text_data = data_bytes.decode("utf-8", errors="replace")
            except:
                text_data = data_bytes.decode("latin-1", errors="replace")
        is_text = (
            is_text_content_type(content_type)
            or is_document_content_type(content_type)
            or is_stylesheet_content_type(content_type)
        )
        stored_data = text_data if is_text else data_bytes
        resource = {
            "id": norm_id,
            "contentType": content_type or "application/octet-stream",
            "data": stored_data,
            "data_bytes": data_bytes,
            "transferEncoding": transfer_enc,
            "contentId": content_id,
            "contentLocation": content_location,
            "rawId": res_id_raw,
        }
        if norm_id not in resources:
            resources[norm_id] = resource
        if res_id_raw != norm_id and res_id_raw not in resources:
            resources[res_id_raw] = resource
        if content_id:
            frames[content_id] = resource
            if content_id not in resources:
                resources[content_id] = resource
        if content_location:
            pass
        if index is None and is_document_content_type(content_type):
            index = norm_id
    if index is None:
        for rid, res in resources.items():
            if is_document_content_type(res.get("contentType", "")):
                index = res["id"]
                break
    if index is None and resources:
        first = next(iter(resources.values()))
        index = first["id"]
    return {"headers": headers, "frames": frames, "resources": resources, "index": index, "anomalies": anomalies}
def normalize_location(value: str) -> str:
    if not value:
        return value
    value = value.strip()
    if value.startswith("<") and value.endswith(">"):
        return value
    if value.startswith("_"):
        return value
    try:
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            return value
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        if scheme == "http" and netloc.endswith(":80"):
            netloc = netloc[:-3]
        elif scheme == "https" and netloc.endswith(":443"):
            netloc = netloc[:-4]
        normalized = urlunparse((scheme, netloc, parsed.path or "", parsed.params, parsed.query, parsed.fragment))
        return normalized
    except Exception:
        return value
def parse_headers_from_bytes(header_bytes: bytes):
    try:
        text = header_bytes.decode("utf-8", errors="replace")
    except:
        text = header_bytes.decode("latin-1", errors="replace")
    headers = {}
    current_key = None
    for line in text.splitlines():
        if not line:
            continue
        if HEADER_CONT_RE.match(line) and current_key:
            headers[current_key] += " " + line.strip()
        elif HEADER_NAME_RE.match(line):
            idx = line.find(":")
            if idx != -1:
                key = line[:idx].strip().lower()
                val = line[idx + 1 :].strip()
                headers[key] = val
                current_key = key
    return headers
def parse_mhtml(file_path_or_bytes):
    if isinstance(file_path_or_bytes, (bytes, bytearray)):
        return parse_mhtml_bytes(bytes(file_path_or_bytes))
    else:
        p = Path(file_path_or_bytes)
        data = p.read_bytes()
        return parse_mhtml_bytes(data)
def parse_mhtml_bytes(data: bytes):
    if not data:
        return {"headers": {}, "frames": {}, "resources": {}, "index": None, "anomalies": []}
    if starts_with_markup(data):
        bom_charset, bom_off = get_bom_charset(data)
        charset = bom_charset or "utf-8"
        try:
            text = data[bom_off:].decode(charset, errors="replace")
        except:
            text = data.decode("utf-8", errors="replace")
        res_id = "_0"
        resources = {
            res_id: {
                "id": res_id,
                "contentType": TEXT_HTML,
                "data": text,
                "data_bytes": data,
                "transferEncoding": None,
                "contentId": None,
            }
        }
        return {
            "headers": {"content-type": TEXT_HTML},
            "frames": {},
            "resources": resources,
            "index": res_id,
            "anomalies": [{"type": "document-mislabeled-as-archive"}],
        }
    try:
        parser = BytesParser(policy=policy.default)
        msg = parser.parsebytes(data)
        if msg.is_multipart():
            resources = {}
            frames = {}
            anomalies = []
            headers = {}
            for k, v in msg.items():
                headers[k.lower()] = str(v)
            index = None
            gen_id = 0
            for part in msg.iter_parts():
                if part.is_multipart():
                    continue
                content_type = part.get_content_type() or "application/octet-stream"
                ct_header = part.get("Content-Type") or content_type
                content_location = part.get("Content-Location")
                content_id = part.get("Content-ID")
                transfer_enc = (part.get("Content-Transfer-Encoding") or "").lower()
                payload_bytes = part.get_payload(decode=True)
                if payload_bytes is None:
                    payload = part.get_payload(decode=False)
                    if isinstance(payload, str):
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            payload_bytes = payload.encode(charset, errors="replace")
                        except:
                            payload_bytes = payload.encode("utf-8", errors="replace")
                    elif isinstance(payload, bytes):
                        payload_bytes = payload
                    else:
                        payload_bytes = b""
                raw_id = content_location or content_id
                if not raw_id:
                    raw_id = f"_{gen_id}"
                    gen_id += 1
                norm_id = normalize_location(raw_id)
                is_text = (
                    is_text_content_type(content_type)
                    or is_document_content_type(content_type)
                    or is_stylesheet_content_type(content_type)
                )
                charset = part.get_content_charset() or get_charset(ct_header) or "utf-8"
                bom_charset, bom_off = get_bom_charset(payload_bytes)
                used_charset = bom_charset or charset
                try:
                    if bom_charset:
                        text_data = payload_bytes[bom_off:].decode(used_charset, errors="replace")
                    else:
                        text_data = payload_bytes.decode(used_charset, errors="replace")
                except Exception:
                    try:
                        text_data = payload_bytes.decode("utf-8", errors="replace")
                    except:
                        text_data = payload_bytes.decode("latin-1", errors="replace")
                stored_data = text_data if is_text else payload_bytes
                resource = {
                    "id": norm_id,
                    "contentType": ct_header,
                    "contentTypeShort": content_type,
                    "data": stored_data,
                    "data_bytes": payload_bytes,
                    "transferEncoding": transfer_enc,
                    "contentId": content_id,
                    "contentLocation": content_location,
                    "rawId": raw_id,
                }
                if norm_id not in resources:
                    resources[norm_id] = resource
                if raw_id != norm_id and raw_id not in resources:
                    resources[raw_id] = resource
                if content_id:
                    frames[content_id] = resource
                    if content_id not in resources:
                        resources[content_id] = resource
                if index is None and is_document_content_type(content_type):
                    index = norm_id
            if index is None:
                for r in resources.values():
                    if is_document_content_type(r.get("contentTypeShort") or r.get("contentType", "")):
                        index = r["id"]
                        break
            if index is None and resources:
                first = next(iter(resources.values()))
                index = first["id"]
            if resources:
                return {
                    "headers": headers,
                    "frames": frames,
                    "resources": resources,
                    "index": index,
                    "anomalies": anomalies,
                }
    except Exception as e:
        pass
    return manual_parse_mhtml(data)
def replace_stylesheet_urls(
    css_text, base, resources, stylesheets_cache, missing_resources, unfound_resources, fetch_mode=False
):
    if not css_text:
        return css_text
    def import_repl(match):
        url = match.group(1) or match.group(2) or match.group(3) or match.group(4) or match.group(5)
        if not url:
            return match.group(0)
        if url.startswith("data:") or url.startswith("--mhtml_to_html-url"):
            return match.group(0)
        resolved = resolve_path(url, base)
        res = get_resource(resources, resolved, url)
        if res:
            if is_stylesheet_content_type(res.get("contentType", "")) or is_stylesheet_content_type(
                res.get("contentTypeShort", "")
            ):
                inner_css = res.get("data")
                if isinstance(inner_css, bytes):
                    try:
                        inner_css = inner_css.decode("utf-8", errors="replace")
                    except:
                        inner_css = inner_css.decode("latin-1", errors="replace")
                cache_key = res["id"]
                if cache_key not in stylesheets_cache:
                    stylesheets_cache[cache_key] = {}
                    processed = replace_stylesheet_urls(
                        inner_css,
                        res["id"],
                        resources,
                        stylesheets_cache,
                        missing_resources,
                        unfound_resources,
                        fetch_mode,
                    )
                    stylesheets_cache[cache_key] = {"data": processed}
                    inner_css = processed
                else:
                    cached = stylesheets_cache[cache_key]
                    if isinstance(cached, dict) and "data" in cached:
                        inner_css = cached["data"]
                if fetch_mode:
                    pass
                uri = get_resource_uri(res) if not isinstance(res.get("data"), str) or True else get_resource_uri(res)
                return f'@import url("{uri}")'
            else:
                if not fetch_mode:
                    uri = get_resource_uri(res)
                    return f'@import url("{uri}")'
                return match.group(0)
        else:
            if fetch_mode:
                if resolved.startswith("http://") or resolved.startswith("https://"):
                    if not any((r["id"] == resolved for r in missing_resources)):
                        missing_resources.append({"id": resolved, "transferEncoding": "base64"})
            else:
                unfound_resources.add(resolved)
            return match.group(0)
    css_text = CSS_IMPORT_RE.sub(import_repl, css_text)
    def url_repl(match):
        url = match.group(1) or match.group(2) or match.group(3)
        if not url:
            return match.group(0)
        if url.startswith("data:") or url.startswith("--mhtml_to_html-url"):
            return match.group(0)
        if url.startswith("#"):
            return match.group(0)
        resolved = resolve_path(url, base)
        res = get_resource(resources, resolved, url)
        if res:
            if is_stylesheet_content_type(res.get("contentType", "")) or is_stylesheet_content_type(
                res.get("contentTypeShort", "")
            ):
                inner_css = res.get("data")
                if isinstance(inner_css, bytes):
                    try:
                        inner_css = inner_css.decode("utf-8", errors="replace")
                    except:
                        inner_css = inner_css.decode("latin-1", errors="replace")
                cache_key = res["id"]
                if cache_key not in stylesheets_cache:
                    stylesheets_cache[cache_key] = {}
                    processed = replace_stylesheet_urls(
                        inner_css,
                        res["id"],
                        resources,
                        stylesheets_cache,
                        missing_resources,
                        unfound_resources,
                        fetch_mode,
                    )
                    stylesheets_cache[cache_key] = {"data": processed}
            if not fetch_mode:
                uri = get_resource_uri(res)
                return f'/* original URL: {url} */ url("{uri}")'
            else:
                return match.group(0)
        else:
            if fetch_mode:
                if resolved.startswith("http://") or resolved.startswith("https://"):
                    if not any((r["id"] == resolved for r in missing_resources)):
                        missing_resources.append({"id": resolved, "transferEncoding": "base64"})
            elif not resolved.startswith("data:"):
                unfound_resources.add(resolved)
            return match.group(0)
    css_text = CSS_URL_RE.sub(url_repl, css_text)
    return css_text
def resolve_path(path: str, base: str) -> str:
    if not path:
        return path
    if path.startswith("data:"):
        return path
    if not base:
        return path
    try:
        from urllib.parse import urljoin
        return urljoin(base, path)
    except Exception:
        return path
def serialize_node(node, in_raw=False):
    if node.is_text:
        if in_raw:
            text = node.text
            return text
        else:
            return node.text
            return html.escape(node.text, quote=False)
    if node.is_comment:
        return f"<!--{node.text}-->"
    if node.is_doctype:
        return f"<!{node.text}>"
    if node.tag == "document":
        return "".join((serialize_node(child, in_raw=False) for child in node.children))
    tag = node.tag
    attrs_parts = []
    for k, v in node.attrs.items():
        ev = escape_attr(v)
        attrs_parts.append(f'{k}="{ev}"')
    attrs_str = ""
    if attrs_parts:
        attrs_str = " " + " ".join(attrs_parts)
    if tag in VOID_ELEMENTS:
        return f"<{tag}{attrs_str}>"
    is_raw = tag in RAW_TEXT_ELEMENTS
    inner = "".join((serialize_node(child, in_raw=is_raw) for child in node.children))
    if tag in ("script", "style"):
        inner = inner.replace("</", "<\\/").replace("/>", "\\/>")
    return f"<{tag}{attrs_str}>{inner}</{tag}>"
def starts_with_markup(data: bytes) -> bool:
    charset, offset = get_bom_charset(data)
    if charset in ("utf-16le", "utf-16be"):
        try:
            chunk = data[offset : offset + 2048]
            text = chunk.decode(charset, errors="ignore")
            text = text.lstrip()
            return text.startswith("<")
        except Exception:
            return False
    else:
        i = offset
        while i < len(data) and data[i] in (32, 9, 13, 10):
            i += 1
        if i < len(data) and data[i] == 60:
            return True
        return False
def main():
    main_cli()
if __name__ == "__main__":
    main()
