from django.core.management.base import BaseCommand
from django.utils import timezone

from convocatorias.models import Inscripcion, NotificacionUsuario, SolicitudRevision


class Command(BaseCommand):
    help = "Marca solicitudes vencidas y libera cupos automaticamente."

    def handle(self, *args, **options):
        ahora = timezone.now()
        vencidas = (
            SolicitudRevision.objects.select_related("inscripcion", "inscripcion__usuario")
            .filter(
                estado=SolicitudRevision.Estado.RECHAZADA,
                plazo_correccion_limite__lt=ahora,
            )
        )
        total = 0
        for solicitud in vencidas:
            solicitud.estado = SolicitudRevision.Estado.VENCIDA
            solicitud.inscripcion.estado = Inscripcion.Estado.CANCELADA
            solicitud.inscripcion.save(update_fields=["estado"])
            solicitud.save(update_fields=["estado"])
            NotificacionUsuario.objects.create(
                usuario=solicitud.inscripcion.usuario,
                titulo="Solicitud vencida",
                mensaje="Tu plazo de correccion vencio y perdiste el lugar en la convocatoria.",
            )
            total += 1

        self.stdout.write(self.style.SUCCESS(f"Solicitudes vencidas actualizadas: {total}"))
