import os
from jinja2 import Environment, FileSystemLoader
from geo_auditor.models import ScoredAudit


def render_report(audit: ScoredAudit) -> str:
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    env = Environment(loader=FileSystemLoader(os.path.abspath(template_dir)), autoescape=True)
    template = env.get_template("report.html.j2")
    return template.render(audit=audit)
