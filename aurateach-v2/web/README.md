# AuraTeach Web

Aplicación Angular standalone. Este workspace pertenece al monorepo npm; ejecuta los comandos desde `aurateach-v2/` y consulta el [README raíz](../README.md) para la arquitectura completa.

- `npm run start:web`: inicia Angular con proxy de API.
- `npm run build --workspace @aurateach/web`: build.
- `npm run test --workspace @aurateach/web`: pruebas de componentes.
- `npm run lint --workspace @aurateach/web`: lint TypeScript y plantillas Angular.
- `npm run contracts:types`: actualiza los tipos generados desde OpenAPI.
