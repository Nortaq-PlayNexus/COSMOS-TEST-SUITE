"""
Command-line interface for COSMOS TEST SUITE.

Subcommands:
- research search    : search the local scientific corpus
- papers search      : search indexed papers
- data list          : list registered datasets
- data download      : download a dataset
- experiment list    : list experiments
- experiment status  : show status of an experiment
- experiment run     : run an experiment
- experiment delete  : delete an experiment
- simulate           : run a simulation
- analyze            : run an analysis on a dataset
- compare-models     : compare cosmological models
- report             : generate a report for an experiment
- reproduce          : reproduce an experiment from its environment lock
- verify             : verify the reproducibility of an experiment
- replicate          : replicate a published paper
- config             : show/edit configuration
- version            : show version
"""

from __future__ import annotations

import sys
import click

from .. import __version__
from ..config import settings
from ..registry import get_registry
from ..data import get_data_manager, DownloadError

# Experiment implementations that can actually be executed.
# Keys are the public experiment identifiers; values are (runner factory,
# analysis-steps accessor).
IMPLEMENTED_EXPERIMENTS = {
    "EXP-001": "cosmos.experiments:EXP001Experiment",
}


def get_runner(exp_id, seed=42):
    """
    Build a runnable ExperimentRunner for exp_id, or None if not implemented.

    Imports are deferred so that a partially-built module surface does not
    break the whole CLI.
    """
    spec = IMPLEMENTED_EXPERIMENTS.get(exp_id)
    if spec is None:
        return None
    module_name, class_name = spec.split(":")
    try:
        module = __import__(module_name, fromlist=[class_name])
        return getattr(module, class_name)(seed=seed)
    except Exception as exc:  # pragma: no cover - defensive
        click.echo(f"Could not load runner for {exp_id}: {exc}", err=True)
        return None


def get_runner_steps(exp_id):
    """Return the pre-registered analysis steps for a runnable experiment."""
    reg = get_registry()
    exp = reg.get(exp_id)
    if exp is None:
        return None
    runner = get_runner(exp_id)
    if runner is not None:
        return runner._analysis_steps()
    definition = exp.get("definition") or {}
    steps = definition.get("statistical_test")
    return [steps] if steps else None


# ---------------------------------------------------------------------------
# Core group
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--database", "-d", default=None, help="Database URL (default: sqlite:///cosmos.db)")
@click.option("--offline", is_flag=True, help="Offline mode: no data downloads")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def main(ctx, database, offline, verbose):
    """COSMOS TEST SUITE - An Independent Computational Observatory."""
    ctx.ensure_object(dict)
    if database:
        settings.database_url = database
    if offline:
        settings.allow_data_download = False
        get_data_manager().set_offline_mode(True)
    ctx.obj["verbose"] = verbose

    if ctx.invoked_subcommand is None:
        click.echo(click.style("COSMOS TEST SUITE", bold=True))
        click.echo(f"Version {__version__}")
        click.echo("Type 'cosmos <command> --help' for help on a subcommand.")
        click.echo("")
        click.echo("Core principle: DO NOT TRY TO PROVE A THEORY.")
        click.echo("Try to find out whether the DATA CAN DISPROVE IT.")


@main.command()
def version():
    """Show the COSMOS version."""
    click.echo(f"COSMOS TEST SUITE {__version__}")


# ---------------------------------------------------------------------------
# Research search (Section 6)
# ---------------------------------------------------------------------------


@main.group(name="research")
def research_group():
    """Search the research corpus."""


@research_group.command()
@click.argument("query")
@click.option("--limit", "-n", default=20, help="Maximum results")
def search(query, limit):
    """Search the local scientific corpus."""
    click.echo(f"Searching corpus for: {query!r} (limit={limit})")
    click.echo("")
    click.echo("Indexed searches: cosmic topology, dark energy, Hubble tension,")
    click.echo("modified gravity, cosmic web, primordial gravitational waves,")
    click.echo("bubble collision, large scale isotropy, etc.")
    click.echo("")
    click.echo("The corpus is built automatically as papers are downloaded/ingested.")


# ---------------------------------------------------------------------------
# Papers
# ---------------------------------------------------------------------------


@main.group(name="papers")
def papers_group():
    """Manage scientific papers."""


@papers_group.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=20, help="Maximum results")
def papers_search(query, limit):
    """Search indexed papers."""
    click.echo(f"Papers search: {query!r} (limit={limit})")
    click.echo("")
    click.echo("Indexed searches: dark energy evolving DESI, Hubble tension")
    click.echo("distance ladder, modified gravity weak lensing, cosmic web")
    click.echo("Lambda CDM simulations, primordial gravitational waves,")
    click.echo("bubble collision CMB, large scale isotropy, etc.")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@main.group(name="data")
def data_group():
    """Manage datasets."""


@data_group.command()
@click.option("--type", "-t", default=None, help="Filter by data type")
@click.option("--status", "-s", default=None, help="Filter by availability")
def list(type, status):
    """List registered datasets: cosmos data list."""
    dm = get_data_manager()
    records = dm.list_datasets(data_type=type, availability=status)
    click.echo(f"{'name':<30} {'origin':<14} {'type':<16} {'avail':<11} size")
    click.echo("-" * 80)
    for r in records:
        size = f"{r.size_gb:.1f} GB" if r.size_gb else "-"
        click.echo(f"{r.name:<30} {r.origin:<14} {r.data_type:<16} {r.availability:<11} {size}")


@data_group.command()
@click.argument("name")
@click.option("--url", "-u", default=None, help="Override download URL")
def download(name, url):
    """Download a dataset: cosmos data download <name>."""
    dm = get_data_manager()
    try:
        rec = dm.download_dataset(name, url=url)
        click.echo(f"Downloaded {rec.name} v{rec.version} from {rec.origin}")
        click.echo(f"  local path: {rec.local_path}")
    except DownloadError as e:
        click.echo(f"Download error: {e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Experiment registry
# ---------------------------------------------------------------------------


@main.group(name="experiment")
def experiment_group():
    """Manage experiments (EXP-001 ... EXP-016)."""


@experiment_group.command()
@click.option("--status", "-s", default=None, help="Filter by status")
def list(status):
    """List experiments: cosmos experiment list."""
    reg = get_registry()
    click.echo(f"{'exp_id':<10} {'name':<45} {'status':<16} {'score'}")
    click.echo("-" * 80)
    for exp_id, exp in sorted(reg.experiments.items(), key=lambda x: x[1]["order"]):
        if status and exp["status"] != status:
            continue
        click.echo(f"{exp_id:<10} {exp['name'][:44]:<45} {exp['status']:<16} {reg.score(exp_id):.2f}")
    next_line = reg.next_in_line()
    if next_line:
        click.echo("")
        click.echo(click.style(f"NEXT IN LINE: {next_line} - {reg.experiments[next_line]['name']}", bold=True))


@experiment_group.command()
@click.argument("exp_id")
def status(exp_id):
    """Show status of an experiment: cosmos experiment status EXP-001."""
    reg = get_registry()
    exp = reg.get(exp_id)
    if exp is None:
        click.echo(f"Experiment {exp_id} not found.", err=True)
        sys.exit(1)
    definition = exp.get("definition", {}) or {}
    click.echo(f"{exp_id}: {exp['name']}")
    click.echo(f"  status: {exp['status']}")
    click.echo(f"  score: {reg.score(exp_id):.2f}")
    click.echo(f"  started: {exp.get('started_at')}")
    click.echo(f"  completed: {exp.get('completed_at')}")
    click.echo("")
    click.echo("  hypothesis:")
    click.echo("    " + (definition.get("hypothesis") or "none"))
    click.echo("  falsification condition:")
    click.echo("    " + (definition.get("falsification_condition") or "none"))
    datasets = definition.get("datasets") or []
    if datasets:
        click.echo("  datasets:")
        for ds in datasets:
            click.echo(f"    - {ds}")


@experiment_group.command("run")
@click.argument("exp_id")
@click.option("--dry-run", is_flag=True, help="Describe the run without executing")
@click.option("--seed", default=42, show_default=True, help="Random seed for the run")
def run(exp_id, dry_run, seed):
    """
    Run an experiment: cosmos experiment run EXP-001.

    Executes the full pipeline: ingest data, pre-register the analysis plan,
    compute the LambdaCDM prediction, simulate the null distribution, run the
    statistical test, attempt to falsify the result, classify it, write the
    report, and record everything in the database.
    """
    reg = get_registry()
    exp = reg.get(exp_id)
    if exp is None:
        click.echo(f"Experiment {exp_id} not found.", err=True)
        sys.exit(1)

    definition = exp.get("definition") or {}
    datasets = definition.get("datasets") or []
    click.echo(click.style(f"Running {exp_id}: {exp['name']}", bold=True))
    click.echo(f"  seed: {seed}")
    click.echo(f"  datasets: {', '.join(datasets) if datasets else 'curated sample data'}")

    if dry_run:
        steps = get_runner_steps(exp_id)
        if steps is not None:
            click.echo("")
            click.echo("  Planned pipeline:")
            for i, s in enumerate(steps, 1):
                click.echo(f"    {i}. {s}")
        click.echo("")
        click.echo("  [DRY RUN] Nothing was executed.")
        return

    runner = get_runner(exp_id, seed=seed)
    if runner is None:
        click.echo(f"No runnable implementation for {exp_id} yet.", err=True)
        click.echo(
            "Implemented so far: EXP-001. "
            "Remaining experiments are defined in the registry but not yet built.",
            err=True,
        )
        sys.exit(2)

    click.echo("")
    result = runner.run()

    click.echo("")
    click.echo(click.style("RESULT", bold=True))
    click.echo(f"  classification : {result['classification']}")
    if result.get("significance_sigma") is not None:
        click.echo(f"  significance   : {result['significance_sigma']:.2f} sigma")
    click.echo(f"  summary        : {result['summary']}")
    click.echo("")
    click.echo(f"Report: see experiments/{exp_id}/report/")


@experiment_group.command("delete")
@click.argument("exp_id")
def delete(exp_id):
    """Delete an experiment from the registry."""
    reg = get_registry()
    if exp_id not in reg.experiments:
        click.echo(f"Experiment {exp_id} not found.", err=True)
        sys.exit(1)
    reg.experiments.pop(exp_id)
    click.echo(f"Deleted {exp_id}.")


# ---------------------------------------------------------------------------
# Simulate
# ---------------------------------------------------------------------------


@main.group(name="simulate")
def simulate_group():
    """Run simulations."""


@simulate_group.command("lcdm")
@click.option("--nside", default=32, help="Grid resolution (Nyquist)")
@click.option("--seed", default=42, help="Random seed")
def simulate_lcdm(nside, seed):
    """Run a Lambda CDM Gaussian random field simulation."""
    from ..simulations import create_simulation
    sim = create_simulation("EXP-001-lcdm-sim", "lcdm", {"nside": nside, "seed": seed})
    out = sim.run()
    click.echo(f"Simulation {sim.name} complete")
    click.echo(f"  hash: {sim.reproducibility_hash()}")
    click.echo(f"  field stats: mean={out['density'].mean():.4f}, std={out['density'].std():.4f}")


@simulate_group.command("topology")
@click.option("--L", default=500.0, help="Topology side length (Mpc/h)")
@click.option("--seed", default=42, help="Random seed")
def simulate_topology(L, seed):
    """Run a finite-topology (3-torus) simulation."""
    from ..simulations import create_simulation
    sim = create_simulation("EXP-012-topology-sim", "topology", {"L": L, "seed": seed})
    sim.run()
    click.echo(f"Simulation {sim.name} complete")
    click.echo(f"  hash: {sim.reproducibility_hash()}")


@simulate_group.command("bubble-collision")
@click.option("--resolution", default=64, help="Map resolution")
@click.option("--r0", default=0.15, help="Circle radius (radians)")
def simulate_bubble_collision(resolution, r0):
    """Run a bubble-collision injection/recovery simulation (EXP-011)."""
    from ..simulations import create_simulation
    sim = create_simulation("EXP-011-bubble-sim", "bubble_collision", {"resolution": resolution, "r0": r0})
    out = sim.run()
    rec = out["recovery"]
    click.echo(f"Simulation {sim.name} complete")
    click.echo(f"  hash: {sim.reproducibility_hash()}")
    click.echo(f"  recovery fraction: {rec['recovery_fraction']:.2f} ({rec['recovered']}/{rec['n_injections']})")


@simulate_group.command("mock-galaxy")
@click.option("--n-galaxies", default=1000, help="Number of galaxies")
@click.option("--z-max", default=1.0, help="Maximum redshift")
def simulate_mock_galaxy(n_galaxies, z_max):
    """Run a mock galaxy catalog simulation."""
    from ..simulations import create_simulation
    sim = create_simulation("EXP-003-mock-galaxy-sim", "mock_galaxy", {"n_galaxies": n_galaxies, "z_max": z_max})
    out = sim.run()
    click.echo(f"Simulation {sim.name} complete")
    click.echo(f"  hash: {sim.reproducibility_hash()}")
    click.echo(f"  galaxies: {out['n_galaxies']}")


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------


@main.group(name="analyze")
def analyze_group():
    """Run analyses on datasets."""


@analyze_group.command("cmb")
@click.option("--data", default="sample_cmb_map", help="Dataset to analyze")
def analyze_cmb(data):
    """Analyze a CMB map: cosmos analyze cmb."""
    dm = get_data_manager()
    rec = dm.get_dataset(data)
    if rec is None:
        click.echo(f"Dataset {data} not found.", err=True)
        sys.exit(1)
    click.echo(f"Analyzing {data} (from {rec.origin})")
    click.echo("  CMB analysis: power spectrum, monopole/quadrupole, anomaly search")
    click.echo("  (CMB analysis pipeline not yet implemented)")


@analyze_group.command("galaxy-catalog")
@click.option("--data", default="sample_galaxy_catalog", help="Dataset to analyze")
def analyze_galaxy_catalog(data):
    """Analyze a galaxy catalog: cosmos analyze galaxy-catalog."""
    dm = get_data_manager()
    rec = dm.get_dataset(data)
    if rec is None:
        click.echo(f"Dataset {data} not found.", err=True)
        sys.exit(1)
    click.echo(f"Analyzing {data} (from {rec.origin})")
    click.echo("  Galaxy analysis: two-point correlation, power spectrum, homogeneity scale")
    click.echo("  (galaxy analysis pipeline not yet implemented)")


@analyze_group.command("rotation-curve")
@click.option("--data", default="sample_rotation_curves", help="Dataset to analyze")
def analyze_rotation_curve(data):
    """Analyze rotation curve data (dark matter test)."""
    dm = get_data_manager()
    rec = dm.get_dataset(data)
    if rec is None:
        click.echo(f"Dataset {data} not found.", err=True)
        sys.exit(1)
    click.echo(f"Analyzing {data} (from {rec.origin})")
    click.echo("  Rotation curve analysis: circular velocity model fitting")
    click.echo("  (rotation curve analysis pipeline not yet implemented)")


# ---------------------------------------------------------------------------
# Compare models
# ---------------------------------------------------------------------------


@main.command("compare-models")
@click.option("--data", default="sample_rotation_curves", help="Dataset for model comparison")
def compare_models(data):
    """Compare competing models: cosmos compare-models."""
    dm = get_data_manager()
    rec = dm.get_dataset(data)
    if rec is None:
        click.echo(f"Dataset {data} not found.", err=True)
        sys.exit(1)
    click.echo(f"Comparing models on {data}...")
    click.echo("  Models: Lambda CDM, MOND-like, constant-w dark energy")
    click.echo("  (model comparison pipeline not yet implemented)")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@main.group(name="report")
def report_group():
    """Generate reports."""


@report_group.command("generate")
@click.argument("exp_id")
@click.option("--format", "-f", default="markdown", type=click.Choice(["markdown", "json"]))
@click.option("--output", "-o", default=None, help="Output path")
def generate_report(exp_id, format, output):
    """Generate a report for an experiment: cosmos report EXP-001."""
    reg = get_registry()
    if exp_id not in reg.experiments:
        click.echo(f"Experiment {exp_id} not found.", err=True)
        sys.exit(1)
    click.echo(f"Report for {exp_id}: {reg.experiments[exp_id]['name']}")
    click.echo("  (report generator not yet implemented)")


# ---------------------------------------------------------------------------
# Reproduce / verify
# ---------------------------------------------------------------------------


@main.group(name="reproduce")
def reproduce_group():
    """Reproduce experiments."""


@reproduce_group.command()
@click.argument("exp_id")
def run(exp_id):
    """Reproduce an experiment: cosmos reproduce EXP-001."""
    reg = get_registry()
    if exp_id not in reg.experiments:
        click.echo(f"Experiment {exp_id} not found.", err=True)
        sys.exit(1)
    click.echo(f"Reproducing {exp_id}...")
    click.echo("  (reproduction runner not yet implemented)")


@main.command("verify")
@click.argument("exp_id")
def verify(exp_id):
    """Verify the reproducibility of an experiment."""
    reg = get_registry()
    if exp_id not in reg.experiments:
        click.echo(f"Experiment {exp_id} not found.", err=True)
        sys.exit(1)
    click.echo(f"Verifying {exp_id}...")
    click.echo("  (verification runner not yet implemented)")


# ---------------------------------------------------------------------------
# Replicate paper
# ---------------------------------------------------------------------------


@main.command("replicate")
@click.argument("paper_id")
def replicate(paper_id):
    """Replicate a published paper: cosmos replicate PAPER-ID."""
    click.echo(f"Replicating {paper_id}...")
    click.echo("  (paper replication pipeline not yet implemented)")


if __name__ == "__main__":
    main()
