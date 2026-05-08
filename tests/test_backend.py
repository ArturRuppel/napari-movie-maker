from __future__ import annotations

import pytest

from napari_movie_maker._backend import (
    MovieExportError,
    export_axis_movie,
    frame_indices,
)


class FakeDims:
    def __init__(self, current_step: tuple[int, ...]) -> None:
        self.current_step = current_step


class FakeViewer:
    def __init__(self, current_step: tuple[int, ...] = (3, 4)) -> None:
        self.dims = FakeDims(current_step)
        self.captured_steps: list[tuple[int, ...]] = []

    def screenshot(self, canvas_only: bool = True):
        assert canvas_only is True
        self.captured_steps.append(self.dims.current_step)
        return f"frame-{self.dims.current_step}"


class FakeWriter:
    def __init__(self, fail_on_append: bool = False) -> None:
        self.fail_on_append = fail_on_append
        self.frames: list[object] = []
        self.closed = False

    def append_data(self, frame) -> None:
        if self.fail_on_append:
            raise RuntimeError("writer failed")
        self.frames.append(frame)

    def close(self) -> None:
        self.closed = True


def test_frame_indices_uses_inclusive_stop():
    assert frame_indices(start=0, stop=4, step=2) == [0, 2, 4]


def test_frame_indices_rejects_non_positive_step():
    with pytest.raises(MovieExportError, match="Step must be greater than zero"):
        frame_indices(start=0, stop=4, step=0)


def test_frame_indices_rejects_empty_range():
    with pytest.raises(MovieExportError, match="Frame range is empty"):
        frame_indices(start=4, stop=0, step=1)


def test_export_restores_original_step_after_success():
    viewer = FakeViewer(current_step=(3, 4))
    writer = FakeWriter()
    progress: list[tuple[int, int]] = []

    export_axis_movie(
        viewer,
        axis=1,
        frames=[1, 3],
        fps=10,
        output_path="movie.mp4",
        writer_factory=lambda path, fps: writer,
        progress_callback=lambda done, total: progress.append((done, total)),
        process_events=lambda: None,
    )

    assert viewer.dims.current_step == (3, 4)
    assert viewer.captured_steps == [(3, 1), (3, 3)]
    assert writer.frames == ["frame-(3, 1)", "frame-(3, 3)"]
    assert writer.closed is True
    assert progress == [(1, 2), (2, 2)]


def test_export_restores_original_step_after_capture_failure():
    viewer = FakeViewer(current_step=(3, 4))
    writer = FakeWriter()

    def capture_failure():
        raise RuntimeError("capture failed")

    with pytest.raises(RuntimeError, match="capture failed"):
        export_axis_movie(
            viewer,
            axis=1,
            frames=[1, 3],
            fps=10,
            output_path="movie.mp4",
            writer_factory=lambda path, fps: writer,
            capture_frame=capture_failure,
            process_events=lambda: None,
        )

    assert viewer.dims.current_step == (3, 4)
    assert writer.closed is True


def test_export_restores_original_step_after_writer_failure():
    viewer = FakeViewer(current_step=(3, 4))
    writer = FakeWriter(fail_on_append=True)

    with pytest.raises(RuntimeError, match="writer failed"):
        export_axis_movie(
            viewer,
            axis=1,
            frames=[1, 3],
            fps=10,
            output_path="movie.mp4",
            writer_factory=lambda path, fps: writer,
            process_events=lambda: None,
        )

    assert viewer.dims.current_step == (3, 4)
    assert writer.closed is True
