from __future__ import annotations

from pathlib import Path
from typing import Any

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ._backend import MovieExportError, export_axis_movie, frame_indices


class MovieMakerWidget(QWidget):
    """Dock widget for exporting a napari axis sweep movie."""

    def __init__(self, napari_viewer: Any) -> None:
        super().__init__()
        self.viewer = napari_viewer
        self.setWindowTitle("Movie Maker")

        self.axis_combo = QComboBox()
        self.start_spin = QSpinBox()
        self.stop_spin = QSpinBox()
        self.step_spin = QSpinBox()
        self.fps_spin = QSpinBox()
        self.output_path = QLineEdit()
        self.browse_button = QPushButton("Browse")
        self.export_button = QPushButton("Export")
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("")

        self._build_ui()
        self._connect_signals()
        self.refresh_axes()

    def _build_ui(self) -> None:
        self.start_spin.setMinimum(0)
        self.stop_spin.setMinimum(0)
        self.step_spin.setRange(1, 1_000_000)
        self.step_spin.setValue(1)
        self.fps_spin.setRange(1, 240)
        self.fps_spin.setValue(10)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignLeft)

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.output_path)
        path_layout.addWidget(self.browse_button)

        form = QFormLayout()
        form.addRow("Axis", self.axis_combo)
        form.addRow("Start", self.start_spin)
        form.addRow("Stop", self.stop_spin)
        form.addRow("Step", self.step_spin)
        form.addRow("FPS", self.fps_spin)
        form.addRow("Output", path_layout)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.export_button)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def _connect_signals(self) -> None:
        self.axis_combo.currentIndexChanged.connect(self._sync_axis_range)
        self.browse_button.clicked.connect(self._browse_output)
        self.export_button.clicked.connect(self.export_movie)

    def refresh_axes(self) -> None:
        self.axis_combo.clear()
        labels = tuple(getattr(self.viewer.dims, "axis_labels", ()))
        nsteps = tuple(getattr(self.viewer.dims, "nsteps", ()))

        for axis, _axis_length in enumerate(nsteps):
            label = labels[axis] if axis < len(labels) and labels[axis] else f"Axis {axis}"
            self.axis_combo.addItem(str(label), axis)

        self._sync_axis_range()

    def _sync_axis_range(self) -> None:
        axis = self.selected_axis()
        nsteps = tuple(getattr(self.viewer.dims, "nsteps", ()))
        max_index = max(nsteps[axis] - 1, 0) if axis is not None and axis < len(nsteps) else 0

        for spin in (self.start_spin, self.stop_spin):
            spin.setRange(0, max_index)
        self.start_spin.setValue(0)
        self.stop_spin.setValue(max_index)

    def selected_axis(self) -> int | None:
        if self.axis_combo.count() == 0:
            return None
        axis = self.axis_combo.currentData()
        return int(axis) if axis is not None else self.axis_combo.currentIndex()

    def validate_inputs(self) -> list[int] | None:
        axis = self.selected_axis()
        if axis is None:
            self.status_label.setText("No valid dimensions to sweep.")
            return None

        nsteps = tuple(getattr(self.viewer.dims, "nsteps", ()))
        if axis >= len(nsteps) or nsteps[axis] < 2:
            self.status_label.setText("Selected axis has fewer than two exportable frames.")
            return None

        output = self.output_path.text().strip()
        if not output:
            self.status_label.setText("Choose an output path before exporting.")
            return None

        try:
            frames = frame_indices(
                self.start_spin.value(),
                self.stop_spin.value(),
                self.step_spin.value(),
            )
        except MovieExportError as exc:
            self.status_label.setText(str(exc))
            return None

        if len(frames) < 2:
            self.status_label.setText("Selected range has fewer than two exportable frames.")
            return None
        return frames

    def _browse_output(self) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save movie",
            str(Path.home() / "movie.mp4"),
            "Movies (*.mp4 *.mov *.gif);;All files (*)",
        )
        if path:
            self.output_path.setText(path)

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.axis_combo,
            self.start_spin,
            self.stop_spin,
            self.step_spin,
            self.fps_spin,
            self.output_path,
            self.browse_button,
            self.export_button,
        ):
            widget.setEnabled(enabled)

    def export_movie(self) -> None:
        frames = self.validate_inputs()
        if frames is None:
            return

        self._set_controls_enabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Exporting movie...")

        def on_progress(done: int, total: int) -> None:
            self.progress_bar.setValue(round(done / total * 100))

        try:
            export_axis_movie(
                self.viewer,
                axis=self.selected_axis() or 0,
                frames=frames,
                fps=self.fps_spin.value(),
                output_path=self.output_path.text().strip(),
                progress_callback=on_progress,
                process_events=QApplication.processEvents,
            )
        except Exception as exc:
            self.status_label.setText(f"Export failed: {exc}")
        else:
            self.status_label.setText("Export complete.")
        finally:
            self._set_controls_enabled(True)
