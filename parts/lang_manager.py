#!/usr/bin/env python3
#language manager: starts and stops one translation branch per target language.

# reads the post-processed source text (the output of last_flush.py) on stdin
#and copies every line into each running branch. A branch is

#mt-wrapper -> ct2_client.py -> online-text-flow client 
#for one target language. Branches are switched on and off over HTTP:

#GET /lang              -> {"source": .., "active": [..], "available": [..]}
#GET /lang/<code>/on    -> start the branch for <code>
#GET /lang/<code>/off   -> stop it

import argparse
import json
import os
import queue
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from nllb_langs import NLLB

QUEUE_MAX = 10000  # lines buffered per branch before we start dropping


def log(*args):
    print("[lang_manager]", *args, file=sys.stderr, flush=True)




class Branch:
    def __init__(self, lang, cmd):
        self.lang = lang
        self.proc = subprocess.Popen(
            cmd, shell=True, executable="/bin/bash",
            stdin=subprocess.PIPE, stdout=sys.stderr,
            start_new_session=True,  # own process group -> killpg stops the whole pipeline
        )
        self.queue = queue.Queue(maxsize=QUEUE_MAX)
        self.dropped = 0
        self.writer = threading.Thread(target=self._write, daemon=True)
        self.writer.start()

    def _write(self):
        while True:
            line = self.queue.get()
            if line is None:
                return
            try:
                self.proc.stdin.write(line)
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                return  

    def feed(self, line):
        try:
            self.queue.put_nowait(line)
        except queue.Full:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 1000 == 0:
                log(f"{self.lang}: branch is not reading, dropped {self.dropped} lines")

    def alive(self):
        return self.proc.poll() is None

    def stop(self, timeout=5):
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass
        try:
            self.proc.stdin.close()
        except (OSError, ValueError):
            pass
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(self.proc.pid, sig)
            except ProcessLookupError:
                break
            try:
                self.proc.wait(timeout)
                break
            except subprocess.TimeoutExpired:
                continue


class Manager:
    def __init__(self, args):
        self.args = args
        self.lock = threading.Lock()
        self.branches = {}

    def command(self, lang):
        a = self.args
        mt = f"{a.py} -u {a.ct2_client} --tgt {lang} --host {a.host} --port {a.ct2_port}"
        return (
            f"stdbuf -oL {a.mtw} {a.src} --eventsIn --batch-delimiter '|||' --min_status 0 "
            f"--mt {shlex.quote(mt)} "
            f"| stdbuf -oL online-text-flow client -b {lang} ws://{a.host}:{a.tf_port}/textflow"
        )

    def check(self, lang):
        if lang == self.args.src:
            return "source"
        if lang not in NLLB:
            return f"unknown language '{lang}' (no NLLB code in nllb_langs.py)"
        return None

    def start(self, lang):
        with self.lock:
            old = self.branches.get(lang)
            if old is not None and old.alive():
                return "already running"
            if old is not None:
                old.stop()
            branch = Branch(lang, self.command(lang))
            self.branches[lang] = branch
        log(f"{lang}: started (pid {branch.proc.pid})")
        return "started"

    def stop(self, lang):
        with self.lock:
            branch = self.branches.pop(lang, None)
        if branch is None:
            return "not running"
        branch.stop()
        log(f"{lang}: stopped")
        return "stopped"

    def stop_all(self):
        with self.lock:
            branches = list(self.branches.items())
            self.branches.clear()
        for lang, branch in branches:
            branch.stop()
            log(f"{lang}: stopped")


    def active(self):
        with self.lock:
            return sorted(lang for lang, b in self.branches.items() if b.alive())



    def status(self):
        return {
            "source": self.args.src,
            "active": self.active(),
            "available": sorted(k for k in NLLB if k != self.args.src),
        }


    def feed(self, line):
        with self.lock:
            branches = list(self.branches.values())
        for branch in branches:
            if branch.alive():
                branch.feed(line)

    def reap(self):
        #remove branches that exited on their own (crash), so the status stays true."""
        while True:
            time.sleep(1)
            with self.lock:
                dead = [(l, b) for l, b in self.branches.items() if not b.alive()]
                for lang, _ in dead:
                    del self.branches[lang]
            for lang, branch in dead:
                branch.stop()  # kill any leftover processes in its group
                log(f"{lang}: branch exited unexpectedly (code {branch.proc.returncode}), removed")




def make_handler(manager):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if parts == ["lang"]:
                return self.reply(200, manager.status())
            if len(parts) == 3 and parts[0] == "lang" and parts[2] in ("on", "off"):
                lang, action = parts[1].lower(), parts[2]
                problem = manager.check(lang)
                if problem == "source":
                    return self.reply(200, {"lang": lang, "state": "source language, nothing to do",
                                            "active": manager.active()})
                if problem:
                    return self.reply(400, {"lang": lang, "error": problem})
                state = manager.start(lang) if action == "on" else manager.stop(lang)
                return self.reply(200, {"lang": lang, "state": state, "active": manager.active()})
            return self.reply(404, {"error": "use /lang, /lang/<code>/on or /lang/<code>/off"})

        def reply(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            log("http:", fmt % args)

    return Handler


def wait_for_port(host, port, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def start_defaults(manager, langs):
    a = manager.args
    for port in (a.tf_port, a.ct2_port):
        if not wait_for_port(a.host, port, a.wait_timeout):
            log(f"port {port} not up after {a.wait_timeout}s, starting default languages anyway")
    for lang in langs:
        lang = lang.lower()
        problem = manager.check(lang)
        if problem == "source":
            continue
        if problem:
            log(f"default language skipped: {problem}")
            continue
        manager.start(lang)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default="en", help="source language code")
    ap.add_argument("--langs", nargs="*", default=[], help="languages switched on at start")
    ap.add_argument("--listen", default="127.0.0.1", help="address for the HTTP control port")
    ap.add_argument("--port", type=int, default=5001, help="HTTP control port")
    ap.add_argument("--host", default="127.0.0.1", help="where the MT and TextFlow servers run")
    ap.add_argument("--ct2-port", type=int, default=6006)
    ap.add_argument("--tf-port", type=int, default=5000)
    ap.add_argument("--py", default="python3")
    ap.add_argument("--mtw", default="/app/mt-wrapper/mtwrapper.py")
    ap.add_argument("--ct2-client", default="/app/ct2_client.py")
    ap.add_argument("--wait-timeout", type=int, default=600,
                    help="seconds to wait for the servers before starting default languages")
    args = ap.parse_args()

    manager = Manager(args)

    def shutdown(signum=None, frame=None):
        manager.stop_all()
        os._exit(0)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, shutdown)

    server = ThreadingHTTPServer((args.listen, args.port), make_handler(manager))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=manager.reap, daemon=True).start()
    threading.Thread(target=start_defaults, args=(manager, args.langs), daemon=True).start()
    log(f"control on http://{args.listen}:{args.port}/lang, source '{args.src}', "
        f"default languages: {' '.join(args.langs) or 'none'}")

    for line in sys.stdin.buffer:
        manager.feed(line)

    log("input ended, stopping all branches")
    shutdown()


if __name__ == "__main__":
    main()
