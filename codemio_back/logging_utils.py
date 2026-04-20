"""
Logging utilities para el sistema de logging centralizado.
"""
import logging
from rest_framework.views import exception_handler as drf_exception_handler


def get_logger(name):
    """
    Utility function para obtener loggers de manera consistente.
    
    Args:
        name: Nombre del logger (típicamente __name__ del módulo)
    
    Returns:
        Logger configurado
    """
    return logging.getLogger(name)


def custom_exception_handler(exc, context):
    """
    Custom exception handler para Django REST Framework que logea todas las excepciones.
    
    Envuelve el exception handler por defecto de DRF y agrega logging automático
    de todas las excepciones con nivel ERROR o CRITICAL dependiendo del tipo.
    
    Args:
        exc: La excepción que fue levantada
        context: Contexto adicional (incluye view, args, kwargs, request)
    
    Returns:
        Response: La respuesta HTTP generada por el handler default de DRF
    """
    logger = logging.getLogger(__name__)
    
    response = drf_exception_handler(exc, context)
    
    if response is not None:
        view = context.get('view', None)
        request = context.get('request', None)
        
        view_name = view.__class__.__name__ if view else 'Unknown'
        method = request.method if request else 'Unknown'
        path = request.path if request else 'Unknown'
        
        extra_info = {
            'view': view_name,
            'method': method,
            'path': path,
            'status_code': response.status_code,
        }
        
        if response.status_code >= 500:
            msg = f"Server error in {view_name}.{method} {path}: {exc}"
            logger.error(msg, exc_info=True, extra=extra_info)
        elif response.status_code >= 400:
            msg = f"Client error in {view_name}.{method} {path}: {exc}"
            logger.warning(msg, extra=extra_info)
    else:
        msg = f"Unhandled exception: {exc}"
        logger.critical(msg, exc_info=True, extra={'exception_type': type(exc).__name__})
    
    return response
