// Session handling. Token comes from the backend (POST /auth/login).
// "Remember me" -> localStorage (stays after closing browser). Otherwise sessionStorage.
const Auth = (() => {
  const KEY = "gh_session";
  const read = () => {
    try { return JSON.parse(localStorage.getItem(KEY) || sessionStorage.getItem(KEY) || "null"); }
    catch { return null; }
  };
  return {
    save(session, remember) {
      this.clear();
      (remember ? localStorage : sessionStorage).setItem(KEY, JSON.stringify(session));
    },
    get: read,
    token() { const s = read(); return s ? s.token : null; },
    user() { const s = read(); return s ? s.user : null; },
    clear() { localStorage.removeItem(KEY); sessionStorage.removeItem(KEY); },
    // call at the top of protected pages
    require() { if (!this.token()) { location.replace("index.html"); return false; } return true; },
    logout() { this.clear(); location.replace("index.html"); }
  };
})();

// Theme (shared by both pages)
(function () {
  const root = document.documentElement;
  try { const t = localStorage.getItem("gh_theme"); if (t) root.dataset.theme = t; } catch {}
  window.toggleTheme = function () {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme:dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("gh_theme", root.dataset.theme); } catch {}
    window.dispatchEvent(new Event("themechange"));
  };
})();
