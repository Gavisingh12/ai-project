document.addEventListener("DOMContentLoaded", () => {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-revealed");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 },
  );

  document.querySelectorAll(".panel, .metric-card, .feature-card, .activity-card, .trust-card, .auth-card").forEach((element) => {
    revealObserver.observe(element);
  });

  document.querySelectorAll(".tilt-card").forEach((card) => {
    card.addEventListener("pointermove", (event) => {
      const rect = card.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      card.style.transform = `perspective(1000px) rotateX(${(-y * 7).toFixed(2)}deg) rotateY(${(x * 8).toFixed(2)}deg) translateY(-2px)`;
    });

    card.addEventListener("pointerleave", () => {
      card.style.transform = "";
    });
  });

  document.querySelectorAll("[data-countup]").forEach((element) => {
    const target = Number(element.dataset.countup || "0");
    let current = 0;
    const duration = 900;
    const start = performance.now();

    const step = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      current = Math.round(target * progress);
      element.textContent = current.toString();
      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        element.textContent = target.toString();
      }
    };

    requestAnimationFrame(step);
  });
});
