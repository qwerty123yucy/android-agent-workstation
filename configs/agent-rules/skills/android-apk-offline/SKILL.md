---
name: android-apk-offline
description: >-
  Build, align, and sign standalone Android APKs (pure Java/Canvas or fullscreen WebView apps)
  offline on Linux ARM64 PRoot using ECJ, aapt2, D8, zipalign, and ApkSignerTool.
  Use when packaging, updating, or troubleshooting Gradle-free Android APK builds.
---

# Offline Android APK Build & Cache-Safe Delivery

## Toolchain Pipeline (`ECJ + aapt2 + D8 + zipalign + ApkSignerTool`)

When standard `/usr/bin/javac` wrappers fail or Gradle is too heavy in an ARM64 PRoot container, invoke the Eclipse batch compiler (`ECJ`) directly with `-1.8`:

1. **Compile & Link Resources (`aapt2`)**:
   ```bash
   aapt2 compile --dir <res_dir> -o compiled_res.zip
   aapt2 link -I "$TOOLS/android.jar" \
     --manifest <AndroidManifest.xml> [-A <assets_dir>] \
     --java <gen_java_dir> --auto-add-overlay \
     -o base-unaligned.apk compiled_res.zip
   ```
   *(Omit `-A <assets_dir>` for pure-native APKs with no web/raw assets.)*
2. **Compile Java Sources (`ECJ`, Java 8 target)**:
   ```bash
   java -jar /usr/share/java/eclipse-jdt-core-compiler-batch.jar \
     -1.8 -encoding UTF-8 -nowarn \
     -classpath "$TOOLS/android.jar" \
     -d <classes_dir> <R.java_and_app_java_files...>
   ```
3. **DEX Conversion (`D8`)**:
   ```bash
   java -cp "$TOOLS/r8.jar" com.android.tools.r8.D8 \
     --release --min-api 24 --lib "$TOOLS/android.jar" \
     --output <dex_dir> <class_files...>
   ```
4. **Package, Align & Sign (v1/v2/v3)**:
   - Append `classes.dex` (`ZIP_DEFLATED`) to `base-unaligned.apk`.
   - Align: `zipalign -f -p 4 base-unaligned.apk aligned.apk` (or 16 KB align uncompressed `.so` files for Android 16).
   - Sign with `com.android.apksigner.ApkSignerTool sign` (`--v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false`).
   - Verify with `zipalign -c 4 <out.apk>`, `ApkSignerTool verify --verbose <out.apk>`, and `aapt2 dump badging <out.apk>`.

## Packaging, WebView & Native `Canvas` Invariants

1. **Zero Colons in Filenames & Labels**: Never use `:` or `：` in `.apk` filenames, `res/values/strings.xml` `app_name`, or `<title>`.
2. **WebView Cache Busting**: On every WebView asset update, clean stale assets before linking, bump a versioned asset path (`file:///android_asset/app_vNNN.html?v=NNN`), set `WebSettings.LOAD_NO_CACHE`, and call `webView.clearCache(true)` before `loadUrl`.
3. **Avoid Color-Emoji Hijacking on Android `Canvas`**: System `NotoColorEmoji.ttf` intercepts BMP symbols with emoji presentation (`⚔`, `⚡`, `❄`, `⚙`, `☄`, `♥`) in `Canvas.drawText`. Prefer vector `Path` icons or monochrome geometric glyphs (`★`, `✦`, `◈`, `↺`).
4. **CJK Kinsoku & Numeric Token Wrapping**: Custom `Canvas.drawText` line wrappers should keep ASCII numeric/unit tokens (`$15`, `+10%`, `Lv.3`) intact and avoid starting a new line with closing punctuation (`。，！？）》】%`).
5. **Modal Gesture-Origin Isolation**: In custom `View.onTouchEvent`, if an underlying button opens a modal on `ACTION_DOWN` and the modal reacts to `ACTION_UP`, gate modal `ACTION_MOVE`/`ACTION_UP` behind a `modalGestureStarted` flag set only by a fresh `ACTION_DOWN` received *after* opening (plus a ~`200ms` close anti-bounce guard).
