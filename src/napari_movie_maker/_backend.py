from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol

import imageio.v2 as imageio


class MovieExportError(ValueError):
    """Raised when movie export inputs are invalid."""


class MovieWriter(Protocol):
    def append_data(self, frame: Any) -> None: ...

    def close(self) -> None: ...


def frame_indices(start: int, stop: int, step: int) -> list[int]:
    """Return inclusive frame indices for a UI range."""
    if step <= 0:
        raise MovieExportError("Step must be greater than zero.")

    frames = list(range(start, stop + 1, step))
    if not frames:
        raise MovieExportError("Frame range is empty.")
    return frames


def _default_writer_factory(output_path: str | Path, fps: int) -> MovieWriter:
    return imageio.get_writer(output_path, fps=fps)


def _set_axis_step(viewer: Any, axis: int, value: int) -> None:
    current_step = list(viewer.dims.current_step)
    current_step[axis] = value
    viewer.dims.current_step = tuple(current_step)


def export_axis_movie(
    viewer: Any,
    *,
    axis: int,
    frames: Iterable[int],
    fps: int,
    output_path: str | Path,
    writer_factory: Callable[[str | Path, int], MovieWriter] | None = None,
    capture_frame: Callable[[], Any] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    process_events: Callable[[], None] | None = None,
) -> None:
    """Export a canvas-only movie by sweeping one napari dimension axis."""
    frame_list = list(frames)
    if not frame_list:
        raise MovieExportError("Frame range is empty.")
    if fps <= 0:
        raise MovieExportError("FPS must be greater than zero.")
    if not str(output_path):
        raise MovieExportError("Output path is required.")

    original_step = tuple(viewer.dims.current_step)
    writer = None
    make_writer = writer_factory or _default_writer_factory
    capture = capture_frame or (lambda: viewer.screenshot(canvas_only=True))
    pump_events = process_events or (lambda: None)

    try:
        writer = make_writer(output_path, fps)
        total = len(frame_list)
        for done, frame_index in enumerate(frame_list, start=1):
            _set_axis_step(viewer, axis, frame_index)
            pump_events()
            writer.append_data(capture())
            if progress_callback is not None:
                progress_callback(done, total)
    finally:
        viewer.dims.current_step = original_step
        if writer is not None:
            writer.close()
