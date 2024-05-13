#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import argparse
import sys
import os
import subprocess
from tempfile import NamedTemporaryFile

def checkQmakePath(path):
    if path is None:
        return False

    if path == "**Unknown**":
        return False

    if not os.path.isdir(path):
        return False

    return True

def findProgram(path, progName):
    if not checkQmakePath(path):
        return None

    progPath = os.path.join(path, progName)
    if not os.path.isfile(progPath):
        return None

    return progPath


class QmlModuleChecker:
    def __init__(self):
        self.qt5 = True
        self.qmlimportscanner = None
        self.qmlpath = None

    def genQmlFile(self, f, modules):
        for module, version in modules:
            f.write("import {} {}\n".format(module, version))
        f.write("Item {}\n")
        f.flush()

    def scanImports(self, f, modules):
        ret = subprocess.run(
            [
                self.qmlimportscanner,
                "-qmlFiles", f.name,
                "-importPath", self.qmlpath
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        if ret.returncode != 0:
            print(ret.stderr.strip())
            return None

        return json.loads(ret.stdout)

    def checkImports(self, scanlist, modules):
        ret = True
        for name, version in modules:
            found = False
            for entry in scanlist:
                if entry["type"] == "module" and entry["name"] == name:
                    #qt6 modules have no version
                    if self.qt5 and not  entry["version"] == version:
                        continue
                    if "classname" in entry:
                        found = True
                        break
            print("checking for {} {}... {}".format(name, version, "yes" if found else "no"))
            if not found:
                ret = False

        return ret


    def getInstallInfo(self, qtpaths, qtconf):
        if not os.path.isfile(qtpaths):
            print("qtpaths not found")
            return False

        if qtconf:
            ret = subprocess.run(
                [ qtpaths, "--qtconf", qtconf, "--query"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf8"
            )
        else:
            ret = subprocess.run(
                [ qtpaths, "--query"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf8"
            )

        if ret.returncode != 0:
            print(ret.stderr.strip())
            return False

        binpath = None
        libexec = None
        qmlpath = None
        qtmajor = ""
        for l in ret.stdout.splitlines():
            l.strip()
            if l.startswith("QT_HOST_BINS:"):
                binpath = l.split(":", 1)[1]
            elif l.startswith("QT_HOST_LIBEXECS:"):
                libexec = l.split(":", 1)[1]
            elif l.startswith("QT_INSTALL_QML:"):
                self.qmlpath = l.split(":", 1)[1]
            elif l.startswith("QT_VERSION:"):
                qmlversion = l.split(":", 1)[1]
                qtmajor = qmlversion.split(".")[0]

        if qtmajor == "6":
            self.qt5 = False

        if not checkQmakePath(self.qmlpath):
            print("Qml path {} not found".format(self.qmlpath))
            return False

        self.qmlimportscanner = findProgram(binpath, "qmlimportscanner")
        if self.qmlimportscanner is not None:
            return True

        #Qt6 may place qmlimportscanner in libexec
        self.qmlimportscanner = findProgram(libexec, "qmlimportscanner")
        if self.qmlimportscanner is not None:
            return True

        print("qmlimportscanner not found")
        return False


class KeyValue(argparse.Action):
    def __call__( self , parser, namespace,
                  values, option_string = None):
        setattr(namespace, self.dest, [])

        for value in values:
            key, value = value.split('=')
            getattr(namespace, self.dest).append((key, value))

def main():
    parser = argparse.ArgumentParser("check for qml runtime dependencies")
    parser.add_argument(
        "--qtpaths", type=str, required=True,
        help="native qtpaths path")

    parser.add_argument(
        "--qtconf", type=str, required=False,
        help="qtpaths qtconf path")

    parser.add_argument(
        "--modules", nargs="+", action=KeyValue, required=True,
        help="list of modules to check in the form module=version (ex QtQuick=2.12)")

    args = parser.parse_args()

    moduleChecker = QmlModuleChecker()
    if not moduleChecker.getInstallInfo(args.qtpaths, args.qtconf):
        exit(-1)

    with NamedTemporaryFile(mode="w+", suffix=".qml") as f:
        moduleChecker.genQmlFile(f, args.modules)

        scanlist = moduleChecker.scanImports(f, args.modules)
        if scanlist is None:
            exit(-1)

        if not moduleChecker.checkImports(scanlist, args.modules):
            exit(-1)

    exit(0)

if __name__ == "__main__":
    main()
