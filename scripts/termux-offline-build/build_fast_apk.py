#!/usr/bin/env python3
"""Offline fast Java/DEX/APK compiler, 16KB-aligner, and release signer for Custom Termux.

Configurable environment variables:
  TERMUX_BUILD_TOOLS          Offline toolchain dir (default: /opt/termux-build-tools)
  TERMUX_REPO                 termux-app repository path (default: /root/termux-app)
  TERMUX_OUT_DIR              Output directory for built APK (default: /root/migration)
  TERMUX_BASE_APK             Template base APK (default: $TERMUX_OUT_DIR/termux-custom-arm64-v8a.apk)
  TERMUX_KEYSTORE_PROPERTIES  Keystore properties path (default: /root/termux-signing/keystore.properties)
  ECJ_JAR                     Eclipse batch compiler jar path
"""
import collections
import glob
import hashlib
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
import zlib

TOOLS = os.environ.get("TERMUX_BUILD_TOOLS", "/opt/termux-build-tools")
CACHE = os.path.join(TOOLS, "cache")
REPO = os.environ.get("TERMUX_REPO", "/root/termux-app")
OUT_DIR = os.environ.get("TERMUX_OUT_DIR", "/root/migration")
BASE_APK = os.environ.get("TERMUX_BASE_APK", os.path.join(OUT_DIR, "termux-custom-arm64-v8a.apk"))
KEYSTORE_PROPS = os.environ.get("TERMUX_KEYSTORE_PROPERTIES", "/root/termux-signing/keystore.properties")
ECJ_JAR = os.environ.get("ECJ_JAR", "/usr/share/java/eclipse-jdt-core-compiler-batch.jar")


def is_replaced_internal_name(internal_name: str) -> bool:
    """Replace 100% of com/termux/** from fresh source compilation."""
    return internal_name.startswith("com/termux/")


def ensure_cache(work: str):
    """Populate static dependencies (filtered non-termux jars, DrawerLayout, R.java, stubs) once."""
    filtered_jar = f"{CACHE}/filtered-base-classes.jar"
    drawer_jar = f"{CACHE}/drawerlayout-classes.jar"
    gen_dir = f"{CACHE}/gen"
    stubs_dir = f"{CACHE}/ann-stubs"

    os.makedirs(CACHE, exist_ok=True)
    if (
        os.path.exists(filtered_jar)
        and os.path.exists(drawer_jar)
        and os.path.exists(f"{gen_dir}/com/termux/R.java")
        and os.path.exists(f"{stubs_dir}/javax/annotation/Nullable.java")
    ):
        return filtered_jar, drawer_jar, gen_dir, stubs_dir

    print("[cache] Initializing offline library & R.java cache from base APK...")
    tmp_cache = f"{work}/cache-init"
    os.makedirs(tmp_cache, exist_ok=True)

    with zipfile.ZipFile(BASE_APK, "r") as zf:
        zf.extract("classes.dex", tmp_cache)

    raw_jar = f"{tmp_cache}/base-classes.jar"
    subprocess.run(
        [
            "java", "-cp", f"{TOOLS}/d2j/*",
            "com.googlecode.dex2jar.tools.Dex2jarCmd",
            "--force", "-o", raw_jar,
            f"{tmp_cache}/classes.dex",
        ],
        check=True,
    )

    with zipfile.ZipFile(raw_jar, "r") as zin, zipfile.ZipFile(filtered_jar, "w") as zout:
        for item in zin.infolist():
            if item.filename.endswith(".class") and is_replaced_internal_name(item.filename[:-6]):
                continue
            zout.writestr(item, zin.read(item.filename))

    with zipfile.ZipFile(f"{TOOLS}/drawerlayout.aar", "r") as zaar:
        with open(drawer_jar, "wb") as fout:
            fout.write(zaar.read("classes.jar"))

    dump_out = subprocess.check_output(["aapt2", "dump", "resources", BASE_APK], text=True)
    res_by_type = collections.defaultdict(dict)
    for line in dump_out.splitlines():
        m = re.match(r"^\s*resource\s+(0x[0-9a-fA-F]+)\s+([a-zA-Z0-9_]+)/([^\s]+)$", line)
        if m:
            res_id, rtype, rname = m.groups()
            res_by_type[rtype][re.sub(r"[^a-zA-Z0-9_]", "_", rname)] = res_id

    for pkg in ("com.termux", "com.termux.shared", "com.termux.view"):
        pkg_dir = os.path.join(gen_dir, *pkg.split("."))
        os.makedirs(pkg_dir, exist_ok=True)
        with open(os.path.join(pkg_dir, "R.java"), "w", encoding="utf-8") as f:
            f.write(f"package {pkg};\npublic final class R {{\n")
            for rtype, entries in sorted(res_by_type.items()):
                f.write(f"    public static final class {rtype} {{\n")
                for jname, rid in sorted(entries.items()):
                    f.write(f"        public static final int {jname} = {rid};\n")
                f.write("    }\n")
            f.write("}\n")

    os.makedirs(f"{stubs_dir}/org/jetbrains/annotations", exist_ok=True)
    os.makedirs(f"{stubs_dir}/javax/annotation", exist_ok=True)
    with open(f"{stubs_dir}/org/jetbrains/annotations/NotNull.java", "w", encoding="utf-8") as f:
        f.write("package org.jetbrains.annotations;\npublic @interface NotNull {}\n")
    with open(f"{stubs_dir}/javax/annotation/Nullable.java", "w", encoding="utf-8") as f:
        f.write("package javax.annotation;\npublic @interface Nullable {}\n")

    return filtered_jar, drawer_jar, gen_dir, stubs_dir


def strip_termux_class_defs(raw_dex: bytes) -> bytes:
    """Remove all Lcom/termux/* class_defs from base classes.dex and update header + map_list + checksums."""
    dex = bytearray(raw_dex)
    string_ids_size, string_ids_off = struct.unpack_from("<II", dex, 0x38)
    type_ids_size, type_ids_off = struct.unpack_from("<II", dex, 0x40)
    class_defs_size, class_defs_off = struct.unpack_from("<II", dex, 0x60)

    def read_uleb128(pos):
        result = 0
        shift = 0
        while True:
            b = dex[pos]
            pos += 1
            result |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                return result, pos
            shift += 7

    def get_type_descriptor(type_idx: int) -> str:
        (str_idx,) = struct.unpack_from("<I", dex, type_ids_off + type_idx * 4)
        (str_data_off,) = struct.unpack_from("<I", dex, string_ids_off + str_idx * 4)
        _, pos = read_uleb128(str_data_off)
        end = dex.index(0, pos)
        return dex[pos:end].decode("utf-8", errors="replace")

    kept_defs = bytearray()
    removed_count = 0
    for i in range(class_defs_size):
        entry_off = class_defs_off + i * 32
        entry = dex[entry_off : entry_off + 32]
        (class_idx,) = struct.unpack_from("<I", entry, 0)
        desc = get_type_descriptor(class_idx)
        iname = desc[1:-1] if (desc.startswith("L") and desc.endswith(";")) else desc
        if is_replaced_internal_name(iname):
            removed_count += 1
        else:
            kept_defs.extend(entry)

    new_class_defs_size = class_defs_size - removed_count
    print(f"    Removed {removed_count} old class_defs; kept {new_class_defs_size} untouched class_defs.")
    struct.pack_into("<I", dex, 0x60, new_class_defs_size)
    (map_off,) = struct.unpack_from("<I", dex, 0x34)
    (map_list_size,) = struct.unpack_from("<I", dex, map_off)
    for m_idx in range(map_list_size):
        m_item_off = map_off + 4 + m_idx * 12
        m_type, _, _, _ = struct.unpack_from("<HHII", dex, m_item_off)
        if m_type == 0x0006:  # TYPE_CLASS_DEF_ITEM
            struct.pack_into("<I", dex, m_item_off + 4, new_class_defs_size)
    dex[class_defs_off : class_defs_off + len(kept_defs)] = kept_defs
    dex[class_defs_off + len(kept_defs) : class_defs_off + class_defs_size * 32] = b"\x00" * (removed_count * 32)
    dex[12:32] = hashlib.sha1(dex[32:]).digest()
    struct.pack_into("<I", dex, 8, zlib.adler32(dex[12:]) & 0xFFFFFFFF)
    return bytes(dex)


def patch_manifest(raw_axml: bytes, version_code: int, short_sha: str, base_ver: str = "0.118.3") -> bytes:
    """Update versionCode and 7-char custom git SHA inside binary AndroidManifest.xml."""
    axml = bytearray(raw_axml)
    pos = 8
    ver_code_str_idx = None
    patched_ver_code = False
    while pos < len(axml):
        ctype, cheader_size, csize = struct.unpack_from("<HHI", axml, pos)
        if ctype == 0x0180:  # RES_XML_RESOURCE_MAP_TYPE
            count = (csize - cheader_size) // 4
            for idx in range(count):
                (res_id,) = struct.unpack_from("<I", axml, pos + cheader_size + idx * 4)
                if res_id == 0x0101021B:  # android.R.attr.versionCode
                    ver_code_str_idx = idx
                    break
        elif ctype == 0x0102 and ver_code_str_idx is not None:  # RES_XML_START_ELEMENT_TYPE
            attr_ext_off = pos + cheader_size
            attr_start, attr_size, attr_count = struct.unpack_from("<HHH", axml, attr_ext_off + 8)
            attrs_base = attr_ext_off + attr_start
            for i in range(attr_count):
                aoff = attrs_base + i * attr_size
                ns_i, name_i, raw_v, tv_size, tv_zero, tv_type, tv_data = struct.unpack_from("<IIIHBBI", axml, aoff)
                if name_i == ver_code_str_idx and tv_type == 0x10 and tv_data > 0:
                    struct.pack_into("<I", axml, aoff + 16, version_code)
                    patched_ver_code = True
                    break
            if patched_ver_code:
                break
        pos += csize
    assert patched_ver_code, "Failed to locate versionCode in AndroidManifest.xml!"

    ver_prefix = f"{base_ver}+custom."
    ver_name = f"{ver_prefix}{short_sha}"
    assert len(short_sha) == 7, f"Expected 7-char hex SHA, got {short_sha!r}"
    u16_pat = re.escape(ver_prefix.encode("utf-16le")) + rb"(?:[0-9a-f]\x00){7}"
    u8_pat = re.escape(ver_prefix.encode("ascii")) + rb"[0-9a-f]{7}"
    axml_bytes, n16 = re.subn(u16_pat, ver_name.encode("utf-16le"), bytes(axml))
    axml_bytes, n8 = re.subn(u8_pat, ver_name.encode("ascii"), axml_bytes)
    assert (n16 + n8) >= 1, "Failed to update versionName in binary AndroidManifest.xml!"
    return axml_bytes


def align_apk_16kb(in_zip: str, out_zip: str):
    """Align ZIP_STORED .so entries to 16384 bytes (Android 16) and other stored entries to 4 bytes."""
    with zipfile.ZipFile(in_zip, "r") as zin, open(out_zip, "wb") as fout:
        cd_entries = []
        for info in zin.infolist():
            data = zin.read(info.filename)
            fname_bytes = info.filename.encode("utf-8")
            lfh_offset = fout.tell()
            base_data_start = lfh_offset + 30 + len(fname_bytes)
            if info.compress_type == zipfile.ZIP_STORED:
                align = 16384 if info.filename.endswith(".so") else 4
                pad_len = (align - (base_data_start % align)) % align
                if 0 < pad_len < 4:
                    pad_len += align
                extra = (struct.pack("<HH", 0xD935, pad_len - 4) + b"\x00" * (pad_len - 4)) if pad_len >= 4 else b""
                comp_data = data
                crc = zlib.crc32(data) & 0xFFFFFFFF
            else:
                extra = b""
                cobj = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
                comp_data = cobj.compress(data) + cobj.flush()
                crc = zlib.crc32(data) & 0xFFFFFFFF

            dos_time = (info.date_time[3] << 11) | (info.date_time[4] << 5) | (info.date_time[5] // 2)
            dos_date = ((info.date_time[0] - 1980) << 9) | (info.date_time[1] << 5) | info.date_time[2]
            lfh = struct.pack(
                "<4sHHHHHIIIHH",
                b"PK\x03\x04", 20, 0, info.compress_type, dos_time, dos_date,
                crc, len(comp_data), len(data), len(fname_bytes), len(extra),
            )
            fout.write(lfh)
            fout.write(fname_bytes)
            fout.write(extra)
            if info.compress_type == zipfile.ZIP_STORED:
                align = 16384 if info.filename.endswith(".so") else 4
                assert fout.tell() % align == 0, f"Misaligned {info.filename}: {fout.tell()} % {align}"
            fout.write(comp_data)

            cd_hdr = struct.pack(
                "<4sHHHHHHIIIHHHHHII",
                b"PK\x01\x02", 20, 20, 0, info.compress_type, dos_time, dos_date,
                crc, len(comp_data), len(data), len(fname_bytes), 0, 0, 0, 0,
                info.external_attr, lfh_offset,
            )
            cd_entries.append(cd_hdr + fname_bytes)

        cd_offset = fout.tell()
        for cde in cd_entries:
            fout.write(cde)
        cd_size = fout.tell() - cd_offset
        eocd = struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, len(cd_entries), len(cd_entries), cd_size, cd_offset, 0)
        fout.write(eocd)


def main():
    work = tempfile.mkdtemp(prefix="apk-work-")
    os.makedirs(f"{work}/compile-out", exist_ok=True)
    os.makedirs(f"{work}/patch-dex", exist_ok=True)
    os.makedirs(f"{work}/final-dex", exist_ok=True)

    try:
        gradle_text = open(f"{REPO}/app/build.gradle", "r", encoding="utf-8").read()
        vc_match = re.search(r"^\s*versionCode\s+(\d+)", gradle_text, re.MULTILINE)
        vn_match = re.search(r'^\s*versionName\s+"([^"]+)"', gradle_text, re.MULTILINE)
        assert vc_match, "Failed to parse versionCode from app/build.gradle!"
        version_code = int(vc_match.group(1))
        base_ver = vn_match.group(1) if vn_match else "0.118.3"
        short_sha = subprocess.check_output(
            ["git", "-C", REPO, "rev-parse", "--short=7", "HEAD"], text=True
        ).strip()
        print(f"[0/6] Target build: versionCode={version_code}, versionName={base_ver}+custom.{short_sha}")

        print("[1/6] Checking cached libraries & R.java...")
        filtered_jar, drawer_jar, gen_dir, stubs_dir = ensure_cache(work)

        print("[2/6] Compiling all 4 com.termux modules with ECJ (-1.8)...")
        srcs = glob.glob(f"{gen_dir}/**/*.java", recursive=True)
        srcs += glob.glob(f"{stubs_dir}/**/*.java", recursive=True)
        for mod in ("terminal-emulator", "terminal-view", "termux-shared", "app"):
            srcs += glob.glob(f"{REPO}/{mod}/src/main/java/**/*.java", recursive=True)

        subprocess.run(
            [
                "java", "-jar", ECJ_JAR,
                "-1.8", "-nowarn",
                "-classpath", f"{TOOLS}/android.jar:{TOOLS}/annotation-1.3.0.jar:{drawer_jar}:{filtered_jar}",
                "-d", f"{work}/compile-out",
            ] + sorted(srcs),
            check=True,
        )

        for extra_cls in (
            glob.glob(f"{work}/compile-out/**/R.class", recursive=True)
            + glob.glob(f"{work}/compile-out/**/R$*.class", recursive=True)
            + glob.glob(f"{work}/compile-out/org/jetbrains/**/*.class", recursive=True)
            + glob.glob(f"{work}/compile-out/javax/annotation/**/*.class", recursive=True)
        ):
            os.remove(extra_cls)

        compiled_classes = sorted(glob.glob(f"{work}/compile-out/**/*.class", recursive=True))
        print(f"    Compiled {len(compiled_classes)} .class files cleanly.")

        print("[3/6] Compiling .class -> patch-dex/classes.dex via official Google D8...")
        subprocess.run(
            [
                "java", "-cp", f"{TOOLS}/r8.jar",
                "com.android.tools.r8.D8",
                "--release", "--min-api", "24",
                "--lib", f"{TOOLS}/android.jar",
                "--classpath", filtered_jar,
                "--output", f"{work}/patch-dex",
            ] + compiled_classes,
            check=True,
        )

        print("[4/6] Stripping replaced class_defs from base classes.dex & merging via Google D8...")
        with zipfile.ZipFile(BASE_APK, "r") as zbase:
            raw_dex = zbase.read("classes.dex")
            raw_axml = zbase.read("AndroidManifest.xml")

        rest_dex_path = f"{work}/rest.dex"
        with open(rest_dex_path, "wb") as f:
            f.write(strip_termux_class_defs(raw_dex))

        subprocess.run(
            [
                "java", "-cp", f"{TOOLS}/r8.jar",
                "com.android.tools.r8.D8",
                "--release", "--min-api", "24",
                "--lib", f"{TOOLS}/android.jar",
                "--output", f"{work}/final-dex",
                rest_dex_path,
                f"{work}/patch-dex/classes.dex",
            ],
            check=True,
        )
        dex_outputs = sorted(glob.glob(f"{work}/final-dex/*.dex"))
        print(f"    D8 produced {len(dex_outputs)} merged DEX file(s): {[os.path.basename(x) for x in dex_outputs]}")

        print(f"[5/6] Patching manifest (versionCode={version_code}, sha={short_sha}), repackaging & 16KB-aligning...")
        patched_axml = patch_manifest(raw_axml, version_code, short_sha, base_ver=base_ver)
        unsigned_apk = f"{work}/termux-unsigned.apk"
        aligned_apk = f"{work}/termux-aligned.apk"

        assets_dir = f"{REPO}/app/src/main/assets"
        asset_files = []
        if os.path.isdir(assets_dir):
            for root, _, files in os.walk(assets_dir):
                for fn in sorted(files):
                    full = os.path.join(root, fn)
                    rel = "assets/" + os.path.relpath(full, assets_dir).replace(os.sep, "/")
                    asset_files.append((rel, full))
        asset_rel_set = {rel for rel, _ in asset_files}

        with zipfile.ZipFile(BASE_APK, "r") as zin, zipfile.ZipFile(unsigned_apk, "w") as zout:
            for info in zin.infolist():
                if info.filename.startswith("META-INF/") and (
                    info.filename.endswith(".SF") or info.filename.endswith(".RSA") or info.filename == "META-INF/MANIFEST.MF"
                ):
                    continue
                if re.match(r"^classes\d*\.dex$", info.filename):
                    continue
                if info.filename in asset_rel_set:
                    continue
                if info.filename == "AndroidManifest.xml":
                    new_info = zipfile.ZipInfo("AndroidManifest.xml", date_time=(1981, 1, 1, 1, 1, 0))
                    new_info.compress_type = info.compress_type
                    zout.writestr(new_info, patched_axml, compress_type=info.compress_type)
                else:
                    raw_bytes = zin.read(info.filename)
                    new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                    new_info.compress_type = info.compress_type
                    new_info.external_attr = info.external_attr
                    zout.writestr(new_info, raw_bytes, compress_type=info.compress_type)

            for rel, full in asset_files:
                new_info = zipfile.ZipInfo(rel, date_time=(1981, 1, 1, 1, 1, 0))
                new_info.compress_type = zipfile.ZIP_DEFLATED
                zout.writestr(new_info, open(full, "rb").read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

            for dex_path in dex_outputs:
                bname = os.path.basename(dex_path)
                new_info = zipfile.ZipInfo(bname, date_time=(1981, 1, 1, 1, 1, 0))
                new_info.compress_type = zipfile.ZIP_DEFLATED
                zout.writestr(new_info, open(dex_path, "rb").read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

        align_apk_16kb(unsigned_apk, aligned_apk)

        print("[6/6] Signing APK with release keystore...")
        props = {}
        with open(KEYSTORE_PROPS, "r", encoding="utf-8") as kf:
            for line in kf:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    props[k.strip()] = v.strip()

        ks_file = props["storeFile"]
        if not os.path.isabs(ks_file):
            ks_file = os.path.join(os.path.dirname(KEYSTORE_PROPS), ks_file)

        final_name = f"termux-app_v{base_ver}+custom.{short_sha}_arm64-v8a.apk"
        staged_signed = f"{work}/{final_name}"
        subprocess.run(
            [
                "java", "-cp", f"{TOOLS}/apksigner-root/usr/share/java/*",
                "com.android.apksigner.ApkSignerTool",
                "sign",
                "--ks", ks_file,
                "--ks-pass", f"pass:{props['storePassword']}",
                "--ks-key-alias", props["keyAlias"],
                "--key-pass", f"pass:{props['keyPassword']}",
                "--v1-signing-enabled", "true",
                "--v2-signing-enabled", "true",
                "--v3-signing-enabled", "true",
                "--v4-signing-enabled", "false",
                "--out", staged_signed,
                aligned_apk,
            ],
            check=True,
        )

        os.makedirs(OUT_DIR, exist_ok=True)
        final_apk = os.path.join(OUT_DIR, final_name)
        tmp_final = f"{final_apk}.tmp"
        shutil.copy2(staged_signed, tmp_final)
        os.replace(tmp_final, final_apk)

        tmp_alias = f"{BASE_APK}.tmp"
        shutil.copy2(final_apk, tmp_alias)
        os.replace(tmp_alias, BASE_APK)

        for old_apk in glob.glob(os.path.join(OUT_DIR, f"termux-app_v{base_ver}+custom.*_arm64-v8a.apk")):
            if os.path.abspath(old_apk) != os.path.abspath(final_apk):
                os.remove(old_apk)

        apk_bytes = os.path.getsize(final_apk)
        apk_sha = hashlib.sha256(open(final_apk, "rb").read()).hexdigest()
        print(f"FINAL APK: {final_apk} ({apk_bytes} bytes)")
        print(f"ALIAS APK: {BASE_APK}")
        print(f"SHA256:    {apk_sha}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
