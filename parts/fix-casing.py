from mosestokenizer import MosesTokenizer, MosesDetokenizer, MosesSentenceSplitter
import sys
tokenizer = MosesTokenizer('en')
detokenizer = MosesDetokenizer('en') 

splitter = MosesSentenceSplitter("en")


def list_rindex(l,x):
    for i in range(len(l)-1,-1,-1):
        if l[i] == x:
            return i

def in_list_rindex(l,x):
    for i in range(len(l)-1,-1,-1):
        if l[i] in x:
            return i

breakers = ["and","uh","um"] #you","i","i'm","they","he","she"]
def truncate_punct(line,slen):
    N = 80-slen
    print(line,file=sys.stderr,flush=True)
    for sent in splitter([line]):
        tsent = tokenizer(sent)

        while True:
            if len(tsent) <= N:
                for t in tsent:
                    yield t
                N = 80
                break
            if "," in tsent[:N]:
                i = list_rindex([x.lower() for x in tsent[:N]],",")
                for t in tsent[:i-1]:
                    yield t
                yield "."  # changing , to .
                N = 80
                tsent = tsent[i+1:]
                tsent[0] = tsent[0].capitalize() #+ " @@ "

            elif any(x in tsent[:N] for x in breakers):
                i = in_list_rindex([x.lower() for x in tsent[:N]],breakers)
                for t in tsent[:i-1]:
                    yield t
                yield "."  # putting . in front of and
                N = 80
                tsent = tsent[i:]
                tsent[0] = tsent[0].capitalize() #+ " @@ "
            else:
                i = N
                for t in tsent[:i]:
                    yield t
                yield "."
                N = 80
                tsent = tsent[i:]
                tsent[0] = tsent[0].capitalize() #+ " ## "



eos = False
slen = 0
for line in sys.stdin:
    a,b,*_ = line.split(" ")
    line = line[len(a)+len(b)+2:]
    out = []
#    for w in truncate_punct(line):
    for w in truncate_punct(line,slen):
        slen += 1
        if w in [".","!","?"]:
            eos = True
        elif eos:
#            if w != w.capitalize():
#                s = " @@ "
#            else:
#                s = ""
            w = w.capitalize() #+ s
            eos = False
            slen = 0
        out.append(w)
        print(slen,file=sys.stderr)
    detok = " " if line[0] == " " else ""
    detok += detokenizer(out)
#    detok = detok.replace("_ _ _ END _ OF _ VOICE _ _ _", "___END_OF_VOICE___")
    print(a,b,detok,flush=True)