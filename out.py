import time, random, textwrap, string
from termcolor import cprint, colored # type: ignore
from typing import Callable
from shutil import get_terminal_size

#
# Important announcements to the user!
#

sqlstr = "Issued 🢩 "

def announceSqlStart(s):
    print(f"{sqlstr}⟦{s}⟧")

def announceSqlEnd(s):
    print(" " * len(sqlstr) + f"⟦{s}⟧ 🢨 Done!")

def announce(s):
    cprint(f"==> {s}", 'blue', attrs = ['bold'])

def announceLoud(lines: list) -> None:
    maxl = max(map(len, lines))
    lt = "┃⮚ "
    rt = " ⮘┃"
    p = ["{l}{t}{r}".format(l = lt, t = i.center(maxl), r = rt) for i in lines]
    pmaxl = maxl + len(lt) + len(rt)
    cp = lambda x: cprint(x, 'green', attrs = ['bold'])
    cp('┏' + '━' * (pmaxl - 2) + '┓')
    for i in p:
        cp(i)
    cp('┗' + '━' * (pmaxl - 2) + '┛')

def announceBox(s):
    boundary = 80 # maximum length to wrap to
    bl = '║ '
    br = ' ║'
    hz = '═'
    ul = '╔'
    ur = '╗'
    ll = '╚'
    lr = '╝'
    inner = boundary - len(bl) - len(br)
    lines = textwrap.wrap(s, width = inner, break_on_hyphens = False)
    maxl = max(map(len, lines))
    topbord = ul + hz * (maxl + 2) + ur
    botbord = ll + hz * (maxl + 2) + lr
    cp = lambda x: cprint(x, 'magenta', attrs = ['bold'])
    cp(topbord)
    for l in lines:
        cp(bl + l.ljust(maxl) + br)
    cp(botbord)

def spinWait(waitFunc: Callable[[], float]) -> None:
    ls = ' '
    lb = '┠'
    rb = '┨'
    anim1 = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']
    anim2 = ['⣷', '⣯', '⣟', '⡿', '⢿', '⣻', '⣽', '⣾']
    bs = len(ls) + len(anim1[0]) + len(lb) + len(rb) + len(anim2[0])
    maxlen = 0
    f = min(len(anim1), len(anim2))
    barlength = None
    minpctsz = len("─1%─┤")
    cd = lambda x: colored(x, 'red')
    def eraseLine(flush: bool = False):
        cprint(cd(' ' * maxlen), end = '\r', flush = flush)

    i = 0
    pct = 0.0
    while pct < 1.0:
        pct = waitFunc()
        assert pct <= 1.0
        newbarlength = get_terminal_size(fallback = (72, 24)).columns - bs
        if barlength and barlength != newbarlength:
            eraseLine(flush = True)
        barlength = newbarlength
        c = int(pct * barlength)
        if c == 0:
            arrow = ""
        elif c == 1:
            arrow = '┤'
        elif c < minpctsz:
            arrow = (c - 1) * '─' + '┤'
        else:
            p100 = str(int(100 * pct)) + '%'
            rmdr = c - len(p100) - 1 # 1 for arrowhead
            left = rmdr >> 1
            right = rmdr - left
            arrow = left * '─' + p100 + right * '─' + '┤'
        s = ls + anim1[i % f] + lb + arrow + ' ' * (barlength - c) + \
                rb + anim2[i % f]
        maxlen = max(maxlen, len(s))
        print(cd(s), end='\r', flush=True)
        if pct == 1.0:
            # When we finish, erase all traces of progress meter
            eraseLine(flush = False)
            return
        i += 1
        time.sleep(0.25)

def spinWaitTest():
    count = 0.0
    def countUp(maxinc: float) -> float:
        nonlocal count
        count += random.uniform(0.0, maxinc)
        if count > 1.0:
            count = 1.0
        return count
    maxinc = 0.01
    for i in range(1,6):
        spinWait(lambda: countUp(maxinc))
        count = 0.0
        maxinc *= 1.5

# TODO: This shouldn't be in this module. This is a hack.
def randomString(length: int) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k = length))

