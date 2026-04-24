from __future__ import annotations

import re

import javalang

_JAVA_SIGNALS = (
    " class ",
    " interface ",
    " enum ",
    " record ",
    " package ",
    " import ",
    "@interface",
)

_NON_JAVA_SHEBANG = re.compile(r"^\s*#!")
_PYTHON_LIKE = re.compile(r"^\s*(def|import|from)\s+[A-Za-z0-9_\.]+\s*", re.MULTILINE)


def validate_java_source_bytes(raw: bytes, *, source_name: str = "archivo.java") -> None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f'El archivo "{source_name}" no es UTF-8 válido.') from exc

    normalized = f" {text.lower()} "
    if not text.strip():
        raise ValueError(f'El archivo "{source_name}" está vacío.')
    if _NON_JAVA_SHEBANG.search(text):
        raise ValueError(f'El archivo "{source_name}" no parece código Java.')
    if _PYTHON_LIKE.search(text) and not any(signal in normalized for signal in _JAVA_SIGNALS):
        raise ValueError(f'El archivo "{source_name}" no parece código Java.')
    if not any(signal in normalized for signal in _JAVA_SIGNALS):
        raise ValueError(f'El archivo "{source_name}" no parece código Java.')

    try:
        parsed = javalang.parse.parse(text)
    except Exception as exc:
        raise ValueError(f'El archivo "{source_name}" no parece código Java válido.') from exc
    if parsed is None:
        raise ValueError(f'El archivo "{source_name}" no parece código Java.')
    has_type_decl = False
    for _, node in parsed:
        if isinstance(
            node,
            (
                javalang.tree.ClassDeclaration,
                javalang.tree.InterfaceDeclaration,
                javalang.tree.EnumDeclaration,
                javalang.tree.AnnotationDeclaration,
            ),
        ):
            has_type_decl = True
            break
    if not has_type_decl:
        raise ValueError(f'El archivo "{source_name}" no contiene declaraciones Java analizables.')
