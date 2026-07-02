document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      const message = form.getAttribute("data-confirm");
      if (!window.confirm(message)) {
        e.preventDefault();
      }
    });
  });

  document.querySelectorAll(".alert[data-autohide]").forEach((el) => {
    setTimeout(() => {
      el.classList.add("fade");
      setTimeout(() => el.remove(), 400);
    }, 4000);
  });
});
