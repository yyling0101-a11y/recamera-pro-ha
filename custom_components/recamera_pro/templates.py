"""Parsers for the three inference tasks supported by factory reCamera Pro firmware."""

from __future__ import annotations

import json
import re


SUPPORTED_TASKS = ("detection", "classification", "segmentation")


def _fmt_score(score):
    try:
        return f"{float(score) * 100:.1f}%"
    except (ValueError, TypeError):
        return str(score)


def _fmt_box(box):
    try:
        return (
            f"({float(box.get('left', 0)):.2f}, "
            f"{float(box.get('top', 0)):.2f}, "
            f"{float(box.get('right', 0)):.2f}, "
            f"{float(box.get('bottom', 0)):.2f})"
        )
    except (AttributeError, TypeError, ValueError):
        return str(box)


def parse_detection(data):
    entries = data.get("detection", {}).get("entries", [])
    return "\n".join(
        f"{entry.get('class_name', 'unknown')} "
        f"{_fmt_score(entry.get('score', 0))} "
        f"{_fmt_box(entry.get('box', {}))}"
        for entry in entries[:10]
    )


def parse_classification(data):
    entries = data.get("classification", {}).get("entries", [])
    return "\n".join(
        f"{entry.get('class_name', 'unknown')} "
        f"{_fmt_score(entry.get('score', 0))}"
        for entry in entries[:10]
    )


def parse_segmentation(data):
    entries = data.get("segmentation", {}).get("entries", [])
    return "\n".join(
        f"{entry.get('class_name', 'unknown')} "
        f"{_fmt_score(entry.get('score', 0))} "
        f"{_fmt_box(entry.get('box', {}))} "
        f"{entry.get('mask_width', 0)}x{entry.get('mask_height', 0)}"
        for entry in entries[:10]
    )


PARSERS = {
    "detection": parse_detection,
    "classification": parse_classification,
    "segmentation": parse_segmentation,
}


def parse_auto(data):
    task_type = str(data.get("task_type_name", "")).lower()
    if task_type not in SUPPORTED_TASKS:
        task_type = next(
            (task for task in SUPPORTED_TASKS if isinstance(data.get(task), dict)),
            "",
        )
    parser = PARSERS.get(task_type)
    return parser(data) if parser else json.dumps(data, ensure_ascii=False, indent=2)


def apply_custom_template(data, template_str):
    def replace_match(match):
        value = _get_nested(data, match.group(1).strip())
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return re.sub(r"\{\{(.+?)\}\}", replace_match, template_str)


def _get_nested(data, path):
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


BUILTIN_TEMPLATES = [
    {
        "id": "detection",
        "name_key": "template_detection",
        "description_key": "template_detection_description",
        "type": "builtin",
        "parse": parse_detection,
    },
    {
        "id": "classification",
        "name_key": "template_classification",
        "description_key": "template_classification_description",
        "type": "builtin",
        "parse": parse_classification,
    },
    {
        "id": "segmentation",
        "name_key": "template_segmentation",
        "description_key": "template_segmentation_description",
        "type": "builtin",
        "parse": parse_segmentation,
    },
]


def get_builtin_template_info():
    return [
        {
            "id": template["id"],
            "name_key": template["name_key"],
            "description_key": template["description_key"],
            "type": template["type"],
        }
        for template in BUILTIN_TEMPLATES
    ]


def apply_template(data, template_id, custom_templates=None):
    del custom_templates
    parser = PARSERS.get(template_id)
    if parser is None:
        return None
    try:
        return parser(data)
    except (AttributeError, TypeError, ValueError):
        return json.dumps(data, ensure_ascii=False, indent=2)


def get_template_list(custom_templates=None):
    del custom_templates
    return get_builtin_template_info()
