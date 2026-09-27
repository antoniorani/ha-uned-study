# UNED Study — documentación

## Uso normal

1. Abre **UNED Study** desde la barra lateral.
2. Elige una asignatura.
3. Pulsa **Continuar** para estudio inteligente.
4. Opcionalmente usa **Tema** para limitar el estudio a un bloque.
5. En asignaturas tipo test, usa **Simulacro** para reproducir la estructura definida en el contenido.

No necesitas escoger manualmente entre preguntas nuevas, falladas, importantes o vencidas. El motor las combina automáticamente.

## Contenido

Por defecto se sincroniza:

`https://github.com/antoniorani/uned-study-content`

La fuente y la rama se cambian desde la pestaña **Configuración** del complemento.

## Datos

El progreso vive en el volumen persistente `/data` del complemento y forma parte del ciclo de backup de Home Assistant.

## Usuarios

Ingress proporciona a la aplicación el identificador del usuario autenticado de Home Assistant. Cada usuario mantiene progreso, favoritos y sesiones independientes.

## Actualizaciones de contenido

La aplicación comprueba GitHub al iniciar y después según `sync_interval_hours`. Un snapshot nuevo solo se activa si todos los `subject.json` son válidos.
