from dataclasses import dataclass
from typing import Optional


@dataclass
class FunctionNode:
    """A function in the call graph."""
    name: str
    file: str
    line_start: int
    has_body: bool
    body_file: Optional[str] = None
    body_line_start: Optional[int] = None
    body_line_end: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file": self.file,
            "line_start": self.line_start,
            "has_body": self.has_body,
            "body_file": self.body_file,
            "body_line_start": self.body_line_start,
            "body_line_end": self.body_line_end,
        }


@dataclass
class DirectEdge:
    """A direct function call edge."""
    caller: str
    callee: str
    file: str
    line: int

    def to_dict(self) -> dict:
        return {
            "caller": self.caller,
            "callee": self.callee,
            "file": self.file,
            "line": self.line,
        }


@dataclass
class IndirectPoint:
    """A function pointer call site."""
    uid: str
    func: str
    file: str
    line: int
    expression: str

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "func": self.func,
            "file": self.file,
            "line": self.line,
            "expression": self.expression,
        }
