# ADR-0002: Strict hexagonal boundaries in the backend

## Status
Accepted

## Context
AuraTeach will use NestJS, but product rules must remain testable without Nest, HTTP, storage, DeepSeek, Blender, or browser code. Framework structure must not dictate where business behavior lives.

## Decision
Use Ports and Adapters inside each backend capability. The dependency rule is mandatory:

```text
domain <- application <- adapters
                         ^
                 Nest composition root
```

- `domain` contains pure business concepts and rules; it imports no application, adapter, NestJS, or infrastructure code.
- `application` contains use cases plus inbound and outbound port contracts. It may depend only on its own module's application code and domain.
- `adapters/inbound` translates delivery formats (HTTP, later other input) into inbound-port calls.
- `adapters/outbound` implements outbound ports for storage, AI, model assets, or other external services.
- `adapters/nest` and `bootstrap` are outer composition roots. They may know concrete adapters and NestJS and bind them to port tokens.
- No module may import another module's internals. Cross-module collaboration uses an intentionally published `public-api.ts` contract and wiring at the outer boundary.
- NestJS decorators, injection tokens, DTOs, and exceptions stay in the adapters. Do not put framework decorators on domain entities or use cases.

The minimal health endpoint follows the same direction: HTTP controller → inbound port → framework-free use case → HTTP presenter. It exists to exercise the boundary, not as a product module precedent for adding unnecessary layers.

## Alternatives considered
- Nest service/controller directly containing feature logic: rejected because rules would couple to HTTP and Nest DI.
- Generic repository/service layer for every capability: rejected because abstractions are added only when a use case needs an external boundary.

## Consequences
- Use cases can be tested with in-memory port implementations.
- Nest module definitions act as outer wiring, not as the business architecture.
- An automated import-boundary check guards the rule against regressions.
