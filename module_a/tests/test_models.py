import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from module_a.models import FunctionNode, DirectEdge, IndirectPoint


def test_function_node_to_dict():
    fn = FunctionNode(
        name="my_func",
        file="src/main.c",
        line_start=42,
        has_body=True,
        body_file="src/main.c",
        body_line_start=42,
        body_line_end=98,
        params=["int x", "const char *name"],
    )
    d = fn.to_dict()
    assert d["name"] == "my_func"
    assert d["file"] == "src/main.c"
    assert d["has_body"] is True
    assert d["body_line_end"] == 98
    assert d["params"] == ["int x", "const char *name"]


def test_function_node_no_body():
    fn = FunctionNode(
        name="external_func",
        file="include/api.h",
        line_start=15,
        has_body=False,
    )
    d = fn.to_dict()
    assert d["has_body"] is False
    assert d["body_file"] is None
    assert d["body_line_start"] is None
    assert d["body_line_end"] is None
    assert d["params"] == []


def test_direct_edge_to_dict():
    edge = DirectEdge(
        caller="main",
        callee="helper",
        file="main.c",
        line=10,
    )
    d = edge.to_dict()
    assert d == {"caller": "main", "callee": "helper", "file": "main.c", "line": 10}


def test_indirect_point_to_dict():
    ip = IndirectPoint(
        uid="a3f2b1c4",
        func="process",
        file="ops.c",
        line=60,
        expression="ops->read",
    )
    d = ip.to_dict()
    assert d["uid"] == "a3f2b1c4"
    assert d["expression"] == "ops->read"


def test_to_dict_json_serializable():
    """All to_dict() outputs must be JSON-serializable."""
    fn = FunctionNode("f", "a.c", 1, True, "a.c", 1, 5, ["int *p"])
    edge = DirectEdge("f", "g", "a.c", 3)
    ip = IndirectPoint("uid1", "f", "a.c", 4, "(*fp)()")
    json.dumps(fn.to_dict())
    json.dumps(edge.to_dict())
    json.dumps(ip.to_dict())
