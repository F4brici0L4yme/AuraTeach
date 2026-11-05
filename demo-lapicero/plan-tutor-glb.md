# Plan: tutor conversacional que explora modelos GLB

## Objetivo

Permitir que un estudiante cargue un `.glb` escaneado con Polycam, pregunte por voz o texto y reciba una explicación acompañada por movimientos de cámara y anotaciones sobre el modelo. El agente debe indicar incertidumbre cuando el escaneo no permita identificar o ubicar una parte con seguridad.

## Tecnologías y compras

- **Modelo conversacional y visión:** DeepSeek API, usando el modelo Flash con entrada de imágenes y llamadas a funciones. Para el primer prototipo, comenzar con US$2 de saldo y limitar cantidad/tamaño de imágenes y longitud de respuestas. El costo real depende del uso.
- **Aplicación web:** Three.js y `GLTFLoader` para cargar y mostrar el GLB; `Raycaster` y la profundidad de la escena para convertir una ubicación de pantalla en un punto sobre la malla.
- **Backend:** Node.js, con un endpoint que llama a DeepSeek y mantiene la clave API fuera del navegador. No hace falta una base de datos para una prueba local.
- **Voz de prototipo:** reconocimiento de voz del navegador (`SpeechRecognition`/`webkitSpeechRecognition`) para voz a texto y `speechSynthesis` para leer respuestas. Añadir siempre entrada de texto como alternativa. La disponibilidad del reconocimiento varía por navegador.
- **Sin compra inicial adicional:** no comprar Blender, Blender MCP ni un servicio de voz para el MVP. Blender puede ayudar en inspección y depuración, pero no es requisito de ejecución del producto.

## Flujo de usuario y agente

1. El estudiante selecciona un archivo `.glb`; el navegador valida tamaño/formato y lo carga en el visor.
2. La aplicación inspecciona la estructura glTF: nodos, nombres, jerarquía, materiales, dimensiones y mallas. Conserva el GLB en el cliente mientras dure la sesión.
3. El visor renderiza una pequeña colección de vistas del objeto, por ejemplo frente, laterales y parte superior. Se envían a DeepSeek junto con el resumen estructural para que proponga qué objeto es y qué partes visibles reconoce.
4. El agente crea un mapa de partes con nombre tentativo, descripción, nodo asociado o ubicación aproximada y nivel de confianza. Si el modelo es una única malla sin nombres, el agente trabaja con regiones visibles aproximadas y lo indica.
5. El estudiante pregunta hablando o escribiendo. La voz se transcribe en el navegador; se envía el texto al backend junto con el mapa ya calculado y, solo si hace falta, una captura de la vista actual.
6. DeepSeek devuelve explicación, pregunta de seguimiento opcional y una acción estructurada para el visor. El backend valida el formato y el cliente limita la acción a la escena cargada.
7. El visor anima el zoom/orbita, muestra etiqueta y flecha en el punto seleccionado y, cuando haya una pieza independiente, puede resaltarla. La respuesta se muestra y se lee en voz alta.
8. El estudiante puede interrumpir, hacer otra pregunta, girar el objeto manualmente o descartar las anotaciones. Una pregunta nueva cancela el audio y las animaciones pendientes.

## Cómo se localizan y señalan las partes

- **Si el GLB tiene partes/nodos separados y nombrados:** enfocar su centro y resaltar el nodo directamente.
- **Si Polycam produjo una sola malla:** pedir a la visión una ubicación 2D aproximada en una de las vistas conocidas. El cliente usa la cámara de esa vista y un `Raycaster` para proyectar el punto sobre la superficie del GLB. La flecha/etiqueta se ancla al punto 3D encontrado.
- **Si la ubicación es ambigua:** mostrar una propuesta y pedir al estudiante que confirme el punto o seleccione la región con un clic. No presentar coordenadas inferidas como una segmentación exacta.
- **Límite del escaneo:** no se pueden explicar como observadas piezas internas que no aparecen en la geometría/textura. Para enseñar el interior, se necesitaría otro escaneo, un modelo CAD/despiece o una anotación manual.

## Interfaz de acciones del agente

El agente no manipula directamente Blender ni ejecuta JavaScript arbitrario. Puede proponer solo acciones validadas por la aplicación, por ejemplo:

- `focus`: punto/nodo objetivo y distancia de cámara.
- `annotate`: etiqueta, flecha y punto de anclaje 3D.
- `highlight`: nodo independiente si existe.
- `clear_annotations`: limpiar etiquetas y flechas.

Cada acción debe incluir un objetivo válido y valores acotados; si la respuesta no contiene acción válida, se muestra solo la explicación. La cámara y el puntero permanecen bajo control del estudiante.

## ¿Se necesita una skill o MCP?

- **No se necesita una skill ni MCP** para el flujo normal de la aplicación. El backend expone a DeepSeek llamadas de función limitadas y el cliente las traduce a operaciones de Three.js.
- **MCP es opcional** si más adelante se quiere que un agente externo controle Blender, inspeccione archivos en escritorio o reutilice las herramientas de análisis desde varias aplicaciones. No añade comprensión visual por sí solo.
- Una **skill** sería documentación reutilizable para que un agente siga el procedimiento de análisis/enseñanza; no es una dependencia del prototipo ni reemplaza el código de visión, segmentación o visor.

## Fases de implementación

1. **MVP local:** subir un GLB, inspeccionar metadatos y renderizar vistas; usar DeepSeek para describir el objeto/partes; permitir pregunta escrita y respuesta con una acción de foco/etiqueta.
2. **Voz:** añadir dictado del navegador y lectura de la respuesta, con botón para detener/interrumpir y alternativa escrita.
3. **Localización:** enlazar nodos nombrados automáticamente; para mallas únicas, generar ubicaciones aproximadas desde vistas y usar raycasting, confirmando cuando la confianza sea baja.
4. **Pulido educativo:** animaciones suaves, preguntas de seguimiento, historial de conversación por sesión y estados claros de carga/error.

## Criterios de aceptación

- Cargar un GLB local sin subir el archivo completo al proveedor de IA; solo se envían las vistas necesarias y los metadatos seleccionados.
- El estudiante puede preguntar por voz o texto y obtener respuesta en español.
- Una pregunta sobre una parte identificable enfoca el visor y muestra una etiqueta/flecha anclada al modelo.
- El estudiante puede interrumpir la voz y las acciones, y seguir usando los controles manuales.
- En un GLB sin partes identificables, el sistema comunica el límite y pide ayuda/confirmación en lugar de inventar una ubicación.
- La clave DeepSeek solo existe en el backend; se pueden limitar llamadas y gasto para respetar el saldo de prueba.

## Referencias técnicas

- DeepSeek visión: https://api-docs.deepseek.com/guides/vision/
- DeepSeek llamadas a herramientas: https://api-docs.deepseek.com/guides/tool_calls/
- DeepSeek streaming/Responses API: https://api-docs.deepseek.com/guides/responses_api/
- Precios DeepSeek: https://api-docs.deepseek.com/quick_start/pricing/
