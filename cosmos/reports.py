"""
Report generation for COSMOS TEST SUITE.

Generates auto-generated reports for experiments and questions following the
structure in Section 28 of the spec:

- Executive Summary
- Scientific Question
- Hypotheses
- Data
- Method
- Results
- Statistical Significance
- Systematics
- Robustness
- Replication
- Interpretation
- Limitations
- References
- Reproducibility

Four report levels are supported (Section 57 of spec):
- Level 1: plain English
- Level 2: technical
- Level 3: mathematical
- Level 4: research

Reports are written to reports/EXP###/report.md and logged to the database.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import click

from .database import ExperimentRepository, ResultRepository, get_session
from .database.models import Experiment, Result
from .registry import get_registry


def format_level(text: Optional[str], level: int = 2) -> str:
    """Return the text for the given report level, or a placeholder."""
    if text:
        return text
    return "[not yet written at this level]"


def build_experiment_report(exp_id: str, level: int = 2) -> Dict[str, str]:
    """
    Build a structured report for an experiment.

    Returns a dict with report sections at four levels.
    """
    reg = get_registry()
    exp = reg.get(exp_id)
    if not exp:
        raise ValueError(f"Experiment {exp_id} not found")

    definition = exp.get("definition", {}) or {}

    sections = {}
    sections["title"] = f"COSMOS Experiment Report: {exp_id} — {exp['name']}"
    sections["scientific_question"] = (
        definition.get("hypothesis") or "[hypothesis not yet defined]"
    )
    sections["hypotheses"] = format_level(definition.get("hypothesis"), level)
    sections["data"] = "\n".join(
        f"- {ds}" for ds in (definition.get("datasets") or [])
    ) or "- [no datasets registered]"
    sections["method"] = format_level(definition.get("statistical_test"), level)
    sections["limitations"] = "\n".join(
        f"- {s}" for s in definition.get("systematic_errors") or []
    ) or "- [none recorded]"
    sections["references"] = (
        "Refer to the local research corpus (cosmos papers search)."
    )
    sections["reproducibility"] = (
        f"Seed: {exp.get('definition', {}).get('reproducibility', {}).get('random_seed', 42)}\n"
        f"Software: COSMOS {exp.get('definition', {}).get('reproducibility', {}).get('software_version', '0.1.0')}\n"
        "Data version: see cosmos data list"
    )
    return sections


def generate_experiment_report(
    exp_id: str,
    level: int = 2,
    output_dir: Optional[Path | str] = None,
    overwrite: bool = False,
    result: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Generate a full Markdown report for an experiment.

    Writes to <output_dir>/report_<exp_id>.md. When a `result` payload from a
    completed run is supplied, the report is populated with the measured
    numbers, the classification, the systematics assessment, and the
    adversarial findings. Without it the report is rendered as a pre-registered
    analysis plan, which is still useful but must not be mistaken for a result.
    """
    out_dir = Path(output_dir) if output_dir else Path("reports") / exp_id
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"report_{exp_id}.md"

    if report_path.exists() and not overwrite:
        click.echo(f"Report already exists: {report_path}")
        return report_path

    # Read/write UTF-8 explicitly: the Windows default codec (cp1252) cannot
    # encode the scientific symbols used in the report body.
    out_dir.mkdir(parents=True, exist_ok=True)

    reg = get_registry()
    experiment = reg.get(exp_id)
    if not experiment:
        raise ValueError(f"Experiment {exp_id} not found")

    definition = experiment.get("definition", {}) or {}
    result = result or {}
    analysis = result.get("analysis", {}) or {}
    mc = analysis.get("monte_carlo", {}) or {}
    chi2 = analysis.get("chi2_test", {}) or {}
    injection = analysis.get("injection_recovery", {}) or {}
    systematics = result.get("systematics", {}) or {}
    adversarial = result.get("adversarial", {}) or {}
    plan = result.get("analysis_plan", {}) or {}

    has_run = bool(result.get("classification"))

    lines = [
        f"# COSMOS TEST SUITE — Experiment {exp_id}",
        "",
        f"## {experiment['name']}",
        "",
        f"**Status:** {experiment.get('status', 'unknown')}",
        f"**Priority score:** {reg.score(exp_id):.2f}",
        f"**Report generated:** {datetime.datetime.utcnow().isoformat()}",
        f"**Report level:** {level} ({level_text(level)})",
        "",
        "## 1. Executive Summary",
        "",
    ]

    if has_run:
        lines += [
            f"**Outcome: {result['classification']}**",
            "",
            result.get("summary", ""),
            "",
        ]
    else:
        lines += [
            "This report is a **pre-registered analysis plan**. The experiment "
            "has not been run, so it contains no measurements and no verdict.",
            "",
            f"Run it with: `cosmos experiment run {exp_id}`",
            "",
        ]

    lines += [
        "## 2. Scientific Question",
        "",
        f"{definition.get('hypothesis') or '[hypothesis not yet defined]'}",
        "",
        "## 3. Hypotheses",
        "",
        f"**Hypothesis:** {definition.get('hypothesis') or '[none]'}",
        "",
        f"**Null / baseline model:** {definition.get('null_model') or '[none]'}",
        "",
        "#### Alternative models",
        "",
    ]

    for alt in definition.get("alternative_models") or []:
        lines.append(f"- {alt}")
    lines += ["", "**Falsification condition:**"]
    lines.append(
        "  "
        + (definition.get("falsification_condition") or "not defined")
    )

    lines += ["", "## 4. Data", "", "### Datasets used in this run"]
    if has_run and analysis.get("data_origin"):
        lines.append(f"- {analysis['data_origin']}")
    else:
        lines += ["- not yet run"]
    lines += ["", "### Datasets registered for this experiment"]
    for ds in definition.get("datasets") or []:
        lines.append(f"- {ds}")
    lines += ["", "### Preprocessing"]
    for pre in definition.get("preprocessing") or []:
        lines.append(f"- {pre}")

    lines += ["", "## 5. Method", ""]
    if plan.get("analysis_steps"):
        lines.append("The following steps were registered **before** the data were examined:")
        lines.append("")
        for i, step in enumerate(plan["analysis_steps"], 1):
            lines.append(f"{i}. {step}")
    else:
        lines.append(definition.get("statistical_test") or "[not yet defined]")

    lines += ["", "## 6. Results", ""]
    if has_run:
        lines += [
            f"**Classification:** `{result['classification']}`",
            "",
        ]
        if result.get("rationale"):
            lines += [result["rationale"], ""]
        if chi2:
            lines += [
                f"- chi-square = {chi2.get('chi2', float('nan')):.1f} "
                f"on {chi2.get('dof', '?')} degrees of freedom "
                f"(reduced chi-square {chi2.get('reduced_chi2', float('nan')):.2f})",
            ]
        if mc:
            lines += [
                f"- Monte Carlo null: {mc.get('n_mc', '?')} synthetic Lambda CDM "
                f"realisations, p = {mc.get('p_value', float('nan')):.3g}",
                f"- Equivalent significance: {mc.get('significance_sigma', 0):.2f} sigma",
            ]
        if analysis.get("n_k_bins"):
            lines.append(f"- Wavenumber bins compared: {analysis['n_k_bins']}")
    else:
        lines.append("Not yet computed — run the experiment.")

    lines += ["", "## 7. Statistical Significance", ""]
    if has_run:
        p = result.get("p_value")
        sig = result.get("significance_sigma")
        lines += [
            f"- p-value: {p:.4g}" if p is not None else "- p-value: unavailable",
            f"- Significance: {sig:.2f} sigma" if sig is not None else "- Significance: unavailable",
            "- Discovery threshold: 5 sigma (not reached)" if (sig or 0) < 5 else "- Discovery threshold: 5 sigma (reached)",
            "",
            "The p-value is calibrated by Monte Carlo over synthetic Lambda CDM "
            "realisations, so it accounts for the correlated, non-Gaussian "
            "structure of a P(k) estimate rather than assuming independent "
            "Gaussian bins.",
        ]
    else:
        lines += ["Not yet computed.", "", "Discovery threshold: 5 sigma."]

    lines += ["", "## 8. Systematics", ""]
    sys_entries = systematics.get("systematics") or {}
    if sys_entries:
        lines += ["| Systematic | Quantified | Impact |", "|---|---|---|"]
        for name, entry in sys_entries.items():
            quant = (
                "yes" if isinstance(entry, dict) and entry.get("quantified") else "**no**"
            )
            impact = entry.get("impact", "") if isinstance(entry, dict) else ""
            lines.append(f"| {name.replace('_', ' ')} | {quant} | {impact} |")
        lines.append("")
        if systematics.get("notes"):
            lines.append(systematics["notes"])
    else:
        for s in definition.get("systematic_errors") or []:
            lines.append(f"- {s}")

    lines += ["", "## 9. Adversarial Review ('try to kill it')", ""]
    questions = adversarial.get("adversarial_questions") or []
    if questions:
        lines += ["| Question | Finding | Verdict |", "|---|---|---|"]
        for q in questions:
            lines.append(
                f"| {q.get('question', '')} | {q.get('finding', '')} | {q.get('verdict', '')} |"
            )
        lines.append("")
        lines.append(
            f"**Survived adversarial review:** {adversarial.get('survived')}"
        )
    else:
        lines.append("Not yet performed — run the experiment.")

    lines += [
        "",
        "## 10. Injection and Recovery",
        "",
    ]
    if injection:
        lines += [
            f"- Feature: {injection.get('feature', 'n/a')}",
            f"- Injected amplitude: {injection.get('injected_amplitude', float('nan')):.3f}",
            f"- Signal-to-noise: {injection.get('injected_snr', float('nan')):.2f}",
            f"- Detected: **{injection.get('detected')}**",
            f"- False-positive rate: {injection.get('false_positive_rate', float('nan'))}",
            "",
            injection.get("conclusion", ""),
        ]
    else:
        lines.append("Not yet performed.")

    lines += [
        "",
        "## 11. Replication",
        "",
        "This experiment is reproducible from a clean environment using:",
        "",
        "```",
        f"cosmos reproduce {exp_id}",
        "```",
        "",
        "## 12. Interpretation",
        "",
    ]
    if has_run:
        lines.append(result.get("rationale", "[no interpretation recorded]"))
    else:
        lines.append("[pending analysis]")

    lines += ["", "## 13. Limitations and what cannot be concluded", ""]
    caveats = result.get("caveats") or []
    for c in caveats:
        lines.append(f"- {c}")
    if not caveats:
        for u in definition.get("uncertainty") or []:
            lines.append(f"- {u}")
    if result.get("unresolved_questions"):
        lines += ["", "**Open questions left by this run:**", ""]
        for q in result["unresolved_questions"]:
            lines.append(f"- {q}")

    lines += [
        "",
        "## 14. References",
        "",
        "Search the local corpus: `cosmos papers search <topic>`.",
        "",
        "## 15. Provenance",
        "",
    ]
    provenance = result.get("provenance") or []
    if provenance:
        lines += ["| Stage | Identifier | Description |", "|---|---|---|"]
        for link in provenance:
            lines.append(
                f"| {link.get('node_type', '')} | `{link.get('node_id', '')}` | "
                f"{link.get('description', '')} |"
            )
    else:
        lines.append("No provenance recorded yet.")

    lines += [
        "",
        "## 16. Reproducibility",
        "",
        f"- Random seed: {plan.get('random_seed', definition.get('reproducibility', {}).get('random_seed', 42))}",
        f"- Software version: {(plan.get('commit', 'unknown') and 'commit ' + str(plan.get('commit'))) or 'commit unknown'}",
        "- Analysis version: v1",
        f"- Analysis plan registered: {plan.get('timestamp', 'not recorded')}",
        "- Datasets: see `cosmos data list`",
        f"- Reproducibility package: `experiments/{exp_id}/reproducibility/`",
        "",
        "---",
        f"*Generated by COSMOS TEST SUITE {get_report_footer()}.*",
    ]

    content = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)

    click.echo(f"Report written to {report_path}")
    return report_path


def level_text(level: int) -> str:
    texts = {1: "plain English", 2: "technical", 3: "mathematical", 4: "research"}
    return texts.get(level, "technical")


def get_report_footer() -> str:
    return "0.1.0"


def record_result_to_db(
    exp_id: str,
    classification: str,
    significance_sigma: Optional[float] = None,
    p_value: Optional[float] = None,
    result_summary: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> None:
    """
    Record an experiment result in the database (Section 35/51 of spec).
    """
    with get_session() as session:
        exp_repo = ExperimentRepository(session, Experiment)
        result_repo = ResultRepository(session, Result)
        exp_db = exp_repo.find_by_exp_id(exp_id)
        if exp_db is None:
            raise ValueError(f"Experiment {exp_id} not found in database")

        now = datetime.datetime.utcnow()
        run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}"

        result_repo.record_result(
            exp_id=exp_db.id,
            run_id=run_id,
            classification=classification,
            significance_sigma=significance_sigma,
            p_value=p_value,
            result_summary=result_summary,
            output_dir=output_dir,
        )

        if classification not in ("not_testable", "insufficient_data"):
            exp_db.status = "completed"
        exp_db.result_classification = classification
        exp_db.result_summary = result_summary
        exp_db.significance_sigma = significance_sigma
        exp_db.p_value = p_value
        exp_db.end_date = now
        click.echo(f"Result recorded: {exp_id} -> {classification}")


def print_result_table(exp_id: Optional[str] = None) -> None:
    """Print a table of experiment results from the database."""
    with get_session() as session:
        result_repo = ResultRepository(session, Result)
        results = result_repo.list_all(limit=100) if not exp_id else result_repo.list_for_experiment(exp_id)
        click.echo(f"{'exp_id':<10} {'run_id':<18} {'classification':<34} {'sigma'}")
        click.echo("-" * 75)
        for r in results:
            exp = r.experiment
            exp_id_disp = exp.exp_id if exp else "n/a"
            sigma = f"{r.significance_sigma:.2f} sigma" if r.significance_sigma else "-"
            click.echo(f"{exp_id_disp:<10} {r.run_id:<18} {r.classification:<34} {sigma}")
