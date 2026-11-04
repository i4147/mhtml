"""Loguru-backed conversion logging and progress callback dispatch."""

from __future__ import annotations

from collections.abc import Callable

from loguru import logger

from .config import ConverterConfig


class ConverterLogger:
    """Scoped logging facade that does not reset the application's Loguru sinks."""

    def __init__(self, config: ConverterConfig | None = None) -> None:
        """Bind a component logger and optionally add a rotating file sink."""
        self.config = config or ConverterConfig()
        self.progress_callback: Callable[[str, float], None] | None = (
            self.config.progress_callback
        )
        self._logger = logger.bind(component="mhtml.converter")
        self._minimum_level = logger.level(self.config.log_level.upper()).no
        self._file_sink: int | None = None
        if self.config.log_file is not None:
            self.config.log_file.parent.mkdir(parents=True, exist_ok=True)
            self._file_sink = logger.add(
                self.config.log_file,
                level=self.config.log_level.upper(),
                rotation="10 MB",
                retention=3,
                enqueue=True,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            )

    def set_progress_callback(
        self,
        callback: Callable[[str, float], None] | None,
    ) -> None:
        """Set or clear the callback invoked at progress milestones."""
        self.progress_callback = callback

    def log_progress(self, message: str, progress: float) -> None:
        """Log progress and invoke the optional callback with a clamped value."""
        clamped_progress = min(1.0, max(0.0, progress))
        self.info("Progress: {:.1f}% - {}", clamped_progress * 100, message)
        if self.progress_callback is not None:
            try:
                self.progress_callback(message, clamped_progress)
            # User callback exceptions must not abort the conversion pipeline.
            except Exception:  # pylint: disable=broad-exception-caught
                self._logger.exception("Progress callback failed")

    def trace(self, message: str, *args: object) -> None:
        """Log a trace-level message when enabled by the configured threshold."""
        self._log("TRACE", message, *args)

    def debug(self, message: str, *args: object) -> None:
        """Log a debug message when enabled by the configured threshold."""
        self._log("DEBUG", message, *args)

    def info(self, message: str, *args: object) -> None:
        """Log an informational message."""
        self._log("INFO", message, *args)

    def warning(self, message: str, *args: object) -> None:
        """Log a warning message."""
        self._log("WARNING", message, *args)

    def error(self, message: str, *args: object) -> None:
        """Log an error message."""
        self._log("ERROR", message, *args)

    def exception(self, message: str, *args: object) -> None:
        """Log an error with the active exception traceback."""
        if self._minimum_level <= logger.level("ERROR").no:
            self._logger.exception(message, *args)

    def close(self) -> None:
        """Remove this instance's optional Loguru file sink."""
        if self._file_sink is not None:
            logger.remove(self._file_sink)
            self._file_sink = None

    def _log(self, level: str, message: str, *args: object) -> None:
        if logger.level(level).no >= self._minimum_level:
            self._logger.log(level, message, *args)


__all__ = ["ConverterLogger"]
