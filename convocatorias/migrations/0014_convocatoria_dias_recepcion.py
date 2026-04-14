from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("convocatorias", "0013_convocatoria_recepcion_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="convocatoria",
            name="dias_recepcion",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
