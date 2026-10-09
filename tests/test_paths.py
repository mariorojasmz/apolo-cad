"""Qué bundle de UI sirve la API: en un checkout gana `ui/dist`, instalado la empaquetada."""

from __future__ import annotations

from apolo import paths


def _bundle(dir_):
    dir_.mkdir(parents=True)
    (dir_ / "index.html").write_text("<html></html>", encoding="utf-8")
    return dir_


def test_checkout_prefiere_ui_dist_sobre_la_empaquetada(tmp_path, monkeypatch):
    # tras un stage_ui.py de release, el checkout tiene AMBAS: debe servir lo recién compilado
    pkg = tmp_path / "core" / "apolo"
    _bundle(pkg / "webui")
    built = _bundle(tmp_path / "ui" / "dist")
    monkeypatch.setattr(paths, "_PKG", pkg)
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    assert paths.ui_dist() == built


def test_checkout_sin_build_cae_a_la_empaquetada(tmp_path, monkeypatch):
    pkg = tmp_path / "core" / "apolo"
    packaged = _bundle(pkg / "webui")
    monkeypatch.setattr(paths, "_PKG", pkg)
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    assert paths.ui_dist() == packaged


def test_instalado_sirve_la_empaquetada(tmp_path, monkeypatch):
    pkg = tmp_path / "site-packages" / "apolo"
    packaged = _bundle(pkg / "webui")
    monkeypatch.setattr(paths, "_PKG", pkg)
    monkeypatch.setattr(paths, "repo_root", lambda: None)
    assert paths.ui_dist() == packaged


def test_sin_ningun_bundle_queda_headless(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "_PKG", tmp_path / "core" / "apolo")
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    assert paths.ui_dist() is None


def test_publicaciones_en_un_checkout_van_a_data(tmp_path, monkeypatch):
    """D14 del plan publicacion-tienda: en un checkout, junto a la SQLite (`/data/` está
    fuera de git: un video pesa decenas de MB). No se crea al consultarla."""
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    assert paths.publicaciones_dir() == tmp_path / "data" / "publicaciones"
    assert not paths.publicaciones_dir().exists()


def test_publicaciones_instalado_van_a_apolo_home(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "repo_root", lambda: None)
    monkeypatch.setattr(paths, "home", lambda: tmp_path / ".apolo")
    assert paths.publicaciones_dir() == tmp_path / ".apolo" / "publicaciones"
