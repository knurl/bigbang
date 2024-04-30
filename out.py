import time
import textwrap
from termcolor import cprint, colored # type: ignore
from typing import Callable
from shutil import get_terminal_size

#
# Important announcements to the user!
#

sqlstr = "Issued 🢩 "

def announceSql(i: int, s: str) -> None:
    print(f'Stored Cmd {i}  ')


def announceSqlEnd(s: str) -> None:
    print(' ' * len(sqlstr) + f"⟦{s}⟧ 🢨 Done!")

def announce(s: str) -> None:
    cprint(f'==> {s}', 'blue', attrs = ['bold'])

def announceStart(s: str) -> None:
    cprint(f'--> ⇩ ⟦{s}⟧ START ⇩', 'cyan', attrs = ['bold'])

def announceEnd(s: str, tinterv: float) -> None:
    ts = time.strftime("%Mm%Ss", time.gmtime(tinterv))
    cprint(f'--> ⇧ ⟦{s}⟧ ENDED in {ts} ⇧', 'cyan', attrs = ['bold'])

def announceLoud(lines: list[str]) -> None:
    maxl = max(map(len, lines))
    lt = "┃⮚ "
    rt = " ⮘┃"
    p = ["{l}{t}{r}".format(l = lt, t = i.center(maxl), r = rt) for i in lines]
    pmaxl = maxl + len(lt) + len(rt)
    def cp(x):
        return cprint(x, 'green', attrs = ['bold'])
    cp('┏' + '━' * (pmaxl - 2) + '┓')
    for i in p:
        cp(i)
    cp('┗' + '━' * (pmaxl - 2) + '┛')

def announceBox(s: str) -> None:
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
    def cp(x):
        return cprint(x, 'magenta', attrs = ['bold'])
    cp(topbord)
    for line in lines:
        cp(bl + line.ljust(maxl) + br)
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
    def cd(x):
        return colored(x, 'red')
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
