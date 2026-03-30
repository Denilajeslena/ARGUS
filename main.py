import threading
import time
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2

from alert import set_alerts
from detector import detect

MODE = "camera"
IMAGE_PATH = "sample.jpg"
VIDEO_PATH = "sample.mp4"

CROWD_THRESHOLD = 4
PERSON_CONFIDENCE_THRESHOLD = 0.4
DEFAULT_CROWD_MODEL_PATH = "yolov8m.pt"
DEFAULT_ROI = (200, 150, 450, 400)

PERSON_CLASS_ID = 0
ANIMAL_CLASS_IDS = {15, 16, 17, 18, 19, 20, 21, 22, 23, 24}

logger = logging.getLogger("argus")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")

ALERT_MEDIA_DIR = Path(__file__).resolve().with_name("alert_media")
SNAPSHOT_DIR = ALERT_MEDIA_DIR / "snapshots"
CLIP_DIR = ALERT_MEDIA_DIR / "clips"


@dataclass
class FrameSummary:
    alerts: list[str]
    person_count: int
    animal_count: int
    restricted_entry: bool
    status_text: str


class AlertEventRecorder:
    def __init__(self, cooldown_seconds=1.5, clip_fps=12, clip_seconds=4):
        self.cooldown_seconds = cooldown_seconds
        self.clip_fps = clip_fps
        self.clip_seconds = clip_seconds
        self._last_emit_by_alert = {}

        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        CLIP_DIR.mkdir(parents=True, exist_ok=True)

    def should_emit(self, alerts):
        now = time.time()
        to_emit = []
        for alert_text in alerts:
            last_ts = self._last_emit_by_alert.get(alert_text, 0.0)
            if now - last_ts >= self.cooldown_seconds:
                to_emit.append(alert_text)
                self._last_emit_by_alert[alert_text] = now
        return to_emit

    def save_snapshot(self, frame, alerts):
        if frame is None:
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_alert = "_".join(alerts).replace(" ", "_") if alerts else "ALERT"
        file_path = SNAPSHOT_DIR / f"{ts}_{safe_alert}.jpg"
        cv2.imwrite(str(file_path), frame)
        return file_path

    def save_clip(self, frames):
        if not frames:
            return None

        first = frames[0]
        h, w = first.shape[:2]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_path = CLIP_DIR / f"{ts}_alert.mp4"

        writer = cv2.VideoWriter(
            str(file_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            self.clip_fps,
            (w, h),
        )
        for frame in frames:
            writer.write(frame)
        writer.release()
        return file_path


def parse_video_source(source_value):
    text = str(source_value).strip()
    if text.isdigit():
        return int(text)
    return text


def resize_frame(frame, max_width=640):
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / float(w)
    return cv2.resize(frame, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)


def intersection_area(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    return iw * ih


def is_person_in_roi(person_box, roi_box):
    return intersection_area(person_box, roi_box) > 0


def check_roi_overlap(detection_box, roi_box):
    overlap = intersection_area(detection_box, roi_box) > 0
    logger.info("ROI overlap=%s for box=%s roi=%s", overlap, detection_box, roi_box)
    return overlap


def detect_objects(frame, model_path="yolov8n.pt", conf=PERSON_CONFIDENCE_THRESHOLD):
    # Run one inference pass for person + supported animal classes only.
    interested_classes = [PERSON_CLASS_ID, *sorted(ANIMAL_CLASS_IDS)]
    results = detect(frame, model_path=model_path, conf=conf, imgsz=640, classes=interested_classes)
    detections = []
    names = {}

    for result in results:
        names = result.names
        for box in result.boxes:
            cls_id = int(box.cls[0])
            if cls_id == PERSON_CLASS_ID:
                label = "Person"
            elif cls_id in ANIMAL_CLASS_IDS:
                label = "Animal"
            else:
                continue

            score = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            detections.append(
                {
                    "bbox": (x1, y1, x2, y2),
                    "conf": score,
                    "label": label,
                    "class_id": cls_id,
                }
            )

    logger.info(
        "Detected class_ids=%s labels=%s",
        [det["class_id"] for det in detections],
        [det["label"] for det in detections],
    )

    persons = [det for det in detections if det["label"] == "Person"]
    animals = [det for det in detections if det["label"] == "Animal"]
    return persons, animals


def detect_people_only(frame, model_path=DEFAULT_CROWD_MODEL_PATH, conf=PERSON_CONFIDENCE_THRESHOLD):
    # Crowd mode must only detect COCO class 0 (person).
    results = detect(frame, model_path=model_path, conf=conf, imgsz=640, classes=[PERSON_CLASS_ID])
    persons = []

    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            if cls_id != PERSON_CLASS_ID:
                continue

            score = float(box.conf[0])
            if score < conf:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            persons.append(
                {
                    "bbox": (x1, y1, x2, y2),
                    "conf": score,
                    "label": "Person",
                    "class_id": PERSON_CLASS_ID,
                }
            )

    confidences = [round(person["conf"], 3) for person in persons]
    logger.info("Crowd mode persons=%d confs=%s", len(persons), confidences)
    print(f"[CrowdMode] persons={len(persons)} confs={confidences}")
    return persons


def count_people(person_detections):
    # YOLO already applies NMS, so each remaining box is one person.
    return len(person_detections)


def process_crowd_frame(frame, model_path=DEFAULT_CROWD_MODEL_PATH, conf=PERSON_CONFIDENCE_THRESHOLD):
    resized = resize_frame(frame, max_width=640)
    persons = detect_people_only(resized, model_path=model_path, conf=conf)
    person_count = count_people(persons)

    status_text = "CROWD DETECTED" if person_count >= CROWD_THRESHOLD else "NORMAL"
    alerts = ["CROWD DETECTED"] if person_count >= CROWD_THRESHOLD else []

    annotated = resized.copy()
    for detection in persons:
        x1, y1, x2, y2 = detection["bbox"]
        score = detection["conf"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (50, 220, 80), 2)
        cv2.putText(
            annotated,
            f"Person {score:.2f}",
            (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (50, 220, 80),
            2,
        )

    cv2.putText(
        annotated,
        f"People Count: {person_count}",
        (35, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 220, 255),
        3,
    )
    cv2.putText(
        annotated,
        status_text,
        (35, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 255) if status_text == "CROWD DETECTED" else (60, 220, 90),
        3,
    )

    summary = FrameSummary(
        alerts=alerts,
        person_count=person_count,
        animal_count=0,
        restricted_entry=False,
        status_text=status_text,
    )
    return annotated, summary


def annotate_frame(frame, persons, animals, roi, monitoring_mode):
    annotated = frame.copy()
    rx1, ry1, rx2, ry2 = roi

    for detection in persons:
        x1, y1, x2, y2 = detection["bbox"]
        conf = detection["conf"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (50, 220, 80), 2)
        cv2.putText(
            annotated,
            f"Person {conf:.2f}",
            (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (50, 220, 80),
            2,
        )

    for detection in animals:
        x1, y1, x2, y2 = detection["bbox"]
        conf = detection["conf"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 180, 255), 2)
        cv2.putText(
            annotated,
            f"Animal {conf:.2f}",
            (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 180, 255),
            2,
        )

    person_in_roi = any(check_roi_overlap(person["bbox"], roi) for person in persons)
    animal_in_roi = any(check_roi_overlap(animal["bbox"], roi) for animal in animals)
    restricted_entry = person_in_roi or animal_in_roi

    if monitoring_mode == "Restricted Area Monitoring":
        cv2.rectangle(annotated, (rx1, ry1), (rx2, ry2), (0, 0, 255), 2)
        cv2.putText(
            annotated,
            "Restricted Zone",
            (rx1, max(ry1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )

    person_count = len(persons)
    animal_count = len(animals)
    alerts = []

    if monitoring_mode == "Restricted Area Monitoring":
        if person_in_roi:
            alerts.append("PERSON IN RESTRICTED AREA")
        if animal_in_roi:
            alerts.append("ANIMAL IN RESTRICTED AREA")

        if alerts:
            status_text = "ALERT"
            y = 55
            for alert_text in alerts:
                cv2.putText(
                    annotated,
                    alert_text,
                    (35, y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 0, 255),
                    3,
                )
                y += 40
        else:
            status_text = "CAMPUS SAFE"
            cv2.putText(
                annotated,
                "CAMPUS SAFE",
                (35, 55),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (60, 220, 90),
                3,
            )
    else:
        raise ValueError("annotate_frame only supports 'Restricted Area Monitoring'")

    logger.info(
        "alert_state=%s person_count=%d animal_count=%d roi_hit=%s",
        alerts,
        person_count,
        animal_count,
        restricted_entry,
    )

    summary = FrameSummary(
        alerts=alerts,
        person_count=person_count,
        animal_count=animal_count,
        restricted_entry=restricted_entry,
        status_text=status_text,
    )
    return annotated, summary


def process_frame(frame, monitoring_mode="Restricted Area Monitoring", roi=DEFAULT_ROI, model_path="yolov8n.pt"):
    if monitoring_mode == "Crowd Monitoring":
        return process_crowd_frame(
            frame,
            model_path=DEFAULT_CROWD_MODEL_PATH,
            conf=PERSON_CONFIDENCE_THRESHOLD,
        )

    frame = resize_frame(frame, max_width=640)
    persons, animals = detect_objects(frame, model_path=model_path)
    return annotate_frame(frame, persons, animals, roi, monitoring_mode)


def initialize_video_capture(source, max_retries=5, retry_delay=0.7):
    for _ in range(max_retries):
        cap = cv2.VideoCapture(source)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            return cap
        cap.release()
        time.sleep(retry_delay)
    return None


class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {
            "latest_result": {
                "frame": None,
                "alerts": [],
                "person_count": 0,
                "animal_count": 0,
                "status_text": "CAMPUS SAFE",
            },
            "connected": False,
            "error": "",
            "last_update": 0.0,
        }

    def update(self, **kwargs):
        with self._lock:
            self._data.update(kwargs)
            self._data["last_update"] = time.time()

    def snapshot(self):
        with self._lock:
            snap = dict(self._data)
            latest_result = dict(snap["latest_result"])
            frame = latest_result["frame"]
            latest_result["frame"] = frame.copy() if frame is not None else None
            latest_result["alerts"] = list(latest_result["alerts"])
            snap["latest_result"] = latest_result
            return snap


class RealtimeDetectionService:
    def __init__(
        self,
        source=0,
        monitoring_mode="Restricted Area Monitoring",
        roi=DEFAULT_ROI,
        model_path="yolov8n.pt",
    ):
        self.source = parse_video_source(source)
        self.monitoring_mode = monitoring_mode
        self.roi = roi
        self.model_path = model_path

        self.state = SharedState()
        self._running = threading.Event()
        self._config_lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._result_lock = threading.Lock()

        self._latest_frame = None
        self._latest_frame_id = 0
        self._latest_result = {
            "frame": None,
            "alerts": [],
            "person_count": 0,
            "animal_count": 0,
            "status_text": "CAMPUS SAFE",
        }

        self._capture_thread = None
        self._detect_thread = None
        self._capture = None

        self._alert_recorder = AlertEventRecorder(cooldown_seconds=1.5, clip_fps=12, clip_seconds=4)
        self._clip_buffer = deque(maxlen=self._alert_recorder.clip_fps * self._alert_recorder.clip_seconds)

    def start(self):
        if self._running.is_set():
            return
        self._running.set()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._detect_thread = threading.Thread(target=self._detect_loop, daemon=True)
        self._capture_thread.start()
        self._detect_thread.start()

    def stop(self):
        if not self._running.is_set():
            return
        self._running.clear()
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2.0)
        if self._detect_thread is not None:
            self._detect_thread.join(timeout=2.0)
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self.state.update(connected=False)

    def update_config(self, monitoring_mode=None, roi=None):
        with self._config_lock:
            if monitoring_mode is not None:
                self.monitoring_mode = monitoring_mode
            if roi is not None:
                self.roi = roi

    def get_snapshot(self):
        with self._result_lock:
            result_copy = {
                "frame": None if self._latest_result["frame"] is None else self._latest_result["frame"].copy(),
                "alerts": list(self._latest_result["alerts"]),
                "person_count": self._latest_result["person_count"],
                "animal_count": self._latest_result["animal_count"],
                "status_text": self._latest_result["status_text"],
            }
        self.state.update(latest_result=result_copy)
        return self.state.snapshot()

    def _capture_loop(self):
        while self._running.is_set():
            cap = initialize_video_capture(self.source, max_retries=3)
            if cap is None:
                self.state.update(connected=False, error="Unable to open camera/RTSP source. Retrying...")
                time.sleep(0.8)
                continue

            self._capture = cap
            self.state.update(connected=True, error="")

            while self._running.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    self.state.update(connected=False, error="Camera disconnected. Reconnecting...")
                    break

                with self._frame_lock:
                    self._latest_frame = frame
                    self._latest_frame_id += 1

            cap.release()
            self._capture = None
            time.sleep(0.3)

    def _detect_loop(self):
        last_processed_id = -1
        while self._running.is_set():
            with self._frame_lock:
                frame_id = self._latest_frame_id
                frame = None if self._latest_frame is None else self._latest_frame.copy()

            if frame is None or frame_id == last_processed_id:
                time.sleep(0.01)
                continue

            with self._config_lock:
                monitoring_mode = self.monitoring_mode
                roi = self.roi

            annotated, summary = process_frame(
                frame,
                monitoring_mode=monitoring_mode,
                roi=roi,
                model_path=self.model_path,
            )

            set_alerts(summary.alerts)
            next_result = {
                "frame": annotated,
                "alerts": summary.alerts,
                "person_count": summary.person_count,
                "animal_count": summary.animal_count,
                "status_text": summary.status_text,
            }

            self._clip_buffer.append(annotated.copy())

            if monitoring_mode == "Restricted Area Monitoring" and summary.alerts:
                emitted_alerts = self._alert_recorder.should_emit(summary.alerts)
                if emitted_alerts:
                    snapshot_path = self._alert_recorder.save_snapshot(annotated, emitted_alerts)
                    clip_path = self._alert_recorder.save_clip(list(self._clip_buffer))
                    logger.info(
                        "ALERT EVENT emitted=%s snapshot=%s clip=%s",
                        emitted_alerts,
                        str(snapshot_path) if snapshot_path else "-",
                        str(clip_path) if clip_path else "-",
                    )

            with self._result_lock:
                self._latest_result = next_result

            self.state.update(latest_result=next_result)

            last_processed_id = frame_id


def run_detection(
    mode,
    image_path=None,
    video_path=None,
    frame_callback=None,
    show_window=False,
    monitoring_mode="Restricted Area Monitoring",
    roi=DEFAULT_ROI,
    model_path="yolov8n.pt",
):
    if not isinstance(mode, str):
        annotated, summary = process_frame(
            mode,
            monitoring_mode=monitoring_mode,
            roi=roi,
            model_path=model_path,
        )
        set_alerts(summary.alerts)
        if frame_callback:
            frame_callback(annotated, summary)
        return annotated, summary

    mode = mode.lower()
    last_annotated = None
    last_summary = FrameSummary(alerts=[], person_count=0, animal_count=0, restricted_entry=False, status_text="CAMPUS SAFE")

    if mode == "image":
        if not image_path:
            raise ValueError("image_path is required for image mode")

        frame = cv2.imread(image_path)
        if frame is None:
            raise FileNotFoundError(f"Image not found: {image_path}")

        last_annotated, summary = process_frame(
            frame,
            monitoring_mode=monitoring_mode,
            roi=roi,
            model_path=model_path,
        )
        last_summary = summary
        set_alerts(summary.alerts)

        if frame_callback:
            frame_callback(last_annotated, summary)

        return last_annotated, summary

    if mode in ("camera", "video"):
        source = 0 if mode == "camera" else video_path
        if mode == "video" and not video_path:
            raise ValueError("video_path is required for video mode")

        cap = initialize_video_capture(source, max_retries=4)
        if cap is None:
            if mode == "camera":
                raise RuntimeError("Camera could not be opened")
            raise FileNotFoundError(f"Video not found or cannot be opened: {video_path}")

        window_title = "ARGUS Campus Safety System"

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            last_annotated, summary = process_frame(
                frame,
                monitoring_mode=monitoring_mode,
                roi=roi,
                model_path=model_path,
            )
            last_summary = summary
            set_alerts(summary.alerts)

            if frame_callback:
                should_continue = frame_callback(last_annotated, summary)
                if should_continue is False:
                    break

            if show_window:
                cv2.imshow(window_title, last_annotated)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

        cap.release()
        return last_annotated, last_summary

    raise ValueError("mode must be one of: 'camera', 'image', 'video'")


if __name__ == "__main__":
    if MODE == "image":
        annotated, _ = run_detection("image", image_path=IMAGE_PATH)
        cv2.imshow("ARGUS Campus Safety System - Image Mode", annotated)
        cv2.waitKey(0)
    elif MODE == "camera":
        run_detection("camera", show_window=True)
    elif MODE == "video":
        run_detection("video", video_path=VIDEO_PATH, show_window=True)
    else:
        raise ValueError("MODE must be one of: 'camera', 'image', 'video'")

    cv2.destroyAllWindows()
