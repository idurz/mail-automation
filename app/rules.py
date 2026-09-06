from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Any

from .config import Rule
from .email_parser import ParsedEmail
from .rspamd import RspamdResult


class RuleError(ValueError):
    pass


class RuleEvaluator:
    def evaluate(self, rule: Rule, message: ParsedEmail, result: RspamdResult) -> bool:
        expression = rule.condition.strip()
        if expression.lower() == "true":
            return True
        if expression.lower() == "false":
            return False
        context: dict[str, Any] = {
            "score": result.score,
            "required_score": result.required_score,
            "rspamd_action": result.action,
            "subject": message.subject,
            "text": message.text,
            "from_addr": message.from_addr,
            "from_name": message.from_name,
            "to_addr": message.to_addr,
            "size": message.size,
            "symbols": result.symbols,
            "has_symbol": lambda name: name in result.symbols,
            "contains": lambda value, text: str(text).casefold() in str(value).casefold(),
        }
        tree = ast.parse(expression, mode="eval")
        return bool(self._evaluate(tree.body, context))

    def _evaluate(self, node: ast.AST, context: dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name) and node.id in context:
            return context[node.id]
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            values = [bool(self._evaluate(value, context)) for value in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not bool(self._evaluate(node.operand, context))
        if isinstance(node, ast.Compare):
            left = self._evaluate(node.left, context)
            operators: dict[type[ast.AST], Callable[[Any, Any], bool]] = {
                ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
                ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
                ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
                ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
            }
            for operator, comparator in zip(node.ops, node.comparators):
                right = self._evaluate(comparator, context)
                handler = operators.get(type(operator))
                if handler is None or not handler(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Tuple):
            return tuple(self._evaluate(element, context) for element in node.elts)
        if isinstance(node, ast.Dict):
            return {self._evaluate(key, context): self._evaluate(value, context)
                    for key, value in zip(node.keys, node.values)}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "has_symbol" and len(node.args) == 1 and not node.keywords:
                return context["has_symbol"](self._evaluate(node.args[0], context))
            if node.func.id == "contains" and len(node.args) == 2 and not node.keywords:
                return context["contains"](*(self._evaluate(arg, context) for arg in node.args))
            raise RuleError("unsupported function call")
        raise RuleError(f"unsupported expression element: {type(node).__name__}")
