from __future__ import annotations

from pathlib import Path


def test_manifest_exposes_movie_maker_widget():
    manifest = Path("src/napari_movie_maker/napari.yaml").read_text()

    assert "display_name: Movie Maker" in manifest
    assert "id: napari-movie-maker" in manifest
    assert "contributions:" in manifest
    assert "command: napari-movie-maker.make_qwidget" in manifest
    assert "display_name: Movie Maker" in manifest
