document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("diagnosisForm");
  const resultContainer = document.getElementById("diagnosis-result-container");
  const resultContent = document.getElementById("diagnosis-result-content");
  const feedback = document.getElementById("diagnosisFeedback");

  if (!form || !resultContainer || !resultContent || !feedback) {
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    feedback.classList.remove("hidden");
    feedback.textContent = "Working on your analysis...";

    const formData = new FormData(form);

    try {
      const response = await fetch(form.action || window.location.pathname, {
        method: "POST",
        body: formData,
        headers: {
          "Accept": "application/json"
        }
      });

      const payload = await response.json();
      if (payload.redirect) {
        window.location.href = payload.redirect;
        return;
      }

      if (!response.ok || !payload.success) {
        throw new Error(payload.error || "Something went wrong while generating the analysis.");
      }

      resultContent.innerHTML = payload.html;
      feedback.textContent = "Analysis generated successfully.";
      resultContainer.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      feedback.textContent = error.message;
    }
  });
});
