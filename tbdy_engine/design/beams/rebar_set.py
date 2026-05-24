from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from ..rebar.real_rebar import normalize_real_rebar

try:
    from tbdy_engine.design.rebar.provided_rebar import ProvidedRebarResolver
except Exception:  # fail-safe: provided rebar layer is optional
    ProvidedRebarResolver = None  # type: ignore


@dataclass
class BeamRebarSet:
    element_id: str
    story: str = ""
    source: str = "unknown"

    # Longitudinal rebar
    as_top_provided_mm2: Optional[float] = None
    as_bottom_provided_mm2: Optional[float] = None

    # Transverse rebar
    av_s_provided_mm2_per_m: Optional[float] = None
    stirrup_diameter_mm: Optional[float] = None
    stirrup_spacing_mm: Optional[float] = None
    stirrup_leg_count: Optional[float] = None

    status: str = "NO_DATA"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        v = float(str(value).replace(",", "."))
        if v != v:
            return default
        return v
    except Exception:
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    v = _safe_float(value, None)
    if v is None:
        return default
    return int(round(v))


def _make_key(story: Any, label: Any) -> str:
    return f"{str(story or '').strip()}|{str(label or '').strip()}"


def _norm_col(df: Any, names: list[str]) -> Optional[str]:
    if df is None or not hasattr(df, "columns"):
        return None

    targets = {
        str(n).strip().lower().replace(" ", "").replace("_", "")
        for n in names
    }

    for c in df.columns:
        cc = str(c).strip().lower().replace(" ", "").replace("_", "")
        if cc in targets:
            return c

    for c in df.columns:
        cc = str(c).strip().lower().replace(" ", "").replace("_", "")
        if any(t in cc for t in targets):
            return c

    return None


def _m2_to_mm2(value: Any) -> float:
    """
    ETABS bazı rebar çıktılarında m2, bazı normalize tablolarda mm2 gelebilir.

    Conservative rule:
    - 0 < value < 100 ise m2 kabul edip mm2'ye çevir.
    - Aksi halde mm2 kabul et.
    """
    x = _safe_float(value, 0.0) or 0.0
    if 0.0 < x < 100.0:
        return x * 1_000_000.0
    return x


class BeamRebarResolver:
    """
    Beam rebar resolver.

    Priority:
    1. Provided/final rebar schedule from ModelContext.
    2. Real rebar normalizer.
    3. ETABS beam_design_summary fallback.

    It never opens ETABS directly. It only reads ModelContext dictionaries.
    """

    def __init__(self, ctx: Any):
        self.ctx = ctx

    def resolve(self) -> Dict[str, BeamRebarSet]:
        out: Dict[str, BeamRebarSet] = {}

        # ------------------------------------------------------------------
        # 1. PROVIDED / FINAL REBAR
        # ------------------------------------------------------------------
        self._resolve_provided_rebar(out)

        # ------------------------------------------------------------------
        # 2. NORMALIZED REAL REBAR
        # ------------------------------------------------------------------
        self._resolve_normalized_real_rebar(out)

        # ------------------------------------------------------------------
        # 3. ETABS DESIGN SUMMARY FALLBACK
        # ------------------------------------------------------------------
        self._resolve_etabs_design_summary(out)

        # ------------------------------------------------------------------
        # 4. Label-only aliases only when the label is unique.
        # ------------------------------------------------------------------
        self._add_unique_label_aliases(out)

        return out

    def _resolve_provided_rebar(self, out: Dict[str, BeamRebarSet]) -> None:
        if ProvidedRebarResolver is None:
            return

        try:
            provided = ProvidedRebarResolver(self.ctx).resolve_beams()
        except Exception:
            return

        seen_records: set[str] = set()

        for _, rec in provided.items():
            label = str(getattr(rec, "label", "") or "").strip()
            story = str(getattr(rec, "story", "") or "").strip()

            if not label:
                continue

            key = _make_key(story, label)

            # Avoid processing label alias and story|label record twice.
            if key in seen_records:
                continue
            seen_records.add(key)

            top = _safe_float(getattr(rec, "as_top_mm2", None))
            bot = _safe_float(getattr(rec, "as_bottom_mm2", None))
            avs = _safe_float(getattr(rec, "av_s_mm2_per_m", None))

            missing = []
            if top is None or top <= 0:
                missing.append("top As")
            if bot is None or bot <= 0:
                missing.append("bottom As")
            if avs is None or avs <= 0:
                missing.append("shear Av/s")

            item = BeamRebarSet(
                element_id=label,
                story=story,
                source=str(getattr(rec, "source", "") or "provided_rebar"),
                as_top_provided_mm2=top,
                as_bottom_provided_mm2=bot,
                av_s_provided_mm2_per_m=avs,
                stirrup_diameter_mm=_safe_float(getattr(rec, "stirrup_diameter_mm", None)),
                stirrup_spacing_mm=_safe_float(getattr(rec, "stirrup_spacing_mm", None)),
                stirrup_leg_count=_safe_int(getattr(rec, "stirrup_legs", None)),
                status="OK" if not missing else "WARNING",
                note="final provided beam rebar" if not missing else "provided rebar missing: " + ", ".join(missing),
            )

            out[key] = item

            # If story is missing, allow label-only provided fallback.
            if not story:
                out[label] = item

    def _resolve_normalized_real_rebar(self, out: Dict[str, BeamRebarSet]) -> None:
        try:
            rows = normalize_real_rebar(self.ctx).get("BEAM", [])
        except Exception:
            rows = []

        for rec in rows:
            label = str(rec.get("element_id") or "").strip()
            story = str(rec.get("story") or "").strip()

            if not label:
                continue

            key = _make_key(story, label)

            # Provided rebar has higher priority.
            if key in out:
                continue

            status = str(rec.get("status") or "WARNING")

            item = BeamRebarSet(
                element_id=label,
                story=story,
                source=str(rec.get("source_table") or "real_rebar_schedule"),
                as_top_provided_mm2=_safe_float(rec.get("as_top_provided_mm2")),
                as_bottom_provided_mm2=_safe_float(rec.get("as_bottom_provided_mm2")),
                av_s_provided_mm2_per_m=_safe_float(rec.get("av_s_provided_mm2_per_m")),
                stirrup_diameter_mm=_safe_float(rec.get("stirrup_diameter_mm")),
                stirrup_spacing_mm=_safe_float(rec.get("stirrup_spacing_mm")),
                stirrup_leg_count=_safe_int(rec.get("stirrup_leg_count")),
                status=status,
                note=str(rec.get("note") or ""),
            )

            out[key] = item

    def _resolve_etabs_design_summary(self, out: Dict[str, BeamRebarSet]) -> None:
        tables = getattr(self.ctx, "tables", {}) or {}
        design_metadata = getattr(self.ctx, "design_metadata", {}) or {}

        df = tables.get("beam_design_summary")
        if df is None:
            df = design_metadata.get("beam_design_summary")

        if df is None or not hasattr(df, "empty") or df.empty:
            return

        label_col = _norm_col(df, ["label", "beam", "frame", "element", "objlabel"])
        story_col = _norm_col(df, ["story", "level"])

        if not label_col:
            return

        group_cols = [label_col]
        if story_col:
            group_cols = [story_col, label_col]

        for group_key, group in df.groupby(group_cols):
            if story_col:
                story, label = group_key
            else:
                story, label = "", group_key

            label_s = str(label or "").strip()
            story_s = str(story or "").strip()

            if not label_s:
                continue

            key = _make_key(story_s, label_s)

            # Provided / real rebar has higher priority.
            if key in out:
                continue

            top = 0.0
            bot = 0.0
            avs = 0.0

            for _, row in group.iterrows():
                top = max(
                    top,
                    _m2_to_mm2(row.get("tottoprebar")),
                    _m2_to_mm2(row.get("astop")),
                    _m2_to_mm2(row.get("asmintop")),
                )

                bot = max(
                    bot,
                    _m2_to_mm2(row.get("totbotrebar")),
                    _m2_to_mm2(row.get("asbot")),
                    _m2_to_mm2(row.get("asminbot")),
                )

                avs = max(
                    avs,
                    _m2_to_mm2(row.get("tottrnrebar")),
                    _m2_to_mm2(row.get("vrebar")),
                )

            missing = []
            if top <= 0:
                missing.append("top As")
            if bot <= 0:
                missing.append("bottom As")
            if avs <= 0:
                missing.append("shear Av/s")

            item = BeamRebarSet(
                element_id=label_s,
                story=story_s,
                source="etabs_beam_design_summary",
                as_top_provided_mm2=top if top > 0 else None,
                as_bottom_provided_mm2=bot if bot > 0 else None,
                av_s_provided_mm2_per_m=avs if avs > 0 else None,
                status="OK" if not missing else "WARNING",
                note=(
                    "ETABS beam_design_summary design rebar demand"
                    if not missing
                    else "ETABS beam_design_summary missing: " + ", ".join(missing)
                ),
            )

            out[key] = item

    def _add_unique_label_aliases(self, out: Dict[str, BeamRebarSet]) -> None:
        label_counts: Dict[str, int] = {}

        for key, item in out.items():
            # Ignore existing label-only aliases during count.
            if "|" not in key:
                continue
            label_counts[item.element_id] = label_counts.get(item.element_id, 0) + 1

        for key, item in list(out.items()):
            if "|" not in key:
                continue

            label = item.element_id
            if label_counts.get(label, 0) == 1 and label not in out:
                out[label] = item


def resolve_beam_rebar(ctx: Any) -> Dict[str, Dict[str, Any]]:
    return {k: v.to_dict() for k, v in BeamRebarResolver(ctx).resolve().items()}
