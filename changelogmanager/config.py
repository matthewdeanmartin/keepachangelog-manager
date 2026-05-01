# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Configuration Management"""

from typing import Any, Dict, Mapping, Sequence

import yaml

import changelogmanager._llvm_diagnostics as logging


def validate_configuration(file_path: str, config: Mapping[str, Any]) -> None:
    """Verifies if the provided configuration file is accoriding to expectations"""
    if not config.get("project") or not config["project"].get("components"):
        raise logging.Error(
            file_path=file_path, message="Incorrect Project configuration format!"
        )

    for component in config["project"]["components"]:
        if not component.get("name") or not component.get("changelog"):
            raise logging.Error(
                file_path=file_path, message="Incorrect Component configuration format!"
            )


def get_component_from_config(config: str, component: str) -> Dict[str, Any]:
    """Retrieves a specific component from the configuration file"""
    with open(config, "r", encoding="UTF-8") as file_handle:
        configuration = yaml.safe_load(file_handle)

    validate_configuration(config, configuration)

    project = configuration.get("project", {})

    def filter_component(
        components: Sequence[Dict[str, Any]], name: str
    ) -> Dict[str, Any]:
        for component in components:
            if component.get("name") == name:
                return component

        raise logging.Error(file_path=config, message=f"Unknown component name: {name}")

    return filter_component(project.get("components", []), component)
