PMD_MESSAGE_ES_BY_RULE = {
    'SystemPrintln': 'Evita usar System.out/err; utiliza un logger con niveles.',
    'UnusedPrivateField': 'Evita campos privados sin uso.',
    'UnusedLocalVariable': 'Evita variables locales sin uso.',
    'CompareObjectsWithEquals': 'Usa equals() para comparar referencias de objetos.',
    'UseEqualsToCompareStrings': "Usa equals() para comparar cadenas en lugar de '==' o '!='.",
    'PrimitiveWrapperInstantiation': 'Evita constructores de wrappers; usa valueOf().',
    'CloseResource': 'Asegura cerrar los recursos después de usarlos.',
    'RelianceOnDefaultCharset': 'Especifica el charset explícitamente en lugar del charset por defecto.',
    'AvoidCatchingGenericException': 'Evita capturar Exception genérica; captura excepciones específicas.',
    'AvoidPrintStackTrace': 'Evita printStackTrace(); usa logging estructurado.',
    'TestClassWithoutTestCases': 'La clase parece de pruebas pero no contiene casos de prueba.',
}

SPOTBUGS_MESSAGE_ES_BY_RULE = {
    'DLS_DEAD_LOCAL_STORE': 'Se asigna un valor a una variable local que nunca se utiliza.',
    'DM_DEFAULT_ENCODING': 'Se depende de la codificación por defecto del sistema.',
    'DM_NUMBER_CTOR': 'Se invoca un constructor ineficiente de Number; usa valueOf().',
    'ES_COMPARING_PARAMETER_STRING_WITH_EQ': "Se compara un String usando '==' o '!='.",
    'NP_ALWAYS_NULL': 'Posible desreferenciación de puntero nulo.',
    'NP_NULL_PARAM_DEREF_ALL_TARGETS_DANGEROUS': 'Se pasa null a un parámetro que no debería ser nulo.',
    'OBL_UNSATISFIED_OBLIGATION': 'El método podría no liberar correctamente un recurso o stream.',
    'OS_OPEN_STREAM': 'El método podría no cerrar correctamente un stream abierto.',
    'RV_RETURN_VALUE_IGNORED_NO_SIDE_EFFECT': 'Se ignora el valor de retorno de un método sin efectos secundarios.',
    'UUF_UNUSED_PUBLIC_OR_PROTECTED_FIELD': 'Campo público o protegido sin uso.',
}

MESSAGE_ES_BY_TOOL = {
    'pmd': PMD_MESSAGE_ES_BY_RULE,
    'spotbugs': SPOTBUGS_MESSAGE_ES_BY_RULE,
}


def get_message_es(tool: str, rule: str, default_message: str) -> str:
    tool_catalog = MESSAGE_ES_BY_TOOL.get(tool.lower())
    if not tool_catalog:
        return default_message
    translated = tool_catalog.get(rule)
    return translated or default_message
