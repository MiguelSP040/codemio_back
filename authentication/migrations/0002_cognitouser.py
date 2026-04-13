from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CognitoUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(db_index=True, max_length=254, unique=True)),
                ('username', models.CharField(max_length=255)),
                (
                    'cognito_sub',
                    models.CharField(blank=True, db_index=True, max_length=128, null=True),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[('UNCONFIRMED', 'Sin confirmar'), ('CONFIRMED', 'Confirmada')],
                        default='UNCONFIRMED',
                        max_length=20,
                    ),
                ),
            ],
            options={
                'verbose_name': 'Usuario Cognito (flujo)',
                'verbose_name_plural': 'Usuarios Cognito (flujo)',
            },
        ),
    ]
