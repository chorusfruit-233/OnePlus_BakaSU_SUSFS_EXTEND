#!/usr/bin/env python3
"""Recover only the known SUSFS namespace include/declaration reject."""
import argparse
from pathlib import Path

ADDITIONS = (
    "#ifdef CONFIG_KSU_SUSFS",
    "#include <linux/susfs_def.h>",
    "#endif // #ifdef CONFIG_KSU_SUSFS",
    "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT",
    "extern bool susfs_is_current_ksu_domain(void);",
    "extern struct static_key_true susfs_is_sdcard_android_data_not_decrypted;",
    "#define CL_COPY_MNT_NS BIT(25) /* used by copy_mnt_ns() */",
    "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT",
)
INCLUDE = "\n".join(ADDITIONS[:3]) + "\n"
DECLARATIONS = "\n".join(ADDITIONS[3:]) + "\n"


def recover(source):
    target = source / "fs/namespace.c"
    reject = source / "fs/namespace.c.rej"
    if not reject.is_file():
        return False
    lines = reject.read_text().splitlines()
    additions = [line[1:].strip() for line in lines
                 if line.startswith("+") and not line.startswith("+++") and line[1:].strip()]
    # A reject containing another hunk or any functional change stays intact.
    if sum(line.startswith("@@ ") for line in lines) != 1 or sorted(additions) != sorted(ADDITIONS):
        return False

    text = target.read_text()
    include_present = ADDITIONS[1] in text
    symbol_presence = [line in text for line in ADDITIONS[4:7]]
    if any(symbol_presence) and not all(symbol_presence):
        return False
    anchors = []
    if not include_present:
        anchors.append("#include <linux/mnt_idmapping.h>\n")
    if not all(symbol_presence):
        anchors.append('#include "internal.h"\n')
    if any(text.count(anchor) != 1 for anchor in anchors):
        return False

    if not include_present:
        anchor = "#include <linux/mnt_idmapping.h>\n"
        text = text.replace(anchor, anchor + INCLUDE, 1)
    if not all(symbol_presence):
        anchor = '#include "internal.h"\n'
        text = text.replace(anchor, anchor + DECLARATIONS, 1)
    target.write_text(text)
    reject.unlink()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    try:
        if recover(args.source):
            print("Recovered the known SUSFS namespace header context")
    except (OSError, ValueError) as error:
        # Keep the action's existing reject dump and fatal error handling.
        print("::warning::SUSFS namespace context recovery declined: " + str(error))


if __name__ == "__main__":
    main()
