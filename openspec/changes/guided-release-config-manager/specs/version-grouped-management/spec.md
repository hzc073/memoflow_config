## ADDED Requirements

### Requirement: Management view groups release records by version

The local config manager SHALL present release management by normalized version groups instead of flat lists of announcement and localization files.

#### Scenario: Version group combines related records

- **GIVEN** local config contains source announcements, localized announcements, update candidates, legacy `version_info`, and donor references
- **WHEN** the management view loads
- **THEN** the system SHALL group related records by normalized version or release tag
- **AND** each group SHALL include matching source announcements, localized announcements, update candidates, legacy platform entries, GitHub release data when available, and donor references.

#### Scenario: Version grouping prefers stable release identity

- **GIVEN** multiple records can identify a release through `release_tag`, `version`, `updates[].version`, or GitHub tag
- **WHEN** the system assigns records to a version group
- **THEN** it SHALL prefer `release_tag` without a leading `v`, then announcement `version`, then update candidate `version`, then GitHub release tag without a leading `v`
- **AND** it SHALL keep records with conflicting identifiers visible as warnings instead of silently hiding them.

#### Scenario: Version groups are semver-sorted

- **GIVEN** version groups include versions such as `1.0.9`, `1.0.10`, and `1.0.33`
- **WHEN** the management view orders groups
- **THEN** it SHALL sort them using semver-like descending order
- **AND** it SHALL NOT rely on plain string sorting for version order.

### Requirement: Version group actions preserve config integrity

The management view SHALL provide edit and delete actions from the grouped version context while preserving manifest and localization integrity.

#### Scenario: Editing a grouped release keeps related records visible

- **GIVEN** the operator opens a version group
- **WHEN** they edit the source announcement, localized content, update candidates, or donor references
- **THEN** the UI SHALL keep the related records visible within the same version context
- **AND** it SHALL show which `update/` source files will be affected.

#### Scenario: Deleting a grouped announcement updates indexes safely

- **GIVEN** the operator deletes a source announcement from a version group
- **WHEN** the deletion is confirmed
- **THEN** the service SHALL remove the announcement id from `manifest.announcement_ids`
- **AND** it SHALL remove matching entries from `manifest.announcement_tag_index`
- **AND** it SHALL protect against leaving `latest_announcement_id` pointing to a deleted announcement.

#### Scenario: Group status summarizes readiness

- **GIVEN** the management view lists version groups
- **WHEN** a version has missing translations, stale translations, missing download links, unresolved release note links, or GitHub/local version mismatch
- **THEN** the group summary SHALL surface those readiness issues without requiring the operator to inspect every file manually.
