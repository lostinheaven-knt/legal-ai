from pathlib import Path

import typer

from legal_ai.commands.check import check_workspace
from legal_ai.commands.evidence import analyze_evidence_workspace
from legal_ai.commands.init import init_workspace
from legal_ai.commands.listing import review_listing_workspace
from legal_ai.commands.report import build_report_workspace


app = typer.Typer(
    name="legal-ai",
    help="Local-first ecommerce compliance pre-check toolkit.",
    no_args_is_help=True,
)
listing_app = typer.Typer(help="Listing claim review commands.")
evidence_app = typer.Typer(help="Evidence gap commands.")
report_app = typer.Typer(help="Report generation commands.")


@app.command("init")
def init_command(
    target: Path = typer.Argument(..., help="Workspace directory to create."),
) -> None:
    """Create a demo workspace."""
    init_workspace(target)


@app.command("check")
def check_command(
    workspace: Path = typer.Argument(Path("."), help="Workspace directory."),
    market: str | None = typer.Option(
        None,
        "--market",
        help="Comma-separated markets, supported: EU,US.",
    ),
    platform: str | None = typer.Option(
        None,
        "--platform",
        help="Marketplace platform, supported: amazon.",
    ),
    strict: bool | None = typer.Option(
        None,
        "--strict/--no-strict",
        help="Enable strict pre-check behavior.",
    ),
    llm: str | None = typer.Option(None, "--llm", help="LLM mode override: auto, always, or off."),
) -> None:
    """Run the full pre-check pipeline."""
    check_workspace(workspace=workspace, market=market, platform=platform, strict=strict, llm=llm)


@listing_app.command("review")
def listing_review_command(
    workspace: Path = typer.Argument(Path("."), help="Workspace directory."),
    market: str | None = typer.Option(
        None,
        "--market",
        help="Comma-separated markets, supported: EU,US.",
    ),
    platform: str | None = typer.Option(
        None,
        "--platform",
        help="Marketplace platform, supported: amazon.",
    ),
    llm: str | None = typer.Option(None, "--llm", help="LLM mode override: auto, always, or off."),
) -> None:
    """Review listing claims."""
    review_listing_workspace(workspace=workspace, market=market, platform=platform, llm=llm)


@evidence_app.command("gap")
def evidence_gap_command(
    workspace: Path = typer.Argument(Path("."), help="Workspace directory."),
    market: str | None = typer.Option(
        None,
        "--market",
        help="Comma-separated markets, supported: EU,US.",
    ),
    platform: str | None = typer.Option(
        None,
        "--platform",
        help="Marketplace platform, supported: amazon.",
    ),
    llm: str | None = typer.Option(None, "--llm", help="LLM mode override: auto, always, or off."),
) -> None:
    """Analyze supplier evidence gaps."""
    analyze_evidence_workspace(workspace=workspace, market=market, platform=platform, llm=llm)


@report_app.command("build")
def report_build_command(
    workspace: Path = typer.Argument(Path("."), help="Workspace directory."),
    llm: str | None = typer.Option(None, "--llm", help="LLM mode override: auto, always, or off."),
) -> None:
    """Build reports from a structured result."""
    build_report_workspace(workspace=workspace, llm=llm)


app.add_typer(listing_app, name="listing")
app.add_typer(evidence_app, name="evidence")
app.add_typer(report_app, name="report")


if __name__ == "__main__":
    app()
