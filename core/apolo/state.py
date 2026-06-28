"""Estado compartido del proceso servidor.

OCCT no es thread-safe: dos hilos no pueden teselar/regenerar las mismas
formas a la vez. Todo acceso al documento (API y agente) pasa por este lock.
"""

import threading

STATE_LOCK = threading.RLock()
