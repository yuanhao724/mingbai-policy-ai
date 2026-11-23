# Security Policy

## Scope

This is a personal portfolio project. It is not a production service and has no
security SLA. The sample policies are synthetic and are not official advice.

## Secrets

- Never commit `.env`, API keys, tokens, or real customer data.
- Use environment variables for `OPENAI_API_KEY`.
- Do not paste real policy documents containing personal information into a
  public deployment without review.

## Reporting

Please use a private GitHub security advisory for this repository. Do not open a
public issue with secrets, personal data, or an exploit payload.

## Demo Limitations

- The `X-Mori-Role` header is a demo role switch, not real authentication.
- Production should add SSO, RBAC, audit retention, and a reviewed policy
  ingestion workflow.
- The in-process rate limiter is for a single instance. Use Redis or an edge
  limiter for multi-instance deployment.
