from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from convocatorias.models import (
    PasswordResetAttempt,
    IntentoLoginUsuario,
    IntentoLoginTrabajador,
    PasswordResetCode,
)

class Command(BaseCommand):
    help = "Limpia registros viejos de intentos de login y reset"

    def handle(self, *args, **kwargs):
        limite = timezone.now() - timedelta(hours=24)

        r1 = PasswordResetAttempt.objects.filter(creado_en__lt=limite).delete()[0]
        r2 = IntentoLoginUsuario.objects.filter(actualizado_en__lt=limite).delete()[0]
        r3 = IntentoLoginTrabajador.objects.filter(actualizado_en__lt=limite).delete()[0]
        r4 = PasswordResetCode.objects.filter(creado_en__lt=limite, usado=True).delete()[0]

        self.stdout.write(
            f"Eliminados: {r1} attempts reset, {r2} intentos usuario, "
            f"{r3} intentos trabajador, {r4} códigos usados"
        )
