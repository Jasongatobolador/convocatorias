# Generated manually for adding documentos_snapshot to SolicitudRevision.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "convocatorias",
            "0007_rename_convocatori_estado_4dad5a_idx_convocatori_estado_660ee2_idx_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="solicitudrevision",
            name="documentos_snapshot",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
