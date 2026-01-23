#!/usr/bin/env python3
import argparse, socket, sys, re, time

def connect_with_retry(host, port, tries=400, sleep_s=0.05):
    last = None
    for _ in range(tries):
        try:
            return socket.create_connection((host, port), timeout=None)
        except OSError as e:
            last = e
            time.sleep(sleep_s)
    raise last

re_line = re.compile(r"^\s*(\d+)\s+(\d+)\s+(.*)$")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tgt", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6006)
    args = ap.parse_args()

    s = connect_with_retry(args.host, args.port)

    f_in = s.makefile("r", encoding="utf-8", newline="\n")
    f_out = s.makefile("w", encoding="utf-8", newline="\n", buffering=1)

    # read -> send -> print
    while True:
        line = sys.stdin.readline()
        if not line:
            break
            
        line = line.rstrip("\n")
        
        
        m = re_line.match(line)
        if m:
            a, b, txt = m.group(1), m.group(2), m.group(3).strip()
            out_prefix = f"{a} {b} "
        else:
            txt = line.strip()
            out_prefix = ""

        if not txt:
            print(out_prefix.strip(), flush=True)
            continue

        # send to server
        try:
            f_out.write(f"{args.tgt}\t{txt}\n")
            f_out.flush() 
        except BrokenPipeError:
            sys.exit(1)

        tr = f_in.readline()
        if not tr:
            break
        tr = tr.rstrip("\n")

        print(f"{out_prefix}{tr}", flush=True)

if __name__ == "__main__":
    main()