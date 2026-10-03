## ADDED Requirements

### Requirement: Upload and manage chat attachments
The learning composer SHALL support multiple PNG/JPG/JPEG/WebP, PDF/DOCX/TXT/Markdown attachments through a plus menu or drag and drop, with upload status, errors, retry and removal before sending. It SHALL allow at most six attachments, with a 5 MiB image and 10 MiB document limit.

#### Scenario: Remove an uploaded draft
- **WHEN** the user removes an uploaded attachment before sending
- **THEN** the composer removes it and the backend releases its private asset

#### Scenario: Upload unsupported or excessive content
- **WHEN** an attachment violates format, size, parsing or context limits
- **THEN** the service explicitly rejects it and does not silently truncate content

### Requirement: Understand actual attachment content
The answer service SHALL send decoded image content to a vision model and extracted document text to the configured model, require visible AI processing consent, and keep up to six recent turns of attachment context within explicit limits.

#### Scenario: Ask a question using images and documents
- **WHEN** a user sends valid attachments with a question or without text
- **THEN** the answer analyzes actual image and document content and records the attachment source

#### Scenario: Retry an attachment answer
- **WHEN** a failed answer is retried with the same request key
- **THEN** it retains the original attachment IDs and rejects replacement IDs

#### Scenario: Follow up about earlier attachments
- **WHEN** a user asks a follow-up within the retained context
- **THEN** the answer can use the original image and document contents

### Requirement: Keep attachments private and durable
Attachment upload, reading, deletion and answer publication SHALL enforce ownership and source availability. Sent attachments SHALL remain with history; unsent attachments SHALL expire after 24 hours.

#### Scenario: Read sent attachments
- **WHEN** the owner reloads a conversation and opens an attachment
- **THEN** its history metadata and authenticated content remain available

#### Scenario: Another account requests attachment content
- **WHEN** another account requests an attachment ID
- **THEN** the service rejects access without revealing its content
