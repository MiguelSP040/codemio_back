from django.db import migrations


ADMIN_EMAIL = '20233tn170@utez.edu.mx'
ADMIN_SUB_COGNITO = '04f854d8-4021-707a-131a-da35c70e0e84'
ADMIN_NAME = 'Martín Antonio'
ADMIN_AGE = 21


def seed_admin_user(apps, schema_editor):
    Usuario = apps.get_model('authentication', 'Usuario')
    CognitoUser = apps.get_model('authentication', 'CognitoUser')
    user, created = Usuario.objects.get_or_create(
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

    cognito_user, _ = CognitoUser.objects.get_or_create(
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
    Usuario = apps.get_model('authentication', 'Usuario')
    try:
        user = Usuario.objects.get(correo=ADMIN_EMAIL)
    except Usuario.DoesNotExist:
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

