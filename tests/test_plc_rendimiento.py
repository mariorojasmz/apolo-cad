"""Gate de F1 (plan V8.3): ≤ 50 µs por scan con un programa sintético de ~500 líneas.

El programa imita al de la medición de V8.0/F0 (≈ 500 líneas, 60–80 bloques estándar, 25 E/S):
20 instancias de un FUNCTION_BLOCK de motor con TON, TOF, R_TRIG y CTU cada una, una FUNCTION
de escalado, lógica de IF/CASE y un FOR sobre un ARRAY. La cota estricta (50 µs) va marcada
`torture` (depende de la máquina); la suite normal exige una cota holgada para que no sea
frágil en CI. Las dos miden CPU del proceso, no pared (ver `medir_us_por_scan`).
"""

from __future__ import annotations

import time

import pytest

from apolo.plc import PLC, compilar

N_MOTORES = 20


def programa_sintetico() -> str:
    g = ["VAR_GLOBAL"]
    g += [f"  di{i} AT %IX{i // 8}.{i % 8} : BOOL;" for i in range(14)]
    g += [f"  do{i} AT %QX{i // 8}.{i % 8} : BOOL;" for i in range(10)]
    g += ["  nivel AT %IW0 : INT;", "  total : DINT;", "  modo : INT := 1;", "END_VAR"]
    fb = """
FUNCTION_BLOCK Motor
VAR_INPUT
  marcha : BOOL;
  paro : BOOL;
  falla : BOOL;
  sensor : BOOL;
END_VAR
VAR_OUTPUT
  salida : BOOL;
  alarma : BOOL;
  cuenta : INT;
END_VAR
VAR
  arranque : TON;
  parada : TOF;
  flanco : R_TRIG;
  piezas : CTU;
  enclavado : BOOL;
END_VAR
enclavado := (marcha OR enclavado) AND NOT paro AND NOT falla;
arranque(IN := enclavado, PT := T#200ms);
parada(IN := arranque.Q, PT := T#500ms);
salida := parada.Q;
flanco(CLK := sensor AND salida);
piezas(CU := flanco.Q, R := paro, PV := 1000);
cuenta := piezas.CV;
IF falla THEN
  alarma := TRUE;
ELSIF paro THEN
  alarma := FALSE;
END_IF;
END_FUNCTION_BLOCK
""".strip().splitlines()
    fn = """
FUNCTION Escalar : REAL
VAR_INPUT
  cuentas : INT;
  minimo : REAL;
  maximo : REAL;
END_VAR
Escalar := minimo + (maximo - minimo) * INT_TO_REAL(cuentas) / 27648.0;
END_FUNCTION
""".strip().splitlines()
    p = ["PROGRAM Main", "VAR"]
    p += [f"  m{i} : Motor;" for i in range(N_MOTORES)]
    p += ["  i : INT;", "  acum : DINT;", "  nivel_pct : REAL;", "  hist : ARRAY[1..10] OF INT;",
          "  estado : INT;", "  aux : BOOL;", "  k : DINT;", "END_VAR"]
    for i in range(N_MOTORES):
        a, b, c, d = (i % 14), ((i + 3) % 14), ((i + 5) % 14), ((i + 7) % 14)
        p += [f"m{i}(marcha := di{a},", f"   paro := di{b},", f"   falla := di{c} AND di{d},",
              f"   sensor := di{(i + 9) % 14});"]
        p += [f"IF m{i}.salida THEN", f"  acum := acum + m{i}.cuenta;", "ELSE",
              "  acum := acum - 1;", "END_IF;"]
    p += ["nivel_pct := Escalar(nivel, 0.0, 100.0);"]
    for j in range(18):
        p += ["CASE estado OF", f"  0: IF nivel_pct > {j * 8}.0 THEN estado := 1; END_IF;",
              f"  1: k := k + {j};", f"     IF k > {1000 + j} THEN estado := 2; END_IF;",
              "  2: k := 0;", "     estado := 0;", "ELSE", "  estado := 0;", "END_CASE;",
              f"aux := (k MOD {j + 2} = 0) XOR di{j % 14};",
              f"IF aux AND modo = 1 THEN total := total + {j}; END_IF;"]
    p += ["FOR i := 1 TO 10 DO", "  hist[i] := hist[i] + i;",
          "  IF hist[i] > 1000 THEN hist[i] := 0; END_IF;", "END_FOR;"]
    for i in range(10):
        p += [f"do{i} := m{i}.salida OR (m{(i + 5) % N_MOTORES}.alarma AND NOT di{i});"]
    p += ["END_PROGRAM"]
    return "\n".join(g + fb + fn + p) + "\n"


def medir_us_por_scan(lotes: int = 5, scans: int = 400) -> tuple[float, int]:
    """µs de CPU por scan (media de `lotes × scans`). CPU del proceso y no reloj de pared: con la
    suite en paralelo (`-n auto`) los otros workers inflan la pared, no el costo del scan. En
    Windows `process_time` avanza de a 15,6 ms: por eso el total, no el mejor lote (~10 ms)."""
    fuente = programa_sintetico()
    plc = PLC(compilar(fuente), ciclo_ms=10)
    t = 0
    c0 = time.process_time()
    for n in range(lotes * scans):
        plc.escribir_entrada(f"I{(n % 14) // 8}.{(n % 14) % 8}", n % 3 == 0)
        plc.scan(t)
        t += 10
    us = (time.process_time() - c0) / (lotes * scans) * 1e6
    assert plc.estado == "RUN", plc.falla
    return us, len(fuente.splitlines())


def test_el_programa_sintetico_es_del_tamano_del_gate():
    fuente = programa_sintetico()
    assert 450 <= len(fuente.splitlines()) <= 600
    c = compilar(fuente)
    por_motor = sum(1 for x in c.disposiciones["motor"] if x.fb in ("ton", "tof", "r_trig", "ctu"))
    motores = sum(1 for x in c.disposiciones["main"] if x.fb == "motor")
    assert (por_motor, motores) == (4, N_MOTORES)          # 80 bloques estándar
    assert len(c.entradas) + len(c.salidas) == 25


def test_scan_rapido_con_tolerancia_para_ci():
    # Sólo atrapa un desastre (p. ej. volver a interpretar el árbol): con la PC cargada por otras
    # suites midió 686 µs (V8.3 F5) y 200 daba rojos falsos. El gate real de 50 µs es de tortura.
    us, _ = medir_us_por_scan()
    assert us <= 2000, f"{us:.1f} µs por scan"


@pytest.mark.torture
def test_scan_dentro_del_gate_de_50_us():
    us, lineas = medir_us_por_scan(lotes=10)
    print(f"\n{lineas} líneas: {us:.1f} µs por scan")
    assert us <= 50, f"{us:.1f} µs por scan con {lineas} líneas"
