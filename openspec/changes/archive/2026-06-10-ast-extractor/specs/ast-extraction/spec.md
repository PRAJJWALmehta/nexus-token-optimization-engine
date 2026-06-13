## ADDED Requirements

### Requirement: Parse Python source code
The system SHALL use Tree-sitter to parse Python source files and extract functions, classes, and import statements.

#### Scenario: Python class with methods
- **WHEN** a Python file containing a class and methods is processed
- **THEN** the system extracts a class node and child function nodes for its methods.

### Requirement: Parse TypeScript source code
The system SHALL use Tree-sitter to parse TypeScript source files and extract functions, classes, and import statements.

#### Scenario: TypeScript imports and functions
- **WHEN** a TypeScript file with imports and functions is processed
- **THEN** the system extracts import dependency edges and function nodes.

### Requirement: Store AST dependencies in Graphify
The system SHALL store the extracted AST nodes and edges in the local Graphify storage.

#### Scenario: Updating local graph
- **WHEN** the AST extraction completes for a repository
- **THEN** the Graphify storage is updated with the new nodes (functions, classes) and edges (imports, calls).

### Requirement: Graph query endpoint
The system SHALL expose an endpoint to query the extracted AST graph.

#### Scenario: Querying dependencies of a function
- **WHEN** a client requests the dependencies for a specific function node via the API
- **THEN** the system returns a subgraph of nodes that the function depends on.
