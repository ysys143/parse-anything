from __future__ import annotations

from odl_vl.pipeline.diagnose import SourceDiagnosis
from odl_vl.pipeline.profile import SourceProfile, from_d1_diagnosis


def test_source_profile_roundtrip():
    p = SourceProfile("csnl", "det_vlm", 0.7, "D-2", ("structure present",), {"scan_fraction": 0.25}, {"k": 1}, "2026-06-24T00:00:00")
    p2 = SourceProfile.from_dict(p.to_dict())
    assert p2.recommended_mode == "det_vlm" and p2.tier == "D-2"
    assert p2.reasons == ("structure present",) and p2.thresholds == {"scan_fraction": 0.25}
    assert p2.created_at == "2026-06-24T00:00:00"


def test_from_d1_diagnosis_adapts_to_profile():
    diag = SourceDiagnosis(
        recommended_mode="det_vlm", confidence=0.6, n_pages=24, n_sampled=5, scan_fraction=0.0,
        mean_token_divergence=0.09, pages_with_tables=1, pages_with_figures=0,
        reasons=("structure present",), samples=({"page_index": 0},),
    )
    prof = from_d1_diagnosis(diag, source_id="csnl", created_at="2026-06-24T00:00:00")
    assert prof.tier == "D-1" and prof.recommended_mode == "det_vlm" and prof.source_id == "csnl"
    assert prof.evidence["pages_with_tables"] == 1 and "token_divergence" in prof.thresholds
    assert prof.created_at == "2026-06-24T00:00:00"
