"""임의 코드를 실행하지 않는 제한형 사용자 지표 수식 언어."""

from __future__ import annotations

import ast
import math
import re
from typing import Any, Dict, Iterable, List, Mapping, Set


class UserIndicatorLanguage:
    MAX_EXPRESSIONS = 24
    MAX_AST_NODES = 96
    MAX_DEPTH = 12
    BASE_FIELDS = {
        "open", "high", "low", "close", "current_price", "price", "volume",
        "rsi", "atr", "adx", "macd", "macd_signal", "macd_histogram",
        "bb_position", "bb_width", "ma20", "ma50", "ma200",
        "sma20", "sma50", "sma200", "ema20", "ema50", "ema200",
        "volume_sma20", "volume_ratio", "trend_strength", "market_volatility",
    }
    SAFE_FUNCTIONS = {"abs", "min", "max", "clamp", "sma", "ema", "rsi", "atr", "volume_sma"}
    _NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
    _BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)
    _UNARYOPS = (ast.UAdd, ast.USub)

    @classmethod
    def field_key(cls, name: Any) -> str:
        return f"user_{str(name or '').strip().lower()}"

    @classmethod
    def _indicator_key(cls, function: str, args: List[Any]) -> str:
        reference = cls._indicator_reference(function, args)
        return (
            f"custom_{reference['indicator']}_{reference['period']}_"
            f"{reference['timeframe']}_{reference['source']}"
        )

    @classmethod
    def _indicator_reference(cls, function: str, args: List[Any]) -> Dict[str, Any]:
        if function == "atr":
            period = int(args[0]) if args else 14
            timeframe = str(args[1]) if len(args) > 1 else "5m"
            source = str(args[2]) if len(args) > 2 else "close"
        else:
            if not args:
                raise ValueError(f"{function}:period_required")
            period = int(args[0])
            timeframe = str(args[1]) if len(args) > 1 else "5m"
            source = str(args[2]) if len(args) > 2 else ("volume" if function == "volume_sma" else "close")
        if not 2 <= period <= 500:
            raise ValueError(f"{function}:period_out_of_range")
        if timeframe not in {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}:
            raise ValueError(f"{function}:unsupported_timeframe")
        if source not in {"open", "high", "low", "close", "volume"}:
            raise ValueError(f"{function}:unsupported_source")
        return {
            "indicator": function, "period": period,
            "timeframe": timeframe, "source": source,
        }

    @classmethod
    def _depth(cls, node: ast.AST) -> int:
        children = list(ast.iter_child_nodes(node))
        return 1 + (max(cls._depth(item) for item in children) if children else 0)

    @classmethod
    def _literal_args(cls, node: ast.Call) -> List[Any]:
        if node.keywords:
            raise ValueError("keyword_arguments_not_allowed")
        output: List[Any] = []
        for argument in node.args:
            if not isinstance(argument, ast.Constant) or not isinstance(argument.value, (int, float, str)):
                raise ValueError("indicator_arguments_must_be_literals")
            output.append(argument.value)
        return output

    @classmethod
    def parse(cls, expression: Any, *, known_names: Iterable[str] = ()) -> Dict[str, Any]:
        source = str(expression or "").strip()
        if not source or len(source) > 500:
            raise ValueError("empty_or_too_long_expression")
        try:
            tree = ast.parse(source, mode="eval")
        except SyntaxError as exc:
            raise ValueError("invalid_expression_syntax") from exc
        nodes = list(ast.walk(tree))
        if len(nodes) > cls.MAX_AST_NODES or cls._depth(tree) > cls.MAX_DEPTH:
            raise ValueError("expression_complexity_limit")
        dependencies: Set[str] = set()
        indicator_dependencies: Set[str] = set()
        indicator_references: Dict[str, Dict[str, Any]] = {}
        allowed_names = set(cls.BASE_FIELDS) | {str(item) for item in known_names}
        for node in nodes:
            if isinstance(node, (ast.Expression, ast.Load)):
                continue
            if isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)) and abs(float(node.value)) > 1_000_000_000:
                    raise ValueError("constant_out_of_range")
                if isinstance(node.value, str) and len(node.value) > 16:
                    raise ValueError("string_literal_too_long")
                if not isinstance(node.value, (int, float, str)):
                    raise ValueError("unsupported_constant")
                continue
            if isinstance(node, ast.BinOp):
                if not isinstance(node.op, cls._BINOPS):
                    raise ValueError("unsupported_binary_operator")
                if isinstance(node.op, ast.Pow):
                    if not isinstance(node.right, ast.Constant) or not isinstance(node.right.value, (int, float)) or abs(float(node.right.value)) > 8:
                        raise ValueError("power_exponent_out_of_range")
                continue
            if isinstance(node, cls._BINOPS + cls._UNARYOPS):
                continue
            if isinstance(node, ast.UnaryOp):
                if not isinstance(node.op, cls._UNARYOPS):
                    raise ValueError("unsupported_unary_operator")
                continue
            if isinstance(node, ast.Name):
                if node.id not in allowed_names and node.id not in cls.SAFE_FUNCTIONS:
                    raise ValueError(f"unsupported_variable:{node.id}")
                if node.id in allowed_names:
                    dependencies.add(node.id)
                continue
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in cls.SAFE_FUNCTIONS:
                    raise ValueError("unsupported_function")
                if node.func.id in {"sma", "ema", "rsi", "atr", "volume_sma"}:
                    args = cls._literal_args(node)
                    key = cls._indicator_key(node.func.id, args)
                    indicator_dependencies.add(key)
                    indicator_references[key] = cls._indicator_reference(node.func.id, args)
                continue
            raise ValueError(f"unsupported_syntax:{node.__class__.__name__}")
        return {
            "expression": source,
            "dependencies": sorted(dependencies),
            "indicator_dependencies": sorted(indicator_dependencies),
            "indicator_references": [indicator_references[key] for key in sorted(indicator_references)],
            "ast_nodes": len(nodes),
        }

    @classmethod
    def validate_definitions(cls, definitions: Any) -> Dict[str, Any]:
        if definitions in (None, {}, []):
            return {"valid": True, "errors": [], "order": [], "dependencies": {}}
        if isinstance(definitions, list):
            definitions = {str(item.get("name") or ""): item.get("expression") for item in definitions if isinstance(item, Mapping)}
        if not isinstance(definitions, Mapping) or len(definitions) > cls.MAX_EXPRESSIONS:
            return {"valid": False, "errors": ["user_indicators:invalid_definitions"], "order": [], "dependencies": {}}
        names = [str(name).strip().lower() for name in definitions]
        errors: List[str] = []
        if len(set(names)) != len(names):
            errors.append("user_indicators:duplicate_name")
        for name in names:
            if not cls._NAME_RE.fullmatch(name) or name in cls.BASE_FIELDS or name in cls.SAFE_FUNCTIONS:
                errors.append(f"user_indicators:invalid_name:{name}")
        graph: Dict[str, Set[str]] = {}
        details: Dict[str, Any] = {}
        known = set(names)
        for raw_name, expression in definitions.items():
            name = str(raw_name).strip().lower()
            try:
                parsed = cls.parse(expression, known_names=known)
                graph[name] = set(parsed["dependencies"]) & known
                details[name] = parsed
            except ValueError as exc:
                errors.append(f"user_indicators.{name}:{exc}")
        order: List[str] = []
        pending = {name: set(deps) for name, deps in graph.items()}
        while pending:
            ready = sorted(name for name, deps in pending.items() if not deps)
            if not ready:
                errors.append("user_indicators:dependency_cycle")
                break
            for name in ready:
                order.append(name)
                pending.pop(name)
            for deps in pending.values():
                deps.difference_update(ready)
        return {"valid": not errors, "errors": errors, "order": order, "dependencies": details}

    @classmethod
    def evaluate_definitions(cls, definitions: Any, context: Mapping[str, Any]) -> Dict[str, float]:
        validation = cls.validate_definitions(definitions)
        if not validation["valid"]:
            raise ValueError(", ".join(validation["errors"]))
        source_map = dict(definitions or {})
        if isinstance(definitions, list):
            source_map = {str(item.get("name") or "").strip().lower(): item.get("expression") for item in definitions if isinstance(item, Mapping)}
        values: Dict[str, Any] = dict(context or {})
        output: Dict[str, float] = {}

        def indicator(function: str, *args: Any) -> float:
            key = cls._indicator_key(function, list(args))
            value = values.get(key)
            if value is None:
                raise ValueError(f"missing_indicator:{key}")
            return float(value)

        safe_functions = {
            "abs": abs, "min": min, "max": max,
            "clamp": lambda value, low, high: min(max(value, low), high),
            **{name: (lambda *args, _name=name: indicator(_name, *args)) for name in ("sma", "ema", "rsi", "atr", "volume_sma")},
        }
        for name in validation["order"]:
            tree = ast.parse(str(source_map[name]), mode="eval")
            compiled = compile(tree, "<noah-user-indicator>", "eval")
            value = eval(compiled, {"__builtins__": {}}, {**safe_functions, **values})
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"non_finite_result:{name}")
            values[name] = number
            output[cls.field_key(name)] = number
        return output
