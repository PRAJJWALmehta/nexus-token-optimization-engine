## 1. Setup

- [x] 1.1 Add `tree-sitter`, `tree-sitter-python`, and `tree-sitter-typescript` to `pyproject.toml`
- [x] 1.2 Create `src/ast_extractor` module structure
- [x] 1.3 Create `src/routers/ast.py` router

## 2. Core Implementation

- [x] 2.1 Implement `tree-sitter` language initialization for Python and TypeScript
- [x] 2.2 Write AST extraction logic (S-expressions/visitors) for Python to capture functions, classes, and imports
- [x] 2.3 Write AST extraction logic (S-expressions/visitors) for TypeScript to capture functions, classes, and imports
- [x] 2.4 Implement Graphify storage adapter to save extracted nodes and edges to local Graphify format
- [x] 2.5 Implement the `/api/ast/query` endpoint logic in `src/routers/ast.py` to retrieve subgraphs

## 3. Testing and Verification

- [x] 3.1 Write unit tests for Python AST extraction
- [x] 3.2 Write unit tests for TypeScript AST extraction
- [x] 3.3 Add integration tests for the `/api/ast/query` endpoint
- [x] 3.4 Verify Graphify storage generation works end-to-end on a sample directory
