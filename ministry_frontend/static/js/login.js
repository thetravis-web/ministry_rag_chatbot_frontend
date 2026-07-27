/* Login logic. Posts to POST /api/login. The mock backend accepts any
   @ict.go.ug-style email + non-empty password and returns a role, so the
   dashboard redirect logic is real even though there's no real user store
   yet — swap in the real User/Role check (see Class Diagram) later. */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("login-form");
  if (!form) return;

  const helpToggle = document.getElementById("login-help-toggle");
  const helpPanel = document.getElementById("login-help-panel");
  if (helpToggle) {
    helpToggle.addEventListener("click", () => {
      helpPanel.classList.toggle("hidden");
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const errorBox = document.getElementById("login-error");
    const btn = document.getElementById("login-submit");

    errorBox.classList.add("hidden");
    btn.disabled = true;
    btn.textContent = "Signing in…";

    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Sign-in failed");
      window.location.href = data.redirect || "/dashboard";
    } catch (err) {
      errorBox.textContent = err.message || "Invalid credentials. Please try again.";
      errorBox.classList.remove("hidden");
      btn.disabled = false;
      btn.textContent = "Sign In to Dashboard";
    }
  });
});
