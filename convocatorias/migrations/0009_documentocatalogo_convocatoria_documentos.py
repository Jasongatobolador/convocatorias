# Generated manually for dynamic documents per convocatoria.

from django.db import migrations, models


BASE_DOCUMENTOS = [
    {
        "codigo": "identificacion_oficial",
        "nombre": "Identificacion oficial",
        "descripcion": "INE, pasaporte o documento oficial vigente.",
    },
    {
        "codigo": "curp",
        "nombre": "CURP",
        "descripcion": "Documento CURP actualizado y legible.",
    },
    {
        "codigo": "comprobante_domicilio",
        "nombre": "Comprobante de domicilio",
        "descripcion": "Recibo reciente con antiguedad maxima de 3 meses.",
    },
]


def cargar_documentos_base(apps, schema_editor):
    Convocatoria = apps.get_model("convocatorias", "Convocatoria")
    DocumentoCatalogo = apps.get_model("convocatorias", "DocumentoCatalogo")

    codigos = []
    for orden, data in enumerate(BASE_DOCUMENTOS, start=1):
        DocumentoCatalogo.objects.update_or_create(
            codigo=data["codigo"],
            defaults={
                "nombre": data["nombre"],
                "descripcion": data["descripcion"],
                "activo": True,
                "orden": orden,
            },
        )
        codigos.append(data["codigo"])

    documentos_base = list(DocumentoCatalogo.objects.filter(codigo__in=codigos))
    for convocatoria in Convocatoria.objects.all():
        if convocatoria.documentos_requeridos.count() == 0:
            convocatoria.documentos_requeridos.add(*documentos_base)


class Migration(migrations.Migration):

    dependencies = [
        ("convocatorias", "0008_solicitudrevision_documentos_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentoCatalogo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.CharField(max_length=50, unique=True)),
                ("nombre", models.CharField(max_length=120)),
                ("descripcion", models.CharField(blank=True, max_length=255)),
                ("activo", models.BooleanField(default=True)),
                ("orden", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Documento del catalogo",
                "verbose_name_plural": "Documentos del catalogo",
                "ordering": ["orden", "nombre"],
            },
        ),
        migrations.AddField(
            model_name="convocatoria",
            name="documentos_requeridos",
            field=models.ManyToManyField(blank=True, help_text="Selecciona los documentos obligatorios para esta convocatoria.", related_name="convocatorias", to="convocatorias.documentocatalogo"),
        ),
        migrations.AlterField(
            model_name="documentousuario",
            name="tipo",
            field=models.CharField(max_length=50),
        ),
        migrations.RunPython(cargar_documentos_base, migrations.RunPython.noop),
    ]
