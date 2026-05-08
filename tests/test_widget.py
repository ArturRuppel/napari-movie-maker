from __future__ import annotations

import inspect

import pytest

pytest.importorskip("qtpy")

from qtpy.QtWidgets import QApplication

from napari_movie_maker import MovieMakerWidget


class FakeDims:
    axis_labels = ("time", "z")
    nsteps = (5, 3)
    current_step = (0, 0)


class FakeViewer:
    dims = FakeDims()


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_widget_axis_options_reflect_viewer_dims(qapp):
    widget = MovieMakerWidget(FakeViewer())

    assert [widget.axis_combo.itemText(i) for i in range(widget.axis_combo.count())] == [
        "time",
        "z",
    ]


def test_widget_range_controls_update_for_selected_axis(qapp):
    widget = MovieMakerWidget(FakeViewer())

    widget.axis_combo.setCurrentIndex(1)

    assert widget.start_spin.maximum() == 2
    assert widget.stop_spin.maximum() == 2
    assert widget.start_spin.value() == 0
    assert widget.stop_spin.value() == 2


def test_widget_validates_required_output_path(qapp):
    widget = MovieMakerWidget(FakeViewer())

    assert widget.validate_inputs() is None
    assert "output path" in widget.status_label.text().lower()


def test_widget_constructor_uses_napari_viewer_injection_name():
    signature = inspect.signature(MovieMakerWidget.__init__)

    assert "napari_viewer" in signature.parameters
