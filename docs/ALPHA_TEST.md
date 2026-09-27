# UNED Study 0.1.0-alpha.1 — Home Assistant OS test

This checklist is for the first real installation on Home Assistant OS.

## Before installing

1. Create a Home Assistant backup.
2. Confirm the backup includes the Home Assistant configuration directory.
3. Do not delete `/config/uned_study/` when updating the integration. That directory contains the SQLite progress database and the cached content snapshot.
4. The alpha targets Home Assistant 2026.9.x and has CI compatibility coverage against 2026.9.3.

## Manual installation from the release ZIP

The release ZIP contains:

```text
custom_components/
└── uned_study/
    └── ...
```

Extract the ZIP into:

```text
/config/
```

After extraction, this file must exist:

```text
/config/custom_components/uned_study/manifest.json
```

Restart Home Assistant.

## Configure

Go to:

**Settings → Devices & services → Add integration → UNED Study**

Default content source:

- repository: `https://github.com/antoniorani/uned-study-content`
- branch: `main`

The integration should create a **UNED Study** item in the sidebar.

## First-pass acceptance checklist

### Integration lifecycle

- [ ] UNED Study can be added through the UI.
- [ ] The sidebar panel appears without a browser console error.
- [ ] Restarting Home Assistant preserves the config entry.
- [ ] Restarting Home Assistant preserves the sidebar panel.
- [ ] Reconfiguring repository/branch reloads cleanly.

### Content synchronization

- [ ] Admin user sees the GitHub synchronization controls.
- [ ] Non-admin user cannot perform content synchronization.
- [ ] A successful synchronization shows repository, branch and timestamp.
- [ ] A failed synchronization leaves the previous valid content active.
- [ ] Synchronization state survives a Home Assistant restart.

### Users and persistence

Test with at least two Home Assistant users.

- [ ] Each user has independent favorites.
- [ ] Favorite ordering is independent per user.
- [ ] Each user has independent question/card progress.
- [ ] Progress survives a Home Assistant restart.
- [ ] Starting a new session for one user does not affect another user.

### Test study mode

- [ ] Question renders correctly.
- [ ] Markdown renders correctly.
- [ ] Correct answer is not exposed before answering.
- [ ] Explanation appears after answering.
- [ ] Repeated network/UI submission does not double-count progress.
- [ ] Adaptive, due, errors, new and important modes behave sensibly.
- [ ] Topic filtering works.

### Flashcards

- [ ] Front renders before the answer.
- [ ] Back stays hidden until requested.
- [ ] Markdown, hint and mnemonic render.
- [ ] Again / Hard / Good / Easy persist progress.
- [ ] Leaving and returning can continue the active session.

### Mock exam

- [ ] Exam uses the configured question count, capped by the available bank.
- [ ] Timer counts down from the server-provided deadline.
- [ ] Answers can be changed before submission.
- [ ] Previous/next navigation preserves answers.
- [ ] Leaving the panel and returning resumes the same question.
- [ ] Restarting Home Assistant preserves exam answers and current position.
- [ ] No correctness feedback appears before submission.
- [ ] Time expiry forces correction rather than accepting new answers.
- [ ] Final correction shows correct, incorrect and blank questions.
- [ ] Wrong-answer penalty is reflected in the score.
- [ ] Finished answered questions are incorporated into long-term progress.

### Markdown assets

Use at least one subject image.

- [ ] Relative `assets/...` image renders.
- [ ] Image still renders after refreshing the browser.
- [ ] An unauthenticated direct asset URL is not usable without a signed/authenticated path.
- [ ] Unsupported files are not served by the asset endpoint.

### Mobile

- [ ] Dashboard is usable on a phone.
- [ ] Question buttons are comfortably tappable.
- [ ] Flashcard rating controls fit the viewport.
- [ ] Mock-exam timer and navigation remain visible/readable.

## Updating an alpha

Replace:

```text
/config/custom_components/uned_study/
```

with the new release contents and restart Home Assistant.

Do **not** replace or remove:

```text
/config/uned_study/
```

The database has forward migrations. Keep a Home Assistant backup before moving between alpha versions.

## Rollback

For a code-only rollback, restore the previous `custom_components/uned_study` package and restart.

If the newer alpha migrated the SQLite schema beyond what the older package understands, restore the Home Assistant backup instead of manually editing the database.

## Useful diagnostics after a failure

Record:

- Home Assistant Core version;
- UNED Study version;
- whether the failure occurs as admin or non-admin;
- browser/device;
- Home Assistant log lines containing `uned_study`;
- whether the issue survives a full HA restart;
- exact action that triggered the problem.

Do not share authentication tokens, signed asset URLs, or the raw Home Assistant auth database.
