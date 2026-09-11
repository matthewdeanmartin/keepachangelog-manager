"""Update TOML data while retaining comments on surviving keys and tables."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

import tomlkit
from tomlkit.items import AoT


def update_document(
    target: MutableMapping[str, Any], source: Mapping[str, Any]
) -> None:
    for key in list(target):
        if key not in source:
            del target[key]
    for key, value in source.items():
        current = target.get(key)
        if isinstance(value, Mapping) and isinstance(current, MutableMapping):
            update_document(current, value)
        elif isinstance(current, AoT) and isinstance(value, list):
            # Components have stable names; retaining their tables keeps comments
            # attached to the right component even after reorder/removal.
            updated = tomlkit.aot()
            by_name = {item.get("name"): item for item in current if "name" in item}
            for index, item in enumerate(value):
                previous = (
                    by_name.get(item.get("name"))
                    if "name" in item
                    else (current[index] if index < len(current) else None)
                )
                table = previous if previous is not None else tomlkit.table()
                update_document(table, item)
                updated.append(table)
            target[key] = updated
        elif current != value:
            target[key] = value
