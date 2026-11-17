"""The deployment files. No Docker here, so the image is checked the next best way: lay out
exactly what the Dockerfile copies, with nothing else beside it, and boot the app from there."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def final_stage_copies(dockerfile: str) -> tuple[str, list[tuple[list[str], str]]]:
    """(workdir, [(sources, destination)]) of the last stage, for COPY lines that read from the repository."""
    stage = dockerfile.split("\nFROM ")[-1]
    workdir = re.search(r"^WORKDIR\s+(\S+)", stage, re.M).group(1)
    copies = []
    for line in re.findall(r"^COPY\s+(?!--from)(.+)$", stage, re.M):
        *sources, dest = line.split()
        copies.append((sources, dest))
    return workdir, copies


def test_both_dockerfiles_build_the_sanad_app_and_are_identical():
    a, b = (REPO / "Dockerfile").read_text(), (REPO / "Dockerfile.sanad").read_text()
    assert a == b
    assert "sanad_app:app" in a and "main:app" not in a and "COPY frontend/" not in a
    assert "COPY sanad-chat/" in a


def test_railway_builds_the_sanad_image_by_default():
    for name, dockerfile in (("railway.toml", "Dockerfile"), ("railway.sanad.toml", "Dockerfile.sanad")):
        text = (REPO / name).read_text()
        assert f'dockerfilePath = "{dockerfile}"' in text and 'healthcheckPath = "/api/health"' in text
        assert (REPO / dockerfile).exists()


def test_the_image_contents_are_enough_to_run_the_app(tmp_path):
    workdir, copies = final_stage_copies((REPO / "Dockerfile").read_text())
    root = tmp_path / "image"
    wd = root / workdir.lstrip("/")
    wd.mkdir(parents=True)
    for sources, dest in copies:
        target = (wd / dest) if not dest.startswith("/") else (root / dest.lstrip("/"))
        for src in sources:
            path = REPO / src
            assert path.exists(), f"the Dockerfile copies {src}, which is not in the repository"
            if path.is_dir():
                shutil.copytree(path, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
            elif dest.endswith("/") or len(sources) > 1:
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy(path, target / path.name)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(path, target)
    assert not (wd / "main.py").exists()                                 # the hackathon app is not in the image
    probe = (
        "import json, sanad_app\n"
        "from fastapi.testclient import TestClient\n"
        "with TestClient(sanad_app.app) as c:\n"
        "    h = c.get('/api/health').json()\n"
        "    cfg = c.get('/api/assistant/config').json()\n"
        "    q = c.post('/api/assistant/query', json={'content': 'Show me the status of all the engines.'}).json()\n"
        "    import time\n"
        "    for _ in range(200):\n"
        "        st = c.get('/api/assistant/query/' + q['queryId']).json()\n"
        "        if st['done']: break\n"
        "        time.sleep(0.02)\n"
        "    docs = sum(len(x['documents']) for x in cfg['collections'])\n"
        "    print(json.dumps({'app': h['app'], 'assistant': h['assistant'], 'docs': docs, 'card': st['result']['cards'][0]['id']}))\n"
    )
    env = {"PATH": "/usr/bin:/bin", "SANAD_PERSIST": "false", "FRONTEND_DIST": str(tmp_path / "no-dist"), "PYTHONDONTWRITEBYTECODE": "1"}
    run = subprocess.run([sys.executable, "-c", probe], cwd=wd, env=env, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-1500:]
    import json
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out == {"app": "sanad", "assistant": "built-in", "docs": 9, "card": "engine_status"}
