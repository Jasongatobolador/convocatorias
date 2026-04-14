from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError
from pathlib import Path
import re

from .models import Area, Convocatoria, DocumentoCatalogo, DocumentoUsuario, PerfilUsuario


class RegistroForm(forms.Form):
    email = forms.EmailField(label="Correo electrónico")
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise ValidationError("Este correo ya está registrado.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        if p1:
            try:
                validate_password(p1)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self):
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password1"]
        user = User.objects.create_user(username=email, email=email, password=password)
        return user


class PerfilUsuarioForm(forms.ModelForm):
    class Meta:
        model = PerfilUsuario
        fields = ("nombre_completo", "curp", "telefono", "direccion")
        labels = {
            "nombre_completo": "Nombre completo",
            "curp": "CURP",
            "telefono": "Telefono",
            "direccion": "Direccion",
        }


class SubidaDocumentoForm(forms.Form):
    tipo = forms.ChoiceField(choices=DocumentoUsuario.Tipo.choices)
    archivo = forms.FileField()

    MAX_MB = 5
    EXTENSIONES_PERMITIDAS = {"pdf", "jpg", "jpeg", "png"}
    EXTENSIONES_PELIGROSAS = {"exe", "js", "bat", "cmd", "ps1", "sh", "msi", "com", "scr"}

    def __init__(self, *args, documentos_disponibles=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = documentos_disponibles
        if queryset is None:
            queryset = DocumentoCatalogo.objects.filter(activo=True).order_by("orden", "nombre")
        self._codigos_permitidos = [doc.codigo for doc in queryset]
        self.fields["tipo"].choices = [(doc.codigo, doc.nombre) for doc in queryset]

    def clean_tipo(self):
        tipo = self.cleaned_data["tipo"]
        if tipo not in self._codigos_permitidos:
            raise ValidationError("Selecciona un tipo de documento valido.")
        return tipo

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        nombre = Path(archivo.name).name.lower()
        extension = nombre.rsplit(".", 1)[-1] if "." in nombre else ""
        header = archivo.read(16)
        archivo.seek(0)

        if extension in self.EXTENSIONES_PELIGROSAS:
            raise ValidationError("Tipo de archivo bloqueado por seguridad.")

        if extension not in self.EXTENSIONES_PERMITIDAS:
            raise ValidationError("Formato no permitido. Solo PDF, JPG o PNG.")

        if archivo.size > self.MAX_MB * 1024 * 1024:
            raise ValidationError(f"El archivo supera el tamano maximo permitido ({self.MAX_MB}MB).")

        if extension == "pdf":
            if not header.startswith(b"%PDF-"):
                raise ValidationError("El archivo PDF no es valido.")
        else:
            if extension in {"jpg", "jpeg"} and not header.startswith(b"\xff\xd8\xff"):
                raise ValidationError("La cabecera de la imagen JPG/JPEG no es valida.")
            if extension == "png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValidationError("La cabecera de la imagen PNG no es valida.")
            try:
                imagen = Image.open(archivo)
                imagen.verify()
            except (UnidentifiedImageError, OSError):
                raise ValidationError("La imagen no es valida.")
            finally:
                archivo.seek(0)

        # Higiene adicional para evitar nombres manipulados en almacenamiento/descarga.
        base = Path(archivo.name).name
        base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
        archivo.name = base[:255]
        return archivo


class CambiarContrasenaForm(forms.Form):
    password_actual = forms.CharField(
        label="Contraseña actual",
        widget=forms.PasswordInput
    )
    password_nueva = forms.CharField(
        label="Nueva contraseña",
        widget=forms.PasswordInput
    )
    password_nueva_confirmacion = forms.CharField(
        label="Confirmar nueva contraseña",
        widget=forms.PasswordInput
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password_actual(self):
        password_actual = self.cleaned_data["password_actual"]
        if not self.user.check_password(password_actual):
            raise ValidationError("La contraseña actual es incorrecta.")
        return password_actual

    def clean(self):
        cleaned_data = super().clean()
        password_nueva = cleaned_data.get("password_nueva")
        password_nueva_confirmacion = cleaned_data.get("password_nueva_confirmacion")

        if password_nueva and password_nueva_confirmacion and password_nueva != password_nueva_confirmacion:
            self.add_error("password_nueva_confirmacion", "Las contraseñas no coinciden.")

        if password_nueva:
            password_validation.validate_password(password_nueva, self.user)

        return cleaned_data


class TrabajadorLoginForm(forms.Form):
    email = forms.EmailField(label="Correo")
    password = forms.CharField(label="Contrasena", widget=forms.PasswordInput)


class RevisionRechazoForm(forms.Form):
    motivo_rechazo = forms.CharField(
        label="Motivo del rechazo",
        widget=forms.Textarea(attrs={"rows": 4}),
        min_length=10,
    )
    permitir_reenvio = forms.BooleanField(
        label="Permitir correccion y reenvio",
        required=False,
        initial=True,
    )
    plazo_correccion_dias = forms.IntegerField(
        label="Plazo de correccion (dias)",
        min_value=1,
        max_value=30,
        initial=2,
        required=False,
    )

    def clean(self):
        cleaned = super().clean()
        permitir_reenvio = cleaned.get("permitir_reenvio")
        plazo = cleaned.get("plazo_correccion_dias")
        if permitir_reenvio and not plazo:
            self.add_error("plazo_correccion_dias", "Indica cuantos dias tiene para corregir.")
        return cleaned


class FiltroTrabajadorForm(forms.Form):
    area = forms.ModelChoiceField(
        queryset=Area.objects.none(),
        required=False,
        empty_label="Todas las areas",
    )
    convocatoria = forms.ModelChoiceField(
        queryset=Convocatoria.objects.none(),
        required=False,
        empty_label="Todas las convocatorias",
    )
    fecha = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    estado = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Todos"),
            ("pendiente", "Pendiente"),
            ("aceptada", "Aceptada"),
            ("rechazada", "Rechazada"),
            ("vencida", "Vencida"),
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["area"].queryset = Area.objects.filter(activa=True).order_by("nombre")
        self.fields["convocatoria"].queryset = Convocatoria.objects.filter(activa=True).order_by("titulo")

