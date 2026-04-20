import uuid
import threading
from django.utils.deprecation import MiddlewareMixin


_request_id_storage = threading.local()


def get_request_id():
    """Get the current request ID from thread-local storage."""
    return getattr(_request_id_storage, 'request_id', None)


class RequestIDMiddleware(MiddlewareMixin):
    """
    Middleware que genera un ID único para cada petición HTTP y lo almacena
    en thread-local storage para que esté disponible en el contexto de logging.
    
    También agrega el request ID al response header 'X-Request-ID'.
    """
    
    def process_request(self, request):
        """Generate and store request ID before processing the request."""
        request_id = str(uuid.uuid4())
        request.id = request_id
        _request_id_storage.request_id = request_id
        return None
    
    def process_response(self, request, response):
        """Add request ID to response headers."""
        request_id = getattr(request, 'id', None)
        if request_id:
            response['X-Request-ID'] = request_id
        return response
    
    def process_exception(self, request, exception):
        """Ensure request ID persists even when exceptions occur."""
        return None
