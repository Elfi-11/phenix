#!/usr/bin/env python3
"""Gere la liste de blocage nginx : lignes "deny x.x.x.x;  # at=... until=... reason=...".

Usage : python3 blocklist.py <fichier> [--backup <copie>] {add|remove|list|purge} [options]
  add    --ip IP [--minutes N] [--reason MOTIF] [--protect CIDR ...]   (N=0 : jusqu'a unblock_ip)
  remove --ip IP
  list
  purge                                                                  (retire les blocages expires)
Derniere ligne affichee pour add/remove/purge : changed=yes ou changed=no.
Codes de sortie : 0 = ok, 2 = usage, 3 = refus (adresse invalide, protegee ou parametre hors limite).
"""
import argparse
import ipaddress
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone

HEADER = "# adresses bloquées automatiquement par la remédiation\n"
FMT = "%Y-%m-%dT%H:%M:%SZ"
LINE = re.compile(r"^deny\s+(\d{1,3}(?:\.\d{1,3}){3})\s*;\s*#\s*(.*)$")
REASON = re.compile(r"^[A-Za-z0-9_.:-]{0,60}$")
MAX_MINUTES = 10080


def refuse(msg):
    print("REFUSE : " + msg, file=sys.stderr)
    sys.exit(3)


def now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def check_ip(value):
    try:
        ip = ipaddress.IPv4Address(value)
    except ValueError:
        refuse("adresse IPv4 invalide : %r (un seul IP, pas de plage)" % value)
    return ip


def read_lines(path):
    if not os.path.exists(path):
        return [HEADER]
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)
    return lines or [HEADER]


def meta_of(text):
    return dict(kv.split("=", 1) for kv in text.split() if "=" in kv)


def is_expired(meta, ref):
    until = meta.get("until", "never")
    if until == "never":
        return False
    try:
        return datetime.strptime(until, FMT).replace(tzinfo=timezone.utc) <= ref
    except ValueError:
        return False


def entries(lines):
    out = []
    for i, line in enumerate(lines):
        m = LINE.match(line.strip())
        if m:
            out.append((i, m.group(1), meta_of(m.group(2))))
    return out


def drop(lines, indexes):
    keep = set(indexes)
    return [l for i, l in enumerate(lines) if i not in keep]


def write(path, lines, backup):
    if backup and os.path.exists(path):
        shutil.copyfile(path, backup)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(l if l.endswith("\n") else l + "\n" for l in lines))
    os.replace(tmp, path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("--backup")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--ip", required=True)
    a.add_argument("--minutes", default="0")
    a.add_argument("--reason", default="remediation")
    a.add_argument("--protect", action="append", default=[])
    r = sub.add_parser("remove")
    r.add_argument("--ip", required=True)
    sub.add_parser("list")
    sub.add_parser("purge")
    args = p.parse_args()

    ref = now()
    lines = read_lines(args.file)

    if args.cmd == "list":
        found = entries(lines)
        if not found:
            print("(aucune adresse bloquée)")
        for _, ip, meta in found:
            state = "expiré" if is_expired(meta, ref) else "actif"
            print("%-15s | %s | depuis %s | jusqu'à %s | motif %s" % (
                ip, state, meta.get("at", "?"), meta.get("until", "?"), meta.get("reason", "?")))
        return

    if args.cmd == "purge":
        expired = [i for i, _, m in entries(lines) if is_expired(m, ref)]
        if expired:
            write(args.file, drop(lines, expired), args.backup)
        print("%d blocage(s) expiré(s) retiré(s)" % len(expired))
        print("changed=" + ("yes" if expired else "no"))
        return

    ip = check_ip(args.ip)

    if args.cmd == "remove":
        found = [i for i, x, _ in entries(lines) if x == str(ip)]
        if found:
            write(args.file, drop(lines, found), args.backup)
            print("%s débloquée" % ip)
        else:
            print("%s n'était pas bloquée" % ip)
        print("changed=" + ("yes" if found else "no"))
        return

    # add
    if not re.fullmatch(r"[0-9]{1,5}", args.minutes):
        refuse("durée invalide : %r (minutes, entier)" % args.minutes)
    minutes = int(args.minutes)
    if minutes > MAX_MINUTES:
        refuse("durée trop longue (maximum %d minutes)" % MAX_MINUTES)
    if not REASON.match(args.reason):
        refuse("motif invalide (lettres, chiffres, _ . : - seulement, 60 caractères max, sans espace)")
    for cidr in args.protect:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            refuse("plage protégée invalide : %r" % cidr)
        if net.version == 4 and ip in net:
            refuse("adresse protégée, jamais bloquée : %s (plage %s)" % (ip, cidr))

    expired = [i for i, _, m in entries(lines) if is_expired(m, ref)]
    same = [i for i, x, _ in entries(lines) if x == str(ip)]
    lines = drop(lines, set(expired) | set(same))
    until = "never" if minutes == 0 else (ref + timedelta(minutes=minutes)).strftime(FMT)
    lines.append("deny %s;  # at=%s until=%s reason=%s\n" % (ip, ref.strftime(FMT), until, args.reason or "none"))
    write(args.file, lines, args.backup)
    print("%s bloquée %s" % (ip, "jusqu'à levée par un admin (unblock_ip)" if until == "never" else "jusqu'à " + until))
    print("changed=yes")


if __name__ == "__main__":
    main()
