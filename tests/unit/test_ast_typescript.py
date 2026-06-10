import os
import pytest
from src.ast_extractor.extractor import ASTExtractor


def test_typescript_extraction(tmp_path):
    code = """import { helper } from "./utils";

class UserManager {
    name: string;
    constructor(name: string) {
        this.name = name;
    }

    getName() {
        return this.name;
    }

    validate() {
        helper();
        this.getName();
    }
}

function topLevelFunc() {
}
"""
    file_path = tmp_path / "user.ts"
    file_path.write_text(code, encoding="utf-8")

    extractor = ASTExtractor()
    result = extractor.parse_file(str(file_path))

    nodes = result["nodes"]
    links = result["links"]

    # Verify nodes
    labels = {n["label"] for n in nodes}
    assert "user.ts" in labels
    assert "UserManager" in labels
    assert ".constructor()" in labels or ".getName()" in labels or ".validate()" in labels
    assert "topLevelFunc()" in labels

    # Verify unique node IDs
    node_ids = {n["id"] for n in nodes}
    file_id = extractor._make_file_id(str(file_path))
    assert file_id in node_ids
    assert f"{file_id}_usermanager" in node_ids
    assert f"{file_id}_usermanager_getname" in node_ids
    assert f"{file_id}_toplevelfunc" in node_ids

    # Verify structural links
    contains_links = [l for l in links if l["relation"] == "contains"]
    assert len(contains_links) >= 3

    # Verify calls
    call_links = [l for l in links if l["relation"] == "calls"]
    # validate() callsgetName()
    assert len(call_links) >= 1
