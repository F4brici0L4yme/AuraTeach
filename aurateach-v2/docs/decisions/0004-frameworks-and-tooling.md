# ADR-0004: NestJS and Angular with npm workspaces

## Status
Accepted

## Context
The team wants a strongly typed backend and a full web framework, while keeping the prototype in one repository and using a familiar toolchain.

## Decision
Use Node.js 22.12+ with npm workspaces, NestJS for the API, Angular standalone applications for the web client, and OpenAPI for the REST boundary. Use the current stable CLI versions and commit the lockfile for reproducible installs.

## Consequences
- Server and web can be started, tested, and built separately or from the workspace root.
- Angular pages are organized by feature with standalone components and lazy routes; classic MVC is not imposed on the frontend.
- Framework upgrades are handled as explicit dependency changes and reviewed against supported Node/TypeScript versions.
