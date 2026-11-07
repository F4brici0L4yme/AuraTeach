# ADR-0001: Modular monolith

## Status
Accepted

## Context
AuraTeach needs to move quickly as a small team while keeping its capabilities independently understandable and replaceable. There is no demonstrated scaling or deployment need for distributed services.

## Decision
Build one deployable NestJS API organized by product capability, with an Angular web client in the same npm workspace. Keep capability boundaries explicit and avoid direct imports into another module's internals.

## Alternatives considered
- Microservices: rejected for the current scale because independent deployments and network coordination would slow prototyping.
- A single technical-layered application: rejected because each feature's rules and integrations would be spread across global folders.

## Consequences
- Features can be built and demonstrated one at a time.
- Module contracts are explicit; extraction into services remains possible if later justified.
- A module is not created until there is a real vertical slice for it.
