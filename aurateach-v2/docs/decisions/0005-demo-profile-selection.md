# ADR-0005: Selector de perfiles de demostración

## Estado
Aceptado

## Contexto
La siguiente vista del prototipo necesita distinguir un recorrido de docente y otro de alumno. La demo no requiere cuentas personales ni debe recopilar credenciales de menores.

## Decisión
La primera pantalla muestra los perfiles “Docente” y “Alumno”. Al elegir uno y pulsar “Entrar”, Angular conserva el perfil de demostración en `sessionStorage` y navega a una pantalla placeholder. La ruta del dashboard requiere el perfil docente; el perfil alumno vuelve a su propia vista. No se añade endpoint de identidad.

Esto solo organiza la navegación de la demo. No verifica quién usa el dispositivo, no constituye autenticación, y la guarda de Angular no protege datos o endpoints de producción.

## Alternativas consideradas
- Contraseña propia: descartada para esta etapa porque añade gestión de credenciales sin aportar valor a la presentación.
- Google Workspace u otro proveedor real: pospuesto hasta que la demo necesite identidad verificable y control de acceso en el servidor.

## Consecuencias
- El flujo es inmediato y no solicita información personal.
- El perfil desaparece al cerrar la sesión de la pestaña.
- Antes de publicar datos reales se debe implementar identidad y autorización en el servidor, con un proveedor elegido explícitamente.
