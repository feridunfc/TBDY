"""Public C14.1-P1 live minimum-compliance entry point."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from tbdy_engine.features.etabs_com_attach import (
    EtabsAttachResult,
    attach_to_running_etabs,
)
from tbdy_engine.product._minimum_compliance_runner import (
    run_live_beam_column_minimum_compliance as _run_live_product,
)
from tbdy_engine.product._minimum_compliance_source import _load_live_source
from tbdy_engine.product._minimum_compliance_checks import (
    _evaluate_absolute_beam_depth,
    _evaluate_depth_vs_slab,
    _evaluate_web_detailing_trigger,
)
from tbdy_engine.product._minimum_compliance_summary import _summary

AttachRunner = Callable[[], EtabsAttachResult]
SourceLoader = Callable[[EtabsAttachResult, Path], Mapping[str, object]]
_KNOWN_COMPONENT_TYPES = frozenset({"Beam", "Column", "Brace", "Null"})


def run_live_beam_column_minimum_compliance(
    *,
    output_dir: Path,
    element_type: str | None = None,
    story: str | None = None,
    section: str | None = None,
    attach_runner: AttachRunner = attach_to_running_etabs,
    source_loader: SourceLoader | None = None,
) -> Mapping[str, object]:
    effective_loader = source_loader or _load_live_source

    def preserving_loader(
        attach_result: EtabsAttachResult,
        work_dir: Path,
    ) -> Mapping[str, object]:
        source = dict(effective_loader(attach_result, work_dir))
        diagnostics = [dict(item) for item in source.get("source_diagnostics", ()) if isinstance(item, Mapping)]
        for row in source.get("component_rows", ()):
            if not isinstance(row, Mapping) or row.get("UniqueName") in (None, ""):
                continue
            raw_type = row.get("Type")
            if raw_type in _KNOWN_COMPONENT_TYPES:
                continue
            diagnostics.append(
                {
                    "status": "BLOCKED",
                    "code": "COMPONENT_TYPE_UNKNOWN",
                    "component_id": str(row.get("UniqueName")),
                    "component_type": "unknown",
                    "raw_component_type": raw_type,
                    "message": f"Unknown raw component type: {raw_type or '<missing>'}",
                }
            )
        source["source_diagnostics"] = diagnostics
        return source

    return _run_live_product(
        output_dir=output_dir,
        element_type=element_type,
        story=story,
        section=section,
        attach_runner=attach_runner,
        source_loader=preserving_loader,
    )


__all__ = [
    "run_live_beam_column_minimum_compliance",
    "_evaluate_absolute_beam_depth",
    "_evaluate_depth_vs_slab",
    "_evaluate_web_detailing_trigger",
    "_summary",
]
