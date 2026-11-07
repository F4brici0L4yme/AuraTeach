# ADR-0006: PostgreSQL y datos sintéticos del dashboard

## Estado
Aceptado

## Contexto
Se necesita una base reproducible que permita diseñar después las analíticas del docente, sin integrar todavía las rutas de producto ni almacenar actividad real de estudiantes.

## Decisión
Usar PostgreSQL 17 en Docker Compose, con volumen persistente y healthcheck. La base se publica en `5434` porque `5432` y `5433` ya están ocupados en el entorno de desarrollo. Drizzle mantiene el esquema y las migraciones SQL desde `server/src/infrastructure/database`; un script idempotente inserta una docente, un aula, 12 alumnos seudónimos, 3 modelos, 36 visitas y 18 preguntas.

Las semillas son ficticias, no incluyen correos ni contraseñas y no se conectan al selector de perfil. Drizzle y PostgreSQL permanecen fuera de dominio y aplicación. Los scripts de base de datos son herramientas del adaptador de infraestructura, no endpoints de identidad.

## Alternativas consideradas
- SQLite local: descartado porque el equipo decidió que la futura persistencia del proyecto será PostgreSQL.
- Base remota compartida: pospuesta para evitar credenciales e infraestructura externa durante el prototipo.
- Guardar interacciones del perfil de demo: descartado; el selector no representa usuarios verificados.

## Consecuencias
- Cualquier integrante puede reiniciar la base local y regenerar las mismas filas sintéticas.
- La visualización del dashboard todavía no existe; la base prepara datos para ese módulo posterior.
- Antes de usar datos reales deben definirse identidad de servidor, consentimiento, retención y controles de acceso.
