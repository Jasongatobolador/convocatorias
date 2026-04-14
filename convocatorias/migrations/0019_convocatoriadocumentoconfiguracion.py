from django.db import migrations, models
import django.db.models.deletion


def poblar_configuracion_desde_m2m(apps, schema_editor):
    Convocatoria = apps.get_model("convocatorias", "Convocatoria")
    ConvocatoriaDocumentoConfiguracion = apps.get_model("convocatorias", "ConvocatoriaDocumentoConfiguracion")

    for convocatoria in Convocatoria.objects.all():
        for documento in convocatoria.documentos_requeridos.all():
            ConvocatoriaDocumentoConfiguracion.objects.get_or_create(
                convocatoria_id=convocatoria.id,
                documento_id=documento.id,
                defaults={
                    "copias": 1,
                    "requiere_original": False,
                    "observaciones": "",
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ("convocatorias", "0018_alinear_estado_modelos"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConvocatoriaDocumentoConfiguracion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("copias", models.PositiveSmallIntegerField(default=1)),
                ("requiere_original", models.BooleanField(default=False)),
                ("observaciones", models.CharField(blank=True, max_length=255)),
                (
                    "convocatoria",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documentos_configurados",
                        to="convocatorias.convocatoria",
                    ),
                ),
                (
                    "documento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="configuraciones_convocatoria",
                        to="convocatorias.documentocatalogo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Documento requerido por convocatoria",
                "verbose_name_plural": "Documentos requeridos por convocatoria",
                "ordering": ["documento__orden", "documento__nombre"],
            },
        ),
        migrations.AddConstraint(
            model_name="convocatoriadocumentoconfiguracion",
            constraint=models.UniqueConstraint(
                fields=("convocatoria", "documento"),
                name="uniq_config_documento_por_convocatoria",
            ),
        ),
        migrations.RunPython(poblar_configuracion_desde_m2m, migrations.RunPython.noop),
    ]
