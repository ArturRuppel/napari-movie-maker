"""Headless movie export — drive an offscreen napari viewer with no GUI.

The interactive widget sweeps a *visible* viewer's dimension axis and captures
the canvas. Batch/pipeline callers have no window, so this module stands up an
**offscreen** viewer, lets the caller populate it (layers, colormaps, camera),
and reuses :func:`napari_movie_maker._backend.export_axis_movie` to do the sweep.

Typical use from a headless pipeline::

    from napari_movie_maker import export_movie_headless

    def configure(viewer):
        viewer.add_image(beads, colormap="gray")
        viewer.add_vectors(quiver, edge_color="cyan")

    export_movie_headless(
        configure=configure,
        axis=0, start=0, stop=39, fps=10,
        output_path="displacement.mp4", canvas_size=(512, 512),
    )

Nothing here imports napari or Qt at module load: the heavy imports happen only
when an offscreen viewer is actually created, so the pure orchestration is
testable (and importable) without a display.

.. important::
   napari renders its canvas with **OpenGL** (vispy). Qt's bare ``offscreen``
   platform — which :func:`ensure_offscreen_qt` selects when there is no display
   — gives you a windowless Qt but *no GL context*, so ``screenshot()`` will
   abort. Real headless capture therefore needs a GL-capable framebuffer:

   - **xvfb** (recommended, standard for napari CI)::

         xvfb-run -a -s "-screen 0 1280x1024x24" python run_batch.py

     ``xvfb`` provides a virtual X display with Mesa software GL, and sets
     ``DISPLAY`` so this module renders through it automatically.
   - A real desktop/X session (``DISPLAY`` already set) also works.
   - Software EGL (``LIBGL_ALWAYS_SOFTWARE=1`` + an EGL-capable build) is a
     no-X alternative but is finickier to provision.

   In short: this module supplies the *windowless* orchestration; the deployment
   still owns a GL surface (xvfb is the cheap, reliable choice). The viewer is
   created with ``show=True`` so its GL canvas is realized — under xvfb that
   render target is simply invisible.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ._backend import MovieExportError, export_axis_movie, frame_indices

#: Layer objects, or a ``configure(viewer)`` callback that populates the viewer.
ViewerConfigurator = Callable[[Any], None]


def ensure_offscreen_qt() -> None:
    """Select Qt's ``offscreen`` platform when there is no display.

    Must run *before* any ``QApplication`` is created (Qt reads the platform
    once, at app construction). No-op when a platform is already pinned via
    ``QT_QPA_PLATFORM`` or when a display is present — so a developer running
    this on their desktop still renders through the real GPU stack.
    """
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if os.name == "posix" and not os.environ.get("DISPLAY") and not os.environ.get(
        "WAYLAND_DISPLAY"
    ):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"


@contextmanager
def offscreen_viewer(
    configure: ViewerConfigurator | None = None,
    layers: Iterable[Any] | None = None,
):
    """Yield a populated napari viewer, torn down for you.

    The viewer is realized (``show=True``) so its GL canvas can be captured, but
    on a virtual display (xvfb) nothing is visible — see the module docstring.
    ``layers`` (napari ``Layer`` objects) are added first, then ``configure`` is
    called with the viewer for anything the simple list can't express — camera,
    zoom, contrast limits, per-layer colormaps. The viewer is always closed on
    exit, even if population or export raises.
    """
    import napari  # heavy; imported only when an offscreen viewer is needed

    ensure_offscreen_qt()
    # show=True *realizes* the GL canvas. A hidden (show=False) viewer never
    # creates a real framebuffer, so screenshots come back black and frozen on
    # the first slice. Under a virtual display (xvfb) the window renders to an
    # invisible surface — nobody sees it, but the capture is correct.
    viewer = napari.Viewer(show=True)
    try:
        for layer in layers or ():
            viewer.add_layer(layer)
        if configure is not None:
            configure(viewer)
        yield viewer
    finally:
        viewer.close()


def _make_capture(viewer: Any, canvas_size: tuple[int, int] | None) -> Callable[[], Any]:
    """Screenshot the canvas at a fixed size — required when no window sets one."""
    def capture() -> Any:
        # size forces an offscreen render at a known resolution; flash=False
        # skips the viewer's capture-flash animation (pointless without a GUI).
        return viewer.screenshot(canvas_only=True, size=canvas_size, flash=False)

    return capture


def export_movie_headless(
    *,
    axis: int,
    output_path: str | Path,
    fps: int = 10,
    frames: Iterable[int] | None = None,
    start: int | None = None,
    stop: int | None = None,
    step: int = 1,
    layers: Iterable[Any] | None = None,
    configure: ViewerConfigurator | None = None,
    canvas_size: tuple[int, int] | None = None,
    viewer: Any | None = None,
    writer_factory: Callable[[str | Path, int], Any] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """Export an axis-sweep movie with no GUI, from layer data alone.

    Supply the frame range as either an explicit ``frames`` iterable or
    ``start``/``stop`` (inclusive) with an optional ``step``.

    Populate the scene with ``layers`` and/or a ``configure`` callback. When
    ``viewer`` is given it is used as-is and left open (the caller owns it);
    otherwise a hidden offscreen viewer is created and closed automatically.

    ``canvas_size`` is ``(height, width)`` in pixels; pass it for headless runs
    so the offscreen render has a defined resolution.
    """
    if frames is None:
        if start is None or stop is None:
            raise MovieExportError(
                "Provide either `frames` or both `start` and `stop`."
            )
        frames = frame_indices(start, stop, step)

    # Pump Qt events so the canvas redraws to the new slice before capture.
    # A single processEvents() can race the slice update, so pump a few times.
    # Lazy-imported so the module stays importable without Qt.
    try:
        from qtpy.QtWidgets import QApplication

        def process_events() -> None:
            for _ in range(3):
                QApplication.processEvents()
    except Exception:  # pragma: no cover - Qt always present with napari
        process_events = None  # type: ignore[assignment]

    def run(active_viewer: Any) -> None:
        export_axis_movie(
            active_viewer,
            axis=axis,
            frames=frames,
            fps=fps,
            output_path=output_path,
            writer_factory=writer_factory,
            capture_frame=_make_capture(active_viewer, canvas_size),
            progress_callback=progress_callback,
            process_events=process_events,
        )

    if viewer is not None:
        run(viewer)
    else:
        with offscreen_viewer(configure=configure, layers=layers) as created:
            run(created)
