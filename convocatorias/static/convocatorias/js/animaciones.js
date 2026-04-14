const hero = document.querySelector(".hero");
if (hero) {
    const bg = hero.getAttribute("data-bg");
    if (bg) hero.style.backgroundImage = `url(${bg})`;
}
