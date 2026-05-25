#!/usr/bin/env python3
"""Trim config.yaml's sensors[] to a subset of types.

Used by the firstrun snippet to honour the per-device sensor selection that
the researcher made on the web setup page. Pi-side, after bootstrap.sh has
seeded config.yaml from the template (which lists every supported sensor),
this script removes the entries the researcher unchecked.

Example:
    util_set_sensors.py --keep BME280,Camera,IWS660CS

Idempotent. Safe to re-run with the same `--keep`. Pass `--keep all` (or
omit the flag) to leave the config untouched.
"""

import argparse
import os
import sys

try:
    import yaml
except ImportError:
    print("Error: The 'yaml' library is missing.", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", required=True,
                        help='Comma-separated sensor types to keep (e.g. "BME280,Camera"), '
                             'or "all" to leave the config untouched.')
    parser.add_argument("--config", default=DEFAULT_CONFIG,
                        help="Path to config.yaml (default: project root config.yaml)")
    args = parser.parse_args()

    if args.keep.strip().lower() in ("", "all"):
        print("util_set_sensors: --keep is 'all'; leaving config.yaml untouched.")
        return 0

    keep = {t.strip() for t in args.keep.split(",") if t.strip()}
    if not keep:
        print("util_set_sensors: --keep parsed to an empty set; refusing to delete every sensor.",
              file=sys.stderr)
        return 1

    if not os.path.exists(args.config):
        print(f"util_set_sensors: config not found at {args.config}", file=sys.stderr)
        return 1

    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f) or {}

    before = cfg.get("sensors") or []
    before_types = {s.get("type") for s in before}
    after = [s for s in before if s.get("type") in keep]

    # Warn (don't fail) when --keep names a type that isn't in the
    # template's sensor list — usually a typo. Doesn't abort because the
    # remaining names may still produce a viable config.
    unknown = sorted(keep - before_types)
    if unknown:
        print(f"util_set_sensors: warning — these --keep names matched no sensor "
              f"in the template and were ignored: {unknown}. "
              f"Available types: {sorted(before_types)}.", file=sys.stderr)

    if not after:
        print(f"util_set_sensors: refusing to write an empty sensors list "
              f"(none of {sorted(keep)} matched the template's "
              f"{sorted({s.get('type') for s in before})}).", file=sys.stderr)
        return 1

    cfg["sensors"] = after

    with open(args.config, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    removed = sorted({s.get("type") for s in before} - {s.get("type") for s in after})
    print(f"util_set_sensors: kept {len(after)}/{len(before)} sensors. "
          f"Active: {sorted({s.get('type') for s in after})}. "
          f"Removed: {removed or 'none'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
