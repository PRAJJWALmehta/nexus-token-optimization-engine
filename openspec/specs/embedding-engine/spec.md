## ADDED Requirements

### Requirement: Local sentence embedding engine
The system SHALL provide an embedding engine that loads the `all-MiniLM-L6-v2` model at application startup and encodes text strings into 384-dimensional float vectors.

#### Scenario: Embedding engine initializes at startup
- **WHEN** the application starts with caching enabled
- **THEN** the system SHALL load the `all-MiniLM-L6-v2` model into memory and make it available for embedding requests within the application process

#### Scenario: Text string is embedded into a vector
- **WHEN** the embedding engine receives a text string
- **THEN** the system SHALL return a 384-dimensional numpy array of float32 values representing the semantic embedding of the input text

#### Scenario: Empty or whitespace-only input
- **WHEN** the embedding engine receives an empty string or whitespace-only string
- **THEN** the system SHALL return a zero vector of 384 dimensions

#### Scenario: Embedding engine unavailable at startup
- **WHEN** the `all-MiniLM-L6-v2` model fails to load (e.g., missing files, memory error)
- **THEN** the system SHALL log an error, disable caching, and continue operating in pass-through mode without the embedding engine
