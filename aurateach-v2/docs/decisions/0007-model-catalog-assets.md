# ADR-0007: Catálogo y assets de modelos 3D

## Estado
Aceptado

## Contexto
El catálogo necesita mostrar modelos GLB de la escuela y permitir su descarga al navegador, manteniendo la API independiente de las rutas del sistema de archivos y de Angular.

## Decisión
- `model-catalog` será un módulo de producto hexagonal. El dominio y los casos de uso no dependerán de NestJS, Drizzle ni del sistema de archivos.
- OpenAPI define los endpoints versionados para listar/consultar modelos y transmitir sus assets. La interfaz consume tipos generados desde ese contrato.
- PostgreSQL mantiene los metadatos consultables y los conteos sintéticos; un manifiesto versionado declara los IDs y las rutas permitidas de GLB y miniaturas. El adaptador resuelve archivos solo a través del manifiesto.
- Los GLB propios se abren localmente en el navegador y no se envían al servidor.
- La actividad del selector de perfil demo no se persiste como actividad real de estudiantes.

## Alternativas consideradas
- Servir rutas construidas desde el ID recibido: descartado porque permitiría solicitar archivos fuera del catálogo.
- Subir y persistir GLB propios: pospuesto; la demo requiere solo una vista temporal local.
- Reutilizar el código de servidor de V1: descartado para mantener las reglas de arquitectura de V2.

## Consecuencias
- Los archivos servidos quedan limitados a los manifiestos y pueden cambiarse sin exponer carpetas arbitrarias.
- Una fila sintética legada de «Suelo y erosión» queda fuera del catálogo para conservar sus asociaciones de visitas/preguntas; las tarjetas muestran conteos solo de sus propias filas.
- Los assets se mantienen como copias de V1 dentro de V2. La licencia y procedencia legal no están documentadas; no se debe afirmar una licencia de redistribución.
- La integración de gestos, despiece e IA permanece fuera de esta etapa.
