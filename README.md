# UNED Study — Home Assistant App

UNED Study is a stable study application for Home Assistant OS. It is distributed as a Home Assistant **app** (formerly add-on) and opens inside Home Assistant through Ingress.

Each subject has exactly one study format: **test** or **flashcards**. The application deliberately does not mix both formats inside the same subject.

## Install

In Home Assistant OS:

1. Open **Settings → Apps → App store**.
2. Open the repositories menu.
3. Add:

   `https://github.com/antoniorani/ha-uned-study`

4. Install **UNED Study**.
5. Start it and enable **Show in sidebar**.

No HACS installation and no files under `custom_components` are required.

## Product philosophy

The study engine can be sophisticated; the interface should not be.

The normal user chooses only:

- the subject;
- **Continue** for smart study;
- optionally a specific **Topic**;
- **Mock exam** for test subjects.

Weak questions, due reviews, new material and academic importance are mixed automatically by the scheduler instead of being exposed as separate study modes.

## Persistence

The app keeps mutable state in its persistent `/data` volume:

- SQLite study progress;
- active sessions;
- cached content;
- content synchronization metadata.

Each Home Assistant user is isolated by the authenticated Ingress user ID.

## Content

Study material remains separate in:

`https://github.com/antoniorani/uned-study-content`

The app synchronizes that repository automatically and validates content before activating it.
