# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""JSON backend shim.

Prefers :mod:`orjson` (fast, C-backed) when it is installed and transparently
falls back to the standard library :mod:`json` otherwise. ``orjson`` ships native
wheels that are not yet available for every interpreter (e.g. brand-new CPython
releases), so it is an *optional* dependency; importing this module always works.

Only the subset used by this project is wrapped:

* ``dumps(obj, option=OPT_INDENT_2)`` -> ``bytes`` (callers ``.decode()`` it,
  matching orjson's bytes-returning API).
* ``loads(data)`` accepting ``str`` or ``bytes``.
* ``OPT_INDENT_2`` flag.

Use :data:`USING_ORJSON` if you need to know which backend is active.
"""

from typing import Any

try:
    import orjson as _orjson

    USING_ORJSON = True

    OPT_INDENT_2 = _orjson.OPT_INDENT_2

    def dumps(obj: Any, option: int = 0) -> bytes:
        """Serialize ``obj`` to JSON ``bytes`` (orjson backend)."""
        return _orjson.dumps(obj, option=option)

    def loads(data: Any) -> Any:
        """Deserialize JSON ``str``/``bytes`` to a Python object (orjson backend)."""
        return _orjson.loads(data)

except (
    ImportError
):  # pragma: no cover - exercised on interpreters lacking orjson wheels
    import json as _json

    USING_ORJSON = False

    # Sentinel flag mirroring orjson.OPT_INDENT_2 so callers can pass it through.
    OPT_INDENT_2 = 1

    def dumps(obj: Any, option: int = 0) -> bytes:
        """Serialize ``obj`` to JSON ``bytes`` (stdlib json backend).

        orjson always returns bytes, so we encode the stdlib's ``str`` output to
        keep the ``.decode()`` call sites working unchanged.
        """
        indent = 2 if option & OPT_INDENT_2 else None
        return _json.dumps(obj, indent=indent).encode()

    def loads(data: Any) -> Any:
        """Deserialize JSON ``str``/``bytes`` to a Python object (stdlib backend)."""
        return _json.loads(data)


__all__ = ["OPT_INDENT_2", "USING_ORJSON", "dumps", "loads"]
