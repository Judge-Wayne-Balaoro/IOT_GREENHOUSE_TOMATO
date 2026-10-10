// Deployment config. After creating the Render API, replace the placeholder URL below.
const host = window.location.hostname || "127.0.0.1";
const isLocal = host === "localhost" || host === "127.0.0.1";
const deployedApiBase = "https://tomato-greenhouse-api.onrender.com";
window.CONFIG = {
  USE_MOCK: false,
  API_BASE: isLocal ? `http://${host}:8000` : deployedApiBase,
  GREENHOUSE_ID: 6,
  PLANT_ID: 1,
  REFRESH_MS: 10000
};
