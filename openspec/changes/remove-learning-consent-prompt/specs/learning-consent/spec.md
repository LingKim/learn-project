## ADDED Requirements

### Requirement: Learning chat without a consent prompt
The learning room SHALL allow authenticated users to ask questions and upload chat attachments without displaying or requiring the learning AI processing consent prompt. It SHALL NOT automatically create consent records on the user's behalf.

#### Scenario: A user has no learning consent record
- **WHEN** an authenticated user enters the learning room and submits text or supported attachments
- **THEN** the room does not display the consent prompt and the absence of a consent record does not block upload or answers

#### Scenario: Existing consent records
- **WHEN** the prompt is removed
- **THEN** existing records remain unchanged and the application does not automatically create new records

#### Scenario: Scope boundaries
- **WHEN** this change is implemented
- **THEN** ownership, file validation and source checks remain in place and content-library document processing is unchanged
