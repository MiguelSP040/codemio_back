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
    big_o_hint: str
    big_o_reason: str


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
                big_o_hint='Desconocida',
                big_o_reason='No se pudo parsear el archivo para estimar complejidad.',
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
    big_o_hint, big_o_reason = _estimate_file_big_o(parsed_unit)

    return JavaFileSyntaxMetrics(
        file_path=rel_path,
        classes_count=counters['classes_count'],
        methods_count=counters['methods_count'],
        parameters_count=counters['parameters_count'],
        inheritance_count=counters['inheritance_count'],
        interclass_calls_count=counters['interclass_calls_count'],
        big_o_hint=big_o_hint,
        big_o_reason=big_o_reason,
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


def _estimate_file_big_o(parsed_unit) -> tuple[str, str]:
    method_names = _collect_method_names(parsed_unit)
    signals = _collect_big_o_signals(parsed_unit, method_names)
    return _classify_big_o(signals)


def _collect_method_names(parsed_unit) -> set[str]:
    names: set[str] = set()
    for _, node in parsed_unit:
        if isinstance(node, javalang.tree.MethodDeclaration) and getattr(node, 'name', None):
            names.add(node.name)
    return names


def _collect_big_o_signals(parsed_unit, method_names: set[str]) -> dict[str, int | bool]:
    loop_nodes = (
        javalang.tree.ForStatement,
        javalang.tree.WhileStatement,
        javalang.tree.DoStatement,
        javalang.tree.EnhancedForControl,
    )
    signals: dict[str, int | bool] = {
        'loop_count': 0,
        'max_loop_depth': 0,
        'current_loop_depth': 0,
        'has_sort_call': False,
        'has_binary_search_call': False,
        'has_recursive_method': False,
    }

    def walk(node):
        if node is None:
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return

        entered_loop = isinstance(node, loop_nodes)
        if entered_loop:
            signals['loop_count'] += 1
            signals['current_loop_depth'] += 1
            signals['max_loop_depth'] = max(signals['max_loop_depth'], signals['current_loop_depth'])

        if isinstance(node, javalang.tree.MethodInvocation):
            _update_invocation_signals(node, method_names, signals)

        for attr in getattr(node, 'attrs', []) or []:
            walk(getattr(node, attr, None))

        if entered_loop:
            signals['current_loop_depth'] = max(0, signals['current_loop_depth'] - 1)

    walk(parsed_unit)
    return signals


def _update_invocation_signals(node, method_names: set[str], signals: dict[str, int | bool]) -> None:
    member = str(getattr(node, 'member', '') or '').lower()
    if member in {'sort', 'sorted'}:
        signals['has_sort_call'] = True
    if member in {'binarysearch', 'binary_search'}:
        signals['has_binary_search_call'] = True
    qualifier_name = str(getattr(node, 'qualifier', None) or '')
    if member and (member in method_names or qualifier_name in method_names):
        signals['has_recursive_method'] = True


def _classify_big_o(signals: dict[str, int | bool]) -> tuple[str, str]:
    max_loop_depth = int(signals['max_loop_depth'])
    loop_count = int(signals['loop_count'])
    has_recursive_method = bool(signals['has_recursive_method'])
    has_sort_call = bool(signals['has_sort_call'])
    has_binary_search_call = bool(signals['has_binary_search_call'])

    if has_recursive_method and max_loop_depth >= 1:
        return 'O(n^2)', 'Recursión combinada con iteraciones detectadas (estimación conservadora).'
    if max_loop_depth >= 3:
        return 'O(n^3+)', 'Se detectaron 3 o más niveles de ciclos anidados.'
    if max_loop_depth == 2:
        return 'O(n^2)', 'Se detectaron ciclos anidados.'
    if has_sort_call:
        return 'O(n log n)', 'Se detectó llamada a ordenamiento (sort/sorted).'
    if has_binary_search_call:
        return 'O(log n)', 'Se detectó patrón de búsqueda binaria.'
    if max_loop_depth == 1:
        return 'O(n)', 'Se detectó un ciclo principal sobre colecciones/datos.'
    if loop_count == 0:
        return 'O(1)', 'No se detectaron ciclos en el archivo.'
    return 'Desconocida', 'No hubo señales suficientes para estimar complejidad.'
