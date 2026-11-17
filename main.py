import os
import json
import ssl
from fastapi import FastAPI
from pydantic import BaseModel
import paho.mqtt.client as mqtt
import google.generativeai as genai

app = FastAPI(title="Cactus AI Cloud Brain")

# Environment configs
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MQTT_BROKER = os.getenv("MQTT_BROKER", "")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_SALT = os.getenv("MQTT_SALT", "cactus_salt_2026")

TOPIC_PC_CMD = f"cactus/{MQTT_SALT}/pc/cmd"
TOPIC_PC_RES = f"cactus/{MQTT_SALT}/pc/res"
TOPIC_TELEMETRY = f"cactus/{MQTT_SALT}/telemetry"

# Initialize Gemini with gemini-2.5-flash
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
else:
    model = None

# Initialize MQTT Client
mqtt_client = None
if MQTT_BROKER and MQTT_USER:
    try:
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        mqtt_client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
        mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
        print("[+] MQTT Client started.")
    except Exception as e:
        print(f"[!] MQTT connection failed: {e}")

class CommandRequest(BaseModel):
    query: str
    target: str = "pc"

@app.get("/")
@app.get("/health")
def health():
    """Endpoint for UptimeRobot 5-minute keep-alive."""
    return {
        "status": "online",
        "system": "Cactus AI Cloud Brain 24/7",
        "gemini_ready": model is not None,
        "mqtt_connected": mqtt_client is not None
    }

@app.post("/execute")
def execute_command(req: CommandRequest):
    if not model:
        return {"error": "GEMINI_API_KEY is not set in Environment Variables."}
    
    prompt = f"""
    You are Cactus AI Operator, controlling the user's PC and Phone.
    User request: "{req.query}"
    
    Convert this request into an exact executable JSON action:
    {{
        "target": "pc",
        "action": "shell" | "screen_capture" | "gui_click" | "open_app" | "browser_navigate",
        "payload": {{ ... }},
        "explanation": "Brief explanation of the action"
    }}
    Return only valid JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        text_resp = response.text.strip()
        if text_resp.startswith("```json"):
            text_resp = text_resp[7:]
        if text_resp.endswith("```"):
            text_resp = text_resp[:-3]
        action_data = json.loads(text_resp.strip())
        
        # Publish to MQTT if connected
        if mqtt_client and action_data.get("target") == "pc":
            mqtt_client.publish(TOPIC_PC_CMD, json.dumps(action_data), qos=1)
            action_data["dispatched_via_mqtt"] = True
            
        return {"status": "success", "action": action_data}
    except Exception as e:
        return {"error": str(e)}
