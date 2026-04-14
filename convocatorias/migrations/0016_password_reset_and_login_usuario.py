from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("convocatorias", "0015_area_fecha_registro_date"),
    ]

    operations = [
        migrations.CreateModel(
            name="IntentoLoginUsuario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(max_length=150)),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                ("intentos_fallidos", models.PositiveSmallIntegerField(default=0)),
                ("bloqueado_hasta", models.DateTimeField(blank=True, null=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("username", "ip"), name="uniq_intento_login_usuario"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PasswordResetCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.CharField(max_length=12)),
                ("creado_en", models.DateTimeField(default=django.utils.timezone.now)),
                ("usado", models.BooleanField(default=False)),
                ("intentos_fallidos", models.PositiveSmallIntegerField(default=0)),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reset_codes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["usuario", "creado_en"], name="convocatori_usuario_4a7b36_idx"),
                    models.Index(fields=["usado"], name="convocatori_usado_1a21f0_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PasswordResetAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254)),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                ("creado_en", models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["email", "creado_en"], name="convocatori_email_2502d8_idx"),
                ],
            },
        ),
    ]
