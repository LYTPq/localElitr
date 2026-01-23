#!/usr/bin/env python3
import sys
for line in sys.stdin:
	print(line,end="",flush=True)
	beg, end, *_ = line.split(" ")
	if int(end)-int(beg) != 100:
		print(line.strip()+" ",flush=True)