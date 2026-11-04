"""Public API for the MHTML-to-HTML converter package."""

from .config import ConversionProfile, ConverterConfig
from .converter import MHTMLConverter
from .css_processor import CSSProcessor
from .html_processor import HTMLNode, HTMLProcessor, HTMLTreeParser
from .logger import ConverterLogger
from .parser import (
    MHTMLParser,
    Resource,
    ResourceType,
    classify_resource_type,
    resolve_resource_url,
    resource_to_data_uri,
)
from .plugins import ConverterPlugin
from .resource_manager import ResourceCache, ResourceManager

__all__ = [
    "CSSProcessor",
    "ConversionProfile",
    "ConverterConfig",
    "ConverterLogger",
    "ConverterPlugin",
    "HTMLNode",
    "HTMLProcessor",
    "HTMLTreeParser",
    "MHTMLConverter",
    "MHTMLParser",
    "Resource",
    "ResourceCache",
    "ResourceManager",
    "ResourceType",
    "classify_resource_type",
    "resolve_resource_url",
    "resource_to_data_uri",
]
