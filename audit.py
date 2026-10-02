import sys
import click
from geo_auditor.config import get_probe_config, get_analysis_config, get_fast_config
from geo_auditor.fetcher import fetch
from geo_auditor.profiler import profile
from geo_auditor.probe import run_probe
from geo_auditor.checks.direct_answer import check_direct_answer
from geo_auditor.checks.fact_density import check_fact_density
from geo_auditor.checks.discoverability import check_discoverability
from geo_auditor.checks.freshness import check_freshness
from geo_auditor.checks.markdown_structure import check_markdown_structure
from geo_auditor.checks.citation_density import check_citation_density
from geo_auditor.checks.org_eeat import check_org_eeat
from geo_auditor.checks.content_depth import check_content_depth
from geo_auditor.checks.wikipedia import check_wikipedia_presence
from geo_auditor.checks.community_citations import check_community_citations
from geo_auditor.scorer import score_audit
from geo_auditor.fixer import generate_fixes
from geo_auditor.reporter import render_report
from geo_auditor.models import ScoredAudit


def _fmt(check) -> str:
    """Console line for a check; unmeasured checks show no number."""
    if not check.measured:
        return "not measured (excluded from score)"
    return f"{check.score}/100"


@click.command()
@click.argument("url")
@click.option("--output", default="report.html", help="Output HTML file path")
def cli(url: str, output: str):
    """Run a GEO audit on URL and write an HTML report to OUTPUT."""
    probe_cfg = get_probe_config()
    analysis_cfg = get_analysis_config()
    fast_cfg = get_fast_config()

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
        click.echo("ERROR: no probe API key — cannot run the visibility probe.", err=True)
        sys.exit(1)
    visibility = run_probe(biz_profile, probe_cfg, fast_cfg)
    click.echo(f"  -> Visibility score: {visibility.score}/100")

    click.echo("Running on-page checks ...")
    check1 = check_direct_answer(fetch_result, analysis_cfg)
    click.echo(f"  -> Direct Answer Lead: {_fmt(check1)}")
    check2 = check_fact_density(fetch_result, analysis_cfg)
    click.echo(f"  -> Fact Density: {_fmt(check2)}")
    check3 = check_discoverability(fetch_result, biz_profile)
    click.echo(f"  -> Agent Discoverability: {_fmt(check3)}")
    check4 = check_freshness(fetch_result)
    click.echo(f"  -> Content Freshness: {_fmt(check4)}")
    check5 = check_markdown_structure(fetch_result)
    click.echo(f"  -> Markdown-safe Structure: {_fmt(check5)}")
    check6 = check_citation_density(fetch_result)
    click.echo(f"  -> Citation Density: {_fmt(check6)}")
    check7 = check_org_eeat(fetch_result)
    click.echo(f"  -> Organization E-E-A-T: {_fmt(check7)}")
    check8 = check_content_depth(fetch_result)
    click.echo(f"  -> Content Depth: {_fmt(check8)}")
    check9 = check_wikipedia_presence(biz_profile)
    click.echo(f"  -> Wikipedia Presence: {_fmt(check9)}")
    # Community Citations reads the probe's grounding sources — must run after run_probe.
    check10 = check_community_citations(visibility)
    click.echo(f"  -> Community Citations: {_fmt(check10)}")
    checks = [check1, check2, check3, check4, check5, check6, check7, check8, check9, check10]

    overall, band = score_audit(visibility, checks)
    click.echo(f"Overall GEO score: {overall}/100  ({band})")

    click.echo("Generating fixes ...")
    fixes = generate_fixes(checks, biz_profile, analysis_cfg)

    audit = ScoredAudit(
        url=url, profile=biz_profile, visibility=visibility,
        checks=checks, overall_score=overall, band=band,
        fixes=fixes,
    )

    html = render_report(audit)
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    click.echo(f"\n Report written to: {output}")


if __name__ == "__main__":
    cli()
