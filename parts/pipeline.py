import argparse
import yaml
import shlex
from pipeliner import Pipeliner

LOCALHOST = "127.0.0.1"

def load_cfg(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def must(d: dict, key: str):
    if key not in d or d[key] is None:
        raise KeyError(f"Missing config key: {key}")
    return d[key]

def generate_env(cfg: dict) -> str:
    exports = []

    def add(k, v):
        exports.append(f"export {k.upper()}={shlex.quote(str(v))}")

    for section in ["paths", "models"]:
        for k, v in cfg.get(section, {}).items():
            add(k, v)

    for k, v in cfg.get("ports", {}).items():
        add(f"{k}_PORT", v)

    for k, v in cfg.get("ct2", {}).items():
        add(f"CT2_{k}", v)

    for k, v in cfg.get("whisper", {}).items():
        if k == "vac" and v is True: v = "1"
        elif k == "vac" and v is False: v = "0"
        add(f"WH_{k}", v)

    return "; ".join(exports)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    cfg = load_cfg(args.config)

    paths = must(cfg, "paths")
    ports = must(cfg, "ports")
    AUDIO_INPUT_PORT = 12345
    



    PY = must(paths, "py")
    MTW = must(paths, "mtw")
    CT2_CLIENT = must(paths, "ct2_client")
    FIX = must(paths, "fix")
    LAST_FLUSH = must(paths, "last_flush")
    START_SERVICES = must(paths, "start_services")
   # AUDIO_SOURCE = must(paths, "audio")

    

    CT2_PORT = int(must(ports, "ct2"))
    ASR_PORT = int(must(ports, "asr"))
    TF_PORT  = int(must(ports, "textflow"))

    LANGS = must(cfg, "langs")
    config_exports = generate_env(cfg)

   
    p = Pipeliner(logsDir="./logs")

    services_cmd = f"{config_exports}; exec bash {START_SERVICES}"
    
    services = p.addLocalNode(
        "services",
        {},
        {"ok": "stdout"},
        f"bash -lc {shlex.quote(services_cmd)}"
    )

    sink = p.addLocalNode(
        "services_sink",
        {"in": "stdin"},
        {},
        "cat >/dev/null"
    )
    p.addEdge(services, "ok", sink, "in", type="none")


    wait_cmd = (
        f"until nc -z {LOCALHOST} {ASR_PORT}; do sleep 0.1; done; "
        f"until nc -z {LOCALHOST} {TF_PORT};  do sleep 0.1; done; "
        f"until nc -z {LOCALHOST} {CT2_PORT}; do sleep 0.1; done; "
    )
    
    stream_cmd = f"exec nc -l -k -p {AUDIO_INPUT_PORT}"

    audio = p.addLocalNode(
        "audio",
        {},
        {"raw": "stdout"},
        f"bash -lc {shlex.quote(wait_cmd + stream_cmd)}"
    )

    asr_client = p.addLocalNode(
        "asr_nc_client",
        {"audio_raw": "stdin"},
        {"asr_text": "stdout"},
        f"bash -lc 'until (echo >/dev/tcp/{LOCALHOST}/{ASR_PORT}) >/dev/null 2>&1; do sleep 0.2; done; "
        f"exec nc {LOCALHOST} {ASR_PORT} < /dev/stdin | tee /tmp/asr_stream.txt'"
    )

    asr_events = p.addLocalNode(
        "asr_events",
        {"asr_text": "stdin"},
        {"events_out": "stdout"},
        "stdbuf -oL online-text-flow events en -b"
    )
    fix_asr = p.addLocalNode(
        "fix_casing",
        {"in": "stdin"},
        {"out": "stdout"},
        f"stdbuf -oL {PY} -u {FIX}"
    )

    last_flush = p.addLocalNode(
        "last_flush",
        {"in": "stdin"},
        {"out": "stdout"},
        f"stdbuf -oL {PY} -u {LAST_FLUSH}"
    )

    textflow_en = p.addLocalNode(
        "textflow_en",
        {"in": "stdin"},
        {},
        f"online-text-flow client -b en ws://{LOCALHOST}:{TF_PORT}/textflow"
    )

    p.addSimpleEdge(audio, asr_client)
    p.addSimpleEdge(asr_client, asr_events)
    p.addSimpleEdge(asr_events, fix_asr)
    p.addSimpleEdge(fix_asr, last_flush)
    p.addSimpleEdge(last_flush, textflow_en)

    # translation branches
    for lang in LANGS:
        mt_cmd = (
            f"stdbuf -oL {MTW} en "
            f"--eventsIn "
            f"--batch-delimiter '|||' "
            f"--min_status 0 "
            f"--mt '{PY} -u {CT2_CLIENT} --tgt {lang} --host {LOCALHOST} --port {CT2_PORT}'"
        )
        
        mt = p.addLocalNode(
            f"mtwrapper_{lang}",
            {"events_in": "stdin"},
            {"events_out": "stdout"},
            mt_cmd
        )

        client = p.addLocalNode(
            f"textflow_client_{lang}",
            {"events_out": "stdin"},
            {},
            f"stdbuf -oL online-text-flow client -b {lang} ws://{LOCALHOST}:{TF_PORT}/textflow"
        )

        p.addSimpleEdge(last_flush, mt)
        p.addSimpleEdge(mt, client)

    p.createPipeline()

if __name__ == "__main__":
    main()