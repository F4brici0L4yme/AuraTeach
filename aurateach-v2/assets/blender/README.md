# Demo de guitarra acústica

Modelo educativo estilizado de una guitarra acústica de cuerdas metálicas. Las piezas se guardan ensambladas y como objetos independientes con nombres descriptivos para que un visor posterior pueda seleccionarlas o separarlas.

## Archivos

- `guitarra_acustica.py`: generador procedural para Blender 5.1 o posterior.
- `guitarra_acustica/guitarra_acustica.blend`: fuente editable, ensamblada, con cámara de revisión.
- `guitarra_acustica/guitarra_acustica.glb`: modelo ensamblado para el visor; conserva la jerarquía y los nombres de sus 53 piezas. No incluye cámara ni luces.
- `guitarra_acustica/vista_ensamblada.png` y `guitarra_acustica/vista_interior.png`: renders de revisión generados con Blender MCP. En el segundo se oculta temporalmente la tapa, las cuerdas y las piezas de la boca y el puente para mostrar el interior.

El MCP se usó localmente para construir, inspeccionar y renderizar el modelo. No forma parte de AuraTeach ni se necesita para cargar o explorar el `.glb`.

Para regenerar el modelo, ejecuta `guitarra_acustica.py` desde Blender o desde Blender MCP. El script escribe las salidas en esta carpeta.
