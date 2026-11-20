# Original feature imports, constants and direct helper functions; no duplicate UI/server bodies.
from __future__ import annotations
from pathlib import Path as _ExportPath

LEGACY_ENTRYPOINT_FILE = str(_ExportPath(__file__).resolve().parents[3] / "help_tutorial.py")
"""Static end-user documentation for the validated SpaShiny core workflow.

This module deliberately contains no analysis code. It renders a public-facing
guide and keeps experimental features separate from the Y7_T core tutorial.
"""
import os
from shiny import ui


def _card(title, *children, anchor=None):
    attrs = {"class": "help-card"}
    if anchor:
        attrs["id"] = anchor
    return ui.tags.section(ui.h2(title, class_="help-section-title"), *children, **attrs)


def _step(number, title, where, settings, outcome):
    return ui.tags.article(
        ui.tags.div(str(number), class_="help-step-number"),
        ui.tags.div(
            ui.h3(title, class_="help-step-title"),
            ui.tags.p(ui.tags.strong("Where: "), where),
            ui.tags.p(ui.tags.strong("Use: "), settings),
            ui.tags.p(ui.tags.strong("Expected result: "), outcome),
        ),
        class_="help-step",
    )


def _parameter_row(parameter, description, default, guidance, workflow):
    return ui.tags.tr(
        ui.tags.td(ui.tags.code(parameter)),
        ui.tags.td(description),
        ui.tags.td(default),
        ui.tags.td(guidance),
        ui.tags.td(workflow),
    )


def help_tutorial_ui():
    from spashiny.features.help.ui import help_tutorial_ui as _entry

    return _entry()
