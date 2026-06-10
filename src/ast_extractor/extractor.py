"""AST Extractor Logic using Tree-sitter.

Parses Python and TypeScript source files, extracts entity nodes (functions, classes)
and relationships (contains, imports, calls), and generates a graph-compatible schema.
"""

import os
import re
from tree_sitter import Language, Parser, Node
import tree_sitter_python as tspython
import tree_sitter_typescript as tstypescript

# Initialize tree-sitter Language bindings
PY_LANGUAGE = Language(tspython.language())
TS_LANGUAGE = Language(tstypescript.language_typescript())


class ASTExtractor:
    """Core class to parse source files and extract AST nodes and links."""

    def __init__(self):
        pass

    def parse_file(self, file_path: str) -> dict:
        """Parse a source file and return its nodes and links.

        Parameters
        ----------
        file_path : str
            Path to the source file to parse.

        Returns
        -------
        dict
            Contains "nodes" and "links" arrays compatible with the Graphify storage schema.
        """
        import time
        from src.telemetry import ast_extractions_total, ast_extraction_latency_seconds

        start_time = time.perf_counter()
        language = "python" if file_path.endswith(".py") else "typescript" if file_path.endswith((".ts", ".tsx")) else "unknown"
        status = "success"

        try:
            if not os.path.exists(file_path):
                status = "not_found"
                return {"nodes": [], "links": []}

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                status = "read_error"
                return {"nodes": [], "links": []}

            is_py = file_path.endswith(".py")
            is_ts = file_path.endswith((".ts", ".tsx"))

            if not (is_py or is_ts):
                status = "unsupported"
                return {"nodes": [], "links": []}

            parser = Parser(PY_LANGUAGE if is_py else TS_LANGUAGE)
            try:
                tree = parser.parse(content.encode("utf-8"))
            except Exception:
                status = "parse_error"
                return {"nodes": [], "links": []}

            nodes = []
            links = []

            # Emit the file node itself
            file_id = self._make_file_id(file_path)
            nodes.append({
                "label": os.path.basename(file_path),
                "file_type": "code",
                "source_file": file_path,
                "source_location": "L1",
                "id": file_id,
                "community": 0,
                "norm_label": os.path.basename(file_path).lower()
            })

            imports = []
            # Step 1: Extract imports
            self._extract_imports(tree.root_node, file_path, is_py, imports)

            # Register file-level imports
            for imported_name, resolved_file in imports:
                if resolved_file:
                    target_file_id = self._make_file_id(resolved_file)
                    links.append({
                        "relation": "imports_from",
                        "context": "import",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": file_path,
                        "source_location": "L1",
                        "weight": 1.0,
                        "source": file_id,
                        "target": target_file_id
                    })

            # Step 2: Traverse tree to find class and function/method definitions
            local_entities = {}  # name -> ID

            def collect_definitions(node: Node, parent_class: str = None):
                node_type = node.type
                if is_py:
                    is_class = node_type == "class_definition"
                    is_func = node_type == "function_definition"
                else:
                    is_class = node_type == "class_declaration"
                    is_func = node_type in ("function_declaration", "method_definition")

                if is_class:
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        class_name = name_node.text.decode("utf-8", errors="ignore")
                        class_id = self._make_entity_id(file_path, class_name)
                        start_line = node.start_point[0] + 1
                        local_entities[class_name] = class_id
                        nodes.append({
                            "label": class_name,
                            "file_type": "code",
                            "source_file": file_path,
                            "source_location": f"L{start_line}",
                            "id": class_id,
                            "community": 0,
                            "norm_label": class_name.lower()
                        })
                        # Link file/parent to class
                        links.append({
                            "relation": "contains",
                            "context": "definition",
                            "confidence": "EXTRACTED",
                            "confidence_score": 1.0,
                            "source_file": file_path,
                            "source_location": f"L{start_line}",
                            "weight": 1.0,
                            "source": file_id,
                            "target": class_id
                        })

                        # Recurse inside body
                        body_node = node.child_by_field_name("body")
                        if body_node:
                            # In TS, class body is class_body, in Python it is block
                            for child in body_node.children:
                                collect_definitions(child, parent_class=class_name)

                elif is_func:
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        func_name = name_node.text.decode("utf-8", errors="ignore")
                        label = f".{func_name}()" if parent_class else f"{func_name}()"
                        entity_name = f"{parent_class}_{func_name}" if parent_class else func_name
                        func_id = self._make_entity_id(file_path, entity_name)
                        start_line = node.start_point[0] + 1
                        local_entities[func_name] = func_id
                        if parent_class:
                            local_entities[f"{parent_class}.{func_name}"] = func_id

                        nodes.append({
                            "label": label,
                            "file_type": "code",
                            "source_file": file_path,
                            "source_location": f"L{start_line}",
                            "id": func_id,
                            "community": 0,
                            "norm_label": label.lower()
                        })

                        # Link parent (class or file) to function
                        parent_id = self._make_entity_id(file_path, parent_class) if parent_class else file_id
                        links.append({
                            "relation": "contains",
                            "context": "definition",
                            "confidence": "EXTRACTED",
                            "confidence_score": 1.0,
                            "source_file": file_path,
                            "source_location": f"L{start_line}",
                            "weight": 1.0,
                            "source": parent_id,
                            "target": func_id
                        })

                        # Recurse inside body/children (avoid re-visiting classes/methods inside this recursion directly)
                        for child in node.children:
                            if child.type not in ("class_definition", "class_declaration", "function_definition", "function_declaration", "method_definition"):
                                collect_definitions(child, parent_class=parent_class)
                else:
                    for child in node.children:
                        collect_definitions(child, parent_class=parent_class)

            collect_definitions(tree.root_node)

            # Step 3: Find calls and link them
            def collect_calls(node: Node, current_func_id: str = None, parent_class: str = None):
                node_type = node.type
                if is_py:
                    is_class = node_type == "class_definition"
                    is_func = node_type == "function_definition"
                    is_call = node_type == "call"
                else:
                    is_class = node_type == "class_declaration"
                    is_func = node_type in ("function_declaration", "method_definition")
                    is_call = node_type == "call_expression"

                next_func_id = current_func_id
                next_parent_class = parent_class

                if is_class:
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        next_parent_class = name_node.text.decode("utf-8", errors="ignore")
                    body_node = node.child_by_field_name("body")
                    if body_node:
                        for child in body_node.children:
                            collect_calls(child, current_func_id=current_func_id, parent_class=next_parent_class)
                    return

                elif is_func:
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        func_name = name_node.text.decode("utf-8", errors="ignore")
                        entity_name = f"{parent_class}_{func_name}" if parent_class else func_name
                        next_func_id = self._make_entity_id(file_path, entity_name)
                    for child in node.children:
                        collect_calls(child, current_func_id=next_func_id, parent_class=parent_class)
                    return

                elif is_call and current_func_id:
                    # Extract target name from call
                    func_node = node.child_by_field_name("function")
                    if func_node:
                        target_name = None
                        if func_node.type in ("identifier", "property_identifier"):
                            target_name = func_node.text.decode("utf-8", errors="ignore")
                        elif func_node.type == "attribute":
                            attr_node = func_node.child_by_field_name("attribute")
                            if attr_node:
                                target_name = attr_node.text.decode("utf-8", errors="ignore")
                        elif func_node.type == "member_expression":
                            prop_node = func_node.child_by_field_name("property")
                            if prop_node:
                                target_name = prop_node.text.decode("utf-8", errors="ignore")

                        if target_name:
                            target_id = self._resolve_call_target(target_name, file_path, local_entities, imports)
                            if target_id:
                                start_line = node.start_point[0] + 1
                                links.append({
                                    "relation": "calls",
                                    "context": "call",
                                    "confidence": "EXTRACTED",
                                    "confidence_score": 1.0,
                                    "source_file": file_path,
                                    "source_location": f"L{start_line}",
                                    "weight": 1.0,
                                    "source": current_func_id,
                                    "target": target_id
                                })

                for child in node.children:
                    collect_calls(child, current_func_id=current_func_id, parent_class=parent_class)

            collect_calls(tree.root_node)

            return {"nodes": nodes, "links": links}
        except Exception:
            status = "error"
            raise
        finally:
            ast_extractions_total.labels(language=language, status=status).inc()
            ast_extraction_latency_seconds.labels(language=language).observe(time.perf_counter() - start_time)


    def _make_file_id(self, file_path: str) -> str:
        path = file_path
        if path.startswith("./"):
            path = path[2:]
        # Normalize Windows path separators
        path = path.replace("\\", "/")
        if path.endswith(".py"):
            path = path[:-3]
        elif path.endswith(".ts"):
            path = path[:-3]
        elif path.endswith(".tsx"):
            path = path[:-4]
        return re.sub(r'[^a-zA-Z0-9_]', '_', path).lower()

    def _make_entity_id(self, file_path: str, entity_name: str) -> str:
        file_id = self._make_file_id(file_path)
        if not entity_name:
            return file_id
        # Normalize and clean entity name
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', entity_name).strip('_').lower()
        if not clean_name:
            clean_name = "init"
        return f"{file_id}_{clean_name}"

    def _extract_imports(self, root_node: Node, file_path: str, is_py: bool, imports: list):
        def traverse_imports(node: Node):
            node_type = node.type
            if is_py:
                if node_type == "import_statement":
                    for child in node.children:
                        if child.type in ("dotted_name", "aliased_import"):
                            dotted = child
                            if child.type == "aliased_import":
                                dotted = child.child_by_field_name("name")
                            if dotted:
                                import_str = dotted.text.decode("utf-8", errors="ignore")
                                resolved = self._resolve_import(file_path, import_str)
                                imports.append((import_str, resolved))
                elif node_type == "import_from_statement":
                    module_node = None
                    import_seen = False
                    imported_names = []
                    for child in node.children:
                        if child.type == "dotted_name" and not import_seen:
                            module_node = child
                        elif child.type == "import":
                            import_seen = True
                        elif import_seen and child.type in ("dotted_name", "aliased_import"):
                            dotted = child
                            if child.type == "aliased_import":
                                dotted = child.child_by_field_name("name")
                            if dotted:
                                imported_names.append(dotted.text.decode("utf-8", errors="ignore"))

                    if module_node:
                        module_str = module_node.text.decode("utf-8", errors="ignore")
                        resolved = self._resolve_import(file_path, module_str)
                        for name in imported_names:
                            imports.append((name, resolved))
            else:
                if node_type == "import_statement":
                    source_node = node.child_by_field_name("source")
                    if source_node:
                        source_str = source_node.text.decode("utf-8", errors="ignore").strip('"\'')
                        resolved = self._resolve_import(file_path, source_str)
                        imports.append((source_str, resolved))

            for child in node.children:
                traverse_imports(child)

        traverse_imports(root_node)

    def _resolve_import(self, current_file: str, import_str: str) -> str:
        if not import_str:
            return ""

        import_str = import_str.strip('"\'')
        curr_dir = os.path.dirname(current_file)

        if import_str.startswith('.'):
            dot_count = 0
            while import_str.startswith('.', dot_count):
                dot_count += 1
            rel_path = import_str[dot_count:]

            temp_dir = curr_dir
            for _ in range(dot_count - 1):
                temp_dir = os.path.dirname(temp_dir)

            parts = rel_path.replace('.', '/').split('/')
            target_path = os.path.join(temp_dir, *[p for p in parts if p])
        else:
            parts = import_str.split('.')
            target_path = os.path.join(*parts)

        # Check extensions
        for ext in ['.py', '.ts', '.tsx', '/__init__.py']:
            potential = target_path + ext
            if os.path.exists(potential):
                return potential

        return ""

    def _resolve_call_target(self, target_name: str, file_path: str, local_entities: dict, imports: list) -> str:
        # Resolve target to an ID
        if target_name in local_entities:
            return local_entities[target_name]

        for imp_name, resolved_file in imports:
            if imp_name == target_name and resolved_file:
                return self._make_entity_id(resolved_file, target_name)

        return ""
