document.addEventListener('DOMContentLoaded', function () {

    const fechaInicio = document.getElementById('id_fecha_inicio_recepcion');
    const fechaFin = document.getElementById('id_fecha_fin_recepcion');
    const personasDia = document.getElementById('id_personas_maximas_por_dia');

    const diasField = document.getElementById('id_dias_recepcion');
    const cupoField = document.getElementById('id_cupo_maximo');

    function calcular() {
        if (fechaInicio.value && fechaFin.value) {
            const inicio = new Date(fechaInicio.value);
            const fin = new Date(fechaFin.value);

            const diff = (fin - inicio) / (1000 * 60 * 60 * 24) + 1;

            if (!isNaN(diff)) {
                diasField.value = diff;

                if (personasDia.value) {
                    cupoField.value = diff * parseInt(personasDia.value, 10);
                }
            }
        }
    }

    fechaInicio.addEventListener('change', calcular);
    fechaFin.addEventListener('change', calcular);
    personasDia.addEventListener('input', calcular);
});
