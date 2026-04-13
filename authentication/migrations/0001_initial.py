from django.db import migrations, models
class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Usuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=255)),
                ('edad', models.IntegerField()),
                ('correo', models.EmailField(db_index=True, max_length=254, unique=True)),
                ('sub_cognito', models.CharField(blank=True, db_index=True, max_length=128, null=True, unique=True)),
                ('perfil_github', models.CharField(blank=True, max_length=255, null=True)),
                ('rol', models.CharField(choices=[('admin', 'Admin'), ('user', 'User')], default='user', max_length=50)),
                ('fecha_registro', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Usuario',
                'verbose_name_plural': 'Usuarios',
                'ordering': ['-fecha_registro'],
            },
        ),
    ]
