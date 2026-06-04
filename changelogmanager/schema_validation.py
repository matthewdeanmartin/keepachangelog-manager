# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""JSON Schema validation for KAG-Manager changelog data.

This module is deliberately isolated from the reader/writer logic. If JSON
Schema validation stops pulling its weight, callers can remove this boundary
without disturbing the rest of the changelog model.

Only the current schema exists today. The public ``schema_version`` parameter is
kept as a narrow extension point for future KAG-Manager schema revisions.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import TYPES_OF_CHANGE

SchemaVersion = Literal["current"]

SCHEMA_VERSIONS: tuple[SchemaVersion, ...] = ("current",)
DEFAULT_SCHEMA_VERSION: SchemaVersion = "current"


def _metadata_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["version", "release_date"],
        "properties": {
            "version": {"type": "string", "minLength": 1},
            "release_date": {
                "oneOf": [
                    {"type": "null"},
                    {"type": "string", "format": "date"},
                ]
            },
            "semantic_version": {
                "type": "object",
                "required": ["major", "minor", "patch", "prerelease", "buildmetadata"],
                "properties": {
                    "major": {"type": "integer", "minimum": 0},
                    "minor": {"type": "integer", "minimum": 0},
                    "patch": {"type": "integer", "minimum": 0},
                    "prerelease": {"oneOf": [{"type": "null"}, {"type": "string"}]},
                    "buildmetadata": {"oneOf": [{"type": "null"}, {"type": "string"}]},
                },
                "additionalProperties": False,
            },
            "pep440_version": {
                "type": "object",
                "required": ["epoch", "release", "pre", "post", "dev", "local"],
                "properties": {
                    "epoch": {"type": "integer", "minimum": 0},
                    "release": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0},
                        "minItems": 1,
                    },
                    "pre": {
                        "oneOf": [
                            {"type": "null"},
                            {
                                "type": "array",
                                "prefixItems": [
                                    {"type": "string"},
                                    {"type": "integer", "minimum": 0},
                                ],
                                "minItems": 2,
                                "maxItems": 2,
                            },
                        ]
                    },
                    "post": {
                        "oneOf": [{"type": "null"}, {"type": "integer", "minimum": 0}]
                    },
                    "dev": {
                        "oneOf": [{"type": "null"}, {"type": "integer", "minimum": 0}]
                    },
                    "local": {"oneOf": [{"type": "null"}, {"type": "string"}]},
                },
                "additionalProperties": False,
            },
            "calendar_version": {
                "type": "object",
                "required": ["year", "month", "day", "micro"],
                "properties": {
                    "year": {"type": "integer", "minimum": 0},
                    "month": {
                        "oneOf": [
                            {"type": "null"},
                            {"type": "integer", "minimum": 1, "maximum": 12},
                        ]
                    },
                    "day": {
                        "oneOf": [
                            {"type": "null"},
                            {"type": "integer", "minimum": 1, "maximum": 31},
                        ]
                    },
                    "micro": {
                        "oneOf": [{"type": "null"}, {"type": "integer", "minimum": 0}]
                    },
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def _release_schema() -> dict[str, Any]:
    properties: dict[str, Any] = {
        "metadata": _metadata_schema(),
    }
    for change_type in TYPES_OF_CHANGE:
        properties[change_type] = {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        }
    return {
        "type": "object",
        "required": ["metadata"],
        "properties": properties,
        "additionalProperties": False,
    }


def _mapping_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://keepachangelog-manager.local/schemas/current/changelog.mapping.schema.json",
        "title": "KAG-Manager changelog mapping",
        "type": "object",
        "propertyNames": {"type": "string", "minLength": 1},
        "additionalProperties": _release_schema(),
    }


def _export_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://keepachangelog-manager.local/schemas/current/changelog.export.schema.json",
        "title": "KAG-Manager JSON export",
        "type": "array",
        "items": _release_schema(),
    }


CHANGELOG_MAPPING_SCHEMA: dict[str, Any] = _mapping_schema()
CHANGELOG_EXPORT_SCHEMA: dict[str, Any] = _export_schema()


def get_changelog_mapping_schema(
    schema_version: SchemaVersion = DEFAULT_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Returns the current mapping schema."""

    _validate_supported_schema_version(schema_version)
    return deepcopy(CHANGELOG_MAPPING_SCHEMA)


def get_changelog_export_schema(
    schema_version: SchemaVersion = DEFAULT_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Returns the current JSON export schema."""

    _validate_supported_schema_version(schema_version)
    return deepcopy(CHANGELOG_EXPORT_SCHEMA)


def validate_changelog_mapping(
    data: Any,
    *,
    schema_version: SchemaVersion = DEFAULT_SCHEMA_VERSION,
    file_path: str | None = None,
) -> None:
    """Validates internal changelog data against a KAG-Manager schema."""

    _validate(
        data,
        schema=get_changelog_mapping_schema(schema_version),
        file_path=file_path,
        target="changelog data",
    )


def validate_changelog_export(
    data: Any,
    *,
    schema_version: SchemaVersion = DEFAULT_SCHEMA_VERSION,
    file_path: str | None = None,
) -> None:
    """Validates exported JSON payloads against a KAG-Manager schema."""

    _validate(
        data,
        schema=get_changelog_export_schema(schema_version),
        file_path=file_path,
        target="JSON export",
    )


def _validate(
    data: Any,
    *,
    schema: dict[str, Any],
    file_path: str | None,
    target: str,
) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    error = next(validator.iter_errors(data), None)
    if error is None:
        return
    raise logging.Error(
        file_path=file_path,
        message=f"Invalid {target}: {_format_validation_error(error)}",
    )


def _format_validation_error(error: ValidationError) -> str:
    location = ".".join(str(part) for part in error.absolute_path)
    if not location:
        location = "<root>"
    return f"{location}: {error.message}"


def _validate_supported_schema_version(schema_version: str) -> None:
    if schema_version not in SCHEMA_VERSIONS:
        supported = ", ".join(SCHEMA_VERSIONS)
        raise logging.Error(
            message=(
                f"Unsupported KAG-Manager schema version '{schema_version}'. "
                f"Only the current schema exists today; supported versions: {supported}"
            )
        )
