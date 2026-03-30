import tempfile
import time
from datetime import datetime
from pathlib import Path

import cv2
import streamlit as st

from alert import get_alerts
from main import DEFAULT_ROI, RealtimeDetectionService, parse_video_source, run_detection

st.set_page_config(page_title="ARGUS Security Dashboard", layout="wide")

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at 20% 10%, #18212e 0%, #0e1117 42%, #0a0d12 100%);
        color: #e8edf7;
    }
    .top-title {
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: 0.3px;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        color: #a8b3c7;
        font-size: 1rem;
        margin-bottom: 0.8rem;
    }
    .live-dot {
        height: 10px;
        width: 10px;
        background-color: #2ecc71;
        border-radius: 50%;
        display: inline-block;
        margin-right: 6px;
        box-shadow: 0 0 10px #2ecc71;
    }
    .section-card {
        background: linear-gradient(135deg, rgba(28,36,52,0.9), rgba(18,24,36,0.9));
        border: 1px solid rgba(129, 159, 199, 0.2);
        border-radius: 14px;
        padding: 16px;
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.28);
        margin-bottom: 14px;
    }
    .card-title {
        color: #d9e3f5;
        font-weight: 600;
        margin-bottom: 4px;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #121823 0%, #0f1520 100%);
        border-right: 1px solid rgba(139, 174, 221, 0.15);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
