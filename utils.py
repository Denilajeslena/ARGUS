import cv2

def draw_alerts(frame, alerts):
    y = 50
    for alert in alerts:
        cv2.putText(frame, alert, (50, y),
        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
        y += 40