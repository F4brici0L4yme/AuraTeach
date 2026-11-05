# Demos de Rodrigo

## Ejecutar el prototipo integrado

Requiere Node.js 22.5 o superior (usa `node:sqlite`). Desde esta carpeta:

```sh
node server.mjs
```

Abre `http://localhost:4177/prototipo/rodrigo-demos/aula.html`. La laptop sirve la página y guarda actividad en `curio-demo.sqlite`.

Para conectar DeepSeek, crea tu archivo local de configuración y pega la clave allí:

```sh
cp .env.example .env
# Edita .env y completa LLM_API_KEY
node --env-file=.env server.mjs
```

La clave se lee solo en el servidor y `.env` está excluido de Git. La barra del tutor indica si la conexión está configurada, sin mostrar la clave. Sin ella, el tutor responde en modo simulado. No la pegues en el navegador ni en los archivos HTML.

Puedes desactivar el seed de demostración con `AURATEACH_SEED_DEMO=false`. Para usar una base aislada define `AURATEACH_DB_PATH=/ruta/a/demo.sqlite`.

## Qué incluye

- Interfaz de escritorio en tema claro, con Air Mouse como mouse Bluetooth para menús y controles.
- Air Mouse controla la interfaz. La cámara se activa después de cargar un modelo; inicia en modo Air Mouse y el gesto pulgar+anular alterna entre Air Mouse y Gestos.
- En modo Gestos, AuraTeach oculta el cursor y descarta entradas de mouse dentro de la app. Puño y movimiento orbitan el modelo; separar/acercar las manos hace zoom; el índice muestra una retícula y resalta la malla apuntada; una pinza breve de índice+pulgar selecciona la pieza para preguntar al tutor.
- Escape vuelve al modo Air Mouse. Detener la cámara, perder el tracking por un momento, o salir del modelo también restaura el Air Mouse. Los gestos no arrastran ni descomponen piezas; las acciones complejas siguen disponibles para el tutor.
- Galería escolar de 3 × 3 con búsqueda y paginación. Incluye los GLB de `3d_lab_aurateach/assets/` y modelos anteriores.
- Miniaturas renderizadas con Blender en `model-thumbnails/`; para volver a generarlas, sigue `BLENDER_MCP_SETUP.md`.
- Canvas Three.js para inspeccionar GLB. El lapicero escolar permite separar y ensamblar mallas con nombre, enfocar piezas y moverlas. Los GLB propios se pueden explorar visualmente, sin disección automática.
- Chat flotante con dictado del navegador. Toca la burbuja para iniciar la sesión de escucha; di «pregunta» y después la consulta, o di «pregunta: …» en una sola frase.
- Dashboard docente con gráficas animadas, preguntas textuales, visitas, inspección de partes e informe imprimible/guardable como PDF.
- Dashboard con datos sintéticos de 8 estudiantes y filtros para ver todo, solo demostración o solo actividad real. El PDF excluye los datos sintéticos de forma predeterminada; se pueden incluir marcando la opción.
- SQLite local y sesiones de demostración por alias. **El acceso de docente/estudiante es simulado, no autenticación de producción.**

## Datos y privacidad de la demo

- El servidor guarda texto exacto de cada pregunta, alias, modelo y fecha para que el docente pueda revisar actividad y exportar el informe.
- Las imágenes del canvas se envían a DeepSeek solo durante la consulta; no se guardan en SQLite. No se almacenan grabaciones de voz.
- La señal «Revisar participación» se calcula con la actividad reciente y sirve como ayuda para el docente; no etiqueta ni decide por el estudiante.
- La clave DeepSeek debe estar en `LLM_API_KEY` del proceso Node, nunca en el navegador.

## Pruebas

Desde esta carpeta ejecuta:

```sh
node server.test.mjs
node hand-gestures.test.mjs
node deepseek-client.test.mjs
node lapicero-parts.test.mjs
```

Para revisar sintaxis del servidor y los módulos:

```sh
node --check server.mjs
node --check demo-seed.mjs
node --check hand-gestures.mjs
node --check deepseek-client.mjs
```

## Blender MCP

El MCP comunitario `mcp-for-blender` sirve desde Codex para preparar modelos y capturas; nunca se expone al navegador ni se conecta directamente a DeepSeek. Blender 5.2.2 está instalado. Sigue `BLENDER_MCP_SETUP.md` para registrar el complemento y usar el comando local de miniaturas. La interacción de aula usa los archivos preparados, por lo que no necesita Blender MCP conectado en vivo.

El reconocimiento de voz del navegador requiere compatibilidad de Web Speech y permiso de micrófono. La cámara de manos requiere HTTPS o `localhost`.

Las demos anteriores siguen disponibles desde el índice. `canvas.html` conserva `window.dispatchCanvasCommand()` como punto de entrada para comandos de interacción.
