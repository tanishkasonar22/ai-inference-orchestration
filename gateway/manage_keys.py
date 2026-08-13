"""Admin CLI for API keys -- no self-service portal yet, this is it for now.

Usage:
  python manage_keys.py create-key <customer-name>
  python manage_keys.py revoke-key <key-prefix>      # prefix shown at creation, e.g. sk-ab12cdef
  python manage_keys.py usage [--customer <name>]
"""
import argparse

import keystore


def cmd_create(args):
    raw_key = keystore.create_api_key(args.customer)
    print(f"Created key for '{args.customer}':\n")
    print(f"  {raw_key}\n")
    print("Save this now -- it will not be shown again.")


def cmd_revoke(args):
    if keystore.revoke_key(args.key_prefix):
        print(f"Revoked key with prefix '{args.key_prefix}'.")
    else:
        print(f"No active key found with prefix '{args.key_prefix}'.")


def cmd_usage(args):
    rows = keystore.usage_summary(args.customer)
    if not rows:
        print("No usage recorded.")
        return
    print(f"{'customer':<20} {'model':<20} {'requests':>10} {'total_tokens':>14}")
    for r in rows:
        print(f"{r['customer']:<20} {r['model']:<20} {r['requests']:>10} "
              f"{r['total_tokens'] or 0:>14}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create-key")
    p.add_argument("customer")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("revoke-key")
    p.add_argument("key_prefix")
    p.set_defaults(func=cmd_revoke)

    p = sub.add_parser("usage")
    p.add_argument("--customer", default=None)
    p.set_defaults(func=cmd_usage)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
