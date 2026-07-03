"""SourceProfile: the diagnosis result that configures how a source is processed.

A profile is produced by a diagnostic tier and then drives the run (no per-page routing):
- D-1: the built-in VLM diagnostic (diagnose.py) -- automated, routine sources.
- D-2: a flagship coding agent in the *oracle position* reviewing sample material by hand --
  hard sources / calibration (docs/.design/diagnostic-d2.md).

Both tiers emit the same SourceProfile so the run and persistence (R4.4) are tier-agnostic.
Thresholds live on the profile because there are no universal cutoffs -- they are calibrated
per domain (D-2 may override D-1's defaults).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceProfile:
    source_id: str
    recommended_mode: str                 # "deterministic" | "det_vlm"
    confidence: float
    tier: str                             # "D-1" | "D-2"
    reasons: tuple[str, ...] = ()
    thresholds: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None         # caller-stamped ISO timestamp (kept out for determinism)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "recommended_mode": self.recommended_mode,
            "confidence": round(self.confidence, 2),
            "tier": self.tier,
            "reasons": list(self.reasons),
            "thresholds": self.thresholds,
            "evidence": self.evidence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceProfile:
        return cls(
            source_id=data["source_id"],
            recommended_mode=data["recommended_mode"],
            confidence=float(data.get("confidence", 0.0)),
            tier=data.get("tier", "D-1"),
            reasons=tuple(data.get("reasons", [])),
            thresholds=dict(data.get("thresholds", {})),
            evidence=dict(data.get("evidence", {})),
            created_at=data.get("created_at"),
        )


def profile_path(profiles_dir: str | Path, source_id: str) -> Path:
    return Path(profiles_dir) / f"{source_id}.json"


def save_profile(profile: SourceProfile, profiles_dir: str | Path) -> Path:
    """Persist a profile to <profiles_dir>/<source_id>.json so the source is not re-diagnosed."""
    path = profile_path(profiles_dir, profile.source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_profile(source_id: str, profiles_dir: str | Path) -> SourceProfile | None:
    path = profile_path(profiles_dir, source_id)
    if not path.exists():
        return None
    return SourceProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))


def from_d1_diagnosis(diagnosis: Any, *, source_id: str, created_at: str | None = None) -> SourceProfile:
    """Adapt a D-1 SourceDiagnosis into a SourceProfile (tier D-1), carrying the thresholds it used."""
    from .diagnose import _DIVERGE_TOKEN, _SCAN_FRACTION

    return SourceProfile(
        source_id=source_id,
        recommended_mode=diagnosis.recommended_mode,
        confidence=diagnosis.confidence,
        tier="D-1",
        reasons=diagnosis.reasons,
        thresholds=dict(diagnosis.thresholds) or {"scan_fraction": _SCAN_FRACTION, "token_divergence": _DIVERGE_TOKEN},
        evidence={
            "n_pages": diagnosis.n_pages,
            "n_sampled": diagnosis.n_sampled,
            "scan_fraction": round(diagnosis.scan_fraction, 3),
            "mean_token_divergence": round(diagnosis.mean_token_divergence, 3),
            "pages_with_tables": diagnosis.pages_with_tables,
            "pages_with_figures": diagnosis.pages_with_figures,
            "samples": list(diagnosis.samples),
        },
        created_at=created_at,
    )
