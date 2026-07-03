"""Fringe von Mises: el campo de esfuerzos pintado sobre la pieza (PNG).

vtkUnstructuredGrid con los tets + σ_vm nodal como escalares → superficie con mapa
de colores azul→rojo + barra de escala en MPa. Reutiliza el patrón off-screen de
``kernel/render_vtk.py`` (VTK ya es dependencia del render PRO). El agente VE dónde
está el esfuerzo, no solo el número.
"""

from __future__ import annotations

import numpy as np


def fringe_png(field, *, title: str = "von Mises [MPa]", size_px: int = 900,
               view: str = "iso") -> bytes:
    # OJO: la fuente por defecto de VTK no tiene 'σ' (sale '_') — títulos en ASCII.
    """PNG del campo von Mises nodal de un FeaField (solver.py)."""
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy

    coords = np.ascontiguousarray(field.coords.T, dtype=np.float64)   # (n, 3)
    tets = np.ascontiguousarray(field.tets.T, dtype=np.int64)         # (m, 4)

    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(coords, deep=True))

    n_tets = tets.shape[0]
    cells = np.hstack([np.full((n_tets, 1), 4, dtype=np.int64), tets]).ravel()
    cell_array = vtk.vtkCellArray()
    cell_array.SetCells(n_tets, numpy_to_vtkIdTypeArray(cells, deep=True))

    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    grid.SetCells(vtk.VTK_TETRA, cell_array)
    scalars = numpy_to_vtk(np.ascontiguousarray(field.vm_nodal, dtype=np.float64),
                           deep=True)
    scalars.SetName("vm")
    grid.GetPointData().SetScalars(scalars)

    surface = vtk.vtkDataSetSurfaceFilter()
    surface.SetInputData(grid)
    surface.Update()

    vm_max = max(float(field.vm_nodal.max()), 1e-9)
    lut = vtk.vtkLookupTable()
    lut.SetHueRange(0.667, 0.0)     # azul (frío) → rojo (caliente)
    lut.SetTableRange(0.0, vm_max)
    lut.Build()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(surface.GetOutputPort())
    mapper.SetLookupTable(lut)
    mapper.SetScalarRange(0.0, vm_max)
    mapper.ScalarVisibilityOn()

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)

    bar = vtk.vtkScalarBarActor()
    bar.SetLookupTable(lut)
    bar.SetTitle("MPa")
    bar.SetNumberOfLabels(6)
    bar.SetUnconstrainedFontSize(True)
    bar.GetLabelTextProperty().SetColor(0.05, 0.05, 0.08)
    bar.GetLabelTextProperty().SetFontSize(16)
    bar.GetTitleTextProperty().SetColor(0.05, 0.05, 0.08)
    bar.GetTitleTextProperty().SetFontSize(18)
    bar.SetMaximumWidthInPixels(int(size_px * 0.09))
    bar.SetPosition(0.88, 0.15)
    bar.SetHeight(0.7)

    txt = vtk.vtkTextActor()
    txt.SetInput(title)
    tp = txt.GetTextProperty()
    tp.SetFontSize(18)
    tp.SetColor(0.05, 0.05, 0.08)
    txt.SetPosition(12, int(size_px * 0.75) - 30)

    ren = vtk.vtkRenderer()
    ren.SetBackground(0.965, 0.97, 0.985)
    ren.SetBackground2(0.86, 0.89, 0.94)
    ren.GradientBackgroundOn()
    ren.AddActor(actor)
    ren.AddActor2D(bar)
    ren.AddActor2D(txt)

    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.AddRenderer(ren)
    rw.SetSize(int(size_px), int(size_px * 0.75))
    rw.SetMultiSamples(8)

    ren.ResetCamera()
    cam = ren.GetActiveCamera()
    if view == "iso":
        cam.Azimuth(-45)
        cam.Elevation(22)
    ren.ResetCamera()
    ren.ResetCameraClippingRange()
    rw.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(rw)
    w2i.ReadFrontBufferOff()
    w2i.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetWriteToMemory(1)
    writer.SetInputConnection(w2i.GetOutputPort())
    writer.Write()
    return vtk_to_numpy(writer.GetResult()).tobytes()
