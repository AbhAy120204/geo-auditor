import os
import sys
import click
from geo_auditor.config import get_probe_config, get_analysis_config
from geo_auditor.fetcher import fetch
from geo_auditor.profiler import profile
from geo_auditor.probe import run_probe
from geo_auditor.checks.direct_answer import check_direct_answer
from geo_auditor.checks.fact_density import check_fact_density
from geo_auditor.checks.discoverability import check_discoverability
from geo_auditor.scorer import score_audit
from geo_auditor.fixer import generate_fixes
from geo_auditor.reporter import render_report
from geo_auditor.models import ScoredAudit
from geo_auditor.llm import chat_complete, web_search_query


@click.command()
@click.argument("url")
@click.option("--output", default="report.html", help="Output HTML file path")
def cli(url: str, output: str):
    """Run a GEO audit on URL and write an HTML report to OUTPUT."""
    probe_cfg = get_probe_config()
    analysis_cfg = get_analysis_config()

    if not analysis_cfg:
        click.echo("ERROR: GEMINI_API_KEY not found in .env — cannot run analysis checks.", err=True)
        sys.exit(1)

    click.echo(f"Fetching {url} ...")
    fetch_result = fetch(url)
    if fetch_result.error:
        click.echo(f"ERROR fetching URL: {fetch_result.error}", err=True)
        sys.exit(1)

    click.echo("Profiling business ...")
    biz_profile = profile(fetch_result, analysis_cfg)
    click.echo(f"  -> {biz_profile.name} | {biz_profile.category} | {biz_profile.city}")

    click.echo("Running AI visibility probe ...")
    if probe_cfg is None:
        click.echo("  ! No probe API key — running in demo mode (mocked)")
    visibility = run_probe(biz_profile, probe_cfg)
    click.echo(f"  -> Visibility score: {visibility.score}/100{'  [MOCKED]' if visibility.is_mocked else ''}")

    click.echo("Running on-page checks ...")
    check1 = check_direct_answer(fetch_result, analysis_cfg)
    click.echo(f"  -> Direct Answer Lead: {check1.score}/100")
    check2 = check_fact_density(fetch_result, analysis_cfg)
    click.echo(f"  -> Fact Density: {check2.score}/100")
    check3 = check_discoverability(fetch_result, biz_profile)
    click.echo(f"  -> Agent Discoverability: {check3.score}/100")
    checks = [check1, check2, check3]

    overall, band = score_audit(visibility, checks)
    click.echo(f"Overall GEO score: {overall}/100  ({band})")

    click.echo("Generating fixes ...")
    fixes = generate_fixes(checks, biz_profile, analysis_cfg)

    audit = ScoredAudit(
        url=url, profile=biz_profile, visibility=visibility,
        checks=checks, overall_score=overall, band=band,
        fixes=fixes, is_mocked=visibility.is_mocked,
    )

    html = render_report(audit)
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    click.echo(f"\n Report written to: {output}")


if __name__ == "__main__":
    cli()
