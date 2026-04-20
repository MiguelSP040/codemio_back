from django.db import migrations, models


def fill_null_cognito_sub_with_empty_string(apps, schema_editor):
    cognito_user_model = apps.get_model('authentication', 'CognitoUser')
    cognito_user_model.objects.filter(cognito_sub__isnull=True).update(cognito_sub='')


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0004_seed_admin_user'),
    ]

    operations = [
        migrations.RunPython(fill_null_cognito_sub_with_empty_string, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='cognitouser',
            name='cognito_sub',
            field=models.CharField(blank=True, db_index=True, max_length=128),
        ),
    ]
