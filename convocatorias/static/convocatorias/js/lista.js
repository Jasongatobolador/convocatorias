document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.card-bg').forEach(function (bg) {
        var img = bg.getAttribute('data-bg');
        if (!img) {
            return;
        }
        bg.style.backgroundImage = 'url(' + JSON.stringify(img) + ')';
    });
});
