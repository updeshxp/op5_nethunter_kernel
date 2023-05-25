import io
import os
import sys
import json
import shutil
import argparse
import platform
from operator import itemgetter

import tools.messages as msg
import tools.commands as ccmd
import tools.cleaning as cm
import tools.fileoperations as fo

from models.kernel import KernelBuilder
from models.assets import AssetCollector
from models.bundle import BundleCreator
from engines.container import ContainerEngine


def parse_args() -> argparse.Namespace:
    """Parse the script arguments."""
    # show the 'help' message if no arguments supplied
    args = None if sys.argv[1:] else ["-h"]
    # parser and subparsers
    parser_parent = argparse.ArgumentParser(description="A custom wrapper for the s0nh kernel.")
    subparsers = parser_parent.add_subparsers(dest="command")
    parser_kernel = subparsers.add_parser("kernel", help="build the kernel")
    parser_assets = subparsers.add_parser("assets", help="collect assets")
    parser_bundle = subparsers.add_parser("bundle", help="build the kernel + collect assets")
    # add a single argument for the main parser
    parser_parent.add_argument("--clean",
                               action="store_true",
                               help="clean the root directory")
    # common argument attributes for subparsers
    help_losversion = "select LineageOS version"
    help_codename = "select device codename"
    help_buildenv = "select build environment"
    help_clean = "remove Docker/Podman image from the host machine after build"
    help_loglvl = "select log level"
    choices_buildenv = ["local", "docker", "podman"]
    choices_loglvl = ["normal", "verbose", "quiet"]
    default_loglvl = "normal"
    help_logfile = "save logs to a file"
    # kernel
    parser_kernel.add_argument("buildenv",
                               choices=choices_buildenv,
                               help=help_buildenv)
    parser_kernel.add_argument("losversion",
                               help=help_losversion)
    parser_kernel.add_argument("codename",
                               help=help_codename)
    parser_kernel.add_argument("-c", "--clean",
                               dest="clean",
                               action="store_true",
                               help="don't build anything, just clean the environment")
    parser_kernel.add_argument("--clean-image",
                               action="store_true",
                               dest="clean_image",
                               help=help_clean)
    parser_kernel.add_argument("--log-level",
                               dest="loglvl",
                               choices=choices_loglvl,
                               default=default_loglvl,
                               help=help_loglvl)
    parser_kernel.add_argument("-o", "--output",
                               dest="outlog",
                               help=help_logfile)
    # assets
    parser_assets.add_argument("buildenv",
                               choices=choices_buildenv,
                               help=help_buildenv)
    parser_assets.add_argument("losversion",
                               help=help_losversion)
    parser_assets.add_argument("codename",
                               help=help_codename)
    parser_assets.add_argument("chroot",
                               choices=["full", "minimal"],
                               help="select Kali chroot type")
    parser_assets.add_argument("--extra-assets",
                               dest="extra_assets",
                               help="select a JSON file with extra assets")
    parser_assets.add_argument("--rom-only",
                               dest="rom_only",
                               action="store_true",
                               help="download only the ROM as an asset")
    parser_assets.add_argument("--clean-image",
                               action="store_true",
                               dest="clean_image",
                               help=help_clean)
    parser_assets.add_argument("--clean",
                               dest="clean",
                               action="store_true",
                               help="autoclean 'assets' folder if it exists")
    parser_assets.add_argument("--log-level",
                               dest="loglvl",
                               choices=choices_loglvl,
                               default=default_loglvl,
                               help=help_loglvl)
    parser_assets.add_argument("-o", "--output",
                               dest="outlog",
                               help=help_logfile)
    # bundle
    parser_bundle.add_argument("buildenv",
                               choices=choices_buildenv,
                               help=help_buildenv)
    parser_bundle.add_argument("losversion",
                               help=help_losversion)
    parser_bundle.add_argument("codename",
                               help=help_codename)
    parser_bundle.add_argument("package_type",
                               choices=["conan", "generic-slim"],
                               help="select package type of the bundle")
    parser_bundle.add_argument("--conan-upload",
                               action="store_true",
                               dest="conan_upload",
                               help="upload Conan packages to remote")
    parser_bundle.add_argument("--clean-image",
                               action="store_true",
                               dest="clean_image",
                               help=help_clean)
    parser_bundle.add_argument("--log-level",
                               dest="loglvl",
                               choices=choices_loglvl,
                               default=default_loglvl,
                               help=help_loglvl)
    parser_bundle.add_argument("-o", "--output",
                               dest="outlog",
                               help=help_logfile)
    return parser_parent.parse_args(args)


def validate_settings(args: argparse.Namespace):
    """Run settings validations."""
    # detect OS family
    if args.buildenv == "local":
        if not platform.system() == "Linux":
            msg.error("Can't build kernel on a non-Linux machine.")
        else:
            # check that it is Debian-based
            try:
                ccmd.launch("apt --version", "quiet")
            except Exception as e:
                msg.error("Detected Linux distribution is not Debian-based, unable to launch.")
    # check if specified device is supported
    with open(os.path.join(os.getenv("ROOTPATH"), "manifests", "devices.json")) as f:
        devices = json.load(f)
    if args.codename not in devices.keys():
        msg.error("Unsupported device codename specified.")
    if args.command == "bundle":
        # check Conan-related argument usage
        if args.package_type != "conan" and args.conan_upload:
            msg.error("Cannot use Conan-related arguments with non-Conan packaging\n")


def main(args: argparse.Namespace) -> None:
    # various environment preparations
    os.environ["ROOTPATH"] = os.path.dirname(os.path.realpath(sys.argv[0]))
    os.chdir(os.getenv("ROOTPATH"))
    if args.clean:
        cm.root()
        sys.exit(0)
    os.environ["LOGLEVEL"] = args.loglvl
    with open(os.path.join(os.getenv("ROOTPATH"), "manifests", "info.json")) as f:
        data = json.load(f)
        os.environ["KNAME"] = data["name"]
        os.environ["KVERSION"] = data["version"]
    validate_settings(args)
    # setup output stream
    if args.command and args.outlog:
        msg.note(f"Writing output to {args.outlog}")
        if args.outlog in os.listdir():
            os.remove(args.outlog)
        os.environ["OSTREAM"] = args.outlog
        msg.outputstream()
    # containerized build
    if args.buildenv in ["docker", "podman"]:
        arguments = vars(args)
        arguments["build_module"] = args.command
        params = {
            "buildenv",
            "build_module",
            "codename",
            "losversion",
            "clean_image",
            "chroot",
            "package_type",
            "clean_kernel",
            "clean_assets",
            "rom_only",
            "extra_assets",
            "conan_upload"
        }
        passed_params = {}
        for key, value in arguments.items():
            if key in params:
                passed_params[key] = value
        del arguments
        del params
        ContainerEngine(config=passed_params)
    # local build
    else:
        if args.command == "kernel":
            KernelBuilder(
                args.codename,
                args.losversion,
                args.clean
            )
        elif args.command == "assets":
            AssetCollector(
                args.codename,
                args.losversion,
                args.chroot,
                args.clean,
                args.rom_only,
                args.extra_assets
            )
        elif args.command == "bundle":
            BundleCreator(
                args.codename,
                args.losversion,
                args.package_type
            )


if __name__ == '__main__':
    main(parse_args())
