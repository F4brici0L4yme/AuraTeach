# ADR-0003: OpenAPI is the REST contract source of truth

## Status
Accepted

## Context
Angular and NestJS need to agree on public HTTP paths and payloads without duplicating TypeScript interfaces or leaking domain models into transport formats.

## Decision
Define versioned REST contracts in `contracts/openapi.yaml`. Validate the document with Redocly and generate Angular-facing TypeScript types with `openapi-typescript`. Nest controllers translate between HTTP request/response DTOs and application ports; generated transport types never become domain entities.

## Alternatives considered
- Manually maintain request/response types in both apps: rejected because the copies can drift.
- Infer public API from Nest decorators as the only source: rejected because the frontend contract would be coupled to framework metadata and harder to review before implementation.

## Consequences
- Contract changes are reviewable before implementation.
- Generated types must be refreshed when OpenAPI changes.
- Runtime validation remains the responsibility of the inbound adapter; TypeScript types alone do not validate incoming JSON.
