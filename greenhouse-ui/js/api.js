// All calls to FastAPI. Authentication uses a bearer token returned by /auth/login.
const Api = (() => {
  const C = window.CONFIG;
  const qs = values => {
    const params = new URLSearchParams();
    Object.entries(values).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== "") params.set(k, v instanceof Date ? v.toISOString() : String(v)); });
    return params.toString();
  };

  async function request(path, opts = {}) {
    const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    const token = Auth.token();
    if (token && path !== "/auth/login") headers.Authorization = "Bearer " + token;
    let res;
    try {
      res = await fetch(C.API_BASE + path, { ...opts, headers, cache: "no-store" });
    } catch {
      throw new Error("Cannot reach FastAPI. Check that uvicorn is running and API_BASE points to this computer.");
    }
    if (res.status === 401 && path !== "/auth/login") {
      Auth.logout();
      throw new Error("Session expired. Please sign in again.");
    }
    if (!res.ok) {
      let msg = `Request failed (${res.status}).`;
      try { const body = await res.json(); if (body.detail) msg = typeof body.detail === "string" ? body.detail : msg; } catch {}
      const error = new Error(msg); error.status = res.status; throw error;
    }
    return res.json();
  }

  function normalizeLightCondition(value) {
    if (value === null || value === undefined || value === "") return null;
    const n = Number(value);
    if (!Number.isFinite(n)) return null;
    // Current firmware reports digital DO (0=bright, 1=dark).
    // Older database rows may contain analog ADC values from prior tests;
    // flashlight readings were low, while a covered sensor was around 4095.
    if (n === 1 || n > 2000) return 1;
    return 0;
  }

  function normalizeEnvironment(r) {
    return {
      id: r.id,
      timestamp: r.timestamp || r.recorded_at,
      temperature: r.temperature ?? r.temperature_c ?? null,
      humidity: r.humidity ?? r.humidity_percent ?? null,
      soil_moisture: r.soil_moisture ?? r.soil_moisture_percent ?? null,
      light_level: normalizeLightCondition(r.light_level),
      plant_height: r.plant_height ?? null,
      pump_status: r.pump_status ?? null,
      fan_status: r.fan_status ?? null,
      grow_light_status: r.grow_light_status ?? null
    };
  }

  async function getEnvironment(startDate, endDate) {
    const data = await request("/api/readings?" + qs({
      greenhouse_id: C.GREENHOUSE_ID, start_date: startDate, end_date: endDate, limit: 50000
    }));
    return (Array.isArray(data) ? data : []).map(normalizeEnvironment)
      .filter(r => r.timestamp && Number.isFinite(new Date(r.timestamp).getTime()))
      .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  }

  async function growthHistory(startDate, endDate) {
    const data = await request("/api/growth/manual?" + qs({
      plant_id: C.PLANT_ID, start_date: startDate, end_date: endDate, limit: 50000
    }));
    return (Array.isArray(data) ? data : []).map(g => ({
      id: g.id, timestamp: g.recorded_at, height_cm: Number(g.height_cm), notes: g.notes || "", method: "ruler"
    })).filter(g => g.timestamp && Number.isFinite(new Date(g.timestamp).getTime()) && Number.isFinite(g.height_cm))
      .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  }

  // Add the most recent ruler measurement at or before each environmental reading.
  async function fetchRealRange(startDate, endDate) {
    const [envRows, growthRows] = await Promise.all([
      getEnvironment(startDate, endDate),
      growthHistory(null, endDate)
    ]);
    let gi = 0, lastHeight = null;
    return envRows.map(row => {
      const t = new Date(row.timestamp).getTime();
      while (gi < growthRows.length && new Date(growthRows[gi].timestamp).getTime() <= t) {
        lastHeight = growthRows[gi].height_cm;
        gi++;
      }
      return { ...row, plant_height: lastHeight };
    });
  }

  return {
    async login(username, password) {
      const response = await request("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
      return { token: response.access_token, user: response.user || { username, name: username } };
    },

    async latest() {
      let reading = null;
      try { reading = await request("/api/readings/latest?" + qs({ greenhouse_id: C.GREENHOUSE_ID })); }
      catch (error) { if (error.status !== 404) throw error; }
      let height = null;
      try {
        const growth = await request("/api/growth/manual/latest?" + qs({ plant_id: C.PLANT_ID }));
        height = growth.height_cm;
      } catch (error) { if (error.status !== 404) throw error; }
      if (!reading) return { timestamp: new Date().toISOString(), temperature: null, humidity: null, soil_moisture: null, light_level: null, plant_height: height, pump_status: null, fan_status: null, grow_light_status: null };
      return { ...normalizeEnvironment(reading), plant_height: height };
    },

    async history(hours) {
      const end = new Date();
      const start = new Date(end.getTime() - hours * 60 * 60 * 1000);
      return fetchRealRange(start, end);
    },

    async exportHistory(startDate, endDate) {
      return fetchRealRange(startDate, endDate);
    },

    async saveManualHeight({ recorded_at, height_cm, notes }) {
      return request("/api/growth/manual", {
        method: "POST",
        body: JSON.stringify({ plant_id: C.PLANT_ID, recorded_at, height_cm: Number(height_cm), notes: notes || null })
      });
    },

    async growthHistory(startDate = null, endDate = null) {
      return growthHistory(startDate, endDate);
    },

    async ultrasonicTests(startDate = null, endDate = null) {
      const rows = await request("/api/ultrasonic-tests?" + qs({
        plant_id: C.PLANT_ID, start_date: startDate, end_date: endDate, limit: 50000
      }));
      return Array.isArray(rows) ? rows : [];
    },

    async deviceStatus() { return request("/device/status"); }
  };
})();
