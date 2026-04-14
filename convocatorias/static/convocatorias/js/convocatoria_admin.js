(function () {
    function parseDate(value) {
        if (!value) {
            return null;
        }
        var parts = value.split('-');
        if (parts.length !== 3) {
            return null;
        }
        var year = parseInt(parts[0], 10);
        var month = parseInt(parts[1], 10) - 1;
        var day = parseInt(parts[2], 10);
        var date = new Date(year, month, day);
        if (Number.isNaN(date.getTime())) {
            return null;
        }
        return date;
    }

    function countWeekdays(startDate, endDate) {
        if (!startDate || !endDate || endDate < startDate) {
            return 0;
        }
        var count = 0;
        var current = new Date(startDate.getTime());
        while (current <= endDate) {
            var day = current.getDay();
            if (day !== 0 && day !== 6) {
                count += 1;
            }
            current.setDate(current.getDate() + 1);
        }
        return count;
    }

    function updateTotals() {
        var inicioInput = document.getElementById('id_fecha_inicio_recepcion');
        var finInput = document.getElementById('id_fecha_fin_recepcion');
        var personasInput = document.getElementById('id_personas_maximas_por_dia');
        var diasInput = document.getElementById('id_dias_recepcion');
        var cupoInput = document.getElementById('id_cupo_total_estimado');

        if (!inicioInput || !finInput || !diasInput || !cupoInput) {
            return;
        }

        var inicio = parseDate(inicioInput.value);
        var fin = parseDate(finInput.value);
        var dias = countWeekdays(inicio, fin);
        var personas = parseInt(personasInput && personasInput.value ? personasInput.value : '0', 10);
        if (Number.isNaN(personas) || personas < 0) {
            personas = 0;
        }
        var cupo = dias * personas;

        diasInput.value = dias;
        cupoInput.value = cupo;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var inputs = [
            document.getElementById('id_fecha_inicio_recepcion'),
            document.getElementById('id_fecha_fin_recepcion'),
            document.getElementById('id_personas_maximas_por_dia')
        ];
        inputs.forEach(function (input) {
            if (!input) {
                return;
            }
            input.addEventListener('change', updateTotals);
            input.addEventListener('keyup', updateTotals);
        });
        updateTotals();
    });
})();
