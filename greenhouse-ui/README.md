# Tomato Greenhouse - Frontend

Plain HTML + CSS + JavaScript (Chart.js from CDN). No build step.

## Run

Open `index.html` in a browser, or serve the folder:

```
python -m http.server 5500
```

Mock mode is on by default. The mock login remains `admin` / `greenhouse123`, but its credentials are no longer displayed on the sign-in page. Mock mode uses generated readings; exports will contain generated readings until the dashboard is connected to the live backend.

## Files

```
index.html        login page
dashboard.html    main dashboard (needs login)
css/style.css     all styles (light + dark)
js/config.js      USE_MOCK, API_BASE, refresh rate
js/auth.js        session storage, route guard, logout, theme
js/api.js         every backend call (+ mock data)
js/login.js       login form
js/dashboard.js   live values, charts, table
```

## Connect to the backend

1. In `js/config.js` set `USE_MOCK: false` and `API_BASE` to the FastAPI URL.
2. Backend must allow CORS from the frontend origin.

## API the frontend expects (for the backend dev)

All endpoints except login need `Authorization: Bearer <token>`.
On `401` the frontend clears the session and returns to the login page.

### POST /auth/login
Request: `{"username": "admin", "password": "..."}`
Response: `{"access_token": "<jwt>", "user": {"username": "admin", "name": "Admin"}}`
Wrong credentials: `401` with `{"detail": "Wrong username or password."}` (the message is shown to the user).

### GET /readings/latest
```
{
  "timestamp": "2026-10-09T14:30:00Z",
  "temperature": 28.5,
  "humidity": 72,
  "soil_moisture": 55,
  "light_level": 680,
  "plant_height": 24.3,
  "pump_status": false,
  "fan_status": true,
  "grow_light_status": true
}
```

### GET /readings?hours=24
Array of the same object, oldest first. Frontend asks for 6, 24 and 168 hours.
Environment rows are saved every 5 min, plant height every 1 hour.

### GET /device/status
`{"wifi_connected": true}`  (used for the Wi-Fi status text in the header)

Field names are all in one place if you want to rename them: `js/api.js` (mock) and `js/dashboard.js`.


## Excel export

The dashboard has an export panel at the bottom. You can choose Today, a specific day, the last 7 days, the last 30 days, a custom date range, or all available data. Workbook content can be raw readings, daily summaries, weekly summaries, or all three worksheets. Summary sheets include average/minimum/maximum sensor values and device-on counts/percentages.

The export fetches data for the selected date range rather than exporting only the ten rows shown in the table. Demo data is generated for 30 days. Live API export expects `GET /api/readings` and `GET /api/growth` to support `start_date`, `end_date`, and `limit` query parameters; an optional backend patch is included in the delivery package. The current login still uses the existing mock auth until the authentication API is implemented.
