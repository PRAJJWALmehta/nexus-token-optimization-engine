import os
import pytest
from src.ast_extractor.extractor import ASTExtractor


def test_python_extraction(tmp_path):
    code = """import os
from math import sin

class Calculator:
    def add(self, a, b):
        return a + b

    def run(self):
        res = self.add(1, 2)
        helper_func()
        return res

def helper_func():
    pass
"""
    file_path = tmp_path / "calc.py"
    file_path.write_text(code, encoding="utf-8")

    extractor = ASTExtractor()
    result = extractor.parse_file(str(file_path))

    nodes = result["nodes"]
    links = result["links"]

    # Verify nodes
    labels = {n["label"] for n in nodes}
    assert "calc.py" in labels
    assert "Calculator" in labels
    assert ".add()" in labels
    assert ".run()" in labels
    assert "helper_func()" in labels

    # Verify unique node IDs
    node_ids = {n["id"] for n in nodes}
    # calc.py ID should be derived
    calc_file_id = extractor._make_file_id(str(file_path))
    assert calc_file_id in node_ids
    assert f"{calc_file_id}_calculator" in node_ids
    assert f"{calc_file_id}_calculator_add" in node_ids
    assert f"{calc_file_id}_calculator_run" in node_ids
    assert f"{calc_file_id}_helper_func" in node_ids

    # Verify structural links (contains)
    contains_links = [l for l in links if l["relation"] == "contains"]
    # File contains Calculator and helper_func, Calculator contains add and run
    assert len(contains_links) == 4

    # Verify calls
    call_links = [l for l in links if l["relation"] == "calls"]
    # calculator_run calls calculator_add and helper_func
    assert len(call_links) == 2
    sources = {l["source"] for l in call_links}
    targets = {l["target"] for l in call_links}
    assert sources == {f"{calc_file_id}_calculator_run"}
    assert targets == {f"{calc_file_id}_calculator_add", f"{calc_file_id}_helper_func"}
