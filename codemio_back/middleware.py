import logging
import time
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware para registrar todas las peticiones HTTP con diferentes niveles de logging.
    
    Niveles de logging:
    - DEBUG: Información detallada de headers y tiempos de ejecución
    - INFO: Peticiones exitosas (2xx, 3xx)
    - WARNING: Errores del cliente (4xx)
    - ERROR: Errores del servidor (5xx)
    - CRITICAL: Excepciones no manejadas
    """
    
    SENSITIVE_HEADERS = {
        'HTTP_AUTHORIZATION',
        'HTTP_COOKIE',
        'HTTP_X_API_KEY',
        'HTTP_X_CSRF_TOKEN',
    }
    
    def process_request(self, request):
        """Marca el tiempo de inicio de la petición"""
        request._start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """Registra la petición y respuesta después de procesarla"""
        if not hasattr(request, '_start_time'):
            return response
        
        # Calcular tiempo de ejecución
        duration_ms = int((time.time() - request._start_time) * 1000)
        
        # Obtener información del request
        method = request.method
        path = request.get_full_path()
        status_code = response.status_code
        
        # Obtener IP del cliente (considerando proxies)
        ip_address = self._get_client_ip(request)
        
        # Obtener usuario autenticado
        user_info = self._get_user_info(request)
        
        # Obtener User-Agent
        user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
        
        # Construir mensaje base
        log_message = (
            f"{method} {path} - {status_code} "
            f"({duration_ms}ms) - {user_info} - IP: {ip_address}"
        )
        
        # Determinar nivel de logging según status code
        if 200 <= status_code < 300:
            logger.info(log_message)
        elif 300 <= status_code < 400:
            logger.info(log_message)
        elif 400 <= status_code < 500:
            logger.warning(log_message)
        elif 500 <= status_code < 600:
            logger.error(log_message)
        
        # Logging DEBUG: información adicional de headers
        if logger.isEnabledFor(logging.DEBUG):
            safe_headers = self._get_safe_headers(request)
            logger.debug(
                f"Request details - User-Agent: {user_agent} - "
                f"Headers: {safe_headers}"
            )
        
        return response
    
    def process_exception(self, request, exception):
        """Registra excepciones no manejadas con nivel CRITICAL"""
        if not hasattr(request, '_start_time'):
            request._start_time = time.time()
        
        duration_ms = int((time.time() - request._start_time) * 1000)
        method = request.method
        path = request.get_full_path()
        user_info = self._get_user_info(request)
        ip_address = self._get_client_ip(request)
        
        logger.critical(
            f"Unhandled exception in {method} {path} - {user_info} - "
            f"IP: {ip_address} - Duration: {duration_ms}ms",
            exc_info=True,
            extra={
                'request_method': method,
                'request_path': path,
                'user_info': user_info,
                'ip_address': ip_address,
            }
        )
        
        return None
    
    def _get_client_ip(self, request):
        """
        Obtiene la IP del cliente considerando proxies y load balancers.
        Revisa X-Forwarded-For primero.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # X-Forwarded-For puede contener múltiples IPs, tomar la primera
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'Unknown')
        return ip
    
    def _get_user_info(self, request):
        """Obtiene información del usuario autenticado si existe"""
        if hasattr(request, 'user') and request.user.is_authenticated:
            # Intentar obtener email o username
            if hasattr(request.user, 'email') and request.user.email:
                return f"User: {request.user.email}"
            elif hasattr(request.user, 'username') and request.user.username:
                return f"User: {request.user.username}"
            else:
                return f"User ID: {request.user.pk}"
        return "Anonymous"
    
    def _get_safe_headers(self, request):
        """
        Retorna headers seguros (excluye headers sensibles como Authorization, Cookie, etc.)
        """
        safe_headers = {}
        for header, value in request.META.items():
            if header.startswith('HTTP_') and header not in self.SENSITIVE_HEADERS:
                # Convertir HTTP_ACCEPT a Accept
                header_name = header[5:].replace('_', '-').title()
                # Truncar valores muy largos
                safe_value = str(value)[:200] if len(str(value)) > 200 else str(value)
                safe_headers[header_name] = safe_value
        return safe_headers
