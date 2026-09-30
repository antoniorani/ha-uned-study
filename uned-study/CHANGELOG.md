# Changelog

## 0.2.1

- Al abrir el panel principal se comprueba inmediatamente el repositorio de contenidos, por lo que las nuevas asignaturas aparecen sin esperar al intervalo periódico ni reiniciar el add-on.
- Si GitHub no está disponible o la actualización no es válida, se mantiene la última copia local válida y la aplicación sigue siendo utilizable.
- Se añade una prueba de regresión para garantizar que la carga del panel dispara la sincronización.

## 0.2.0

- Primera versión estable de UNED Study para Home Assistant.
- La aplicación deja la fase experimental y se publica con `stage: stable`.
- Se consolida como contrato estable que cada asignatura es exclusivamente de tipo `test` o `flashcards`.
- Se refuerza CI para impedir regresiones del estado estable, del contrato de tipos y de los recursos de marca.
- Se añaden icono y logotipo nativos para la presentación de la app en Home Assistant.
- Se conservan todas las correcciones de la fase alpha: Ingress, persistencia multiusuario, sincronización atómica de contenido, estudio adaptativo, simulacros, tema claro/oscuro, recursos sin caché obsoleta e historial de preguntas de examen.

## 0.2.0-alpha.4

- Evita que iOS/Home Assistant reutilice JavaScript y CSS de versiones anteriores: los recursos estáticos llevan versión y se sirven con `no-store`.
- Detecta claro/oscuro a partir del color ya resuelto del iframe por Home Assistant, con `prefers-color-scheme` como fallback.
- Muestra la versión efectiva del add-on en el pie de la pantalla principal.
- Las asignaturas test indican en la portada cuántas preguntas tienen historial de examen, facilitando comprobar que el metadato se ha cargado.

## 0.2.0-alpha.3

- Corrige la sincronización del tema de Home Assistant resolviendo los colores finales dentro del contexto del panel Ingress antes de copiarlos al iframe.
- Mantiene la interfaz sincronizada si el usuario cambia de tema mientras la app está abierta.

## 0.2.0-alpha.2

- La interfaz hereda el tema claro/oscuro y los colores activos de Home Assistant mediante Ingress.
- Las preguntas con `exam_history` muestran una insignia visible de pregunta de examen y sus convocatorias documentadas.
- Los metadatos de historial de examen se conservan desde el JSON hasta la API y la revisión de simulacros.
- Mejora del foco de teclado y uso de colores semánticos del tema para estados de éxito y error.

## 0.2.0-alpha.1

- Primera arquitectura como Home Assistant app/add-on.
- Acceso mediante Ingress.
- Progreso independiente por usuario Home Assistant.
- Estudio inteligente con interfaz simplificada.
- Estudio por tema.
- Flashcards.
- Simulacros persistentes.
- Sincronización automática y atómica del repositorio de contenidos.
