## ADDED Requirements

### Requirement: GitHub-backed dashboard is the default view

The local config manager SHALL open to a dashboard that summarizes GitHub release data and local update configuration state before presenting editing workflows.

#### Scenario: Dashboard loads GitHub and local state

- **GIVEN** the operator opens the local config manager
- **WHEN** the dashboard loads
- **THEN** the UI SHALL display normalized GitHub release information for the configured app repository
- **AND** it SHALL display local configuration state from `update/manifest.json`, `update/announcements/*.json`, `update/locales/{locale}/announcements/*.json`, and `update/donors.json`
- **AND** it SHALL identify whether the latest GitHub release appears synchronized with local update config.

#### Scenario: Dashboard remains useful when GitHub is unavailable

- **GIVEN** GitHub API access fails, is rate-limited, or has no configured token
- **WHEN** the dashboard loads
- **THEN** the UI SHALL show a clear GitHub data error or rate-limit state
- **AND** it SHALL continue to show local configuration state from the repository.

### Requirement: GitHub credentials stay server-side

The system SHALL read GitHub credentials only inside the local service and SHALL NOT expose credentials to browser JavaScript or public update config.

#### Scenario: Token is loaded from environment

- **GIVEN** `MEMOFLOW_CONFIG_GITHUB_TOKEN` is set in the local environment
- **WHEN** the local service fetches GitHub release data
- **THEN** the service SHALL use the token for GitHub API requests
- **AND** the token SHALL NOT be included in any browser response, cached dashboard payload, generated `dist/update/*` file, or `update/` source JSON.

#### Scenario: Repository can be configured locally

- **GIVEN** `MEMOFLOW_CONFIG_GITHUB_REPO` is set
- **WHEN** the dashboard fetches release data
- **THEN** the service SHALL use that repository as the GitHub release source
- **AND** if it is not set, the service SHOULD default to `hzc073/memoflow`.

### Requirement: Dashboard exposes cumulative release download comparisons

The dashboard SHALL compare release download counts using GitHub release asset `download_count` values.

#### Scenario: Per-version downloads are summarized

- **GIVEN** GitHub release data includes assets with `download_count`
- **WHEN** the dashboard renders version comparison charts
- **THEN** it SHALL show cumulative downloads by version
- **AND** it SHALL show cumulative downloads by release asset or inferred platform where asset data is available.

#### Scenario: Historical trends require snapshots

- **GIVEN** the dashboard has only live GitHub release API data
- **WHEN** the operator views download charts
- **THEN** the system SHALL NOT present cumulative GitHub download counts as time-series growth
- **AND** time-series trend charts SHALL require explicit cached snapshots or a later scoped change.
