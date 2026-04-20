from rest_framework.throttling import ScopedRateThrottle

class AnalysisScopedRateThrottle(ScopedRateThrottle):

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            usuario = getattr(request.user, 'usuario', None)
            if usuario is not None and getattr(usuario, 'id', None) is not None:
                ident = str(usuario.id)
            else:
                ident = self.get_ident(request)
        else:
            ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident,
        }
