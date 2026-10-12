# Dataset Register

| Source | URL | Licence / permission | Class mapping (source id -> ours) | Images used (train/val/test) |
|---|---|---|---|---|
| wildfire-40k | https://huggingface.co/datasets/jojomoi-meme/fog_fire_detection | CC-BY-4.0 (Roboflow Universe joachim-serv/wildfire-j4okv) | 0->fire, 1->smoke | train:2000 / val:400 / test:400 |
| ISFire-4 (indoor) | https://huggingface.co/datasets/shahriar-5/ISFire-4 | MIT (Roboflow Universe, IICT BUET) | 0->smoke, 1->fire, 2->smoke, 3->fire | train:1000 / val:200 / test:200 |

| Field | Value |
|---|---|
| Format | YOLO (class cx cy w h, normalised 0-1) |
| Classes | 0 = fire, 1 = smoke |
| Sampling | stratified subset per source, seed 42, up to 15% negatives per split where available |
| Preprocessing | none; Ultralytics augmentation applied at train time only |
| Created | 2026-10-12 23:29:50 |

## Split summary

| Split | Images | fire-only | smoke-only | both | negative | fire boxes | smoke boxes |
|---|---|---|---|---|---|---|---|
| train | 3000 | 988 | 988 | 723 | 301 | 2873 | 2256 |
| val | 600 | 189 | 187 | 164 | 60 | 551 | 487 |
| test | 600 | 203 | 202 | 135 | 60 | 582 | 445 |

Splits follow the upstream train/valid/test partitions of each source, so frames from the same source video do not leak between train and test.
