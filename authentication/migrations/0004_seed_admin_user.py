from django.db import migrations
import os
import sys


ADMIN_EMAIL = '20233tn170@utez.edu.mx'
ADMIN_SUB_COGNITO = '04f854d8-4021-707a-131a-da35c70e0e84'
ADMIN_NAME = 'Martín Antonio'
ADMIN_AGE = 21


def seed_admin_user(apps, schema_editor):
    if 'test' in sys.argv or os.getenv('SKIP_ADMIN_SEED', '').strip().lower() in {'1', 'true', 'yes'}:
        return
    usuario_model = apps.get_model('authentication', 'Usuario')
    cognito_user_model = apps.get_model('authentication', 'CognitoUser')
    user, _ = usuario_model.objects.get_or_create(
        correo=ADMIN_EMAIL,
        defaults={
            'rol': 'admin',
            'nombre': ADMIN_NAME,
            'edad': ADMIN_AGE,
            'sub_cognito': ADMIN_SUB_COGNITO,
        },
    )
    fields_to_update = []
    if user.rol != 'admin':
        user.rol = 'admin'
        fields_to_update.append('rol')
    if user.nombre != ADMIN_NAME:
        user.nombre = ADMIN_NAME
        fields_to_update.append('nombre')
    if user.edad != ADMIN_AGE:
        user.edad = ADMIN_AGE
        fields_to_update.append('edad')
    if user.sub_cognito != ADMIN_SUB_COGNITO:
        user.sub_cognito = ADMIN_SUB_COGNITO
        fields_to_update.append('sub_cognito')
    if fields_to_update:
        user.save(update_fields=fields_to_update)

    cognito_user, _ = cognito_user_model.objects.get_or_create(
        email=ADMIN_EMAIL,
        defaults={
            'username': ADMIN_EMAIL,
            'cognito_sub': ADMIN_SUB_COGNITO,
            'status': 'CONFIRMED',
        },
    )
    cognito_fields = []
    if cognito_user.username != ADMIN_EMAIL:
        cognito_user.username = ADMIN_EMAIL
        cognito_fields.append('username')
    if cognito_user.cognito_sub != ADMIN_SUB_COGNITO:
        cognito_user.cognito_sub = ADMIN_SUB_COGNITO
        cognito_fields.append('cognito_sub')
    if cognito_user.status != 'CONFIRMED':
        cognito_user.status = 'CONFIRMED'
        cognito_fields.append('status')
    if cognito_fields:
        cognito_user.save(update_fields=cognito_fields)


def reverse_seed_admin_user(apps, schema_editor):
    usuario_model = apps.get_model('authentication', 'Usuario')
    try:
        user = usuario_model.objects.get(correo=ADMIN_EMAIL)
    except usuario_model.DoesNotExist:
        return
    if user.rol == 'admin':
        user.rol = 'user'
        user.save(update_fields=['rol'])


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0003_usuario_onboarding_nullable'),
    ]

    operations = [
        migrations.RunPython(seed_admin_user, reverse_seed_admin_user),
    ]

