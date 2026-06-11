"""Tiny URL-shortener CLI used as the audit target for P11.

It has a few planted issues across independent dimensions (docs, errors,
secrets, deps, tests) so a code audit has something concrete to find.
"""
import sys
import json
import requests  # noqa: F401  (declared in requirements, never actually used)

# Planted issue (secrets): a hardcoded credential.
API_KEY = "sk-live-9c2f1a77b3e84d0fa1c6"

_STORE = {}


def shorten(url):
    code = str(abs(hash(url)) % 1000000)
    _STORE[code] = url
    return code


def resolve(code):
    # Planted issue (errors): bare except that hides the real failure.
    try:
        return _STORE[code]
    except:  # noqa: E722
        return None


def save(path):
    with open(path, "w") as f:
        json.dump(_STORE, f)


def main():
    # Planted issue (docs): README claims a stats command that does not exist.
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "shorten":
        print(shorten(sys.argv[2]))
    elif cmd == "resolve":
        print(resolve(sys.argv[2]))
    else:
        print("usage: app.py [shorten URL | resolve CODE]")


if __name__ == "__main__":
    main()
