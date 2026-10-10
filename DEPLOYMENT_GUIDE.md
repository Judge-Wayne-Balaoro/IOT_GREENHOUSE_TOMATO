# Tomato Greenhouse — Vercel + Render + Neon deployment guide

This is a deployment-prepared copy of the Tomato Greenhouse project. Deploy the static dashboard on Vercel, the FastAPI backend on Render, and PostgreSQL on Neon. The package intentionally excludes real `.env` values and the real `embedded/greenhouse_secrets.py`; never commit secrets.

## Project layout

The repository root should contain:

- `render.yaml`
- `embedded/`
- `greenhouse-ui/`
- `tomato_greenhouse_backend/`
- `.gitignore`

**Important:** upload the contents of this folder to the GitHub repository root, not the enclosing folder itself. `render.yaml` must be in the repo root for Render Blueprint discovery.

## 1. Create a private GitHub repository

1. Download and extract this ZIP.
2. Create a new **private** GitHub repository.
3. Upload/commit the contents of `IOT-Vercel-deployment-ready/` into the repository root.
4. Check that `render.yaml` is visible at the top level of the repository.
5. Do not upload your original local `.env`, `embedded/greenhouse_secrets.py`, Wi-Fi credentials, or real API keys. The `.gitignore` excludes `.env` and `greenhouse_secrets.py`.

## 2. Deploy the frontend to Vercel first

1. Sign in at https://vercel.com/ and choose **Add New → Project**.
2. Import the private GitHub repository and authorize Vercel to access it.
3. On the Configure Project page set:
   - **Root Directory:** `greenhouse-ui`
   - **Framework Preset:** `Other`
   - **Build Command:** override it and leave the field empty (there is no build step for this plain HTML/CSS/JS site)
   - **Output Directory:** `.`
   - **Install Command:** leave blank/default; there is no package.json to install
4. Deploy and copy the production URL, for example `https://your-project.vercel.app`.

The API URL in `greenhouse-ui/js/config.js` is a placeholder at this stage, so the site may load but login/data calls will not work until the backend is deployed and the URL is updated.

## 3. Create the Neon PostgreSQL database

1. Open https://neon.com/ and create a project/database.
2. Open **Connect** / **Connection Details** and copy a PostgreSQL connection string. Keep `sslmode=require` enabled. A pooled connection string is fine for this API.
3. Keep the connection string private. Do not paste it into frontend files or GitHub.

## 4. Deploy the FastAPI backend on Render

1. Open https://render.com/ and choose **New → Blueprint**.
2. Connect the same GitHub repository. Render should find `render.yaml` in the repository root.
3. Review the blueprint; it defines a web service with root directory `tomato_greenhouse_backend`, installs `requirements.txt`, applies Alembic migrations, seeds the expected greenhouse/plant IDs, and starts Uvicorn.
4. Provide values for these environment variables when prompted:

   - `DATABASE_URL`: the full Neon PostgreSQL connection string.
   - `ADMIN_USERNAME`: the username you will use on the dashboard.
   - `ADMIN_PASSWORD`: a long, unique password for dashboard login.
   - `AUTH_SECRET`: a unique random secret of at least 32 characters.
   - `DEVICE_API_KEY`: a second, separate random secret of at least 32 characters. The ESP32 must use this exact same value.
   - `FRONTEND_ORIGINS`: the exact production Vercel origin copied in Step 2, with no trailing slash, e.g. `https://your-project.vercel.app`.

   Generate each random secret separately in Windows PowerShell with:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   Use one generated value for `AUTH_SECRET` and a different one for `DEVICE_API_KEY`. Save them in a password manager or another private location; don't share them in screenshots or commit them to GitHub.

5. Deploy the Blueprint and wait for the build/start process to finish.
6. Open `https://YOUR-API-SERVICE.onrender.com/health`. It should return `{"status":"ok"}`. `/docs` should also load.

If the initial deployment fails, open Render's service **Logs** and look for a missing environment variable, failed database connection, or migration error before retrying.

## 5. Point the Vercel dashboard at Render

1. In the local extracted project, edit `greenhouse-ui/js/config.js`.
2. Replace:

   ```javascript
   const deployedApiBase = "https://YOUR-API-SERVICE.onrender.com";
   ```

   with your real Render service origin, for example:

   ```javascript
   const deployedApiBase = "https://tomato-greenhouse-api.onrender.com";
   ```

   Use your actual hostname and do not add a path after `.onrender.com`.

3. Commit and push this change to GitHub. Vercel should automatically redeploy the frontend.
4. Confirm that Render's `FRONTEND_ORIGINS` matches the exact Vercel production origin. If you change the Vercel production domain, update `FRONTEND_ORIGINS` on Render and redeploy/restart the backend.

## 6. Configure the ESP32-S3

1. In your local copy, create the private settings file from the example:

   ```powershell
   Copy-Item .\embedded\greenhouse_secrets.py.example .\embedded\greenhouse_secrets.py
   ```

2. Edit `embedded/greenhouse_secrets.py` and set:

   ```python
   API_HOST = "YOUR-ACTUAL-SERVICE.onrender.com"  # hostname only; no https://
   API_PORT = 443
   API_USE_TLS = True
   DEVICE_API_KEY = "THE_EXACT_DEVICE_API_KEY_FROM_RENDER"
   ```

   The key must exactly match Render's `DEVICE_API_KEY`. Keep `greenhouse_secrets.py` private and out of GitHub.

3. From the repository root, upload firmware and drivers (replace `COM7` with the actual port):

   ```powershell
   mpremote connect COM7 fs cp .\embedded\main.py :main.py
   mpremote connect COM7 fs cp .\embedded\greenhouse_secrets.py :greenhouse_secrets.py
   mpremote connect COM7 fs cp .\embedded\hcsr04.py :hcsr04.py
   mpremote connect COM7 fs cp .\embedded\ssd1306.py :ssd1306.py
   mpremote connect COM7 fs cp .\embedded\i2c_lcd.py :i2c_lcd.py
   mpremote connect COM7 reset
   ```

   The board's MicroPython firmware must support `ssl.wrap_socket(..., server_hostname=...)` for HTTPS/SNI. If TLS fails, check the board's MicroPython build and serial error first; don't switch the public API to plain HTTP.

## 7. Verify end-to-end

1. Open the Vercel site; sign in with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from Render.
2. Confirm the dashboard loads data from the deployed API.
3. Watch the ESP32 serial output for successful HTTP responses and `[QUEUE] Synced` messages.
4. With the board powered, disconnect Wi-Fi for several sensor intervals. Look for `[QUEUE] Stored` messages.
5. Reconnect Wi-Fi and confirm queued records upload with their original `recorded_at` timestamps and appear only once.
6. Repeat after an ESP32 reset to confirm the pending queue persists on device storage.

Do the first tests while supervised. Automatic watering is still uncalibrated; keep the pump disconnected or its control disabled until you finish soil calibration and verify the relay behavior.

## Operational notes

- `ENV_INTERVAL` is currently 10 seconds for testing. Before running continuously, change it to `300` seconds (five minutes) and redeploy/upload the firmware.
- Existing rows in your local PostgreSQL database are not automatically copied to Neon.
- The old `/greenhouse_logs.jsonl` local archive is not automatically imported into the new pending queue. The pending queue only contains newly captured records saved by this firmware.
- Keep backups of important database data and monitor hosting/database usage and free-tier limits. Render free web services may spin down while idle, which can delay the first API request after inactivity.
