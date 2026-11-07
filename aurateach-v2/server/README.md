# AuraTeach API

Este workspace pertenece al monorepo npm. Ejecuta comandos desde `aurateach-v2/`; la arquitectura, contratos y comandos están documentados en el [README raíz](../README.md).

- `npm run start:server`: servidor de desarrollo.
- `npm run build --workspace @aurateach/server`: build.
- `npm run test --workspace @aurateach/server`: pruebas unitarias.
- `npm run test:e2e --workspace @aurateach/server`: contrato HTTP de health.
- `npm run architecture --workspace @aurateach/server`: valida imports entre capas y módulos.
- `npm run db:seed:dashboard-smoke --workspace @aurateach/server`: agrega datos sintéticos aislados para probar la analítica; se puede repetir.
- PostgreSQL 17 escucha en `localhost:5434` por defecto.
