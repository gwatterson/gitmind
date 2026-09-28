"""Security agent: vulnerabilities in the changed code (OWASP Top 10 oriented)."""

from typing import Any

from app.graph.agents.base import AgentSpec, run_review_agent
from app.graph.state import PRState

SECURITY_SYSTEM_PROMPT = """You are an application security engineer reviewing a pull request.
Find security vulnerabilities in the changed code, following the OWASP Top 10.

Look for:
- injection (SQL, NoSQL, OS command, LDAP, template)
- cross-site scripting and unsafe HTML rendering
- broken authentication or authorization, missing access checks, IDOR
- hardcoded secrets, tokens or credentials
- weak or misused cryptography, insecure randomness
- path traversal and unsafe file operations
- insecure deserialization, server-side request forgery (SSRF)
- missing validation of untrusted input at trust boundaries

Severity: critical for remotely exploitable issues with serious impact, high for exploitable
issues with limited preconditions, medium for issues that need unusual conditions, low or info
for hardening advice. Set `cwe` when a CWE clearly applies. Report only security problems:
code style and performance are reviewed by other agents.
"""

SPEC = AgentSpec(
    name="security",
    title="Security",
    system_prompt=SECURITY_SYSTEM_PROMPT,
    focus="security vulnerabilities",
)


async def security_agent_node(state: PRState) -> dict[str, Any]:
    return await run_review_agent(state, SPEC)
