document.addEventListener('DOMContentLoaded', function () {
    var formUnirse = document.getElementById('formUnirse');
    if (!formUnirse) {
        return;
    }

    formUnirse.addEventListener('submit', function (event) {
        if (formUnirse.dataset.documentosCompletos !== 'true') {
            event.preventDefault();
            alert(
                'Tus documentos obligatorios aun no estan completos. Ve al apartado "Perfil y documentos" para cargarlos y poder participar en esta convocatoria.'
            );
        }
    });
});
