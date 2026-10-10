# Tomato Greenhouse - ESP32 MicroPython
import time,json,socket,network,ntptime,os,machine,ssl
from machine import Pin,ADC,SoftI2C
import dht
from hcsr04 import HCSR04
import ssd1306

# GPIO
OLED_SDA,OLED_SCL=12,13
DHT_PIN=4
US_TRIG,US_ECHO=5,6
SOIL_PIN,LDR_PIN=7,8
PUMP_RELAY,FAN_RELAY,LIGHT_RELAY=9,10,11
ON,OFF=0,1

VERSION="1.2-offline-queue"

# IDs
GREENHOUSE_ID=6
PLANT_ID=1

# Soil calibration (temporary)
SOIL_DRY_RAW=3500
SOIL_WET_RAW=1500
SOIL_PUMP_ON=40
PUMP_RUN_TIME=5
PUMP_COOLDOWN=300

# Fan
FAN_TEMP_ON,FAN_TEMP_OFF=27,25
FAN_HUM_ON,FAN_HUM_OFF=80,75

# Grow light schedule
LIGHT_ON_HOUR=6
LIGHT_OFF_HOUR=22

# Plant height calibration
SENSOR_TO_SOIL_CM=80.0

# Recording
ENV_INTERVAL=10        # test value; change to 300 later
API_SELF_TEST=False      # disabled after API connectivity was verified
HEIGHT_INTERVAL=3600
# Pending records remain here until the API acknowledges them.
# The old /greenhouse_logs.jsonl archive is left untouched for compatibility.
PENDING_FILE="/greenhouse_pending.jsonl"
PENDING_TMP_FILE="/greenhouse_pending.tmp"
PENDING_BACKUP_FILE="/greenhouse_pending.bak"
SYNC_INTERVAL=5
SYNC_BATCH_SIZE=5

# Public HTTPS backend configuration is stored in greenhouse_secrets.py.
# Copy greenhouse_secrets.py.example to greenhouse_secrets.py and set the real values.
try:
    import greenhouse_secrets as _gh_secrets
    API_HOST = _gh_secrets.API_HOST
    API_PORT = getattr(_gh_secrets, "API_PORT", 443)
    API_USE_TLS = getattr(_gh_secrets, "API_USE_TLS", True)
    DEVICE_API_KEY = _gh_secrets.DEVICE_API_KEY
except Exception as _secrets_error:
    # This fallback is useful for a clear setup error; do not deploy these placeholders.
    API_HOST = "YOUR-API-SERVICE.onrender.com"
    API_PORT = 443
    API_USE_TLS = True
    DEVICE_API_KEY = "REPLACE_WITH_THE_DEVICE_API_KEY_FROM_RENDER"
    print("[CONFIG ERROR] Create embedded/greenhouse_secrets.py from the example before deployment:", _secrets_error)

READING_PATH="/api/readings"
GROWTH_PATH="/api/ultrasonic-tests"

# Wi-Fi
WIFI_FILE="/wifi.json"
SETUP_AP_NAME="Greenhouse-Setup"
SETUP_AP_PASSWORD="greenhouse123"
WIFI_RETRY_INTERVAL=10
TIMEZONE_OFFSET=8*60*60

# OLED
i2c=SoftI2C(scl=Pin(OLED_SCL),sda=Pin(OLED_SDA))
try:
    oled=ssd1306.SSD1306_I2C(128,64,i2c)
    oled_ok=True
except Exception as e:
    oled=None
    oled_ok=False
    print("[OLED ERROR]",e)

# Sensors
dht_sensor=dht.DHT11(Pin(DHT_PIN))
ultrasonic=HCSR04(trigger_pin=US_TRIG,echo_pin=US_ECHO,echo_timeout_us=10000)
soil_adc=ADC(Pin(SOIL_PIN))
soil_adc.atten(ADC.ATTN_11DB)
ldr_pin=Pin(LDR_PIN,Pin.IN)

# Relays: active-low
pump_relay=Pin(PUMP_RELAY,Pin.OUT)
fan_relay=Pin(FAN_RELAY,Pin.OUT)
light_relay=Pin(LIGHT_RELAY,Pin.OUT)
pump_relay.value(OFF)
fan_relay.value(OFF)
light_relay.value(OFF)

# State
pump_state=False
fan_state=False
grow_light_state=False
pump_start=0
pump_cooldown_until=0
last_env=time.ticks_ms()
last_height=time.ticks_ms()
last_wifi_attempt=time.ticks_ms()
api_test_attempted=False
last_sync_attempt=time.ticks_ms()
event_counter=0

# Network interfaces
sta=network.WLAN(network.STA_IF)
ap=network.WLAN(network.AP_IF)

# Wi-Fi credentials
def save_wifi(ssid,password):
    try:
        with open(WIFI_FILE,"w") as f:
            json.dump({"ssid":ssid,"password":password},f)
        return True
    except Exception as e:
        print("[WIFI SAVE ERROR]",e)
        return False

def load_wifi():
    try:
        with open(WIFI_FILE,"r") as f:
            d=json.load(f)
        return d.get("ssid"),d.get("password","")
    except:
        return None,None

def connect_wifi(timeout=15):
    ssid,password=load_wifi()
    if not ssid:
        return False

    sta.active(True)
    try:
        sta.disconnect()
    except:
        pass
    time.sleep(1)

    try:
        sta.connect(ssid,password)
    except Exception as e:
        print("[WIFI ERROR]",e)
        return False

    start=time.ticks_ms()
    while not sta.isconnected():
        if time.ticks_diff(time.ticks_ms(),start)>=timeout*1000:
            print("[WIFI] Connection failed")
            return False
        time.sleep_ms(250)

    print("[WIFI] Connected:",sta.ifconfig()[0])
    return True

def sync_time():
    if not sta.isconnected():
        return False
    for _ in range(3):
        try:
            ntptime.settime()
            print("[TIME] Synced")
            return True
        except Exception as e:
            print("[TIME ERROR]",e)
            time.sleep(2)
    return False

def timestamp():
    t=time.localtime(time.time()+TIMEZONE_OFFSET)
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        t[0],t[1],t[2],t[3],t[4],t[5]
    )

def api_timestamp():
    return timestamp().replace(" ","T")+"+08:00"

def current_hour():
    return time.localtime(time.time()+TIMEZONE_OFFSET)[3]

def scan_wifi():
    try:
        nets=sta.scan()
    except:
        return []
    found={}
    for n in nets:
        try:
            ssid=n[0].decode("utf-8","ignore")
        except:
            ssid=""
        if ssid:
            if ssid not in found or n[3]>found[ssid]:
                found[ssid]=n[3]
    return sorted(found.items(),key=lambda x:x[1],reverse=True)

def url_decode(v):
    v=v.replace("+"," ")
    out=""
    i=0
    while i<len(v):
        if v[i]=="%" and i+2<len(v):
            try:
                out+=chr(int(v[i+1:i+3],16))
                i+=3
            except:
                out+=v[i]
                i+=1
        else:
            out+=v[i]
            i+=1
    return out

def get_query(path,key):
    if "?" not in path:
        return None
    for item in path.split("?",1)[1].split("&"):
        if "=" in item:
            k,v=item.split("=",1)
            if url_decode(k)==key:
                return url_decode(v)
    return None

def setup_page():
    options=""
    for ssid,rssi in scan_wifi():
        safe=(ssid.replace("&","&amp;").replace("<","&lt;")
              .replace(">","&gt;").replace('"',"&quot;"))
        options+=f'<option value="{safe}">{safe} ({rssi} dBm)</option>'
    if not options:
        options='<option value="">No networks found</option>'
    return """<!DOCTYPE html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Greenhouse Wi-Fi</title>
<style>
body{font-family:Arial;padding:20px;background:#f2f2f2}
.box{max-width:420px;margin:auto;background:white;padding:20px;border-radius:12px}
select,input,button{width:100%;padding:12px;margin-top:10px;box-sizing:border-box}
button{background:#222;color:white;border:0;border-radius:6px}
</style></head><body><div class="box"><h2>Greenhouse Wi-Fi</h2>
<form action="/save"><select name="ssid">""" + options + """</select>
<input type="password" name="password" placeholder="Wi-Fi password">
<button>Connect</button></form></div></body></html>"""

def start_setup_mode():
    pump_relay.value(OFF)
    fan_relay.value(OFF)
    light_relay.value(OFF)
    sta.active(True)
    ap.active(True)
    try:
        ap.config(essid=SETUP_AP_NAME,password=SETUP_AP_PASSWORD)
    except Exception as e:
        print("[AP ERROR]",e)
    time.sleep(2)

    print("[WIFI] Setup:",SETUP_AP_NAME)
    print("[WIFI] Password:",SETUP_AP_PASSWORD)
    print("[WIFI] IP:",ap.ifconfig()[0])

    server=socket.socket()
    server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    server.bind(("0.0.0.0",80))
    server.listen(1)
    server.settimeout(0.5)
    connected=False

    while not connected:
        try:
            client,_=server.accept()
        except OSError:
            continue
        try:
            req=client.recv(2048).decode("utf-8","ignore")
            path=req.split("\r\n")[0].split(" ")[1]
            if path.startswith("/save"):
                ssid=get_query(path,"ssid")
                password=get_query(path,"password") or ""
                if ssid and save_wifi(ssid,password):
                    client.send(
                        "HTTP/1.1 200 OK\r\nContent-Type:text/html\r\n"
                        "Connection:close\r\n\r\n<h2>Connecting...</h2>"
                    )
                    client.close()
                    ap.active(False)
                    connected=connect_wifi(15)
                    if connected:
                        sync_time()
                        break
                    ap.active(True)
            else:
                client.send(
                    "HTTP/1.1 200 OK\r\nContent-Type:text/html\r\n"
                    "Connection:close\r\n\r\n"+setup_page()
                )
        except Exception as e:
            print("[WIFI SETUP ERROR]",e)
        try:
            client.close()
        except:
            pass

    server.close()
    ap.active(False)


def initialize_wifi():
    ssid, _ = load_wifi()
    if not ssid:
        start_setup_mode()
        return sta.isconnected()
    if connect_wifi():
        sync_time()
        return True
    print("[WIFI] Saved network unavailable. Running offline.")
    return False

def maintain_wifi():
    global last_wifi_attempt
    if sta.isconnected():
        return True
    now=time.ticks_ms()
    if time.ticks_diff(now,last_wifi_attempt)<WIFI_RETRY_INTERVAL*1000:
        return False
    last_wifi_attempt=now
    print("[WIFI] Reconnecting...")
    if connect_wifi(8):
        sync_time()
        print("[WIFI] Reconnected")
        return True
    print("[WIFI] Still offline")
    return False

# Sensor reads
def read_dht():
    try:
        dht_sensor.measure()
        return dht_sensor.temperature(),dht_sensor.humidity()
    except Exception as e:
        print("[DHT ERROR]",e)
        return None,None

def read_soil():
    try:
        return soil_adc.read()
    except Exception as e:
        print("[SOIL ERROR]",e)
        return None

def soil_percent(raw):
    if raw is None or SOIL_DRY_RAW==SOIL_WET_RAW:
        return None
    p=(SOIL_DRY_RAW-raw)*100/(SOIL_DRY_RAW-SOIL_WET_RAW)
    return round(max(0,min(100,p)),1)

def read_ldr():
    # This is the module's digital DO output: LOW=bright, HIGH=dark.
    try:
        return ldr_pin.value()
    except Exception as e:
        print("[LDR ERROR]",e)
        return None

def ldr_status(light):
    if light is None:
        return "N/A"
    return "Dark" if int(light) == 1 else "Bright"

def read_ultrasonic():
    try:
        return ultrasonic.distance_cm()
    except Exception as e:
        print("[ULTRASONIC ERROR]",e)
        return None

def plant_height(distance):
    if distance is None:
        return None
    return round(max(0,SENSOR_TO_SOIL_CM-distance),1)

# Pump
def control_pump(soil):
    global pump_state,pump_start,pump_cooldown_until
    now=time.ticks_ms()
    if pump_state:
        if time.ticks_diff(now,pump_start)>=PUMP_RUN_TIME*1000:
            pump_relay.value(OFF)
            pump_state=False
            pump_cooldown_until=time.ticks_add(now,PUMP_COOLDOWN*1000)
            print("[PUMP] OFF")
        return pump_state
    if time.ticks_diff(now,pump_cooldown_until)<0 or soil is None:
        return False
    if soil<SOIL_PUMP_ON:
        pump_relay.value(ON)
        pump_state=True
        pump_start=now
        print("[PUMP] ON")
        return True
    pump_relay.value(OFF)
    return False

# Fan
def control_fan(temp,hum):
    global fan_state
    if temp is None or hum is None:
        fan_relay.value(OFF)
        fan_state=False
        return False
    if temp>FAN_TEMP_ON or hum>FAN_HUM_ON:
        fan_relay.value(ON)
        fan_state=True
    elif temp<=FAN_TEMP_OFF and hum<=FAN_HUM_OFF:
        fan_relay.value(OFF)
        fan_state=False
    return fan_state

# Grow light
def control_light():
    global grow_light_state
    h=current_hour()
    grow_light_state=LIGHT_ON_HOUR<=h<LIGHT_OFF_HOUR
    light_relay.value(ON if grow_light_state else OFF)
    return grow_light_state

# OLED
def update_oled(temp,hum,soil,light,height):
    if not oled_ok:
        return
    oled.fill(0)
    oled.text("GREENHOUSE",22,0)
    oled.hline(0,10,128,1)
    t=str(temp)+"C" if temp is not None else "N/A"
    h=str(hum)+"%" if hum is not None else "N/A"
    s=str(soil)+"%" if soil is not None else "N/A"
    ht=str(height)+"cm" if height is not None else "N/A"
    oled.text("T:"+t+" H:"+h,0,14)
    oled.text("Soil:"+s,0,25)
    oled.text("LDR:"+ldr_status(light).upper(),0,36)
    oled.text("Ht:"+ht,70,36)
    oled.hline(0,47,128,1)
    oled.text(
        "P:"+("ON" if pump_state else "OFF")+
        " F:"+("ON" if fan_state else "OFF")+
        " L:"+("ON" if grow_light_state else "OFF"),
        0,53
    )
    oled.show()

# Persistent offline queue + API
# Each queued record includes its stable event_id and the exact payload to retry.
# The pending file contains only records not yet acknowledged by the API.
def file_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False

def remove_file(path):
    try:
        os.remove(path)
    except OSError:
        pass

def recover_queue_files():
    """Recover a queue replacement interrupted by a reset/power loss."""
    queue_exists=file_exists(PENDING_FILE)
    backup_exists=file_exists(PENDING_BACKUP_FILE)
    temp_exists=file_exists(PENDING_TMP_FILE)

    if queue_exists:
        # If the new queue exists, it is canonical. A backup is only stale data.
        remove_file(PENDING_TMP_FILE)
        remove_file(PENDING_BACKUP_FILE)
        return

    if backup_exists:
        try:
            os.rename(PENDING_BACKUP_FILE,PENDING_FILE)
            print("[QUEUE] Recovered backup queue")
        except Exception as e:
            print("[QUEUE RECOVERY ERROR]",e)
        remove_file(PENDING_TMP_FILE)
        return

    if temp_exists:
        # This can happen if the queue was first created while a prior rename
        # was interrupted. Keep the only available copy rather than deleting it.
        try:
            os.rename(PENDING_TMP_FILE,PENDING_FILE)
            print("[QUEUE] Recovered temporary queue")
        except Exception as e:
            print("[QUEUE RECOVERY ERROR]",e)

def commit_queue_temp():
    """Replace queue with temp using a backup so a reset cannot erase both."""
    had_queue=file_exists(PENDING_FILE)
    remove_file(PENDING_BACKUP_FILE)
    try:
        if had_queue:
            os.rename(PENDING_FILE,PENDING_BACKUP_FILE)
        os.rename(PENDING_TMP_FILE,PENDING_FILE)
        remove_file(PENDING_BACKUP_FILE)
        return True
    except Exception as e:
        print("[QUEUE COMMIT ERROR]",e)
        if not file_exists(PENDING_FILE) and file_exists(PENDING_BACKUP_FILE):
            try:
                os.rename(PENDING_BACKUP_FILE,PENDING_FILE)
            except Exception as restore_error:
                print("[QUEUE RESTORE ERROR]",restore_error)
        return False

def new_event_id(prefix):
    global event_counter
    event_counter+=1
    try:
        uid="".join("{:02x}".format(b) for b in machine.unique_id())
    except Exception:
        uid="esp32"
    try:
        nonce=machine.rng()
    except Exception:
        nonce=time.ticks_ms() ^ time.time() ^ event_counter
    return "{}-{}-{}-{}-{}-{}".format(
        prefix,uid,time.time(),time.ticks_ms(),nonce,event_counter
    )

def append_pending(kind,payload):
    record={"kind":kind,"event_id":payload["event_id"],"payload":payload}
    try:
        with open(PENDING_FILE,"a") as f:
            f.write(json.dumps(record)+"\n")
            try:
                f.flush()
            except Exception:
                pass
        print("[QUEUE] Stored",kind,record["event_id"])
        return True
    except Exception as e:
        # Do not send a reading that could not first be persisted locally.
        print("[QUEUE STORAGE ERROR]",e)
        return False

def build_environment_payload(temp,hum,soil,light):
    return {
        "event_id":new_event_id("ESP32-ENV"),
        "greenhouse_id":GREENHOUSE_ID,
        "recorded_at":api_timestamp(),
        "temperature_c":temp,
        "humidity_percent":hum,
        "soil_moisture_percent":soil,
        "light_level":light,
        "pump_status":pump_state,
        "fan_status":fan_state,
        "grow_light_status":grow_light_state
    }

def build_growth_payload(height,distance):
    return {
        "event_id":new_event_id("ESP32-US"),
        "plant_id":PLANT_ID,
        "recorded_at":api_timestamp(),
        "distance_cm":distance,
        "estimated_height_cm":height
    }

def queue_environment(temp,hum,soil,light):
    payload=build_environment_payload(temp,hum,soil,light)
    return append_pending("environment",payload)

def queue_growth(height,distance):
    # Experimental ultrasonic data remains separate from official ruler growth.
    if height is None and distance is None:
        return False
    payload=build_growth_payload(height,distance)
    return append_pending("ultrasonic",payload)

def post_json(path,data):
    if not sta.isconnected():
        print("[API] Offline")
        return False

    try:
        body=json.dumps(data)
        body_bytes=body.encode()
        host_header = API_HOST if API_PORT in (80, 443) else API_HOST+":"+str(API_PORT)
        request=(
            "POST "+path+" HTTP/1.1\r\n"
            "Host: "+host_header+"\r\n"
            "Content-Type: application/json\r\n"
            "X-Device-Key: "+DEVICE_API_KEY+"\r\n"
            "Content-Length: "+str(len(body_bytes))+"\r\n"
            "Connection: close\r\n\r\n"
        ).encode()+body_bytes

        sock=socket.socket()
        sock.settimeout(15)
        try:
            # Resolve the hostname explicitly for public cloud deployments.
            address=socket.getaddrinfo(API_HOST,API_PORT)[0][-1]
            sock.connect(address)
            if API_USE_TLS:
                # Use SNI so multi-tenant HTTPS hosts can select the right certificate.
                sock=ssl.wrap_socket(sock, server_hostname=API_HOST)
                sock.settimeout(15)
            # Send the full request even if socket.send transmits only a portion.
            offset=0
            while offset<len(request):
                sent=sock.send(request[offset:])
                if not sent:
                    raise OSError("Socket closed while sending request")
                offset+=sent

            chunks=[]
            while True:
                try:
                    chunk=sock.recv(512)
                except OSError:
                    # A timeout after response bytes can still leave a useful
                    # HTTP response to parse; no bytes means the request failed.
                    if chunks:
                        break
                    raise
                if not chunk:
                    break
                chunks.append(chunk)
            if not chunks:
                print("[API] No response received")
                return False
            response=b"".join(chunks).decode("utf-8","ignore")
            status_line=response.split("\r\n",1)[0]
            try:
                status=int(status_line.split()[1])
            except Exception:
                print("[API] Invalid HTTP response:",response[:200])
                return False

            print("[API] HTTP",status)
            if 200<=status<300:
                print("[API] Upload acknowledged")
                return True

            # The backend uses HTTP 409 when this exact event_id was already
            # stored (for example, the board reset after POST but before ACK).
            # Treat only that explicit duplicate response as delivered.
            if status==409 and "Event ID already exists" in response:
                print("[API] Duplicate event already stored; treating as acknowledged")
                return True

            print("[API] Upload failed:",response[:200])
            return False
        finally:
            try:
                sock.close()
            except Exception:
                pass
    except Exception as e:
        print("[API ERROR]",e)
        return False

def send_queued_record(record):
    kind=record.get("kind")
    payload=record.get("payload")
    if not isinstance(payload,dict) or not payload.get("event_id"):
        print("[QUEUE ERROR] Invalid queued record; retaining it for inspection")
        return False
    if kind=="environment":
        path=READING_PATH
    elif kind=="ultrasonic":
        path=GROWTH_PATH
    else:
        print("[QUEUE ERROR] Unknown record type; retaining it:",kind)
        return False
    print("[QUEUE] Uploading",kind,record["event_id"])
    return post_json(path,payload)

def sync_pending_records():
    """Upload up to SYNC_BATCH_SIZE records, preserving order and retry data."""
    if not sta.isconnected() or not file_exists(PENDING_FILE):
        return 0

    delivered=0
    try:
        source=open(PENDING_FILE,"r")
        target=open(PENDING_TMP_FILE,"w")
        try:
            for line in source:
                if not line.strip():
                    continue

                if delivered>=SYNC_BATCH_SIZE:
                    target.write(line)
                    continue

                try:
                    record=json.loads(line)
                except Exception as e:
                    # Preserve malformed data and all records behind it; never
                    # silently discard a line that might contain a reading.
                    print("[QUEUE PARSE ERROR] Retaining queue from this line:",e)
                    target.write(line)
                    for rest in source:
                        if rest.strip():
                            target.write(rest)
                    break

                if send_queued_record(record):
                    delivered+=1
                    print("[QUEUE] Acknowledged",record.get("event_id"))
                else:
                    # Keep this failed record and everything after it in order.
                    target.write(line)
                    for rest in source:
                        if rest.strip():
                            target.write(rest)
                    break
        finally:
            source.close()
            target.close()

        if delivered:
            if commit_queue_temp():
                print("[QUEUE] Synced",delivered,"record(s)")
            else:
                print("[QUEUE] Could not update queue; acknowledged records may retry safely")
        else:
            remove_file(PENDING_TMP_FILE)
        return delivered
    except Exception as e:
        print("[QUEUE SYNC ERROR]",e)
        remove_file(PENDING_TMP_FILE)
        return delivered

def send_reading(temp,hum,soil,light):
    # Retained for the optional one-time API self-test only.
    data=build_environment_payload(temp,hum,soil,light)
    print("[API] Sending environment self-test...")
    return post_json(READING_PATH,data)

def send_growth(height,distance):
    # Retained for compatibility/testing; production readings use the queue.
    if height is None and distance is None:
        return False
    data=build_growth_payload(height,distance)
    print("[API] Sending experimental ultrasonic self-test...")
    return post_json(GROWTH_PATH,data)

# Start
recover_queue_files()
print("[BOOT] Greenhouse main.py v"+VERSION)
wifi_connected=initialize_wifi()
print("Wi-Fi:","CONNECTED" if wifi_connected else "OFFLINE")

while True:
    try:
        maintain_wifi()

        # One-time mock reading, sent as soon as Wi-Fi is available
        if API_SELF_TEST and sta.isconnected() and not api_test_attempted:
            api_test_attempted=True
            print("[API TEST] Sending mock reading...")
            ok=send_reading(25,60,50,300)
            print("[API TEST]","SUCCESS" if ok else "FAILED")
            last_env=time.ticks_ms()

        distance=read_ultrasonic()
        height=plant_height(distance)
        temp,hum=read_dht()
        soil=soil_percent(read_soil())
        light=read_ldr()

        # Automatic watering is intentionally disabled until soil calibration is verified.
        # Re-enable control_pump(soil) only after confirming dry/wet raw values at the prototype.
        # control_pump(soil)
        control_fan(temp,hum)
        control_light()
        update_oled(temp,hum,soil,light,height)

        now=time.ticks_ms()

        # Display sensor readings on the terminal every loop
        print(
            "Time:", timestamp(),
            "| T:", temp,
            "| H:", hum,
            "| Soil:", soil,
            "| LDR:", ldr_status(light),
            "| Height:", height,
            "| Pump:", pump_state,
            "| Fan:", fan_state,
            "| Light:", grow_light_state,
            "| WiFi:", sta.isconnected()
        )

        # Persist each sample first. The queue will retry it until the API ACKs it.
        now = time.ticks_ms()
        if time.ticks_diff(now, last_env) >= ENV_INTERVAL * 1000:
            print("[QUEUE] Capturing environmental reading...")
            queue_environment(temp, hum, soil, light)
            last_env = time.ticks_ms()

        # Experimental ultrasonic records stay separate from official growth data.
        now = time.ticks_ms()
        if time.ticks_diff(now, last_height) >= HEIGHT_INTERVAL * 1000:
            queue_growth(height, distance)
            last_height = time.ticks_ms()

        # Sync periodically in small batches so a large backlog doesn't freeze
        # sensor sampling and relay control for too long.
        now = time.ticks_ms()
        if time.ticks_diff(now, last_sync_attempt) >= SYNC_INTERVAL * 1000:
            last_sync_attempt = now
            if sta.isconnected():
                sync_pending_records()

        time.sleep(1)

    except Exception as e:
        print("[SYSTEM ERROR]",e)
        pump_relay.value(OFF)
        fan_relay.value(OFF)
        light_relay.value(OFF)
        pump_state=False
        fan_state=False
        grow_light_state=False
        time.sleep(2)