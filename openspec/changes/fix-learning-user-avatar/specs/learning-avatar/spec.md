## ADDED Requirements

### Requirement: Display the current user's configured avatar in learning messages
The learning room SHALL display the current authenticated user's configured avatar in the existing user-message avatar position, using the existing private profile and avatar data access layer.

#### Scenario: User has configured an avatar
- **WHEN** the user opens an existing conversation or sends a new message
- **THEN** the user-message avatar displays the configured image

#### Scenario: Avatar changes
- **WHEN** the user's profile and avatar cache update after an avatar change
- **THEN** the existing user-message avatar updates to the current image

#### Scenario: Avatar is absent or unavailable
- **WHEN** the avatar is unset, deleted, fails to download, or fails to decode
- **THEN** the existing default user icon appears in the same position
