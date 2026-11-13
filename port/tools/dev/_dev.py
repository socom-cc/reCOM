"""_dev.py: shared paths for the port development tools (imported by the other .py tools here).

REPO      checkout root, derived from this file's location (port/tools/dev/../../..).
elf()     bytes of the reference ELF: SOCOM_ELF if set, else <repo>/support/socom.elf.
scratch() the worker scratch folder: SOCOM_SCRATCH (absolute, or relative to the repo root),
          default <repo>/build/port/dev (build/ is ignored by git).
types()   DWARF type rows (list of dicts) from build/port/dwarf-graph-rows.json, cached as
          build/port/cache/types.pkl (SOCOM_DEV_CACHE moves the cache); the rows file is generated on first use with
          `python tools/socom.py debug import-plan --rows --output build/port/dwarf-graph-rows.json`.
Read-only on the reference ELF; writes only under build/.
"""
import os
import pickle
import subprocess
import sys

DEV = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(DEV, '..', '..', '..'))
SRC = os.path.join(REPO, 'src')
ROWS = os.path.join(REPO, 'build', 'port', 'dwarf-graph-rows.json')


def _abs(p):
    p = os.path.expanduser(p)
    return p if os.path.isabs(p) else os.path.join(REPO, p)


def elf_path():
    return _abs(os.environ.get('SOCOM_ELF') or os.path.join('support', 'socom.elf'))


_elf = None


def elf():
    global _elf
    if _elf is None:
        p = elf_path()
        if not os.path.isfile(p):
            sys.exit('reference ELF not found: %s (put it at support/socom.elf or set SOCOM_ELF)' % p)
        with open(p, 'rb') as f:
            _elf = f.read()
    return _elf


def scratch(sub=None, make=True):
    d = _abs(os.environ.get('SOCOM_SCRATCH') or os.path.join('build', 'port', 'dev'))
    if sub:
        d = os.path.join(d, sub)
    if make:
        os.makedirs(d, exist_ok=True)
    return d


def types():
    cache = _abs(os.environ.get('SOCOM_DEV_CACHE') or os.path.join('build', 'port', 'cache'))
    pkl = os.path.join(cache, 'types.pkl')
    if os.path.exists(pkl) and os.path.exists(ROWS) and os.path.getmtime(pkl) >= os.path.getmtime(ROWS):
        with open(pkl, 'rb') as f:
            return pickle.load(f)
    if not os.path.exists(ROWS):
        sys.stderr.write('generating %s (one-time, about 30 s)\n' % os.path.relpath(ROWS, REPO))
        r = subprocess.run([sys.executable, os.path.join(REPO, 'tools', 'socom.py'), 'debug', 'import-plan',
                            '--rows', '--output', os.path.relpath(ROWS, REPO).replace(os.sep, '/')],
                           cwd=REPO, stdout=subprocess.DEVNULL)
        if r.returncode or not os.path.exists(ROWS):
            sys.exit('could not generate the DWARF rows; run: python tools/socom.py debug import-plan '
                     '--rows --output build/port/dwarf-graph-rows.json')
    import json
    with open(ROWS, encoding='utf-8') as f:
        t = json.load(f)['types']
    os.makedirs(cache, exist_ok=True)
    with open(pkl, 'wb') as f:
        pickle.dump(t, f)
    return t
