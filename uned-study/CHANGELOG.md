# Changelog

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
