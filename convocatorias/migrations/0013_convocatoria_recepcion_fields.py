from datetime import time

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("convocatorias", "0012_area_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="convocatoria",
            name="fecha_inicio_recepcion",
            field=models.DateField(blank=True, help_text="Fecha de inicio para recibir documentos", null=True),
        ),
        migrations.AddField(
            model_name="convocatoria",
            name="fecha_fin_recepcion",
            field=models.DateField(blank=True, help_text="Fecha límite para recibir documentos", null=True),
        ),
        migrations.AlterField(
            model_name="convocatoria",
            name="fecha_inicio",
            field=models.DateField(help_text="Fecha de inicio de la convocatoria (inscripciones)"),
        ),
        migrations.AlterField(
            model_name="convocatoria",
            name="fecha_fin",
            field=models.DateField(help_text="Fecha fin de la convocatoria (inscripciones)"),
        ),
        migrations.AlterField(
            model_name="convocatoria",
            name="horario",
            field=models.CharField(help_text="Horario de atención (fijo)", max_length=100),
        ),
        migrations.AlterField(
            model_name="convocatoria",
            name="hora_recepcion_inicio",
            field=models.TimeField(default=time(10, 0), help_text="Hora de inicio de recepcion documental"),
        ),
    ]
