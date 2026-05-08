# napari Movie Maker

`napari-movie-maker` is a compact napari plugin for exporting canvas-only movies by sweeping one selected dimension axis.

The plugin captures the rendered napari canvas with `viewer.screenshot(canvas_only=True)`, so exported frames reflect the visible viewer state rather than raw layer data.
