from __future__ import annotations

import re


_EXACT_RULE_TRANSLATIONS: dict[str, str] = {
    "java:S106": "Reemplaza el uso de System.out por un logger.",
    "java:S1118": "Agrega un constructor privado para ocultar el constructor implícito público.",
    "java:S1128": "Elimina las importaciones no utilizadas.",
    "java:S1155": "Usa isEmpty() en lugar de comparar size() con cero.",
    "java:S1197": 'No uses los corchetes de arreglo "[]" después del nombre del tipo.',
    "java:S1698": 'Usa "equals" en lugar de "==" para comparar objetos.',
    "java:S1905": "Elimina este casting innecesario.",
    "java:S6201": "Simplifica el operador ternario redundante.",
    "java:S6202": "Simplifica el instanceof con pattern matching.",
    "java:S6541": "Reduce la complejidad ciclomática de este método.",
    "TestClassWithoutTestCases": "La clase parece de pruebas, pero no contiene casos de prueba.",
    "UnusedPrivateField": "Evita campos privados no utilizados.",
    "SystemPrintln": "Evita usar System.out/err; usa un logger.",
    "SimplifyBooleanReturns": "Este if puede reemplazarse por `return condición;`.",
    "CompareObjectsWithEquals": 'Usa equals() para comparar referencias de objetos.',
    "UseEqualsToCompareStrings": 'Usa equals() para comparar cadenas en lugar de "==" o "!=".',
    "PrimitiveWrapperInstantiation": "No uses `new Integer(...)`; prefiere `Integer.valueOf(...)`.",
    "CollapsibleIfStatements": "Este if puede combinarse con su bloque padre.",
    "AvoidDeeplyNestedIfStmts": "Los if anidados en exceso dificultan la lectura.",
    "SignatureDeclareThrowsException": "Un método/constructor no debería declarar explícitamente java.lang.Exception.",
    "CloseResource": "Asegura cerrar correctamente los recursos después de usarlos.",
    "RelianceOnDefaultCharset": "Especifica un charset en lugar de depender del predeterminado.",
    "UnusedLocalVariable": "Evita variables locales no utilizadas.",
    "AvoidCatchingGenericException": "Evita capturar Exception de forma genérica.",
    "AvoidPrintStackTrace": "Evita printStackTrace(); usa logging estructurado.",
}

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\s*Replace this use of System\.out by a logger\.?\s*$", re.I), "Reemplaza el uso de System.out por un logger."),
    (re.compile(r'File path\s+"([^"]+)"\s+should match package name\s+"([^"]+)"', re.I), 'La ruta del archivo "{0}" no coincide con el nombre del paquete "{1}". Mueve el archivo o cambia el nombre del paquete.'),
    (re.compile(r'^\s*Refactor this method to reduce its Cognitive Complexity', re.I), "Refactoriza este método para reducir la complejidad cognitiva."),
    (re.compile(r'^\s*Refactor this method to reduce its Cyclomatic Complexity', re.I), "Refactoriza este método para reducir la complejidad ciclomática."),
    (re.compile(r'^\s*Use isEmpty\(\) instead of', re.I), "Usa isEmpty() en lugar de comparar el tamaño con cero."),
    (re.compile(r'^\s*Use a StringBuilder', re.I), "Usa StringBuilder en lugar de concatenar cadenas."),
    (re.compile(r'^\s*Avoid (nested )?ternary operators?', re.I), "Evita los operadores ternarios anidados."),
    (re.compile(r'^\s*Potential null pointer', re.I), "Posible referencia nula: valida el valor antes de usarlo."),
    (re.compile(r'^\s*Dead store to', re.I), "Asignación innecesaria detectada; elimina el valor que nunca se usa."),
    (re.compile(r'^\s*Unused (import|variable|field|method)', re.I), "Elemento no utilizado detectado; elimínalo para limpiar el código."),
    (re.compile(r"^\s*Usage of System\.out/err\s*$", re.I), "Evita usar System.out/err; usa un logger."),
    (re.compile(r"^\s*This if statement can be replaced by `return \{condition\};`\s*$", re.I), "Este if puede reemplazarse por `return condición;`."),
    (re.compile(r"^\s*Use equals\(\) to compare object references\.\s*$", re.I), 'Usa equals() para comparar referencias de objetos.'),
    (re.compile(r"^\s*Use equals\(\) to compare strings instead of '(==|!=)'\s*$", re.I), 'Usa equals() para comparar cadenas en lugar de "==" o "!=".'),
    (re.compile(r"^\s*Do not use `new Integer\(\.\.\.\)`, prefer `Integer\.valueOf\(\.\.\.\)`\s*$", re.I), "No uses `new Integer(...)`; prefiere `Integer.valueOf(...)`."),
    (re.compile(r"^\s*This if statement could be combined with its parent\s*$", re.I), "Este if puede combinarse con su bloque padre."),
    (re.compile(r"^\s*Deeply nested if\.\.then statements are hard to read\s*$", re.I), "Los if anidados en exceso dificultan la lectura."),
    (re.compile(r"^\s*A method/constructor should not explicitly throw java\.lang\.Exception\s*$", re.I), "Un método/constructor no debería declarar explícitamente java.lang.Exception."),
    (re.compile(r"^\s*Ensure that resources like this .* are closed after use\s*$", re.I), "Asegura cerrar correctamente los recursos después de usarlos."),
    (re.compile(r"^\s*Specify a character set instead of relying on the default charset\s*$", re.I), "Especifica un charset en lugar de depender del predeterminado."),
    (re.compile(r"^\s*Avoid unused local variables?\s*", re.I), "Evita variables locales no utilizadas."),
    (re.compile(r"^\s*Avoid catching Exception in try-catch block\s*$", re.I), "Evita capturar Exception de forma genérica."),
    (re.compile(r"^\s*Avoid printStackTrace\(\); use a logger call instead\.\s*$", re.I), "Evita printStackTrace(); usa logging estructurado."),
]

_QUICK_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bcode smell\b", re.I), "code smell"),
    (re.compile(r"\bvulnerability\b", re.I), "vulnerabilidad"),
    (re.compile(r"\bvulnerabilities\b", re.I), "vulnerabilidades"),
    (re.compile(r"\bbug\b", re.I), "bug"),
    (re.compile(r"\bbugs\b", re.I), "bugs"),
    (re.compile(r"\bmethod\b", re.I), "método"),
    (re.compile(r"\bclass\b", re.I), "clase"),
    (re.compile(r"\bfile\b", re.I), "archivo"),
    (re.compile(r"\bline\b", re.I), "línea"),
]


def translate_finding_message(*, rule: str, message: str) -> str:
    text = (message or "").strip()
    if not text:
        return ""

    rule_key = (rule or "").strip()
    if rule_key in _EXACT_RULE_TRANSLATIONS:
        return _EXACT_RULE_TRANSLATIONS[rule_key]

    for pattern, template in _PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if match.groups():
            try:
                return template.format(*match.groups())
            except Exception:
                return template
        return template

    translated = text
    for pattern, replacement in _QUICK_REPLACEMENTS:
        translated = pattern.sub(replacement, translated)

    return translated
