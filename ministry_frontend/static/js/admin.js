document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("tr[data-role-id] input[type='checkbox']").forEach((checkbox) => {
    checkbox.addEventListener("change", async () => {
      const row = checkbox.closest("tr[data-role-id]");
      const roleId = row.getAttribute("data-role-id");
      const payload = {};
      row.querySelectorAll("input[data-permission]").forEach((input) => {
        payload[input.getAttribute("data-permission")] = input.checked;
      });

      checkbox.disabled = true;
      try {
        const res = await fetch(`/api/roles/${roleId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Could not update role.");
        showToast("Role permissions updated");
      } catch (err) {
        checkbox.checked = !checkbox.checked;
        showToast(err.message || "Role update failed", "error");
      } finally {
        checkbox.disabled = false;
      }
    });
  });

  document.querySelectorAll(".user-role-select").forEach((select) => {
    select.addEventListener("change", async () => {
      const userId = select.getAttribute("data-user-id");
      const previous = select.getAttribute("data-current-role") || select.value;
      select.disabled = true;
      try {
        const res = await fetch(`/api/users/${userId}/role`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role: select.value }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Could not update user role.");
        select.setAttribute("data-current-role", select.value);
        showToast("User role updated");
      } catch (err) {
        select.value = previous;
        showToast(err.message || "User role update failed", "error");
      } finally {
        select.disabled = false;
      }
    });
    select.setAttribute("data-current-role", select.value);
  });
});
