#!/usr/bin/env python3
"""Allow Android modprobe to recognize already built-in wireless dependencies."""
import argparse
from pathlib import Path

from verify_vendor_wifi_abi import selected_references

HELPER = '''/* Android modprobe treats EEXIST as an already loaded dependency.
 * These factory modules are replaced by ABI-checked built-in implementations;
 * do not reach duplicate-export validation and abort the WLAN dependency chain.
 */
static bool builtin_wifi_dependency(const struct module *mod)
{
	return (IS_BUILTIN(CONFIG_CFG80211) && !strcmp(mod->name, "cfg80211")) ||
	       (IS_BUILTIN(CONFIG_RFKILL) && !strcmp(mod->name, "rfkill"));
}

'''
ANCHOR = 'static int add_unformed_module(struct module *mod)\n{\n\tint err;\n'
GUARD = '\n\tif (builtin_wifi_dependency(mod))\n\t\treturn -EEXIST;\n'


def install(source):
    path = source / 'kernel/module/main.c'
    text = path.read_text()
    if HELPER in text and ANCHOR + GUARD in text:
        return
    if 'builtin_wifi_dependency' in text or text.count(ANCHOR) != 1:
        raise ValueError('Unexpected module loader layout; refusing partial compatibility patch')
    text = text.replace(ANCHOR, HELPER + ANCHOR + GUARD)
    path.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--model', required=True)
    parser.add_argument('--os-version', required=True)
    parser.add_argument('--kernel', required=True)
    args = parser.parse_args()
    refs = selected_references(args.model, args.os_version, args.kernel)
    if not any(ref.get('builtin_module_compat') for ref in refs):
        print('No factory-validated built-in module compatibility override for this target')
        return
    install(args.source)
    print('Factory WLAN dependency compatibility: built-in cfg80211/rfkill return EEXIST')


if __name__ == '__main__':
    main()
