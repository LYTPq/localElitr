#!/usr/bin/env python3
import threading, queue, sys, time, argparse, socketserver, os
from collections import OrderedDict
import ctranslate2
from transformers import AutoTokenizer

CFG_MAX_LEN = 64            
CFG_SRC_MAX_LEN = 256       
CFG_MAX_BATCH = 32          
CFG_MAX_LINE_BYTES = 6500  

BATCH_DELIM = "|||"

NLLB = {
  "en": "eng_Latn", "ru": "rus_Cyrl", "de": "deu_Latn",
  "fr": "fra_Latn", "es": "spa_Latn", "it": "ita_Latn",
  "uk": "ukr_Cyrl", "pl": "pol_Latn",
}

CACHE_MAX = 50000
_cache = OrderedDict()
_cache_lock = threading.Lock()

def cache_get(key):
    with _cache_lock:
        v = _cache.get(key)
        if v: _cache.move_to_end(key)
        return v

def cache_put(key, val):
    with _cache_lock:
        _cache[key] = val
        if len(_cache) > CACHE_MAX: _cache.popitem(last=False)

# work queue 
class Job:
    __slots__ = ("tgt_tok", "text_norm", "cache_key", "result", "event")
    def __init__(self, tgt_tok, text_norm, cache_key):
        self.tgt_tok = tgt_tok
        self.text_norm = text_norm
        self.cache_key = cache_key
        self.result = None
        self.event = threading.Event()

_job_q = queue.Queue()

def normalize(s: str) -> str:
    return " ".join(s.split())

def translate_worker(translator, tokenizer, beam_size):

    tok_src = NLLB["en"]
    while True:
        try:
            first_job = _job_q.get()
        except EOFError:
            break

        batch = [first_job]
        
        # we grab anything currently waiting up to limit
        while len(batch) < CFG_MAX_BATCH:
            try:
                batch.append(_job_q.get_nowait())
            except queue.Empty:
                break
        
        texts = [j.text_norm for j in batch]
        
        # tokenize
        enc = tokenizer(
            texts, 
            add_special_tokens=False, 
            padding=False, 
            truncation=True, 
            max_length=CFG_SRC_MAX_LEN, 
            return_attention_mask=False
        )

        source_tokens = []
        for ids in enc["input_ids"]:
            t = tokenizer.convert_ids_to_tokens(ids)
            source_tokens.append([tok_src] + t + ["</s>"])

        target_prefix = [[j.tgt_tok] for j in batch]

        # translate
        try:
            results = translator.translate_batch(
                source_tokens,
                target_prefix=target_prefix,
                beam_size=beam_size,
                max_decoding_length=CFG_MAX_LEN,
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            for j in batch: j.event.set()
            continue

        # decode
        for j, res in zip(batch, results):
            out_tokens = res.hypotheses[0]
            if out_tokens and out_tokens[0] == j.tgt_tok:
                out_tokens = out_tokens[1:]
            
            out_text = tokenizer.convert_tokens_to_string(out_tokens).replace("\n", " ").strip()
            cache_put(j.cache_key, out_text)
            j.result = out_text
            j.event.set()

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        w = self.wfile
        while True:
            line = self.rfile.readline()
            if not line: break
            if len(line) > CFG_MAX_LINE_BYTES: w.write(b"\n"); continue
            
            line_str = line.decode("utf-8", errors="ignore").rstrip()
            if not line_str or "\t" not in line_str: w.write(b"\n"); continue

            tgt, text = line_str.split("\t", 1)
            tok_tgt = NLLB.get(tgt)
            if not tok_tgt or not text: w.write(b"\n"); continue

            parts = text.split(BATCH_DELIM)
            valid_indices = [i for i, p in enumerate(parts) if p.strip()]
            
            if not valid_indices:
                w.write((BATCH_DELIM.join([""]*len(parts)) + "\n").encode())
                continue

            jobs = []
            outs = [""] * len(parts)
            
            for i in valid_indices:
                raw = parts[i]
                norm = normalize(raw)
                key = (tgt, norm)
                cached = cache_get(key)
                if cached is not None:
                    outs[i] = cached
                else:
                    j = Job(tok_tgt, norm, key)
                    jobs.append((i, j))
                    _job_q.put(j)

            for i, j in jobs:
                j.event.wait()
                if j.result: outs[i] = j.result

            w.write((BATCH_DELIM.join(outs) + "\n").encode())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=6006)
    ap.add_argument("--ct2_model", required=True)
    ap.add_argument("--hf_tokenizer", required=True)
    ap.add_argument("--device", default="cuda", choices=["cuda","cpu"])
    ap.add_argument("--beam", type=int, default=1) 
    ap.add_argument("--workers", type=int, default=1)
    
    ap.add_argument("--inter_threads", type=int, default=1)
    ap.add_argument("--intra_threads", type=int, default=4)

    args = ap.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.hf_tokenizer, use_fast=True)
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    
    translator = ctranslate2.Translator(
        args.ct2_model,
        device=args.device,
        compute_type="int8" if args.device=="cpu" else "float16",
        inter_threads=args.inter_threads,
        intra_threads=args.intra_threads
    )

    # start workers
    for _ in range(args.workers):
        t = threading.Thread(
            target=translate_worker, 
            args=(translator, tokenizer, args.beam), 
            daemon=True
        )
        t.start()

    class ThreadingServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    server = ThreadingServer((args.host, args.port), Handler)
    server.serve_forever()

if __name__ == "__main__":
    main()