# AuraTeach v2 contributor instructions

Read [README.md](README.md) and the relevant ADRs in `docs/decisions/` before changing architecture.

## Backend dependency rule

- Keep domain and application code framework-free and independent of delivery and infrastructure.
- Define inbound and outbound ports in the application core; put Nest injection tokens and provider bindings in `adapters/nest` or `bootstrap` only.
- Controllers translate HTTP input to a port call. Presenters map application output to HTTP. Neither owns business rules.
- Adapters implement the ports. A module never imports another module's internals; use its `public-api.ts` contract when a cross-module boundary is needed.
- Run `npm run architecture` after backend changes. Its import rules are part of the architecture, not optional style.

## Contracts and frontend

- Change `contracts/openapi.yaml` first for public REST changes, then refresh generated Angular API types with `npm run contracts:types`.
- Keep generated transport types out of the domain.
- Organize Angular by feature with standalone components and lazy routes. Views call feature services; services adapt HTTP contracts.

## Verification

Run `npm run verify` from this directory before declaring changes ready.

## Demo profile and database scope

- The initial “Docente” / “Alumno” screen is a demo profile selector only. It does not verify identity or protect production data; do not describe it as real authentication.
- Profile state is tab-scoped in `sessionStorage`. Do not add passwords, emails, or personal data to this demo flow.
- Synthetic PostgreSQL persistence is allowed for preparing the teacher dashboard. Keep Drizzle and PostgreSQL in `server/src/infrastructure/database` and scripts; never import them into domain or application code.
- Demo seeds must use fictional pseudonyms and stable unique seed keys so reruns do not duplicate data. Do not seed real student information.
- No production identity provider, analytics endpoint, AI provider, or Blender integration is in scope unless a later task explicitly requests it.
