from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("convocatorias", "0010_expandir_catalogo_documentos"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentousuario",
            name="archivo_binario",
            field=models.BinaryField(blank=True, default=b""),
        ),
        migrations.AddField(
            model_name="documentousuario",
            name="archivo_mime",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="documentousuario",
            name="archivo_nombre",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="documentousuario",
            name="archivo_tamano",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RemoveField(
            model_name="documentousuario",
            name="archivo",
        ),
    ]
