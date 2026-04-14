# Generated manually to expand available documents in catalog.

from django.db import migrations


DOCUMENTOS_ADICIONALES = [
    ("identificacion_oficial", "Identificacion oficial", "INE, pasaporte o documento oficial vigente.", 1),
    ("curp", "CURP", "Documento CURP actualizado y legible.", 2),
    ("comprobante_domicilio", "Comprobante de domicilio", "Recibo reciente con antiguedad maxima de 3 meses.", 3),
    ("rfc", "RFC", "Constancia de situacion fiscal vigente.", 4),
    ("constancia_fiscal", "Constancia fiscal", "Documento emitido por SAT.", 5),
    ("plan_negocios", "Plan de negocios", "Plan o resumen ejecutivo del negocio.", 6),
    ("fotografia_negocio", "Fotografia del negocio", "Imagenes de fachada o interior del negocio.", 7),
    ("fotografias_vivienda", "Fotografias de vivienda", "Imagenes del inmueble solicitado.", 8),
    ("croquis_ubicacion", "Croquis de ubicacion", "Croquis con referencias para localizar domicilio o negocio.", 9),
    ("carta_compromiso", "Carta compromiso", "Carta firmada por la persona solicitante.", 10),
    ("evidencia_fotografica_producto", "Evidencia fotografica del producto", "Fotos claras del producto o servicio.", 11),
    ("estado_cuenta", "Estado de cuenta", "Estado de cuenta bancario reciente.", 12),
]


def expandir_catalogo(apps, schema_editor):
    DocumentoCatalogo = apps.get_model("convocatorias", "DocumentoCatalogo")
    for codigo, nombre, descripcion, orden in DOCUMENTOS_ADICIONALES:
        DocumentoCatalogo.objects.update_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "descripcion": descripcion,
                "activo": True,
                "orden": orden,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("convocatorias", "0009_documentocatalogo_convocatoria_documentos"),
    ]

    operations = [
        migrations.RunPython(expandir_catalogo, migrations.RunPython.noop),
    ]
