from django.contrib import admin
from authentication.models import Usuario

@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ('correo', 'nombre', 'rol', 'sub_cognito', 'fecha_registro')
    search_fields = ('correo', 'nombre', 'sub_cognito', 'perfil_github')
    list_filter = ('rol',)
