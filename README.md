# UNED Study for Home Assistant

UNED Study is a custom Home Assistant integration and sidebar panel for adaptive study with multiple Home Assistant users.

> Development status: early bootstrap. The backend data model, persistence layer, content loader, adaptive scheduler, WebSocket API and a minimal panel are being built first. GitHub content synchronization and the full Markdown renderer will follow.

## Design goals

- One progress history per Home Assistant user.
- Two subject types: multiple-choice tests and development/flashcards.
- Subject content lives outside the application, in versioned JSON files.
- Progress survives Home Assistant restarts and integration updates.
- Importance, past errors and review due dates influence item selection.
- A realistic exam mode can be kept separate from adaptive study mode.

## Repository layout

```text
custom_components/uned_study/
├── __init__.py
├── backup.py
├── config_flow.py
├── const.py
├── database.py
├── manifest.json
├── panel.py
├── websocket.py
├── content/
├── scheduler/
├── frontend/
└── translations/
```

## Local development content

Until GitHub synchronization is implemented, subject folders can be placed in:

```text
/config/uned_study/content/<subject_id>/subject.json
```

The integration scans that directory at startup and exposes valid subjects in the sidebar panel.

## Home Assistant

The implementation targets current Home Assistant releases and is intended primarily for Home Assistant OS installations. It uses a config entry, Home Assistant authentication, a custom sidebar panel and Home Assistant's WebSocket API.

## Data persistence

User progress is stored separately from subject JSON in:

```text
/config/uned_study/uned_study.db
```

The database is never part of the application package, so updating the custom integration does not overwrite study progress.
