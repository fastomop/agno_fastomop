"""
Berlin ARDS Classification Tools

Deterministic tools for applying the Berlin Definition of Acute Respiratory
Distress Syndrome to structured patient data. These are registered as Function
tools on the ARDS Team — the Qwen 3 orchestrator gathers data from the database
agent and MedGemma imaging agent, then passes it here for computation.

NO LLM inference happens in these tools — all logic is rule-based.

Berlin Definition (2012):
  ALL 4 criteria must be met:
  1. Timing:        Acute onset within 1 week of clinical insult
  2. Chest Imaging: Bilateral opacities not explained by effusions/collapse/nodules
  3. Origin:        Not fully explained by cardiac failure or fluid overload
  4. Oxygenation:   PaO2/FiO2 with PEEP >= 5 cmH2O
                    Mild:     200 < PF <= 300
                    Moderate: 100 < PF <= 200
                    Severe:   PF <= 100
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from agno.tools.function import Function


# ── Constants ──────────────────────────────────────────────────────────────────

# BNP thresholds for cardiogenic edema suspicion
BNP_THRESHOLD = 100        # pg/mL — BNP > 100 suggests cardiac cause
NT_PROBNP_THRESHOLD = 300  # pg/mL — NT-proBNP > 300 suggests cardiac cause
LVEF_THRESHOLD = 40        # % — LVEF < 40% suggests cardiac cause

# Berlin oxygenation severity thresholds (PaO2/FiO2 with PEEP >= 5)
PF_SEVERE = 100
PF_MODERATE = 200
PF_MILD = 300

# Timing: onset must be within 7 days
TIMING_WINDOW_DAYS = 7

# Minimum PEEP for oxygenation criterion
MIN_PEEP = 5.0


# ── Helper Functions ───────────────────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a date string in common formats. Returns None if unparseable."""
    if not date_str or str(date_str).lower() in ("null", "none", ""):
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except ValueError:
            continue
    return None


def _safe_float(val: Any) -> Optional[float]:
    """Convert value to float, returning None if not possible."""
    if val is None or (isinstance(val, str) and val.lower() in ("null", "none", "")):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _normalise_fio2(fio2: Optional[float]) -> Optional[float]:
    """Normalise FiO2 to fraction (0.0–1.0). Values > 1.0 are treated as percentages."""
    if fio2 is None:
        return None
    if fio2 > 1.0:
        return fio2 / 100.0
    return fio2


# ── Criterion Evaluators ──────────────────────────────────────────────────────

def _evaluate_timing(timing: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate Berlin Criterion 1: Timing (acute onset within 7 days)."""
    insult_date = _parse_date(timing.get("clinical_insult_date"))
    onset_date = _parse_date(timing.get("respiratory_onset_date"))

    if insult_date is None and onset_date is None:
        return {
            "criterion": "Timing",
            "status": "INDETERMINATE",
            "reason": "No clinical insult date or respiratory onset date available",
            "days_between": None,
        }

    if insult_date is None:
        return {
            "criterion": "Timing",
            "status": "INDETERMINATE",
            "reason": "Clinical insult date not found; cannot calculate interval",
            "days_between": None,
        }

    if onset_date is None:
        return {
            "criterion": "Timing",
            "status": "INDETERMINATE",
            "reason": "Respiratory onset date not found; cannot calculate interval",
            "days_between": None,
        }

    days_diff = abs((onset_date - insult_date).days)

    if days_diff <= TIMING_WINDOW_DAYS:
        return {
            "criterion": "Timing",
            "status": "MET",
            "reason": f"Onset within {days_diff} day(s) of clinical insult (threshold: {TIMING_WINDOW_DAYS} days)",
            "days_between": days_diff,
        }
    else:
        return {
            "criterion": "Timing",
            "status": "NOT_MET",
            "reason": f"Onset {days_diff} days after clinical insult exceeds {TIMING_WINDOW_DAYS}-day window",
            "days_between": days_diff,
        }


def _evaluate_oxygenation(oxy: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate Berlin Criterion 4: Oxygenation (PaO2/FiO2 with PEEP >= 5)."""
    pao2 = _safe_float(oxy.get("pao2"))
    fio2_raw = _safe_float(oxy.get("fio2"))
    peep = _safe_float(oxy.get("peep"))
    spo2 = _safe_float(oxy.get("spo2"))

    fio2 = _normalise_fio2(fio2_raw)

    # Check PEEP requirement
    if peep is None:
        peep_note = "PEEP value not available"
        peep_met = False
    elif peep < MIN_PEEP:
        peep_note = f"PEEP {peep} cmH2O is below minimum threshold of {MIN_PEEP} cmH2O"
        peep_met = False
    else:
        peep_note = f"PEEP {peep} cmH2O meets minimum threshold"
        peep_met = True

    # Calculate PF ratio
    pf_ratio = None
    severity = None

    if pao2 is not None and fio2 is not None and fio2 > 0:
        pf_ratio = round(pao2 / fio2, 1)

        if peep_met:
            if pf_ratio <= PF_SEVERE:
                severity = "Severe"
            elif pf_ratio <= PF_MODERATE:
                severity = "Moderate"
            elif pf_ratio <= PF_MILD:
                severity = "Mild"
            else:
                severity = None  # PF > 300 = not ARDS by oxygenation

    # Determine status
    if pao2 is None or fio2 is None:
        status = "INDETERMINATE"
        reason = "PaO2 and/or FiO2 values not available"
    elif not peep_met:
        status = "INDETERMINATE"
        reason = f"Cannot evaluate — {peep_note}"
    elif severity is not None:
        status = "MET"
        reason = f"PaO2/FiO2 ratio = {pf_ratio} with PEEP >= {MIN_PEEP} => {severity} ARDS"
    else:
        status = "NOT_MET"
        reason = f"PaO2/FiO2 ratio = {pf_ratio} exceeds 300 (Mild ARDS threshold)"

    return {
        "criterion": "Oxygenation",
        "status": status,
        "reason": reason,
        "pao2": pao2,
        "fio2": fio2,
        "fio2_raw": fio2_raw,
        "peep": peep,
        "spo2": spo2,
        "pf_ratio": pf_ratio,
        "severity": severity,
        "peep_note": peep_note,
    }


def _evaluate_cardiac(cardiac: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate Berlin Criterion 3: Origin of Edema (not fully cardiogenic).

    Incorporates MedGemma cardiomegaly detection when available.
    """
    bnp_val = _safe_float(cardiac.get("bnp_value"))
    bnp_type = cardiac.get("bnp_type")  # "BNP" or "NT-proBNP"
    lvef = _safe_float(cardiac.get("lvef"))
    hf_dx = bool(cardiac.get("heart_failure_diagnosed", False))
    fluid_overload = bool(cardiac.get("fluid_overload_diagnosed", False))
    cardiomegaly_imaging = bool(cardiac.get("cardiomegaly_on_imaging", False))
    # MedGemma cardiomegaly finding (from imaging agent CXR analysis)
    medgemma_cardiomegaly = cardiac.get("medgemma_cardiomegaly_detected")

    cardiac_flags = []
    non_cardiac_flags = []

    # BNP assessment
    if bnp_val is not None:
        if bnp_type and "nt" in str(bnp_type).lower():
            if bnp_val > NT_PROBNP_THRESHOLD:
                cardiac_flags.append(f"NT-proBNP elevated: {bnp_val} pg/mL (>{NT_PROBNP_THRESHOLD})")
            else:
                non_cardiac_flags.append(f"NT-proBNP normal: {bnp_val} pg/mL (<={NT_PROBNP_THRESHOLD})")
        else:  # Assume BNP
            if bnp_val > BNP_THRESHOLD:
                cardiac_flags.append(f"BNP elevated: {bnp_val} pg/mL (>{BNP_THRESHOLD})")
            else:
                non_cardiac_flags.append(f"BNP normal: {bnp_val} pg/mL (<={BNP_THRESHOLD})")

    # LVEF assessment
    if lvef is not None:
        if lvef < LVEF_THRESHOLD:
            cardiac_flags.append(f"LVEF reduced: {lvef}% (<{LVEF_THRESHOLD}%)")
        else:
            non_cardiac_flags.append(f"LVEF preserved: {lvef}% (>={LVEF_THRESHOLD}%)")

    # Diagnoses
    if hf_dx:
        cardiac_flags.append("Heart failure diagnosed")
    if fluid_overload:
        cardiac_flags.append("Fluid overload diagnosed")
    if cardiomegaly_imaging:
        cardiac_flags.append("Cardiomegaly on CheXpert labels")

    # MedGemma cardiomegaly (weighted — vision model finding)
    if medgemma_cardiomegaly is True:
        cardiac_flags.append("MedGemma: Cardiomegaly detected on CXR")
    elif medgemma_cardiomegaly is False:
        non_cardiac_flags.append("MedGemma: No cardiomegaly on CXR")

    # Determine status
    has_any_data = (
        bnp_val is not None
        or lvef is not None
        or hf_dx
        or fluid_overload
        or cardiomegaly_imaging
        or medgemma_cardiomegaly is not None
    )

    if not has_any_data:
        return {
            "criterion": "Origin of Edema",
            "status": "INDETERMINATE",
            "reason": "No cardiac assessment data available (BNP, LVEF, heart failure dx, or imaging)",
            "cardiac_flags": [],
            "non_cardiac_flags": [],
        }

    if len(cardiac_flags) >= 2:
        return {
            "criterion": "Origin of Edema",
            "status": "NOT_MET",
            "reason": "Multiple indicators suggest cardiogenic edema: " + "; ".join(cardiac_flags),
            "cardiac_flags": cardiac_flags,
            "non_cardiac_flags": non_cardiac_flags,
        }
    elif len(cardiac_flags) == 1 and len(non_cardiac_flags) == 0:
        return {
            "criterion": "Origin of Edema",
            "status": "INDETERMINATE",
            "reason": "Single cardiac flag with no reassuring data: " + cardiac_flags[0],
            "cardiac_flags": cardiac_flags,
            "non_cardiac_flags": non_cardiac_flags,
        }
    elif len(cardiac_flags) == 0:
        return {
            "criterion": "Origin of Edema",
            "status": "MET",
            "reason": "No evidence of cardiogenic edema: " + "; ".join(non_cardiac_flags),
            "cardiac_flags": cardiac_flags,
            "non_cardiac_flags": non_cardiac_flags,
        }
    else:
        # Mixed signals — cardiac flags exist but outweighed by non-cardiac
        if len(non_cardiac_flags) > len(cardiac_flags):
            return {
                "criterion": "Origin of Edema",
                "status": "MET",
                "reason": "Cardiac flags present but outweighed by non-cardiac evidence. "
                          f"Cardiac: {'; '.join(cardiac_flags)}. Non-cardiac: {'; '.join(non_cardiac_flags)}",
                "cardiac_flags": cardiac_flags,
                "non_cardiac_flags": non_cardiac_flags,
            }
        return {
            "criterion": "Origin of Edema",
            "status": "INDETERMINATE",
            "reason": "Mixed cardiac indicators. Flags: " + "; ".join(cardiac_flags)
                      + ". Reassuring: " + "; ".join(non_cardiac_flags),
            "cardiac_flags": cardiac_flags,
            "non_cardiac_flags": non_cardiac_flags,
        }


def _evaluate_imaging(imaging: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate Berlin Criterion 2: Chest Imaging (bilateral opacities).

    MedGemma visual assessment has HIGHEST weight — this is the challenge differentiator.
    Priority: MedGemma > CheXpert labels > Radiology report keywords.
    """
    has_bilateral = imaging.get("has_bilateral_opacities")
    chexpert = imaging.get("chexpert_labels", {}) or {}
    report_findings = imaging.get("radiology_report_findings", "") or ""
    local_paths = imaging.get("local_paths", []) or []

    # MedGemma findings (highest priority)
    medgemma = imaging.get("medgemma_findings", {}) or {}
    medgemma_bilateral = medgemma.get("bilateral_opacities_present")
    medgemma_explained = medgemma.get("opacities_explained_by_effusion_or_collapse")
    medgemma_cardiomegaly = medgemma.get("cardiomegaly_detected")
    medgemma_devices = medgemma.get("support_devices", []) or []
    medgemma_raw = medgemma.get("raw_assessment", "")

    evidence_for = []
    evidence_against = []

    # ── MedGemma visual evidence (HIGHEST WEIGHT) ──
    medgemma_available = medgemma_bilateral is not None

    if medgemma_bilateral is True:
        evidence_for.append("MedGemma: Bilateral opacities detected on CXR")
        if medgemma_explained is False:
            evidence_for.append("MedGemma: Opacities NOT explained by effusions or collapse")
        elif medgemma_explained is True:
            evidence_against.append("MedGemma: Opacities may be explained by effusions/collapse")
    elif medgemma_bilateral is False:
        evidence_against.append("MedGemma: No bilateral opacities detected on CXR")

    if medgemma_devices:
        evidence_for.append(f"MedGemma: Support devices present ({', '.join(medgemma_devices)})")

    # ── CheXpert structured labels (supporting evidence) ──
    opacity_labels = ["Lung Opacity", "Edema", "Consolidation"]
    exclusion_labels = ["Pleural Effusion", "Atelectasis"]

    for label in opacity_labels:
        if chexpert.get(label, False):
            evidence_for.append(f"CheXpert: {label} positive")

    for label in exclusion_labels:
        if chexpert.get(label, False):
            evidence_against.append(f"CheXpert: {label} positive (may explain opacities)")

    if chexpert.get("Cardiomegaly", False):
        evidence_against.append("CheXpert: Cardiomegaly positive")

    # ── Radiology report keywords (supplementary) ──
    if report_findings:
        report_lower = report_findings.lower()
        bilateral_keywords = [
            "bilateral opacities", "bilateral infiltrates", "bilateral",
            "diffuse opacities", "diffuse infiltrates", "both lungs",
            "ground glass", "bilateral consolidation",
        ]
        for kw in bilateral_keywords:
            if kw in report_lower:
                evidence_for.append(f"Radiology report: '{kw}' mentioned")
                break  # one keyword match is sufficient

    # ── Determine status (MedGemma takes priority) ──
    has_any_imaging = bool(chexpert) or bool(report_findings) or has_bilateral is not None or medgemma_available

    if not has_any_imaging:
        return {
            "criterion": "Chest Imaging",
            "status": "INDETERMINATE",
            "reason": "No chest imaging data available (no CXR, no CheXpert labels, no radiology report)",
            "evidence_for": [],
            "evidence_against": [],
            "medgemma_assessment": medgemma_raw,
            "local_paths": local_paths,
        }

    # MedGemma verdict overrides other evidence
    if medgemma_available:
        if medgemma_bilateral is True and medgemma_explained is not True:
            status = "MET"
            reason = "MedGemma confirms bilateral opacities not explained by effusions/collapse"
        elif medgemma_bilateral is True and medgemma_explained is True:
            status = "NOT_MET"
            reason = "MedGemma: bilateral opacities present but explained by effusions/collapse"
        elif medgemma_bilateral is False:
            # MedGemma says no opacities — but check if CheXpert strongly disagrees
            chexpert_opacity_count = sum(1 for l in opacity_labels if chexpert.get(l, False))
            if chexpert_opacity_count >= 2:
                status = "INDETERMINATE"
                reason = ("MedGemma found no bilateral opacities but CheXpert labels "
                          "indicate opacity/edema/consolidation — conflicting evidence")
            else:
                status = "NOT_MET"
                reason = "MedGemma: no bilateral opacities detected on CXR"
        else:
            status = "INDETERMINATE"
            reason = "MedGemma assessment inconclusive"
    else:
        # No MedGemma — fall back to CheXpert + radiology
        if has_bilateral is True or len(evidence_for) >= 2:
            status = "MET"
            reason = "Bilateral opacities identified (without MedGemma visual confirmation): " + "; ".join(evidence_for)
        elif has_bilateral is False and not evidence_for:
            status = "NOT_MET"
            reason = "No bilateral opacities identified (no MedGemma confirmation available)"
        else:
            status = "INDETERMINATE"
            reason = "Imaging evidence equivocal without MedGemma visual confirmation"

    return {
        "criterion": "Chest Imaging",
        "status": status,
        "reason": reason,
        "evidence_for": evidence_for,
        "evidence_against": evidence_against,
        "medgemma_assessment": medgemma_raw,
        "local_paths": local_paths,
    }


# ── Overall Classification ───────────────────────────────────────────────────

def _classify_overall(criteria: List[Dict[str, Any]], oxygenation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Determine overall Berlin ARDS classification from individual criteria."""
    statuses = [c["status"] for c in criteria]

    all_met = all(s == "MET" for s in statuses)
    any_not_met = any(s == "NOT_MET" for s in statuses)
    any_indeterminate = any(s == "INDETERMINATE" for s in statuses)

    severity = oxygenation_result.get("severity")

    if all_met and severity:
        return {
            "classification": f"ARDS - {severity}",
            "ards_present": True,
            "severity": severity,
            "confidence": "HIGH",
            "summary": f"All 4 Berlin criteria met. PaO2/FiO2 = {oxygenation_result.get('pf_ratio')} => {severity} ARDS",
        }
    elif any_not_met:
        not_met = [c["criterion"] for c in criteria if c["status"] == "NOT_MET"]
        return {
            "classification": "NOT ARDS",
            "ards_present": False,
            "severity": None,
            "confidence": "HIGH" if not any_indeterminate else "MODERATE",
            "summary": f"Berlin criteria NOT met. Failed: {', '.join(not_met)}",
        }
    else:
        indeterminate = [c["criterion"] for c in criteria if c["status"] == "INDETERMINATE"]
        met = [c["criterion"] for c in criteria if c["status"] == "MET"]
        return {
            "classification": "INDETERMINATE",
            "ards_present": None,
            "severity": severity,
            "confidence": "LOW",
            "summary": (
                f"Cannot determine — insufficient data for: {', '.join(indeterminate)}. "
                f"Met: {', '.join(met) if met else 'none'}"
            ),
        }


# ── Tool Entrypoints ─────────────────────────────────────────────────────────

def classify_berlin_ards(patient_data_json: str) -> str:
    """
    Apply Berlin ARDS Definition criteria to structured patient data.

    Accepts a JSON string with patient_id, timing, oxygenation, cardiac, and imaging data
    (including medgemma_findings). Returns a JSON classification result.
    """
    try:
        data = json.loads(patient_data_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON input: {str(e)}"})

    patient_id = data.get("patient_id", "unknown")

    # Evaluate each criterion
    timing_result = _evaluate_timing(data.get("timing", {}))
    oxygenation_result = _evaluate_oxygenation(data.get("oxygenation", {}))

    # Cardiac evaluation: merge medgemma cardiomegaly into cardiac data
    cardiac_data = data.get("cardiac", {})
    imaging_data = data.get("imaging", {})
    medgemma = imaging_data.get("medgemma_findings", {}) or {}
    if "medgemma_cardiomegaly_detected" not in cardiac_data and medgemma.get("cardiomegaly_detected") is not None:
        cardiac_data["medgemma_cardiomegaly_detected"] = medgemma["cardiomegaly_detected"]
    cardiac_result = _evaluate_cardiac(cardiac_data)

    imaging_result = _evaluate_imaging(imaging_data)

    criteria = [timing_result, oxygenation_result, cardiac_result, imaging_result]
    overall = _classify_overall(criteria, oxygenation_result)

    result = {
        "patient_id": patient_id,
        "classification": overall["classification"],
        "ards_present": overall["ards_present"],
        "severity": overall["severity"],
        "confidence": overall["confidence"],
        "summary": overall["summary"],
        "criteria": {
            "timing": timing_result,
            "oxygenation": oxygenation_result,
            "cardiac_exclusion": cardiac_result,
            "chest_imaging": imaging_result,
        },
    }

    return json.dumps(result, indent=2, default=str)


def classify_berlin_ards_batch(patient_ids_json: str) -> str:
    """
    Initialize batch ARDS classification. Accepts a JSON array of patient IDs.
    Returns an iteration framework for the orchestrator.
    """
    try:
        patient_ids = json.loads(patient_ids_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {str(e)}"})

    if not isinstance(patient_ids, list):
        return json.dumps({"error": "Expected a JSON array of patient IDs"})

    return json.dumps({
        "batch_mode": True,
        "total_patients": len(patient_ids),
        "patient_ids": patient_ids,
        "instructions": (
            "For each patient_id, gather data using the 4 database queries "
            "(timing, oxygenation, cardiac, imaging) then run MedGemma on the CXR, "
            "then call classify_berlin_ards with the structured data. "
            "Compile results into a summary table."
        ),
    })


# ── Function Tool Builders ────────────────────────────────────────────────────

def make_classify_berlin_ards_tool() -> Function:
    """Build the classify_berlin_ards Function tool for the ARDS team."""
    return Function(
        name="classify_berlin_ards",
        description=(
            "Apply Berlin ARDS Definition criteria to structured patient data. "
            "Pass a JSON string with patient_id, timing, oxygenation, cardiac, and "
            "imaging data (including medgemma_findings from the imaging agent). "
            "Returns deterministic classification: ARDS severity, NOT ARDS, or INDETERMINATE. "
            "Use AFTER gathering all data from database agent AND MedGemma imaging agent."
        ),
        parameters={
            "type": "object",
            "properties": {
                "patient_data_json": {
                    "type": "string",
                    "description": (
                        "JSON string with keys: patient_id (str), "
                        "timing {clinical_insult_date, respiratory_onset_date}, "
                        "oxygenation {pao2, fio2, peep, spo2}, "
                        "cardiac {bnp_value, bnp_type, lvef, heart_failure_diagnosed, "
                        "fluid_overload_diagnosed, cardiomegaly_on_imaging}, "
                        "imaging {has_bilateral_opacities, chexpert_labels, "
                        "radiology_report_findings, local_paths, "
                        "medgemma_findings: {bilateral_opacities_present, "
                        "opacities_explained_by_effusion_or_collapse, "
                        "cardiomegaly_detected, support_devices, raw_assessment}}"
                    ),
                },
            },
            "required": ["patient_data_json"],
        },
        entrypoint=classify_berlin_ards,
    )


def make_classify_berlin_ards_batch_tool() -> Function:
    """Build the batch classification Function tool for the ARDS team."""
    return Function(
        name="classify_berlin_ards_batch",
        description=(
            "Initialize batch ARDS classification for multiple patients. "
            "Pass a JSON array of patient_id strings. Returns instructions for "
            "iterating over patients and calling classify_berlin_ards for each."
        ),
        parameters={
            "type": "object",
            "properties": {
                "patient_ids_json": {
                    "type": "string",
                    "description": "JSON array of patient ID strings, e.g. '[\"12345\", \"67890\"]'",
                },
            },
            "required": ["patient_ids_json"],
        },
        entrypoint=classify_berlin_ards_batch,
    )
