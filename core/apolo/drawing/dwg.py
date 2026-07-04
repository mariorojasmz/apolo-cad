"""Export DWG (V5.9): el DXF que ya producimos, convertido con ODA File Converter.

No existe writer DWG en pip; la vía del ecosistema no-Autodesk (FreeCAD incluido) es
el ODA File Converter (gratuito, instalación manual desde opendesign.com) invocado
por ``ezdxf.addons.odafc``. Patrón de dependencia externa opcional (como MuJoCo/FEA):
sin el conversor, error AMABLE con la instrucción de instalación.

GOTCHA de entorno: el instalador de ODA usa carpeta VERSIONADA
(``C:\\Program Files\\ODA\\ODAFileConverter 26.x.x\\``) y el default de ezdxf apunta a
la carpeta SIN versión → ``_discover()`` la busca con glob y fija la opción.
"""

from __future__ import annotations

import glob
import os
import tempfile
import threading
from pathlib import Path

_LOCK = threading.Lock()  # el conversor es un proceso externo: una conversión a la vez
_DISCOVERED: bool | None = None  # caché del descubrimiento (por proceso)

# raíces donde buscar el exe (parametrizable en tests)
SEARCH_ROOTS = (
    r"C:\Program Files\ODA",
    r"C:\Program Files (x86)\ODA",
)


class DwgError(Exception):
    pass


def _discover(roots=SEARCH_ROOTS) -> bool:
    """True si el ODA File Converter está disponible; si ezdxf no lo ve en su ruta
    default, busca la carpeta VERSIONADA y fija `ezdxf.options`. Cacheado."""
    global _DISCOVERED
    if _DISCOVERED is not None and roots is SEARCH_ROOTS:
        return _DISCOVERED
    import ezdxf
    from ezdxf.addons import odafc

    found = odafc.is_installed()
    if not found:
        for root in roots:
            hits = sorted(glob.glob(os.path.join(root, "*", "ODAFileConverter.exe")))
            if hits:
                ezdxf.options.set("odafc-addon", "win_exec_path", hits[-1])  # la más nueva
                found = odafc.is_installed()
                break
    if roots is SEARCH_ROOTS:
        _DISCOVERED = found
    return found


def require_odafc() -> None:
    if not _discover():
        raise DwgError(
            "El export DWG requiere ODA File Converter (gratuito): descárgalo de "
            "opendesign.com/guestfiles/oda_file_converter, instálalo y reinicia la API"
        )


def dxf_to_dwg_bytes(dxf_bytes: bytes, version: str = "R2018") -> bytes:
    """Convierte un DXF (bytes) a DWG (bytes) vía ODA File Converter. R2018 =
    AC1032, compatible con AutoCAD 2018+."""
    from ezdxf.addons import odafc

    require_odafc()
    with _LOCK, tempfile.TemporaryDirectory(prefix="apolo_dwg_") as tmp:
        src = Path(tmp) / "plano.dxf"
        dst = Path(tmp) / "plano.dwg"
        src.write_bytes(dxf_bytes)
        try:
            odafc.convert(str(src), str(dst), version=version)
        except odafc.ODAFCError as exc:
            raise DwgError(f"ODA File Converter falló: {exc}") from exc
        if not dst.exists():
            raise DwgError("ODA File Converter no produjo el DWG (revisa el DXF de origen)")
        return dst.read_bytes()


def sheet_to_dwg(model, version: str = "R2018") -> bytes:
    """DWG de una lámina (SheetModel) — el DXF existente, convertido."""
    from .dxf import sheet_to_dxf

    return dxf_to_dwg_bytes(sheet_to_dxf(model), version)
