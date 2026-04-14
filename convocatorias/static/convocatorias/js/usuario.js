document.addEventListener('DOMContentLoaded', function () {
    var modal = document.getElementById('fileModal');
    var modalBody = document.getElementById('fileModalBody');
    var modalTitle = document.getElementById('fileModalTitle');
    var closeModalBtn = document.getElementById('closeFileModal');

    if (!modal || !modalBody || !modalTitle || !closeModalBtn) {
        return;
    }

    function clearModalBody() {
        while (modalBody.firstChild) {
            modalBody.removeChild(modalBody.firstChild);
        }
    }

    function closeModal() {
        modal.setAttribute('aria-hidden', 'true');
        clearModalBody();
    }

    function openModal() {
        modal.setAttribute('aria-hidden', 'false');
    }

    document.querySelectorAll('.view-file-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var url = btn.dataset.fileUrl || '';
            var ext = (btn.dataset.fileExtension || '').toLowerCase();
            var name = btn.dataset.fileName || 'Archivo';
            modalTitle.textContent = name;
            clearModalBody();

            if (['jpg', 'jpeg', 'png'].includes(ext)) {
                var img = document.createElement('img');
                img.src = url;
                img.alt = name;
                img.className = 'modal-image';
                modalBody.appendChild(img);
            } else {
                var frame = document.createElement('iframe');
                frame.src = url;
                frame.title = name;
                frame.className = 'modal-frame';
                frame.loading = 'lazy';
                modalBody.appendChild(frame);
            }

            openModal();
        });
    });

    document.querySelectorAll('.replace-file-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var inputId = btn.dataset.target;
            var input = document.getElementById(inputId);
            if (input) {
                input.click();
            }
        });
    });

    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            var message = form.dataset.confirm || '¿Deseas continuar?';
            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });

    closeModalBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', function (event) {
        if (event.target === modal) {
            closeModal();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && modal.getAttribute('aria-hidden') === 'false') {
            closeModal();
        }
    });
});
