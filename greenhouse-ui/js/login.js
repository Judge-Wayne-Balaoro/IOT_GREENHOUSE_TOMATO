// Already signed in? Go straight to the dashboard.
if (Auth.token()) location.replace("dashboard.html");

const $ = s => document.querySelector(s);
const form = $("#form"), err = $("#err"), btn = $("#submit");

$("#themeBtn").onclick = toggleTheme;

$("#toggle").onclick = () => {
  const p = $("#pass"), show = p.type === "password";
  p.type = show ? "text" : "password";
  $("#toggle").textContent = show ? "Hide" : "Show";
  $("#toggle").setAttribute("aria-label", show ? "Hide password" : "Show password");
};


form.addEventListener("submit", async e => {
  e.preventDefault();
  err.textContent = "";
  const username = $("#user").value.trim(), password = $("#pass").value;
  if (!username || !password) { err.textContent = "Enter your username and password."; return; }

  btn.disabled = true; btn.textContent = "Signing in...";
  try {
    const session = await Api.login(username, password);
    Auth.save(session, $("#remember").checked);
    location.replace("dashboard.html");
  } catch (ex) {
    err.textContent = ex.message;
    btn.disabled = false; btn.textContent = "Sign in";
    $("#pass").select();
  }
});
