"""LOCAL-ONLY demonstration API for the Security Lab UI (Session 8).

Everything under /demo is a presentation/observation layer. It adds NO security
controls of its own: authorisation stays in app.authz, tenant scoping in the
repositories, and refund decisions in app.approvals.

All routes fail closed (404) unless explicitly enabled - see app.demo.gate.
"""
