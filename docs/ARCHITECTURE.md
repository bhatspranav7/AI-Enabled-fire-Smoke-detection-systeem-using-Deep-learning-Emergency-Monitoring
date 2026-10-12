# Architecture and Data Flow

## System architecture

```mermaid
flowchart LR
    subgraph Edge["Edge / lab bench"]
        CAM[USB / IP camera] --> INF
        INF["inference/run_live.py<br/>OpenCV capture → YOLO11n → filters"]
        INF --> DE["decision_engine<br/>temporal state machine"]
        DE --> OV[Overlay window + software buzzer]
        DE --> EV[(evidence/*.jpg<br/>logs/events.jsonl)]
        ESP["ESP32 (or iot/sensor_simulator.py)<br/>MQ-2 smoke · temperature · buzzer · relay"]
    end

    subgraph Server["Backend (laptop)"]
        API["backend/app.py<br/>FastAPI"]
        DB[(SQLite<br/>devices · sensor_readings · detections · events · notifications)]
        API <--> DB
    end

    INF -- "POST /detections, /frames, /events" --> API
    INF -- "GET /sensors/latest, /devices/{id}/commands" --> API
    ESP -- "POST /sensors · GET commands" --> API
    DE --> NOTIF["notifications/<br/>console · log · Telegram · email"]
    API --> DASH["dashboard/ (HTML/JS)<br/>live MJPEG · state · sensors · events · ack · e-stop"]
    DASH -- "POST /events/{id}/ack, /control/estop" --> API
```

## Level-1 data-flow diagram

```mermaid
flowchart TD
    A[Camera frames] -->|BGR frame| P1[1. Capture & preprocess]
    P1 -->|resized frame| P2[2. YOLO inference]
    P2 -->|class, conf, bbox| P3[3. Confidence / class / zone filter]
    S[Sensor readings] -->|smoke, temperature, timestamp| P4
    P3 -->|detections| P4[4. Temporal decision engine]
    P4 -->|state + transition| P5[5. Response manager]
    P5 -->|snapshot| D1[(Evidence store)]
    P5 -->|event record| D2[(Events table)]
    P5 -->|message| P6[6. Notification service]
    P5 -->|buzzer / actuator cmd| H[Low-voltage prototype outputs]
    P4 -->|state, detections, frame| P7[7. Dashboard API]
    P7 --> U[Operator dashboard]
    U -->|acknowledge / e-stop| P4
```

## Decision-engine state machine

```mermaid
stateDiagram-v2
    [*] --> NORMAL
    NORMAL --> WARNING: ≥3 hits ≥0.35 in 3 s
    NORMAL --> CONFIRMED: ≥10 hits ≥0.55 over ≥2 s
    NORMAL --> SENSOR_WARNING: sensors elevated ≥5 s, no visual
    WARNING --> CONFIRMED: ≥10 strong hits (≥6 if sensors elevated)
    WARNING --> NORMAL: nothing ≥0.25 for 4 s
    CONFIRMED --> RECOVERY: nothing ≥0.25 for 4 s, or operator ack
    RECOVERY --> NORMAL: 10 s stable
    RECOVERY --> CONFIRMED: target re-appears
    SENSOR_WARNING --> WARNING: possible visual target
    SENSOR_WARNING --> CONFIRMED: visual confirmation
    SENSOR_WARNING --> NORMAL: sensors normal
```

## Sequence: confirmed fire event

```mermaid
sequenceDiagram
    participant C as Camera
    participant I as Inference
    participant E as Decision engine
    participant B as Backend
    participant N as Notifier
    participant D as Dashboard
    loop every frame (≈15 fps)
        C->>I: frame
        I->>I: YOLO → detections
        I->>E: update(detections, sensors)
        I->>B: POST /detections (state, boxes, fps) · POST /frames (JPEG)
    end
    E-->>I: transition NORMAL→WARNING
    I->>I: save snapshot
    I->>B: POST /events (WARNING, evidence)
    E-->>I: transition WARNING→CONFIRMED
    I->>I: buzzer on, snapshot
    I->>B: POST /events (CONFIRMED)
    I->>N: send(alert + evidence)
    N-->>B: POST /notifications (sent/failed)
    D->>B: GET /status, /events (poll 1 s)
    D->>B: POST /events/{id}/ack
    B-->>I: GET /devices/cam01/commands → ack
    I->>E: acknowledge() → RECOVERY, buzzer off
```

## Module boundaries

| Folder | Responsibility | Depends on |
|---|---|---|
| `training/` | dataset build, training, evaluation | ultralytics, dataset zips |
| `vision/` | camera abstraction, overlay drawing | OpenCV |
| `decision_engine/` | pure temporal logic, no I/O | — |
| `inference/` | orchestrates camera → model → engine → outputs | all of the above |
| `notifications/` | channel adapters | requests, smtplib |
| `backend/` | REST API + SQLite + MJPEG | FastAPI |
| `dashboard/` | operator UI, static files | backend API |
| `iot/` | ESP32 firmware and its software simulator | backend API |
| `configs/` | all tunables; no code | — |
