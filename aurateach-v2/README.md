# AuraTeach v2

Base ejecutable para reconstruir AuraTeach por funcionalidades, sin migrar aún la lógica de las demos anteriores. El sistema es un monolito modular con API NestJS, interfaz Angular y contrato HTTP OpenAPI. La biblioteca V1 de modelos se copió como assets versionados para habilitar el catálogo de V2.

## Requisitos y comandos

- Node.js `^22.22.3 || ^24.15.0 || >=26.0.0` y npm 12.2.0 (rango requerido por Angular 22).
- `npm install`: instala los dos workspaces.
- `npm run start:server`: inicia NestJS en `http://localhost:3000`.
- `npm run start:web`: inicia Angular en `http://localhost:4200`; `/api` se envía al servidor.
- `cp .env.example .env`: prepara las variables locales de PostgreSQL (no subas `.env`).
- `npm run db:up`: inicia PostgreSQL 17 en `localhost:5434` con un volumen persistente.
- `npm run db:migrate`: aplica las migraciones Drizzle.
- `npm run db:seed`: carga los datos ficticios base; se puede repetir sin duplicarlos.
- `npm run db:seed:dashboard-smoke`: añade un conjunto sintético separado para ejercitar el dashboard, también idempotente.
- `npm run db:verify`: comprueba los conteos de la semilla.
- `npm run db:down`: detiene el contenedor y conserva el volumen.
- `npm run contracts:types`: genera los tipos TypeScript para Angular desde OpenAPI.
- `npm run architecture`: valida las reglas de importación entre capas y módulos.
- `npm run verify`: ejecuta lint, pruebas, reglas de arquitectura, validación del contrato y builds.

## Selector de perfil de demostración

La primera pantalla ofrece los recorridos “Docente” y “Alumno”. Elegir un perfil y pulsar “Entrar” no pide contraseña y **no autentica ni verifica la identidad**: el perfil ficticio se guarda en `sessionStorage` solo para cambiar la vista de la demo. La guarda del dashboard docente es navegación de interfaz, no una barrera de seguridad. No uses este mecanismo para datos reales.

Al crear la base de datos, `db:seed` inserta 1 docente ficticia, 1 aula, 12 alumnos con seudónimos, 18 modelos de catálogo, 36 visitas y 18 preguntas. `db:seed:dashboard-smoke` agrega estudiantes y actividad sintética en un aula de prueba, sin cambiar esos conteos base. El alumno del flujo interactivo es fijo y ficticio: las visitas y preguntas finales enviadas quedan atribuidas a ese perfil; no se almacenan audio, transcripciones parciales, capturas ni respuestas del tutor. La contraseña local de `.env.example` es únicamente para el contenedor de desarrollo.

La pantalla usa Angular Material y el tema generado por su CLI; no contiene estilos de aplicación propios.

## Límites de arquitectura

### Servidor: hexagonal por módulo

```text
server/src/
├── bootstrap/                 # Composition root de la aplicación Nest
└── modules/<capability>/
    ├── domain/                # Entidades, value objects y reglas puras
    ├── application/
    │   ├── ports/inbound/     # Casos de uso expuestos por el módulo
    │   ├── ports/outbound/    # Interfaces que el caso de uso necesita del exterior
    │   └── use-cases/         # Orquestación de reglas y puertos
    └── adapters/
        ├── inbound/http/      # Controllers, DTOs HTTP y mappers
        ├── outbound/          # Persistencia, IA, archivos y servicios externos
        └── nest/              # Module/providers: cableado de adaptadores y puertos
```

La regla central es **el código depende hacia adentro**. `domain` no importa módulos externos. `application` importa únicamente el dominio y sus propios contratos. Los adaptadores implementan los puertos definidos por el núcleo. NestJS solo aparece en adaptadores y en el cableado de `adapters/nest`/`bootstrap`.

Flujo de entrada: `HTTP → Controller → inbound port → use case → domain/outbound port → adapter`. Los casos de uso no conocen HTTP, Nest, ORM, DeepSeek ni archivos. Los tokens de inyección de Nest se declaran en el borde; no se introduce un import de Nest dentro del núcleo para resolver interfaces de TypeScript.

Un módulo no importa carpetas internas de otro módulo. Cuando necesite colaborar, el módulo proveedor publica un contrato pequeño desde `public-api.ts`; la composición se realiza en el borde. No crear repositorios, eventos, factories o abstracciones si ningún caso de uso los necesita.

### Interfaz: Angular por funcionalidades

```text
web/src/app/
├── core/                      # Configuración global y cliente API
├── shared/                    # UI y utilidades genuinamente compartidas
└── features/<capability>/     # Rutas, páginas, componentes y estado de cada capacidad
```

Usar componentes standalone, rutas lazy por funcionalidad, servicios pequeños y adaptadores HTTP. Las vistas no construyen URLs ni llaman `HttpClient` directamente. Los tipos de respuesta se generan desde el contrato OpenAPI; no se mantienen copias manuales del mismo schema.

## Contrato HTTP

`contracts/openapi.yaml` es la fuente de verdad de la API REST versionada bajo `/api/v1`. Los controladores validan y traducen el formato HTTP a tipos de entrada del caso de uso; el esquema público no se reutiliza como entidad de dominio. El cliente Angular usa tipos generados desde OpenAPI.

## Catálogo y exploración 3D

- El catálogo de la escuela está disponible para el perfil de alumno en `/alumno`. La lista usa `GET /api/v1/models`; sus assets se sirven desde `GET /api/v1/models/{id}/asset` y `.../{id}/thumbnail`.
- El manifiesto `server/assets/model-catalog/manifest.json` es la allowlist de IDs y rutas de archivos. No se debe derivar una ruta del sistema de archivos directamente del parámetro HTTP.
- Los archivos GLB y PNG son copias de la biblioteca V1 bajo `server/assets/model-catalog/`. El manifiesto conserva la fuente original; su licencia figura como `unknown` porque el repositorio no documenta permisos de redistribución.
- El visor Three.js se carga al entrar en una exploración. Los GLB propios se seleccionan desde el dispositivo, se usan temporalmente y nunca se suben ni se guardan.
- Las tarjetas muestran solo las visitas sintéticas vinculadas a cada modelo del catálogo. Se mantiene una fila interna legada «Suelo y erosión» para conservar las 12 visitas y preguntas que ya apuntaban a ella; no se atribuyen a otra tarjeta. Abrir modelos desde el perfil de demo no crea nuevos registros de visita.

## Módulos de producto previstos

- `identity`: identidad y sesiones.
- `model-catalog`: biblioteca de modelos de escuela y acceso seguro a sus assets.
- `exploration`: estado de exploración y acciones permitidas sobre el modelo; la interacción del canvas queda detrás de una API de comandos, separada de Three.js y MediaPipe.
- `tutoring`: preguntas al tutor, proveedor DeepSeek por puerto y propuesta de acciones visuales validadas contra el modelo actual.
- `analytics`: eventos pedagógicos mínimos, resúmenes, preguntas finales y exportación CSV para el docente.

La selección de perfil continúa siendo simulada, sin autenticación real. El dictado usa reconocimiento de voz local del navegador cuando está disponible, y la síntesis de voz se ejecuta en el navegador. El archivo GLB nunca se envía al tutor; las capturas de escena solo se comparten después de activar el consentimiento en el chat. Solo los modelos con manifiesto curado admiten acciones de montaje/desmontaje. Los demás pueden recibir señalización sobre superficies visibles cuando el tutor pueda ubicarla de forma segura.

## Patrones y convenciones

- Modular monolith, Ports and Adapters, Dependency Inversion y casos de uso por operación.
- Controllers delgados; DTOs HTTP separados de inputs/outputs de aplicación y modelos de dominio.
- Dependencias externas se inyectan como puertos; Nest resuelve implementaciones concretas en el composition root.
- Errores de aplicación tienen significado independiente del protocolo; el adaptador HTTP los convierte a respuestas HTTP.
- Interfaces pequeñas y definidas por el consumidor. No usar un `AuraTeachService` que acumule operaciones de varios módulos.
- Las pruebas de dominio y casos de uso usan APIs públicas y dobles en memoria; las pruebas HTTP ejercitan el adaptador real.

## Validación arquitectónica

`npm run architecture` escanea imports TypeScript y falla si el dominio o aplicación importa framework/infraestructura, si application apunta a adapters, o si un módulo accede directamente a las carpetas internas de otro. Las excepciones se limitan al cableado Nest y a contratos públicos.

`npm run verify` es el criterio local antes de integrar cambios. Las funciones del prototipo legado se migrarán después, una funcionalidad a la vez y conservando sus demos como referencia.
