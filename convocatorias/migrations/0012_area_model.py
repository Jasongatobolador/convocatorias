from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def _crear_area_por_codigo(area_model, codigo):
    if codigo is None:
        return None
    nombre = f"Area {codigo}"
    area, _ = area_model.objects.get_or_create(
        nombre=nombre,
        defaults={"descripcion": "", "activa": True, "fecha_registro": timezone.now()},
    )
    return area


def forwards(apps, schema_editor):
    Area = apps.get_model("convocatorias", "Area")
    TrabajadorPerfil = apps.get_model("convocatorias", "TrabajadorPerfil")
    SolicitudRevision = apps.get_model("convocatorias", "SolicitudRevision")

    for perfil in TrabajadorPerfil.objects.all():
        area = _crear_area_por_codigo(Area, getattr(perfil, "area", None))
        if area is not None:
            perfil.area_ref_id = area.id
            perfil.save(update_fields=["area_ref"])

    for solicitud in SolicitudRevision.objects.all():
        area = _crear_area_por_codigo(Area, getattr(solicitud, "area_asignada", None))
        if area is not None:
            solicitud.area_asignada_ref_id = area.id
            solicitud.save(update_fields=["area_asignada_ref"])


def backwards(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("convocatorias", "0011_documentousuario_archivo_en_db"),
    ]

    operations = [
        migrations.CreateModel(
            name="Area",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120, unique=True)),
                ("descripcion", models.CharField(blank=True, max_length=255)),
                ("activa", models.BooleanField(default=True)),
                ("fecha_registro", models.DateTimeField(default=timezone.now)),
            ],
            options={
                "verbose_name": "Area",
                "verbose_name_plural": "Areas",
                "ordering": ["nombre"],
            },
        ),
        migrations.AddField(
            model_name="convocatoria",
            name="area",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="convocatorias",
                to="convocatorias.area",
            ),
        ),
        migrations.AddField(
            model_name="trabajadorperfil",
            name="area_ref",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="trabajadores",
                to="convocatorias.area",
            ),
        ),
        migrations.AddField(
            model_name="solicitudrevision",
            name="area_asignada_ref",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="solicitudes_asignadas",
                to="convocatorias.area",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name="trabajadorperfil",
            name="area",
        ),
        migrations.RemoveField(
            model_name="solicitudrevision",
            name="area_asignada",
        ),
        migrations.RenameField(
            model_name="trabajadorperfil",
            old_name="area_ref",
            new_name="area",
        ),
        migrations.RenameField(
            model_name="solicitudrevision",
            old_name="area_asignada_ref",
            new_name="area_asignada",
        ),
    ]
