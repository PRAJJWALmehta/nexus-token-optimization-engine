## Why

We currently lack a deterministic way to parse the codebase and understand its structure at a fine-grained level (functions, classes, imports). AST extraction using Tree-sitter will allow us to map these entities and their dependencies reliably, storing them locally using Graphify. This enables intelligent querying of codebase context, which is critical for future features like precise dependency analysis and scoped context retrieval.

## What Changes

- Introduce a new module `ast-extractor` to parse source code using Tree-sitter.
- Add Tree-sitter language bindings for Python and TypeScript.
- Implement logic to extract functions, classes, and import statements from ASTs.
- Integrate with Graphify to store the extracted dependency graph locally.
- Implement a graph query endpoint to retrieve scoped context from the AST graph.

## Capabilities

### New Capabilities
- `ast-extraction`: Core capability for extracting ASTs (functions, classes, imports) using Tree-sitter for Python and TypeScript, storing the dependency graph in Graphify, and providing a query endpoint.

### Modified Capabilities

## Impact

- **New Dependencies**: Tree-sitter and its language-specific bindings (Python, TypeScript).
- **Storage**: Graphify will start storing AST-derived nodes and edges.
- **Architecture**: Adds a new foundational layer for code understanding that other modules can query.
