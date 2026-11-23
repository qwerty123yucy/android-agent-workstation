#!/usr/bin/env python3
"""Offline unit test runner for termux-app/terminal-emulator without Gradle.

Configurable environment variables:
  TERMUX_BUILD_TOOLS  Path to offline toolchain dir (default: /opt/termux-build-tools)
  TERMUX_REPO         Path to termux-app git repo (default: /root/termux-app)
  ECJ_JAR             Path to Eclipse batch compiler jar
"""
import glob
import os
import shutil
import subprocess
import tempfile

TOOLS = os.environ.get("TERMUX_BUILD_TOOLS", "/opt/termux-build-tools")
REPO = os.environ.get("TERMUX_REPO", "/root/termux-app")
ECJ_JAR = os.environ.get("ECJ_JAR", "/usr/share/java/eclipse-jdt-core-compiler-batch.jar")


def main() -> None:
    work = tempfile.mkdtemp(prefix="termux-unit-test-")
    os.makedirs(f"{work}/stubs/junit/framework", exist_ok=True)
    os.makedirs(f"{work}/stubs/org/junit", exist_ok=True)
    os.makedirs(f"{work}/classes", exist_ok=True)

    try:
        with open(f"{work}/stubs/junit/framework/AssertionFailedError.java", "w", encoding="utf-8") as f:
            f.write(
                """package junit.framework;
public class AssertionFailedError extends AssertionError {
    public AssertionFailedError() { super(); }
    public AssertionFailedError(String msg) { super(msg); }
}
"""
            )

        with open(f"{work}/stubs/org/junit/Assert.java", "w", encoding="utf-8") as f:
            f.write(
                """package org.junit;
public class Assert extends junit.framework.TestCase {}
"""
            )

        with open(f"{work}/stubs/junit/framework/TestCase.java", "w", encoding="utf-8") as f:
            f.write(
                """package junit.framework;
import java.util.Objects;
public abstract class TestCase {
    protected void setUp() throws Exception {}
    protected void tearDown() throws Exception {}
    public static void assertTrue(boolean cond) { if (!cond) throw new AssertionFailedError("Expected true"); }
    public static void assertTrue(String msg, boolean cond) { if (!cond) throw new AssertionFailedError(msg); }
    public static void assertFalse(boolean cond) { if (cond) throw new AssertionFailedError("Expected false"); }
    public static void assertFalse(String msg, boolean cond) { if (cond) throw new AssertionFailedError(msg); }
    public static void assertNull(Object o) { if (o != null) throw new AssertionFailedError("Expected null, got " + o); }
    public static void assertNotNull(Object o) { if (o == null) throw new AssertionFailedError("Expected non-null"); }
    public static void assertEquals(Object a, Object b) { if (!Objects.equals(a, b)) throw new AssertionFailedError("Expected <" + a + "> but got <" + b + ">"); }
    public static void assertEquals(String msg, Object a, Object b) { if (!Objects.equals(a, b)) throw new AssertionFailedError(msg + ": Expected <" + a + "> but got <" + b + ">"); }
    public static void assertEquals(long a, long b) { if (a != b) throw new AssertionFailedError("Expected " + a + " but got " + b); }
    public static void assertEquals(String msg, long a, long b) { if (a != b) throw new AssertionFailedError(msg + ": Expected " + a + " but got " + b); }
    public static void assertEquals(double a, double b, double delta) { if (Math.abs(a - b) > delta) throw new AssertionFailedError("Expected " + a + " but got " + b); }
    public static void fail(String msg) { throw new AssertionFailedError(msg); }
    public static void fail() { throw new AssertionFailedError("Failed"); }
}
"""
            )

        with open(f"{work}/stubs/TestRunner.java", "w", encoding="utf-8") as f:
            f.write(
                """import java.lang.reflect.Method;
import junit.framework.TestCase;
public class TestRunner {
    public static void main(String[] args) throws Exception {
        int passed = 0;
        Method setUp = TestCase.class.getDeclaredMethod("setUp");
        setUp.setAccessible(true);
        Method tearDown = TestCase.class.getDeclaredMethod("tearDown");
        tearDown.setAccessible(true);
        for (String clsName : args) {
            Class<?> cls = Class.forName(clsName);
            for (Method m : cls.getMethods()) {
                if (m.getName().startsWith("test") && m.getParameterCount() == 0) {
                    TestCase instance = (TestCase) cls.getDeclaredConstructor().newInstance();
                    setUp.invoke(instance);
                    try {
                        m.invoke(instance);
                        passed++;
                    } finally {
                        tearDown.invoke(instance);
                    }
                }
            }
        }
        System.out.println("UNIT TESTS PASSED: " + passed);
    }
}
"""
            )

        main_srcs = glob.glob(f"{REPO}/terminal-emulator/src/main/java/**/*.java", recursive=True)
        test_srcs = glob.glob(f"{REPO}/terminal-emulator/src/test/java/**/*.java", recursive=True)
        stub_srcs = glob.glob(f"{work}/stubs/**/*.java", recursive=True)

        subprocess.run(
            [
                "java", "-jar", ECJ_JAR,
                "-1.8", "-nowarn",
                "-classpath", f"{TOOLS}/android.jar",
                "-d", f"{work}/classes",
            ]
            + stub_srcs
            + main_srcs
            + test_srcs,
            check=True,
        )

        test_classes = [
            f"com.termux.terminal.{os.path.basename(path)[:-5]}"
            for path in sorted(test_srcs)
            if os.path.basename(path)[:-5].endswith("Test")
        ]

        subprocess.run(
            ["java", "-cp", f"{work}/classes:{TOOLS}/android.jar", "TestRunner"] + test_classes,
            check=True,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
