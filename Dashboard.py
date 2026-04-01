
import secrets
import json
import os


# Persistent token store
RESET_TOKEN_FILE = "reset_tokens.json"

def load_tokens():
    if os.path.exists(RESET_TOKEN_FILE):
        try:
            with open(RESET_TOKEN_FILE, "r") as f:
                tokens = json.load(f)
                return tokens
        except Exception:
            return {}
    return {}


def save_tokens(tokens):
    with open(RESET_TOKEN_FILE, "w") as f:
        json.dump(tokens, f)

RESET_TOKENS = load_tokens()

import tempfile
import time
from datetime import datetime
from pathlib import Path

import cv2
import streamlit as st
import random

# ---------------- OTP STORAGE ----------------
if "otp" not in st.session_state:
    st.session_state.otp = None
if "otp_email" not in st.session_state:
    st.session_state.otp_email = None
import random
import smtplib
from email.mime.text import MIMEText
import uuid

# ---------------- OTP STORAGE ----------------
if "otp" not in st.session_state:
    st.session_state.otp = None
if "otp_email" not in st.session_state:
    st.session_state.otp_email = None

# ---------------- DEVICE BINDING ----------------
def get_device_id():
    return str(uuid.getnode())

# ---------------- SEND OTP ----------------
def send_otp(email):
    otp = str(random.randint(100000, 999999))
    st.session_state.otp = otp
    st.session_state.otp_email = email

    # ⚠️ Replace with your email and app password
    sender = "argusmp3@gmail.com"
    password = "mwxf vpmq dkla ishz"

    msg = MIMEText(f"Your ARGUS OTP is: {otp}")
    msg["Subject"] = "ARGUS Login OTP"
    msg["From"] = sender
    msg["To"] = email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, email, msg.as_string())
        server.quit()
        return True
    except:
        return False

# ---------------- SEND RESET EMAIL (SIMPLE) ----------------
def send_reset(email):
    sender = "argusmp3@gmail.com"
    password = "mwxf vpmq dkla ishz"
    # Generate a reset token
    token = secrets.token_urlsafe(24)
    RESET_TOKENS[token] = {"email": email, "created": time.time()}
    save_tokens(RESET_TOKENS)
    reset_link = f"http://localhost:8501/?reset_token={token}"
    msg = MIMEText(f"Click the link to reset your password: {reset_link} (valid for 10 minutes)")
    msg["Subject"] = "ARGUS Reset"
    msg["From"] = sender
    msg["To"] = email
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, email, msg.as_string())
        server.quit()
        return True
    except:
        return False

# Verify reset token
def verify_reset_token(token):
    data = RESET_TOKENS.get(token)
    if not data:
        return None
    # Token valid for 10 minutes (600 seconds)
    # To disable expiry for demo, comment out the next 4 lines:
    # if time.time() - data["created"] > 600:
    #     del RESET_TOKENS[token]
    #     save_tokens(RESET_TOKENS)
    #     return None
    return data["email"]

# Update password in USER_DB
def update_password(email, new_password):
    if email in USER_DB:
        USER_DB[email] = new_password
        save_user_db(USER_DB)
        return True
    return False

from alert import get_alerts
from main import DEFAULT_ROI, RealtimeDetectionService, parse_video_source, run_detection


# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="ARGUS Security System", layout="wide")

# ---------------- SESSION STATE ----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "page" not in st.session_state:
    st.session_state.page = "login"

# ---------------- PERSISTENT USER DATABASE ----------------
USER_DB_FILE = "user_db.json"
def load_user_db():
    if os.path.exists(USER_DB_FILE):
        try:
            with open(USER_DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    # Default user if file missing or error
    return {"argusmp3@gmail.com": "nithu123456"}

def save_user_db(user_db):
    with open(USER_DB_FILE, "w") as f:
        json.dump(user_db, f)

USER_DB = load_user_db()

# ---------------- STYLING ----------------
st.markdown("""
<style>

/* BACKGROUND */
.stApp {
    background: #000000;
    color: white;
}

/* CENTER CARD */
.login-card {
    background: transparent !important;
    padding: 2.5rem;
    border-radius: 18px;
    box-shadow: none !important;
    backdrop-filter: none !important;
    animation: fadeIn 0.8s ease-in-out;
}

/* ARGUS TITLE */
.title {
    text-align: center;
    font-size: 42px;
    font-weight: 900;
    color: white;
    letter-spacing: 6px;

    /* 🔥 GLOW EFFECT */
    text-shadow:
        0 0 10px rgba(255,255,255,0.6),
        0 0 20px rgba(255,255,255,0.4),
        0 0 40px rgba(255,255,255,0.2);
}

/* SUBTITLE */
.subtitle {
    text-align: center;
    font-size: 13px;
    color: #777;
    margin-bottom: 25px;
}

/* INPUTS */
.stTextInput > div > div > input {
    background: #111 !important;
    border: 1px solid #222 !important;
    border-radius: 10px !important;
    color: #ccc !important;
}


/* BUTTON BASE */
.stButton {
    display: flex;
    justify-content: center;
}

/* BUTTON STYLE */
.stButton>button {
    min-width: 140px !important;
    max-width: 240px !important;
    width: auto !important;
    padding: 0.7rem 2.2rem !important;
    border-radius: 12px !important;
    background: white !important;
    color: black !important;
    font-weight: bold;
    letter-spacing: 1px;
    font-size: 1.1rem !important;
    transition: 0.3s;
    margin: 0.5rem auto 0.5rem auto;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    display: flex;
    align-items: center;
    justify-content: center;
}

/* BUTTON HOVER */
.stButton>button:hover {
    transform: scale(1.04);
    box-shadow: 0 0 15px rgba(255,255,255,0.6);
}

/* WARNING BOX */
.stAlert {
    border-radius: 10px;
}

/* ANIMATION */
@keyframes fadeIn {
    from {opacity: 0; transform: translateY(15px);}
                    token = generate_reset_token(email)
                    sent = send_reset_email(email, token)
                    if sent:
                        st.success("📧 Reset link sent to your email!")
                    else:
                        st.error("Failed to send email. Check SMTP credentials.")
}

</style>
""", unsafe_allow_html=True)

# ---------------- LOGIN PAGE ----------------
def login_page():
    col1, col2, col3 = st.columns([1,2,1])

    with col2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)

        st.markdown('<div class="title">ARGUS</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">AI Surveillance & Security System</div>', unsafe_allow_html=True)

        email = st.text_input("Employee Email / ID")
        password = st.text_input("Password", type="password")

        st.warning("Authorized personnel only. All activities are monitored.")


        # STEP 1: VERIFY PASSWORD
        if st.button("Login"):
            if not email or not password:
                st.warning("Enter email & password")
            elif email in USER_DB and USER_DB[email] == password:
                # generate OTP
                otp = str(random.randint(100000, 999999))
                st.session_state.otp = otp
                st.session_state.otp_email = email

                # Send OTP via email
                sender = "argusmp3@gmail.com"
                sender_password = "mwxf vpmq dkla ishz"
                msg = MIMEText(f"Your ARGUS OTP is: {otp}")
                msg["Subject"] = "ARGUS Login OTP"
                msg["From"] = sender
                msg["To"] = email
                try:
                    server = smtplib.SMTP("smtp.gmail.com", 587)
                    server.starttls()
                    server.login(sender, sender_password)
                    server.sendmail(sender, email, msg.as_string())
                    server.quit()
                    st.success("OTP sent to your email")
                    st.session_state.page = "otp"
                    st.rerun()
                except Exception as e:
                    st.error("Failed to send OTP email. Check SMTP credentials.")
            else:
                st.error("Invalid credentials")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Forgot Password?"):
            st.session_state.page = "forgot"
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

# ---------------- OTP PAGE ----------------
def otp_page():
    col1, col2, col3 = st.columns([1,2,1])

    with col2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)

        st.markdown('<div class="title">VERIFY OTP</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Enter the code sent to your email</div>', unsafe_allow_html=True)


        otp_input = st.text_input("Enter OTP")

        if st.button("Verify OTP"):
            if otp_input == st.session_state.otp:
                st.session_state.logged_in = True
                st.session_state.otp = None  # Clear OTP after successful login
                st.success("Login successful")
                st.rerun()
            else:
                st.error(f"Invalid OTP. (Expected: {st.session_state.otp}, Got: {otp_input})")

        if st.button("Back"):
            st.session_state.page = "login"
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

# ---------------- FORGOT PASSWORD ----------------
def forgot_password():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.markdown('<div class="title">Reset Password</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Enter your registered email</div>', unsafe_allow_html=True)
        email = st.text_input("Email")
        if st.button("Send Reset Link"):
            if email in USER_DB:
                success = send_reset(email)
                if success:
                    st.success("📧 Reset link sent to your email!")
                else:
                    st.error("Failed to send email. Check SMTP credentials.")
            else:
                st.error("Email not found")
        if st.button("⬅ Back to Login"):
            st.session_state.page = "login"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# ---------------- RESET PASSWORD PAGE ----------------
def reset_password_page(token):
    email = verify_reset_token(token)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.markdown('<div class="title">Set New Password</div>', unsafe_allow_html=True)
        if not email:
            st.error("Invalid or expired reset link.")
            return
        st.info(f"Resetting password for: {email}")
        new_pass = st.text_input("New Password", type="password")
        confirm_pass = st.text_input("Confirm Password", type="password")
        if st.button("Update Password"):
            if not new_pass or not confirm_pass:
                st.warning("Please fill both fields.")
            elif new_pass != confirm_pass:
                st.error("Passwords do not match.")
            else:
                update_password(email, new_pass)
                st.success("Password updated! You can now login.")
                if token in RESET_TOKENS:
                    del RESET_TOKENS[token]
                    save_tokens(RESET_TOKENS)
                st.session_state.page = "login"
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# ---------------- ROUTING (IMPORTANT) ----------------
if not st.session_state.logged_in:
    # Robust query param detection for all Streamlit versions
    token = None
    query_params = {}
    try:
        if hasattr(st, "query_params"):
            query_params = st.query_params
        elif hasattr(st, "experimental_get_query_params"):
            query_params = st.experimental_get_query_params()
    except Exception:
        pass
    if "reset_token" in query_params:
        val = query_params["reset_token"]
        if isinstance(val, list):
            token = val[0]
        else:
            token = val

    if token:
        reset_password_page(token)
        st.stop()
    elif st.session_state.page == "login":
        login_page()
    elif st.session_state.page == "forgot":
        forgot_password()
    elif st.session_state.page == "otp":
        otp_page()
    st.stop()   # ⛔ stops dashboard before login

# ============================================================
# 🔥 YOUR EXISTING DASHBOARD CODE STARTS BELOW
# ============================================================

st.sidebar.success("🟢 System Active")

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.session_state.page = "login"
    st.rerun()

st.title("ARGUS Dashboard")

# ...existing code...

if "camera_running" not in st.session_state:
    st.session_state.camera_running = False
if "camera_service" not in st.session_state:
    st.session_state.camera_service = None
if "camera_source" not in st.session_state:
    st.session_state.camera_source = "0"
if "camera_error" not in st.session_state:
    st.session_state.camera_error = ""
if "mode" not in st.session_state:
    st.session_state.mode = "Camera"
if "monitoring_mode" not in st.session_state:
    st.session_state.monitoring_mode = "Restricted Area Monitoring"
if "roi_x1" not in st.session_state:
    st.session_state.roi_x1 = DEFAULT_ROI[0]
if "roi_y1" not in st.session_state:
    st.session_state.roi_y1 = DEFAULT_ROI[1]
if "roi_x2" not in st.session_state:
    st.session_state.roi_x2 = DEFAULT_ROI[2]
if "roi_y2" not in st.session_state:
    st.session_state.roi_y2 = DEFAULT_ROI[3]


def normalize_monitoring_mode(selected_mode):
    if selected_mode == "Intrusion Detection":
        return "Restricted Area Monitoring"
    return selected_mode


def get_roi():
    x1 = min(st.session_state.roi_x1, st.session_state.roi_x2 - 1)
    y1 = min(st.session_state.roi_y1, st.session_state.roi_y2 - 1)
    x2 = max(st.session_state.roi_x2, x1 + 1)
    y2 = max(st.session_state.roi_y2, y1 + 1)
    return x1, y1, x2, y2


def stop_camera_service():
    service = st.session_state.camera_service
    if service is not None:
        service.stop()
    st.session_state.camera_service = None
    st.session_state.camera_running = False


def ensure_camera_service(source, monitoring_mode, roi):
    service = st.session_state.camera_service
    if service is None:
        service = RealtimeDetectionService(
            source=source,
            monitoring_mode=monitoring_mode,
            roi=roi,
            model_path="yolov8n.pt",
        )
        service.start()
        st.session_state.camera_service = service
    else:
        service.update_config(monitoring_mode=monitoring_mode, roi=roi)


with st.sidebar:
    st.markdown("## ARGUS Control Panel")
    st.divider()

    mode = st.selectbox(
        "Mode Selection",
        ["Camera", "Image", "Video"],
        key="mode",
    )

    monitoring_mode = st.selectbox(
        "Monitoring Type",
        ["Restricted Area Monitoring", "Crowd Monitoring", "Intrusion Detection"],
        key="monitoring_mode",
    )

    st.divider()
    st.text_input("Camera Source (0/webcam or RTSP URL)", key="camera_source")
    st.caption("Use 0 for webcam, or paste an RTSP URL")

    st.markdown("##### Restricted Area ROI")
    st.slider("ROI X1", 0, 1280, key="roi_x1")
    st.slider("ROI Y1", 0, 720, key="roi_y1")
    st.slider("ROI X2", 1, 1280, key="roi_x2")
    st.slider("ROI Y2", 1, 720, key="roi_y2")

    start_camera_clicked = st.button(
        "Start Camera",
        key="start_camera",
        use_container_width=True,
        disabled=mode != "Camera",
    )
    stop_camera_clicked = st.button(
        "Stop Camera",
        key="stop_camera",
        use_container_width=True,
        disabled=mode != "Camera",
    )

backend_monitoring_mode = normalize_monitoring_mode(monitoring_mode)
roi = get_roi()

st.markdown('<div class="top-title">ARGUS AI Surveillance System</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Real-Time Campus Safety Monitoring</div>', unsafe_allow_html=True)
col_live, col_time = st.columns([1, 3])
with col_live:
    st.markdown('<span class="live-dot"></span> <strong>LIVE</strong>', unsafe_allow_html=True)
with col_time:
    st.caption(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

st.divider()

metric_col1, metric_col2, metric_col3 = st.columns(3)
metrics_placeholder = st.empty()
frame_placeholder = st.empty()
alert_placeholder = st.empty()


def render_metrics(person_count, alerts, status_text):
    with metrics_placeholder.container():
        metric_col1.metric("Total People Detected", int(person_count))
        metric_col2.metric("Active Alerts", len(alerts))
        metric_col3.metric("System Status", status_text)


def render_metrics_extended(person_count, animal_count, alerts, status_text):
    with metrics_placeholder.container():
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("People", int(person_count))
        col2.metric("Animals", int(animal_count))
        col3.metric("Active Alerts", len(alerts))
        col4.metric("System Status", status_text)


def render_crowd_metrics(person_count, status_text):
    with metrics_placeholder.container():
        col1, col2 = st.columns(2)
        col1.metric("Total People Count", int(person_count))
        col2.metric("Crowd Alert Status", status_text)


def show_alerts(alerts):
    with alert_placeholder.container():
        st.markdown("### Live Alerts")
        if alerts:
            for alert in alerts:
                st.error(alert)
        else:
            st.success("CAMPUS SAFE")


def to_rgb(frame_bgr):
    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)


def save_uploaded_file(uploaded_file, suffix):
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.write(uploaded_file.getbuffer())
    temp_file.close()
    return temp_file.name


def update_ui(snapshot, monitoring_mode):
    result = snapshot.get("latest_result", {})
    alerts = result.get("alerts", [])
    status_text = result.get("status_text", "CAMPUS SAFE")
    person_count = result.get("person_count", 0)
    animal_count = result.get("animal_count", 0)

    if monitoring_mode == "Crowd Monitoring":
        render_crowd_metrics(person_count, status_text)
    else:
        render_metrics_extended(person_count, animal_count, alerts, status_text)

    frame = result.get("frame")
    if frame is not None:
        frame_placeholder.image(to_rgb(frame), channels="RGB", caption="Live Camera (Processed)", use_container_width=True)
    elif snapshot.get("connected"):
        frame_placeholder.info("Camera connected. Waiting for frames...")
    else:
        frame_placeholder.warning("Waiting for camera connection...")

    error = snapshot.get("error", "")
    if error:
        st.warning(error)

    with alert_placeholder.container():
        st.markdown("### Live Alerts")
        if monitoring_mode == "Crowd Monitoring":
            if status_text == "CROWD DETECTED":
                st.error("CROWD DETECTED")
            else:
                st.success("NORMAL")
        else:
            if alerts:
                for alert in alerts:
                    st.error(alert)
            else:
                st.success("CAMPUS SAFE")


def render_summary_ui(summary, monitoring_mode):
    alerts = summary.alerts
    if monitoring_mode == "Crowd Monitoring":
        render_crowd_metrics(summary.person_count, summary.status_text)
        with alert_placeholder.container():
            st.markdown("### Live Alerts")
            if summary.status_text == "CROWD DETECTED":
                st.error("CROWD DETECTED")
            else:
                st.success("NORMAL")
    else:
        render_metrics_extended(summary.person_count, summary.animal_count, alerts, summary.status_text)
        show_alerts(alerts)


st.markdown('<div class="section-card"><div class="card-title">Live Feed</div></div>', unsafe_allow_html=True)

if mode != "Camera":
    stop_camera_service()

if mode == "Image":
    uploaded_image = st.file_uploader("Upload Image", type=["jpg", "png", "jpeg"])
    if uploaded_image and st.button("Run Detection", key="run_image"):
        image_path = save_uploaded_file(uploaded_image, suffix=Path(uploaded_image.name).suffix or ".jpg")
        annotated, summary = run_detection(
            "image",
            image_path=image_path,
            monitoring_mode=backend_monitoring_mode,
            roi=roi,
        )
        render_summary_ui(summary, backend_monitoring_mode)
        frame_placeholder.image(to_rgb(annotated), channels="RGB", caption="Processed Image", use_container_width=True)
    else:
        base_alerts = get_alerts()
        render_metrics_extended(0, 0, base_alerts, "ALERT" if base_alerts else "CAMPUS SAFE")
        show_alerts(base_alerts)

elif mode == "Video":
    uploaded_video = st.file_uploader("Upload Video", type=["mp4"])
    if uploaded_video and st.button("Run Detection", key="run_video"):
        video_path = save_uploaded_file(uploaded_video, suffix=".mp4")

        def video_callback(annotated, summary):
            render_summary_ui(summary, backend_monitoring_mode)
            frame_placeholder.image(to_rgb(annotated), channels="RGB", caption="Processed Video", use_container_width=True)
            return True

        run_detection(
            "video",
            video_path=video_path,
            frame_callback=video_callback,
            monitoring_mode=backend_monitoring_mode,
            roi=roi,
        )
    else:
        base_alerts = get_alerts()
        render_metrics_extended(0, 0, base_alerts, "ALERT" if base_alerts else "CAMPUS SAFE")
        show_alerts(base_alerts)

else:
    if start_camera_clicked:
        st.session_state.camera_error = ""
        st.session_state.camera_running = True

    if stop_camera_clicked:
        stop_camera_service()

    if st.session_state.camera_running:
        source = parse_video_source(st.session_state.camera_source)
        ensure_camera_service(source, backend_monitoring_mode, roi)

        @st.fragment(run_every="80ms")
        def live_camera_fragment():
            service = st.session_state.camera_service
            if service is None:
                frame_placeholder.info("Camera service not running")
                render_metrics_extended(0, 0, [], "CAMPUS SAFE")
                show_alerts([])
                return
            snapshot = service.get_snapshot()
            update_ui(snapshot, backend_monitoring_mode)

        live_camera_fragment()
    else:
        render_metrics_extended(0, 0, [], "CAMPUS SAFE")
        frame_placeholder.info("Click Start Camera to begin real-time monitoring")
        show_alerts([])
