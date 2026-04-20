from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import javalang


@dataclass(frozen=True)
class JavaFileSyntaxMetrics:
    file_path: str
    classes_count: int
    methods_count: int
    parameters_count: int
    inheritance_count: int
    interclass_calls_count: int


@dataclass(frozen=True)
class JavaSyntaxMetricsResult:
    files: list[JavaFileSyntaxMetrics]
    classes_count: int
    methods_count: int
    parameters_count: int
    inheritance_count: int
    interclass_calls_count: int


def extract_java_syntax_metrics(source_dir: Path) -> JavaSyntaxMetricsResult:
    file_metrics: list[JavaFileSyntaxMetrics] = []
    for file_path in sorted(_iter_java_files(source_dir)):
        rel_path = file_path.relative_to(source_dir).as_posix()
        try:
            source_code = file_path.read_text(encoding='utf-8', errors='ignore')
            parsed = javalang.parse.parse(source_code)
            metrics = _collect_file_metrics(parsed, rel_path)
        except Exception:
            # Fallback seguro para no romper el análisis completo por un archivo inválido.
            metrics = JavaFileSyntaxMetrics(
                file_path=rel_path,
                classes_count=0,
                methods_count=0,
                parameters_count=0,
                inheritance_count=0,
                interclass_calls_count=0,
            )
        file_metrics.append(metrics)

    return JavaSyntaxMetricsResult(
        files=file_metrics,
        classes_count=sum(item.classes_count for item in file_metrics),
        methods_count=sum(item.methods_count for item in file_metrics),
        parameters_count=sum(item.parameters_count for item in file_metrics),
        inheritance_count=sum(item.inheritance_count for item in file_metrics),
        interclass_calls_count=sum(item.interclass_calls_count for item in file_metrics),
    )


def _iter_java_files(source_dir: Path) -> Iterable[Path]:
    for path in source_dir.rglob('*.java'):
        if path.is_file():
            yield path


def _collect_file_metrics(parsed_unit, rel_path: str) -> JavaFileSyntaxMetrics:
    counters = {
        'classes_count': 0,
        'methods_count': 0,
        'parameters_count': 0,
        'inheritance_count': 0,
        'interclass_calls_count': 0,
    }

    for _, node in parsed_unit:
        if not _is_type_declaration(node):
            continue
        counters['classes_count'] += 1
        _update_type_counters(node, counters)

    return JavaFileSyntaxMetrics(
        file_path=rel_path,
        classes_count=counters['classes_count'],
        methods_count=counters['methods_count'],
        parameters_count=counters['parameters_count'],
        inheritance_count=counters['inheritance_count'],
        interclass_calls_count=counters['interclass_calls_count'],
    )


def _is_type_declaration(node) -> bool:
    return isinstance(node, (javalang.tree.ClassDeclaration, javalang.tree.InterfaceDeclaration))


def _update_type_counters(type_node, counters: dict[str, int]) -> None:
    _add_inheritance_count(type_node, counters)
    methods = list(getattr(type_node, 'methods', []) or [])
    ctors = list(getattr(type_node, 'constructors', []) or [])
    counters['methods_count'] += len(methods) + len(ctors)
    counters['parameters_count'] += _sum_parameters(methods) + _sum_parameters(ctors)
    counters['interclass_calls_count'] += _count_interclass_calls(type_node)


def _add_inheritance_count(type_node, counters: dict[str, int]) -> None:
    if not isinstance(type_node, javalang.tree.ClassDeclaration):
        return
    if type_node.extends is not None:
        counters['inheritance_count'] += 1
    if type_node.implements:
        counters['inheritance_count'] += len(type_node.implements)


def _sum_parameters(callables) -> int:
    return sum(len(getattr(item, 'parameters', None) or []) for item in callables)


def _count_interclass_calls(type_node) -> int:
    calls = 0
    for _, node in type_node:
        if not isinstance(node, javalang.tree.MethodInvocation):
            continue
        qualifier = getattr(node, 'qualifier', None)
        if qualifier and qualifier not in ('this', 'super'):
            calls += 1
    return calls
