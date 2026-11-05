# Blender y MCP para preparar modelos de AuraTeach

## Preparar GLB y miniaturas

Blender se usa fuera de la clase para revisar jerarquías, etiquetar piezas y generar capturas. El navegador consume los GLB/manifiestos preparados; ni la página ni DeepSeek se conectan directamente al proceso de Blender.

Desde la raíz del repositorio:

```sh
blender --background --python prototipo/rodrigo-demos/render-thumbnails.py -- --root .
```

El primer modelo preparado para la demo es `demo-lapicero/lapicero.glb`. El par `lapicero.glb` y `lapicero-exploded.glb` ya aporta posiciones ensambladas y separadas para 38 mallas con nombre. Regenera el manifiesto que consume el servidor con:

```sh
python3 demo-lapicero/build_parts_manifest.py
```

La vista del canvas interpola esas posiciones en el navegador. Para nuevos modelos, prepara el GLB ensamblado y el separado en Blender con nombres de malla coincidentes; agrega su manifiesto y activa la lista de piezas solo para ese modelo. Los GLB propios siguen siendo de exploración visual.

## Instalar el MCP comunitario mcp-for-blender en Codex

El archivo `addon.py` del repositorio corresponde al proyecto comunitario [ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender), no a una integración oficial de Blender. En el equipo con Blender instalado:

1. Instala `uv` si aún no está disponible.
2. Instala el complemento en Blender:

   ```sh
   uvx mcp-for-blender install-addon
   ```

3. En Blender, habilita **MCP for Blender** en preferencias de complementos. En el área 3D, abre la barra lateral con `N`, entra en la pestaña **MCP** y pulsa **Connect** para iniciar el servidor local.
4. Registra el proceso MCP para Codex:

   ```sh
   codex mcp add blender -- uvx mcp-for-blender
   codex mcp list
   ```

5. Reinicia Codex y comprueba que el servidor aparece conectado. Deja Blender abierto con el complemento activo al usarlo.

La sintaxis puede cambiar con nuevas versiones del complemento; si un comando no coincide, sigue el README del repositorio enlazado. El MCP es una herramienta local de Codex para preparar e inspeccionar modelos. **DeepSeek no es un cliente MCP** en esta demo: recibe contexto de las piezas y solicita acciones permitidas a la app; la app modifica el canvas Three.js. No se envía la clave de DeepSeek a Blender.

## Seguridad y alcance

El complemento permite operaciones de Python sobre Blender y su servicio local no debe exponerse a la red. Úsalo solo en localhost, con escenas confiables; no publiques el puerto ni conectes equipos desconocidos. Para la demo, Blender puede estar cerrado durante la interacción de estudiantes: el archivo GLB preparado y el manifiesto son suficientes.
