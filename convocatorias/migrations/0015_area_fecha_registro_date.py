from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("convocatorias", "0014_convocatoria_dias_recepcion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="area",
            name="fecha_registro",
            field=models.DateField(auto_now_add=True),
        ),
    ]
