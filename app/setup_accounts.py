"""Adds or removes Gmail accounts. Passwords are stored in your Mac's Keychain, not in any file."""
from __future__ import annotations

import getpass
import imaplib
import json

import keyring

from common import ACCOUNTS_PATH

SERVICE = "JobTracker-Gmail"


def load():
    if ACCOUNTS_PATH.exists():
        return json.loads(ACCOUNTS_PATH.read_text()).get("accounts", [])
    return []


def save(accts):
    ACCOUNTS_PATH.write_text(json.dumps({"accounts": accts}, indent=1))


def add(accts):
    print("\n  You need a Gmail APP PASSWORD (not your normal password):")
    print("   1. Turn on 2-Step Verification: https://myaccount.google.com/signinoptions/twosv")
    print("   2. Make an app password:        https://myaccount.google.com/apppasswords")
    print("      Name it 'Job Tracker'. Google shows a 16-letter code. Copy it.")
    print("   3. Make sure IMAP is on: Gmail > Settings > See all settings > Forwarding and POP/IMAP > Enable IMAP.\n")
    addr = input("  Gmail address: ").strip().lower()
    if not addr:
        return
    pw = getpass.getpass("  App password (typing is hidden; paste and press Enter): ").replace(" ", "").strip()
    print("  Testing login...")
    try:
        im = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        im.login(addr, pw)
        im.logout()
    except Exception as e:
        print(f"  Login failed: {e}\n  Double-check the address and app password, then try again.")
        return
    keyring.set_password(SERVICE, addr, pw)
    if addr not in accts:
        accts.append(addr)
    save(accts)
    print(f"  Saved {addr}. The password is in your Keychain.")


def remove(accts):
    for i, a in enumerate(accts, 1):
        print(f"   {i}. {a}")
    v = input("  Number to remove: ").strip()
    if v.isdigit() and 1 <= int(v) <= len(accts):
        a = accts.pop(int(v) - 1)
        try:
            keyring.delete_password(SERVICE, a)
        except Exception:
            pass
        save(accts)
        print(f"  Removed {a}.")


def main():
    accts = load()
    while True:
        print("\n  Gmail accounts: " + (", ".join(accts) if accts else "none yet"))
        v = input("  [a] add an account   [r] remove one   [Enter] done: ").strip().lower()
        if v == "a":
            add(accts)
        elif v == "r" and accts:
            remove(accts)
        else:
            break


if __name__ == "__main__":
    main()
