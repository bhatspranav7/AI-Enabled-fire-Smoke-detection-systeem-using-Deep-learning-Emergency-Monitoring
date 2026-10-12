"""Download the two public training sources from Hugging Face (only needed to retrain).

    python training/download_datasets.py

Running the live demo does NOT need this - models/best.pt is committed in the repo.
"""
import pathlib

from huggingface_hub import hf_hub_download

ROOT = pathlib.Path(__file__).resolve().parents[1]
JOBS = [
    ("jojomoi-meme/fog_fire_detection", ["data.yaml", "README.md", "dataset.zip"], ROOT / "dataset" / "raw"),       # ~1.74 GB
    ("shahriar-5/ISFire-4", ["README.md", "Dataset.zip"], ROOT / "dataset" / "raw_isfire"),                        # ~245 MB
]

for repo, files, out in JOBS:
    out.mkdir(parents=True, exist_ok=True)
    for fn in files:
        p = hf_hub_download(repo_id=repo, repo_type="dataset", filename=fn, local_dir=str(out))
        print("downloaded", p, flush=True)
print("ALL DONE - now run: python training/prepare_dataset.py")
