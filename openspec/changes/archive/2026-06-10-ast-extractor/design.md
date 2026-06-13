## Context

The `nexus-token-optimization` application currently operates without a fine-grained understanding of the codebase structure. To support advanced context retrieval and dependency analysis, we need deterministic AST parsing. We will use Tree-sitter to parse Python and TypeScript files, extracting entities (functions, classes, imports) and storing them locally using Graphify.

## Goals / Non-Goals

**Goals:**
- Integrate Tree-sitter for AST parsing of Python and TypeScript files.
- Extract functions, classes, and import statements into a structured dependency format.
- Store extracted dependencies using Graphify.
- Provide a graph query endpoint via the FastAPI app.

**Non-Goals:**
- Support for languages other than Python and TypeScript initially.
- Dynamic cross-repository AST resolution.
- Replacing existing text-based vector search mechanisms entirely (AST parsing is complementary).

## Decisions

- **Architecture Integration**: The `ast-extractor` module will be integrated directly into the `nexus-token-optimization` FastAPI app rather than operating as a standalone microservice. This reduces deployment complexity and latency.
- **Tree-sitter Bindings**: We will use the standard `tree-sitter` Python library along with `tree-sitter-python` and `tree-sitter-typescript` packages. This provides the most mature and flexible API for writing custom AST traversal logic.
- **Storage**: Since Graphify is already implemented in the project, we will utilize its storage format (e.g. `graphify-out/graph.json`) to store the AST nodes and edges, allowing existing Graphify tools to query them.
- **Extraction Mechanism**: We will build Tree-sitter query patterns (S-expressions) to efficiently identify functions, classes, and imports rather than manual recursive AST traversal where possible.

## Risks / Trade-offs

- **Risk: Parse Performance on Large Codebases** → Mitigation: Run AST extraction asynchronously and cache the results. Only re-parse files that have changed based on timestamps or hashes.
- **Risk: Memory Consumption with Tree-sitter** → Mitigation: Ensure AST objects are garbage collected after extraction and we only store the metadata (nodes and edges) in Graphify memory.
