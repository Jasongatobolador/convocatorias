from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("convocatorias", "0019_convocatoriadocumentoconfiguracion"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="convocatoriadocumentoconfiguracion",
            name="observaciones",
        ),
    ]
