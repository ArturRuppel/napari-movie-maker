# napari Movie Maker Design

Date: 2026-05-08

## Purpose

Build a standalone napari plugin that exports a canvas-only movie from the currently rendered viewer by sweeping one selected napari dimension axis.

The plugin is intentionally smaller and more direct than a keyframe animation editor. Its core job is to capture exactly what the user is seeing in the napari canvas while stepping through a chosen axis.

## Prior Art

The closest existing package is `napari-animation`, which provides keyframe-based animation and movie export. It is useful for camera and viewer-state animations, but it is broader than this use case and does not primarily present a simple axis-sweep workflow.

`napari-animated-gif-io` covers GIF-oriented export and some current-view animation behavior, but it is not a general compact movie exporter for selecting a napari axis and writing formats such as MP4.

napari itself exposes `viewer.screenshot(...)`, which is the right low-level primitive for this plugin because it captures the rendered canvas rather than re-rendering layer data independently.

## Scope

The package will be a standalone napari plugin named `napari-movie-maker`, with Python package directory `napari_movie_maker`.

It will provide one dock widget, `Movie Maker`, available from napari's Plugins menu via an npe2 manifest. The same widget should remain importable for scripts that want to call `viewer.window.add_dock_widget(...)` directly.

Version 1 includes:

- Canvas-only movie export.
- One selected napari dimension axis per export.
- Start, stop, and step controls.
- FPS control.
- Output path selection.
- Progress and status reporting.
- Restoration of the original viewer dimension position after export.

Version 1 excludes:

- Full-window screen recording.
- Arbitrary keyframe animation.
- Camera path editing.
- Layer fade tracks.
- Annotation/timeline editing.
- Batch exports across multiple axes.

## User Workflow

1. The user opens data in napari.
2. The user sets the view exactly as desired, including layers, contrast limits, colormaps, labels, blending, scale bar, overlays, zoom, and 3D camera angle.
3. The user opens `Plugins > Movie Maker`.
4. The user selects one dimension axis.
5. The user chooses start, stop, step, FPS, and output file.
6. The user clicks export.
7. The plugin steps through the selected axis, captures the rendered canvas for each frame, and writes the movie.
8. The plugin restores the viewer to its original dimension position.

## Architecture

The package should have three small parts.

### Plugin Manifest

An npe2 manifest registers the dock widget so napari can discover it. The manifest should expose a single widget contribution named `Movie Maker`.

### Qt Widget

The widget owns the user interface and viewer interaction. It should be compact and utility-focused.

Controls:

- Axis selector populated from `viewer.dims.axis_labels` when available, with numeric axis fallback.
- Start spin box.
- Stop spin box.
- Step spin box.
- FPS spin box, defaulting to approximately 10.
- Output path field.
- Browse button.
- Export button.
- Progress/status label or progress bar.

Behavior:

- Controls update when the selected axis changes.
- Axis range defaults to the full selected axis extent.
- Export is rejected with a clear error if the selected axis has fewer than two exportable frames.
- Export is rejected for invalid step values, empty output paths, or empty frame ranges.
- Controls are disabled while export is running.
- The widget reports final success or failure.
- Export runs synchronously in version 1 to keep the first implementation small. The backend/widget boundary should still make it straightforward to move export work into napari's worker-thread utilities later.

### Export Backend

The backend should be a testable function or small class independent of the widget layout. It should accept a viewer, selected axis, frame indices, FPS, output path, and optional writer/capture hooks for testing.

Export sequence:

1. Store the original `viewer.dims.current_step`.
2. Open a movie writer.
3. For each requested axis index:
   - Set `viewer.dims.current_step` with the selected axis changed.
   - Process Qt events so the canvas renders the new state.
   - Capture the canvas with `viewer.screenshot(canvas_only=True)` or the closest compatible napari API.
   - Append the frame to the writer.
   - Report progress.
4. Close the writer.
5. Restore the original `viewer.dims.current_step` in a `finally` block.

The restore behavior is required after both successful export and failures during capture or writing.

## Dependencies

Keep dependencies modest:

- `napari`
- Qt through napari's existing Qt stack
- `numpy`
- `imageio`
- `imageio-ffmpeg` for MP4 writing

The implementation should avoid depending on `napari-animation` for version 1. That keeps the widget focused and avoids pulling in keyframe concepts that are not part of the core workflow.

## Output Semantics

The movie should represent the visible canvas, not raw image data. Therefore the output includes the visible rendered result of:

- Layer visibility and ordering.
- Contrast limits.
- Colormaps.
- Labels rendering.
- Blending.
- Scale bars and overlays if visible in the canvas capture.
- Current 2D/3D rendering mode.
- Current zoom and camera state.

The first version should treat the output file extension as the format hint. MP4 is the primary target. Other formats supported by the writer can be allowed if they work without extra UI complexity.

## Error Handling

The widget should show concise user-facing errors for:

- No valid dimensions to sweep.
- Selected axis length too small.
- Invalid frame range.
- Invalid FPS.
- Missing output path.
- Writer/backend failure.

Internal exceptions should not leave the viewer on the last exported frame. The original dimension position must be restored even if an error is raised.

## Testing

Tests should focus on the backend and light widget behavior.

Backend tests:

- Frame index generation for start, stop, and step.
- Rejection of zero or negative step values.
- Rejection of empty frame ranges.
- Restoration of the original dimension position after successful export.
- Restoration of the original dimension position after capture failure.
- Restoration of the original dimension position after writer failure.

Widget tests:

- Axis options reflect `viewer.dims`.
- Range controls update for the selected axis.
- Export button validates required inputs.
- Widget can be instantiated with a napari viewer.

Plugin tests:

- The npe2 manifest exposes the `Movie Maker` widget.

Most tests should use fake writer and fake capture hooks so they do not require ffmpeg. A real MP4 smoke test can be optional or marked as an integration test when `imageio-ffmpeg` is available.

## Range Semantics

The stop frame is inclusive in the UI, matching user expectations for frame numbers. For example, start `0`, stop `4`, step `2` exports frames `0`, `2`, and `4`.

## Acceptance Criteria

- The plugin can be installed in editable mode and discovered by napari.
- The `Movie Maker` dock widget appears in the Plugins menu.
- A user can select an axis, choose a range, FPS, and output path, then export a canvas-only MP4.
- The exported frames match the visible napari canvas while sweeping the selected axis.
- The viewer returns to the original dimension position after export.
- Backend tests cover frame generation and restore-on-error behavior.
