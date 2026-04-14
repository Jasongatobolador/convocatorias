from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("convocatorias", "0016_password_reset_and_login_usuario"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventoAuditoria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("evento", models.CharField(max_length=80)),
                ("descripcion", models.CharField(max_length=255)),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=255)),
                ("datos", models.JSONField(blank=True, default=dict)),
                ("creado_en", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="eventos_auditoria",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Evento de auditoria",
                "verbose_name_plural": "Eventos de auditoria",
                "ordering": ["-creado_en"],
            },
        ),
        migrations.AddIndex(
            model_name="eventoauditoria",
            index=models.Index(fields=["evento", "creado_en"], name="convocatori_evento_d9c8f6_idx"),
        ),
        migrations.AddIndex(
            model_name="eventoauditoria",
            index=models.Index(fields=["usuario", "creado_en"], name="convocatori_usuario_7dc28f_idx"),
        ),
    ]
