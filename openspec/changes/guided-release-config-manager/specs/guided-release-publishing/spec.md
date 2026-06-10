## ADDED Requirements

### Requirement: Version publishing uses a draft-first step flow

The local config manager SHALL guide adding an update version through a draft-first workflow before writing repository files.

#### Scenario: Operator starts a release draft

- **GIVEN** the operator chooses to add an update version
- **WHEN** the release wizard starts
- **THEN** the system SHALL create an in-memory draft containing version announcement data, optional donor changes, optional download link changes, optional localization choices, preview/check state, and publish options
- **AND** it SHALL NOT write `update/` source files merely by entering or editing early steps.

#### Scenario: Wizard contains the required release steps

- **GIVEN** a release draft is active
- **WHEN** the operator progresses through the wizard
- **THEN** the UI SHALL provide steps for new version announcement, donor selection, download link update decision, multilingual translation decision, preview/check, and local publish
- **AND** each step SHALL surface the file targets or config fields it may affect.

### Requirement: Preview and check validate the draft before publish

The system SHALL validate the proposed draft before committing it to local source files.

#### Scenario: Draft validation runs against temporary source

- **GIVEN** a release draft has unsaved changes
- **WHEN** the operator runs preview/check
- **THEN** the service SHALL validate the draft against a temporary `update/` source tree or equivalent overlay
- **AND** it SHALL report validation success, warnings, and blockers before writing repository files.

#### Scenario: Preview shows local write plan

- **GIVEN** a release draft is ready for review
- **WHEN** the preview/check step is displayed
- **THEN** the UI SHALL show the planned writes to `update/manifest.json`, `update/announcements/*.json`, `update/locales/{locale}/announcements/*.json`, `update/donors.json`, `update/assets/*`, and optional `dist/update/latest.json`
- **AND** it SHALL show announcement index changes including `announcement_tag_index`, `announcement_ids`, and `latest_announcement_id` when those fields would change.

### Requirement: Publish writes local files only

The publish step SHALL save local configuration files and SHALL NOT perform repository publishing operations.

#### Scenario: Local publish saves selected source files

- **GIVEN** the operator confirms publish
- **WHEN** the local publish step runs
- **THEN** the service MAY write `update/manifest.json`, `update/announcements/*.json`, `update/locales/{locale}/announcements/*.json`, `update/donors.json`, and `update/assets/*` according to the draft
- **AND** it SHALL run post-save validation on the saved source state.

#### Scenario: Optional build writes generated latest output

- **GIVEN** the operator selects the build option
- **WHEN** local publish completes source writes
- **THEN** the service SHALL run the existing build script to generate `dist/update/latest.json`
- **AND** if the build option is not selected, publish SHALL leave `dist/update/latest.json` unchanged.

#### Scenario: Publish does not push or deploy

- **GIVEN** the operator confirms publish
- **WHEN** the local publish step runs
- **THEN** the service SHALL NOT run `git commit`, `git push`, gh-pages publication, GitHub Actions dispatch, or Cloudflare Worker update calls.
