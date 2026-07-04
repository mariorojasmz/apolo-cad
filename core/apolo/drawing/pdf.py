"""Exportador PDF de la lámina (matplotlib, tamaño real de papel)."""

from __future__ import annotations

import io

from ..library.materials import hatch_pattern
from .sheet import SheetModel

# patrón de rayado matplotlib por material
PDF_HATCH = {"ansi31": "////", "madera": "xxxx", "vidrio": "||||"}

STYLE = {
    "visible": {"color": "#16181d", "lw": 0.9, "ls": "-"},
    "hidden": {"color": "#7a8290", "lw": 0.55, "ls": (0, (4, 2.5))},
    "frame": {"color": "#16181d", "lw": 1.3, "ls": "-"},
    "dim": {"color": "#3a5e9c", "lw": 0.45, "ls": "-"},
    "center": {"color": "#b0413e", "lw": 0.4, "ls": (0, (6, 1.5, 1, 1.5))},
}
HA = {"start": "left", "middle": "center", "end": "right"}


def _figure(model: SheetModel):
    """Construye (sin guardar) la figura matplotlib de una lámina."""
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["pdf.fonttype"] = 42  # TrueType embebido (Type42), no Type3
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    fig = plt.figure(figsize=(model.width / 25.4, model.height / 25.4))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, model.width)
    ax.set_ylim(0, model.height)
    ax.set_aspect("equal")
    ax.axis("off")

    for im in model.images:  # render raster embebido (iso sombreado a color)
        arr = plt.imread(io.BytesIO(im.png))
        ax.imshow(arr, extent=(im.x, im.x + im.w, im.y, im.y + im.h),
                  origin="upper", aspect="auto", zorder=1, interpolation="bilinear")
    if model.images:  # imshow puede alterar aspecto/límites → restaurar
        ax.set_xlim(0, model.width)
        ax.set_ylim(0, model.height)
        ax.set_aspect("equal")

    if model.polygons:
        from matplotlib.patches import PathPatch
        from matplotlib.path import Path

        for poly in model.polygons:
            verts, codes = [], []
            for ring in poly.rings:
                verts += list(ring) + [ring[0]]
                codes += [Path.MOVETO] + [Path.LINETO] * (len(ring) - 1) + [Path.CLOSEPOLY]
            path = Path(verts, codes)
            if poly.material:
                hatch = PDF_HATCH.get(hatch_pattern(poly.material), "////")
                ax.add_patch(PathPatch(path, facecolor="none", edgecolor="#16181d", lw=0.6, hatch=hatch))
            else:
                ax.add_patch(PathPatch(path, facecolor="#ccd5e3", edgecolor="#16181d", lw=0.7))

    by_kind: dict[str, list] = {}
    for line in model.lines:
        by_kind.setdefault(line.kind, []).append([(line.x1, line.y1), (line.x2, line.y2)])
    for kind, segments in by_kind.items():
        style = STYLE.get(kind, STYLE["visible"])
        ax.add_collection(
            LineCollection(segments, colors=style["color"], linewidths=style["lw"], linestyles=style["ls"])
        )

    if model.circles:
        from matplotlib.patches import Circle as MplCircle

        for c in model.circles:
            ax.add_patch(MplCircle((c.x, c.y), c.r, facecolor="#fdfdfb", edgecolor="#3a5e9c", lw=0.7))

    if model.arcs:  # cosmético de rosca (ISO 6410): arco fino al Ø nominal
        from matplotlib.patches import Arc as MplArc

        for a in model.arcs:
            ax.add_patch(MplArc((a.x, a.y), 2 * a.r, 2 * a.r, theta1=a.a1,
                                theta2=a.a2, lw=0.35, color="#16181d"))

    for lab in model.labels:
        ax.text(
            lab.x,
            lab.y,
            lab.text,
            fontsize=lab.size * 2.45,  # mm → pt aprox
            ha=HA.get(lab.anchor, "center"),
            va="baseline",
            rotation=lab.rotation,
            color="#16181d",
        )
    return fig


def sheet_to_pdf(model: SheetModel) -> bytes:
    import matplotlib.pyplot as plt

    fig = _figure(model)
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf", metadata={"Creator": "Genix Apolo CAD"})
    plt.close(fig)
    return buf.getvalue()


def sheets_to_pdf(models: list) -> bytes:
    """Varias láminas en un PDF MULTIPÁGINA (juego de planos)."""
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    buf = io.BytesIO()
    with PdfPages(buf, metadata={"Creator": "Genix Apolo CAD"}) as pp:
        for model in models:
            fig = _figure(model)
            pp.savefig(fig)
            plt.close(fig)
    return buf.getvalue()
