# UNED Study for Home Assistant

UNED Study is a custom Home Assistant integration and sidebar study application aimed at UNED subjects. It keeps academic content in GitHub while storing each Home Assistant user's study state locally and independently.

> **Status:** `0.1.0-alpha.1`. The core is covered by CI and automated regression tests, but the alpha still requires validation on a real Home Assistant OS instance before it should be treated as stable.

## What is implemented

- Separate progress per authenticated Home Assistant user.
- Persistent SQLite progress under `/config/uned_study/`.
- Test and flashcard subjects.
- JSON subject content synchronized from a GitHub repository.
- Atomic content updates with validation and rollback.
- Markdown study content and protected subject images/assets.
- Favorite subjects with per-user ordering.
- Persistent/restart-safe study sessions.
- Adaptive weighted repetition using importance, errors, due dates and recency.
- Study modes: adaptive, due, errors, new, important and topic-filtered.
- Per-subject and per-topic statistics.
- Timed mock exams with stable question order, saved answers and correction only at submission.
- Wrong-answer penalty support from subject exam metadata.
- SQLite schema migrations and idempotent answer submission.
- English and Spanish integration configuration strings.

## Content repository

Academic material is kept separately in:

`antoniorani/uned-study-content`

Each real subject lives at:

```text
subjects/<subject_id>/
├── subject.json
└── assets/
    └── ...
```

The content repository includes:

- JSON Schema v1;
- examples;
- semantic validation;
- asset validation;
- CI;
- `AGENTS.md` with mandatory rules for LLM/automated content authors.

User progress never belongs in the content repository.

## Persistence

UNED Study stores mutable application data outside the custom integration package:

```text
/config/uned_study/
├── uned_study.db
├── content-sync-state.json
└── content/
    └── ...
```

Updating files under `/config/custom_components/uned_study/` therefore does not replace progress.

## Alpha installation on Home Assistant OS

A tagged alpha release produces a ZIP containing:

```text
custom_components/uned_study/
```

Extract the release ZIP over `/config`, restart Home Assistant, then add **UNED Study** from **Settings → Devices & services → Add integration**.

Before installing or updating an alpha, create a Home Assistant backup.

See [docs/ALPHA_TEST.md](docs/ALPHA_TEST.md) for the full installation, acceptance and rollback checklist.

## Configuration

The default content source is:

```text
https://github.com/antoniorani/uned-study-content
branch: main
```

The source can later be changed with Home Assistant's **Reconfigure** flow without deleting local progress.

## Mock exam behavior

Mock exams are intentionally separate from adaptive study:

- personal weakness/progress does not influence which questions are selected;
- selection is without replacement and weighted only by academic importance;
- the selected order and answers are persisted in the study session;
- correctness is withheld until submission;
- the deadline is server-side;
- answered questions update long-term progress only when the exam is corrected.

The content metadata can define:

```json
{
  "exam": {
    "questions": 20,
    "duration_minutes": 60,
    "wrong_answer_penalty": 0.25
  }
}
```

UNED Study reports the calculated score but does not assume an approval threshold unless the content contract explicitly defines one in a future version.

## Development validation

The pull-request pipeline currently checks:

- Python compilation;
- frontend JavaScript syntax;
- JSON validity;
- installation/import against Home Assistant 2026.9.3 on Python 3.14.2;
- content parser and validation behavior;
- adaptive scheduler behavior;
- SQLite multi-user isolation and persistence;
- SQLite schema migration;
- request idempotency;
- atomic content activation/rollback;
- sync-state persistence;
- mock-exam planning, timing, scoring and session persistence.

## Repository layout

```text
custom_components/uned_study/
├── __init__.py
├── assets.py
├── backup.py
├── config_flow.py
├── const.py
├── database.py
├── exam.py
├── exam_api.py
├── manifest.json
├── panel.py
├── runtime.py
├── sync_api.py
├── websocket.py
├── content/
├── scheduler/
├── frontend/
└── translations/

tests/
tools/
docs/
```

## Release packaging

Tags matching `v*` run the release workflow. The workflow validates the component, builds a manual-install ZIP and creates a GitHub Release. Tags containing `-alpha`, `-beta` or `-rc` are published as prereleases.
