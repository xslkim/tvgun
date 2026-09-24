#!/usr/bin/env bash
# Manual (no-gradle) build chain for the TV Gun APK.
# Usage: ./build.sh          -> build only, produces android/tvgun.apk
#        ./build.sh install  -> build + adb install -r + launch
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
JBR="/c/Program Files/Android/jdk/jdk-8.0.302.8-hotspot/jdk8u302-b08/bin"
SDK="/c/Users/xsl/AppData/Local/Android/Sdk"
AJAR="$SDK/platforms/android-35/android.jar"
BT="$SDK/build-tools/36.0.0"
ADB="$SDK/platform-tools/adb.exe"
# d8/apksigner 需要 Java 11+（JDK8 不够）：用独立的 JRE17 跑它们
J17="/d/Tools/jdk-17.0.20.1+1-jre"
OUT="$ROOT/out"
PKG="com.tvgun.gun"

w() { cygpath -w "$1"; }

# d8.bat / apksigner.bat need JAVA_HOME (Windows-style path) and java on PATH
export JAVA_HOME="$(w "$JBR/..")"
export PATH="$JBR:$PATH"

javac8() { "$JBR/javac.exe" "$@"; }

mkdir -p "$OUT/classes" "$OUT/dex"

echo "==> [1/7] debug keystore"
if [ ! -f "$ROOT/debug.keystore" ]; then
  "$JBR/keytool.exe" -genkeypair -keystore "$(w "$ROOT/debug.keystore")" \
    -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass android -keypass android \
    -dname "CN=Android Debug,O=Android,C=US"
else
  echo "    (keystore exists, skip)"
fi

echo "==> [2/7] aapt2 link"
rm -f "$OUT/unsigned.apk"
"$BT/aapt2.exe" link -o "$(w "$OUT/unsigned.apk")" \
  -I "$(w "$AJAR")" \
  --manifest "$(w "$ROOT/AndroidManifest.xml")" \
  --min-sdk-version 21 --target-sdk-version 28

echo "==> [3/7] javac"
rm -rf "$OUT/classes"; mkdir -p "$OUT/classes"
SRCS=()
while IFS= read -r f; do SRCS+=("$(w "$f")"); done < <(find "$ROOT/src" -name '*.java')
"$JBR/javac.exe" -source 1.8 -target 1.8 -encoding UTF-8 \
  -classpath "$(w "$AJAR")" -d "$(w "$OUT/classes")" "${SRCS[@]}"

echo "==> [4/7] d8"
rm -rf "$OUT/dex"; mkdir -p "$OUT/dex"
CLASSES=()
while IFS= read -r f; do CLASSES+=("$(w "$f")"); done < <(find "$OUT/classes" -name '*.class')
JAVA_HOME="$(w "$J17")" PATH="$J17/bin:$PATH" "$BT/d8.bat" --min-api 21 --lib "$(w "$AJAR")" --output "$(w "$OUT/dex")" "${CLASSES[@]}"

echo "==> [5/7] add classes.dex to apk"
cp "$OUT/unsigned.apk" "$OUT/withdex.apk"
(cd "$OUT/dex" && "$JBR/jar.exe" uf "$(w "$OUT/withdex.apk")" classes.dex)

echo "==> [6/7] zipalign"
"$BT/zipalign.exe" -f 4 "$(w "$OUT/withdex.apk")" "$(w "$OUT/aligned.apk")"

echo "==> [7/7] apksigner sign"
JAVA_HOME="$(w "$J17")" PATH="$J17/bin:$PATH" "$BT/apksigner.bat" sign \
  --ks "$(w "$ROOT/debug.keystore")" \
  --ks-pass pass:android --key-pass pass:android \
  --out "$(w "$ROOT/tvgun.apk")" "$(w "$OUT/aligned.apk")"

echo "Built: $ROOT/tvgun.apk"

if [ "${1:-}" = "install" ]; then
  echo "==> adb install"
  "$ADB" install -r "$(w "$ROOT/tvgun.apk")"
  echo "==> am start"
  "$ADB" shell am start -n "$PKG/.MainActivity"
fi
