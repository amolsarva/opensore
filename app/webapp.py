from __future__ import annotations

from fastapi import FastAPI, Response, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, ValidationError

from app.config import LLMSettings, get_environment
from app.discovery.models import (
    DiscoveryInvestigationPlan,
    DiscoveryInvestigationRequest,
    DiscoveryKeywordSet,
    build_discovery_plan,
    default_keyword_sets,
    discovery_plan_csv,
)
from app.utils.sentry_sdk import init_sentry
from app.version import get_version

init_sentry(entrypoint="webapp")


class HealthResponse(BaseModel):
    ok: bool
    version: str
    llm_configured: bool
    env: str


app = FastAPI(title="OpenSRE Discovery")


def _llm_configured() -> bool:
    try:
        LLMSettings.from_env()
    except ValidationError:
        return False
    return True


def get_health_response() -> HealthResponse:
    llm_configured = _llm_configured()

    return HealthResponse(
        ok=llm_configured,
        version=get_version(),
        llm_configured=llm_configured,
        env=get_environment().value,
    )


@app.get("/", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse)
@app.get("/ok", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    health_response = get_health_response()
    response.status_code = (
        status.HTTP_200_OK if health_response.ok else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return health_response


@app.get("/ui", response_class=HTMLResponse)
def discovery_ui() -> str:
    """Render the first hosted discovery setup screen.

    The web surface is intentionally static for now: it introduces the new
    product direction and points clients at the no-retention API contracts.
    """

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OpenSRE Discovery</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #f7f4ef; color: #202124; }
    main { max-width: 1120px; margin: 0 auto; padding: 48px 24px 72px; }
    header { display: grid; gap: 18px; margin-bottom: 36px; }
    h1 { font-size: 44px; line-height: 1.05; margin: 0; letter-spacing: 0; max-width: 780px; }
    p { font-size: 17px; line-height: 1.55; max-width: 760px; margin: 0; }
    .actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 10px; }
    a, button { border: 1px solid #202124; background: #202124; color: #fff; padding: 11px 14px;
      border-radius: 6px; text-decoration: none; font-weight: 650; font-size: 14px; }
    a.secondary { background: transparent; color: #202124; }
    section { border-top: 1px solid #d7d0c5; padding-top: 24px; margin-top: 28px; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
    .card { background: #fff; border: 1px solid #ddd5ca; border-radius: 8px; padding: 18px; }
    h2 { margin: 0 0 14px; font-size: 22px; }
    h3 { margin: 0 0 8px; font-size: 16px; }
    ul { margin: 0; padding-left: 18px; line-height: 1.65; }
    code { background: #eee8df; padding: 2px 5px; border-radius: 4px; }
    @media (max-width: 760px) { h1 { font-size: 34px; } .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <header>
    <h1>Workplace misconduct discovery without storing evidence on this host.</h1>
    <p>Run targeted investigations across communication and work systems for harassment,
    executive misconduct, retaliation, and sexual misconduct matters. User-owned source
    accounts authenticate directly, and exports are designed to land as CSV files in the
    user's Google Drive.</p>
    <div class="actions">
      <a href="/api/discovery/default-keywords">View keyword seeds</a>
      <a class="secondary" href="/api/discovery/schema">API schema</a>
    </div>
  </header>
  <section class="grid">
    <div class="card"><h3>1. Create matter</h3><p>Name the investigation, add custodians, date range, and keyword sets.</p></div>
    <div class="card"><h3>2. Connect sources</h3><p>Use read-only authorization for Google Workspace, Slack, Microsoft 365, GitHub, Jira, or CSV.</p></div>
    <div class="card"><h3>3. Export to Drive</h3><p>Write reviewable CSV outputs to the user's Drive and discard transient buffers.</p></div>
  </section>
  <section>
    <h2>What this is not</h2>
    <ul>
      <li>It is not legal advice or a replacement for counsel.</li>
      <li>It should not decide whether misconduct happened by itself.</li>
      <li>It should not retain user evidence on the hosted OpenSRE server.</li>
    </ul>
  </section>
</main>
</body>
</html>"""


@app.get("/api/discovery/default-keywords", response_model=list[DiscoveryKeywordSet])
def discovery_default_keywords() -> list[DiscoveryKeywordSet]:
    return default_keyword_sets()


@app.get("/api/discovery/schema")
def discovery_schema() -> dict[str, object]:
    return {
        "request": DiscoveryInvestigationRequest.model_json_schema(),
        "plan": DiscoveryInvestigationPlan.model_json_schema(),
    }


@app.post("/api/discovery/investigations/preview", response_model=DiscoveryInvestigationPlan)
def discovery_preview(request: DiscoveryInvestigationRequest) -> DiscoveryInvestigationPlan:
    """Return a no-evidence plan for a workplace discovery investigation."""

    return build_discovery_plan(request)


@app.post("/api/discovery/investigations/preview.csv", response_class=PlainTextResponse)
def discovery_preview_csv(request: DiscoveryInvestigationRequest) -> str:
    """Return a CSV summary of a no-evidence discovery plan."""

    return discovery_plan_csv(build_discovery_plan(request))
