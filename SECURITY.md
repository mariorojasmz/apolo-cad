**Español** · [English](#security-policy)

# Política de seguridad

## Cómo reportar una vulnerabilidad

**No abras un issue público.** Repórtala en privado desde la pestaña **Security** del repositorio,
con el botón **Report a vulnerability**
(<https://github.com/mariorojasmz/apolo-cad/security/advisories/new>). Sólo la ve el mantenedor.

Incluye, si puedes:

- qué componente afecta (API, MCP, sandbox de scripts, carga de un `.apolo`, UI…);
- la versión de `apolo-cad` (`pip show apolo-cad`) o el commit;
- los pasos para reproducirla y qué consigue quien la explota.

Apolo lo mantiene una sola persona: la respuesta llega lo antes posible, y el arreglo sale en la
siguiente versión de PyPI. Si quieres que te nombremos en el aviso, dilo en el reporte.

## Versiones que se atienden

Sólo la **última versión publicada en PyPI** de `apolo-cad` (y `main`). Si usas una anterior,
actualiza antes de reportar: puede que ya esté arreglado.

---

[Español](#política-de-seguridad) · **English**

# Security policy

## How to report a vulnerability

**Do not open a public issue.** Report it privately from the repository's **Security** tab, with
the **Report a vulnerability** button
(<https://github.com/mariorojasmz/apolo-cad/security/advisories/new>). Only the maintainer sees
it.

If you can, include:

- which component it affects (API, MCP, script sandbox, loading an `.apolo` file, UI…);
- the `apolo-cad` version (`pip show apolo-cad`) or the commit;
- steps to reproduce it and what an attacker gains.

Apolo is maintained by one person: you'll get an answer as soon as possible, and the fix ships in
the next PyPI release. If you'd like to be credited in the advisory, say so in the report.

## Supported versions

Only the **latest release of `apolo-cad` on PyPI** (and `main`). If you use an older one, upgrade
before reporting: it may already be fixed.
