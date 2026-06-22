function togglePassword(fieldId, toggleButton) {
  const passwordField = document.getElementById(fieldId);
  if (!passwordField || !toggleButton) return;

  if (passwordField.type === "password") {
    passwordField.type = "text";
    toggleButton.setAttribute("aria-label", "Hide password");
    toggleButton.setAttribute("title", "Hide password");
  } else {
    passwordField.type = "password";
    toggleButton.setAttribute("aria-label", "Show password");
    toggleButton.setAttribute("title", "Show password");
  }
}
