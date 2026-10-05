#!/usr/bin/env python3
"""Install pinned upstream Hybrid Mount and audit its built-in linkage."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile

LOCK = Path(__file__).resolve().parents[1] / "profiles/hybridmount.json"
FILES = ("Kconfig", "hybridmount.c", "hybridmount.h", "PROVENANCE", "UPSTREAM_README.md")
KCONFIG = 'source "fs/hybridmount/Kconfig"'
MAKEFILE = 'obj-$(CONFIG_HYBRIDMOUNT) += hybridmount/'
FLAGS_CONDITION = '#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 12, 0) && LINUX_VERSION_CODE >= KERNEL_VERSION(5, 2, 0)'


def adapt_xattr(contents, source):
    # Android and vendor trees can backport xattr flags independently of version.
    header = (source / "include/linux/xattr.h").read_text()
    header = re.sub(r"/\*.*?\*/", "", header, flags=re.S)
    signatures = {}
    for name, pattern in (("get", r"\(\s*\*get\s*\)\s*\((.*?)\)\s*;"),
                          ("vfs_getxattr", r"\b__vfs_getxattr\s*\((.*?)\)\s*;")):
        match = re.search(pattern, header, re.S)
        if not match:
            raise ValueError(f"Cannot determine Hybrid Mount xattr API: {name}")
        signatures[name] = bool(re.search(r"\bflags\b", match[1]))
    text = contents["hybridmount.h"].decode()
    if text.count(FLAGS_CONDITION) != 1:
        raise ValueError("Pinned Hybrid Mount xattr compatibility block changed")
    text = text.replace(FLAGS_CONDITION, "#if " + str(int(signatures["get"])))
    text += "\n#define HM_VFS_FLAGS_VAL " + (", flags" if signatures["vfs_getxattr"] else "/* Nothing */") + "\n"
    # A VFS API requiring flags with a callback without flags needs a zero default.
    if signatures["vfs_getxattr"] and not signatures["get"]:
        text = text.replace("#define HM_VFS_FLAGS_VAL , flags", "#define HM_VFS_FLAGS_VAL , 0")
    contents["hybridmount.h"] = text.encode()
    text = contents["hybridmount.c"].decode()
    call = "xattr_full_name(handler, name), buffer, size FLAGS_VAL)"
    if text.count(call) != 1:
        raise ValueError("Pinned Hybrid Mount xattr call changed")
    contents["hybridmount.c"] = text.replace(call, "xattr_full_name(handler, name), buffer, size HM_VFS_FLAGS_VAL)").encode()
    return signatures


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ensure_no_nomount(source, config):
    if ((source / "fs/nomount").exists() or (source / "fs/nomount").is_symlink()
            or re.search(r"^CONFIG_NOMOUNT=[ym]$", config, re.M)
            or "nomount" in (source / "fs/Makefile").read_text()
            or "fs/nomount/Kconfig" in (source / "fs/Kconfig").read_text()):
        raise ValueError("NoMount and Hybrid Mount must not coexist; remove NoMount integration first")


def install(source, archive, lock):
    if digest(archive.read_bytes()) != lock["sha256"]:
        raise ValueError("Hybrid Mount source archive SHA256 mismatch")
    root = "meta-hybrid_mount-" + lock["revision"]
    # Read only the explicitly required regular files; never extract paths or links.
    contents = {}
    with tarfile.open(archive) as tar:
        for name in FILES + ("LICENSE",):
            member = tar.getmember(f"{root}/module/vfs/src/{name}")
            if not member.isfile():
                raise ValueError(f"Hybrid Mount source is not a regular file: {name}")
            contents[name] = tar.extractfile(member).read()
    contents["Makefile"] = b'obj-$(CONFIG_HYBRIDMOUNT) += hybridmount.o\nccflags-y += -std=gnu11 -Wno-declaration-after-statement\n'
    upstream_hashes = {name: digest(contents[name]) for name in FILES}
    xattr_api = adapt_xattr(contents, source)
    target = source / "fs/hybridmount"
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError("Conflicting existing fs/hybridmount; refusing to replace it")
    for name in FILES + ("Makefile", "LICENSE"):
        path = target / name
        if path.is_symlink() or (path.exists() and path.read_bytes() != contents[name]):
            raise ValueError(f"Conflicting existing Hybrid Mount source: {path}")
    wiring = ((source / "fs/Kconfig", KCONFIG), (source / "fs/Makefile", MAKEFILE))
    for path, line in wiring:
        existing = path.read_text()
        if "hybridmount" in existing and line not in existing.splitlines():
            raise ValueError(f"Conflicting Hybrid Mount wiring: {path}")
    defconfig = source / "arch/arm64/configs/gki_defconfig"
    config = defconfig.read_text()
    ensure_no_nomount(source, config)
    target.mkdir(parents=True, exist_ok=True)
    for name in FILES + ("Makefile", "LICENSE"):
        (target / name).write_bytes(contents[name])
    for path, line in wiring:
        if line not in path.read_text().splitlines():
            with path.open("a") as out:
                out.write("\n" + line + "\n")
    config = re.sub(r"^(?:CONFIG_(?:HYBRIDMOUNT|KEYS)=.*|# CONFIG_(?:HYBRIDMOUNT|KEYS) is not set)\n?", "", config, flags=re.M)
    defconfig.write_text(config.rstrip() + "\nCONFIG_KEYS=y\nCONFIG_HYBRIDMOUNT=y\n")
    metadata = source / "hybridmount-support"
    metadata.mkdir(exist_ok=True)
    (metadata / "LICENSE").write_bytes(contents["LICENSE"])
    manifest = dict(lock, upstream_files=upstream_hashes, xattr_api=xattr_api,
                    files={name: digest(value) for name, value in contents.items()})
    (metadata / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def verify(source, config, system_map=None, image=None):
    ensure_no_nomount(source, config.read_text())
    lines = config.read_text().splitlines()
    for symbol in ("KEYS", "HYBRIDMOUNT"):
        entries = [line for line in lines if line.startswith(f"CONFIG_{symbol}=") or line == f"# CONFIG_{symbol} is not set"]
        if entries != [f"CONFIG_{symbol}=y"]:
            raise ValueError(f"CONFIG_{symbol} must remain built-in (=y)")
    metadata = source / "hybridmount-support"
    manifest = json.loads((metadata / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        if digest((source / "fs/hybridmount" / name).read_bytes()) != expected:
            raise ValueError(f"Hybrid Mount source changed after integration: {name}")
    if system_map:
        symbols = [line.split()[-1] for line in system_map.read_text().splitlines() if line.split()]
        for required in ("hybridmount_init", "hm_key_type"):
            if not any(re.fullmatch(re.escape(required) + r"(?:\..*)?", name) for name in symbols):
                raise ValueError(f"Hybrid Mount was not linked into vmlinux: missing {required}")
    if image and b"hybridmount: Loaded successfully" not in image.read_bytes():
        raise ValueError("Hybrid Mount initialization message absent from built Image")
    return f"Hybrid Mount built-in: CONFIG_HYBRIDMOUNT=y, CONFIG_KEYS=y\nSource: {manifest['repository']}/commit/{manifest['revision']}\n" + ("System.map and Image linkage verified\n" if system_map and image else "Configuration verified; Image linkage pending\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "verify"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--system-map", type=Path)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "install":
            if not args.archive:
                parser.error("install requires --archive")
            install(args.source, args.archive, json.loads(LOCK.read_text()))
        else:
            if not args.config:
                parser.error("verify requires --config")
            report = verify(args.source, args.config, args.system_map, args.image)
            if args.report:
                args.report.write_text(report)
            print(report, end="")
    except (ValueError, OSError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f"Hybrid Mount: {error}\n")


if __name__ == "__main__":
    main()
