from __future__ import annotations

import numpy as np
import pytest

from napari_movie_maker import (
    MovieExportError,
    ensure_offscreen_qt,
    export_movie_headless,
)


class FakeDims:
    def __init__(self, current_step: tuple[int, ...]) -> None:
        self.current_step = current_step


class FakeViewer:
    """Minimal stand-in: records sweep steps and the screenshot kwargs used."""

    def __init__(self, current_step: tuple[int, ...] = (0, 0)) -> None:
        self.dims = FakeDims(current_step)
        self.captured_steps: list[tuple[int, ...]] = []
        self.screenshot_kwargs: list[dict] = []
        self.closed = False

    def screenshot(self, canvas_only: bool = True, size=None, flash=True):
        self.screenshot_kwargs.append(
            {"canvas_only": canvas_only, "size": size, "flash": flash}
        )
        self.captured_steps.append(self.dims.current_step)
        return np.zeros((4, 4, 4), dtype=np.uint8)

    def close(self) -> None:
        self.closed = True


class FakeWriter:
    def __init__(self) -> None:
        self.frames: list[object] = []
        self.closed = False

    def append_data(self, frame) -> None:
        self.frames.append(frame)

    def close(self) -> None:
        self.closed = True


# --- ensure_offscreen_qt ----------------------------------------------------


def test_ensure_offscreen_sets_platform_without_display(monkeypatch):
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    ensure_offscreen_qt()

    import os

    assert os.environ["QT_QPA_PLATFORM"] == "offscreen"


def test_ensure_offscreen_respects_existing_platform(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    monkeypatch.delenv("DISPLAY", raising=False)

    ensure_offscreen_qt()

    import os

    assert os.environ["QT_QPA_PLATFORM"] == "xcb"


def test_ensure_offscreen_noop_when_display_present(monkeypatch):
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")

    ensure_offscreen_qt()

    import os

    assert "QT_QPA_PLATFORM" not in os.environ


# --- export_movie_headless (injected viewer, no GUI) ------------------------


def test_headless_export_with_injected_viewer_sweeps_and_keeps_viewer_open():
    viewer = FakeViewer(current_step=(7, 0))
    writer = FakeWriter()
    progress: list[tuple[int, int]] = []

    export_movie_headless(
        viewer=viewer,
        axis=1,
        start=0,
        stop=4,
        step=2,
        fps=12,
        output_path="movie.mp4",
        canvas_size=(64, 48),
        writer_factory=lambda path, fps: writer,
        progress_callback=lambda done, total: progress.append((done, total)),
    )

    # start/stop/step -> [0, 2, 4]; axis 1 swept, axis 0 untouched.
    assert viewer.captured_steps == [(7, 0), (7, 2), (7, 4)]
    # Original step restored by the underlying export.
    assert viewer.dims.current_step == (7, 0)
    assert writer.closed is True
    assert progress == [(1, 3), (2, 3), (3, 3)]
    # Injected viewer is the caller's to keep — not closed.
    assert viewer.closed is False


def test_headless_export_forces_canvas_size_and_disables_flash():
    viewer = FakeViewer()
    writer = FakeWriter()

    export_movie_headless(
        viewer=viewer,
        axis=0,
        frames=[0, 1],
        fps=10,
        output_path="movie.gif",
        canvas_size=(128, 256),
        writer_factory=lambda path, fps: writer,
    )

    assert viewer.screenshot_kwargs == [
        {"canvas_only": True, "size": (128, 256), "flash": False},
        {"canvas_only": True, "size": (128, 256), "flash": False},
    ]


def test_headless_export_requires_frames_or_range():
    viewer = FakeViewer()

    with pytest.raises(MovieExportError, match="Provide either"):
        export_movie_headless(
            viewer=viewer,
            axis=0,
            fps=10,
            output_path="movie.mp4",
            writer_factory=lambda path, fps: FakeWriter(),
        )


# --- real offscreen viewer (integration) ------------------------------------


def test_headless_export_with_real_offscreen_viewer(tmp_path):
    napari = pytest.importorskip("napari")
    # napari renders via OpenGL; Qt's bare "offscreen" platform has no GL
    # context, so real capture needs a framebuffer — a desktop session or an
    # xvfb virtual display (both set DISPLAY). Skip when neither is present
    # rather than hard-crash the interpreter on a GL abort.
    import os

    if os.name == "posix" and not os.environ.get("DISPLAY"):
        pytest.skip("headless GL render needs a display (e.g. run under xvfb-run)")

    # Each slice a distinct flat gray so we can prove the sweep advances frames.
    stack = np.zeros((5, 32, 32), dtype=np.uint8)
    for i in range(5):
        stack[i] = (i + 1) * 40
    out = tmp_path / "sweep.gif"

    def configure(viewer):
        viewer.add_image(stack, name="frames", colormap="gray", contrast_limits=[0, 255])
        viewer.reset_view()

    export_movie_headless(
        configure=configure,
        axis=0,
        start=0,
        stop=4,
        fps=5,
        output_path=out,
        canvas_size=(64, 64),
    )

    assert out.exists() and out.stat().st_size > 0
    import imageio.v2 as imageio

    read_back = imageio.mimread(out)
    assert len(read_back) == 5
    # The sweep must render *different* slices, not the same frame five times.
    means = [int(np.asarray(frame)[..., :3].mean()) for frame in read_back]
    assert len(set(means)) == 5, f"frames not distinct: {means}"
