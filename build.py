#!/usr/bin/env python
#
# Master build script for Linux, OSX and Windows

import os
import sys
import shutil
import traceback
import stat
import glob
import subprocess
import re
from optparse import OptionParser

# Old stuff we might still need
MODULES = [
    ("michaelc", [
        "asl_deblur",
        "asl_mfree",
        "ENABLE",
    ]),
    ("asl", [
        "veaslc",
    ])
]

GITHUB_ORG = "ibme-qubic"

GITHUB_MODULES = [
    "fabber_core", 
    "fabber_models_asl", 
    "fabber_models_cest",
    "fabber_models_dsc",
    "fabber_models_dce", 
    "fabber_models_dualecho", 
    "fabber_models_dwi",  
    "fabber_models_T1", 
    "pyfab",
    "basil",
    "verbena", 
    "oxford_asl",
    "oxasl", 
    "oxasl_enable", 
    "oxasl_ve",
    "oxasl_multite",
    "oxasl_mp",
    "oxasl_surfpvc",
    "oxasl_optpcasl",
    "quantiphyse-fabber",
    "quantiphyse-cest",
    "quantiphyse-asl",
    "quantiphyse-t1",
    "quantiphyse-fsl",
    "quantiphyse-dsc",
    "quantiphyse-dce",
    "quantiphyse-sv",
    "quantiphyse-deeds",
    "quantiphyse-perfsim",
    "quantiphyse",
    "svb",
    "svb_models_asl",
    "avb",
]

TAGS = {}

# Bundle releases
BUNDLES = {
    "oxford_asl" : {
        "${BUILDDIR}/oxford_asl" : ["CITE", "README.md", "LICENSE"],
        "${FSLDEVDIR}/bin" : [
            "asl_calib", "asl_file", "asl_deblur", "asl_gui", 
            "asl_reg", "asl_mfree", "quasil", "oxford_asl", "epi_reg", 
            "basil", "basil_var", "fabber_var", "fabber_asl", "mvntool"
        ],
        "${FSLDEVDIR}" : ["python/asl",],
    },
    "verbena" : {
        "${BUILDDIR}/verbena" : ["CITE", "README.md", "LICENSE"],
        "${FSLDEVDIR}/bin" : ["verbena", "fabber_dsc", "mvntool"],
    },
    "ENABLE" : {
        "${BUILDDIR}/ENABLE" : ["README.md", "LICENSE"],
        "${FSLDEVDIR}/bin" : ["asl_enable",],
        "${FSLDEVDIR}/python" : [
            "asl/__init__.py", "asl/preproc.py", 
            "asl/enable.py", "asl/fslwrap.py",
            "asl/image.py",
        ],
    },
    "oxasl" : {
        "${BUILDDIR}/oxasl" : ["README.md", "oxasl_run"],
        "${FSLDEVDIR}" : [
            "bin/epi_reg", "bin/veasl", "bin/fabber_asl*",
            "lib/*fabbercore_shared.*", "lib/*fabber_models_asl.*",
        ],
        "${PYTHON}" : ["oxasl", "oxasl_ve", "fabber", "fsl", ],
    },
    "fabber" : {
        "__version__" : "fabber_core",
        "${BUILDDIR}/fabber_core" : ["README.md", "LICENSE"],
        "${FSLDEVDIR}" : ["bin/fabber*", "lib/*fabber*", "include/fabber_core"],
    },
}

def bundle_module(mod_name, destdir):
    """
    Bundle a Python module by copying everything under it's
    source file to a destination directory
    """
    mod = __import__(mod_name)
    mod_src = os.path.abspath(os.path.dirname(mod.__file__))
    shutil.copytree(mod_src, os.path.join(destdir, mod_name))

def get_output(cmd):
    """
    Get output of command, nb can't use check_output on python2.6
    """
    return subprocess.Popen(cmd, stdout=subprocess.PIPE).communicate()[0].decode('utf-8').strip(" \n")

def get_version_str(moddir, full=False):
    """
    Full version includes the Git commit hash, by default return 
    standardized version in form major.minor.patch-build
    """
    cwd = os.getcwd()
    os.chdir(moddir)
    full_version = get_output(['git','describe','--dirty'])
    os.chdir(cwd)
    if full:
        return full_version
    else:
        p = re.compile(r"v?(\d+\.\d+\.\d+(-\d+)?).*")
        m = p.match(full_version)
        if m is not None:
            std_version = m.group(1)
        else:
            raise RuntimeError("Failed to parse version string %s" % full_version)
        return std_version

def get_platform_name(options):
    """
    Platform name for embedding into packages
    """
    if options.win:
        return "windows"
    elif options.osx:
        return "osx"
    else:
        distro = get_output(['lsb_release', '-is']).lower()
        version = get_output(['lsb_release', '-rs']).split(".")[0]
        return distro+version

def check_error(retval, text, options):
    if retval != 0: 
        sys.stderr.write("ERROR: %s\n" % text)
        if options.exit_on_error:
            sys.exit(retval)

def build_make(moddir, options, installdir=None):
    """ 
    Build a module using the makefile.
    """
    print("\nBuilding %s using MAKE" % moddir)
    if installdir is None:
        installdir = options.fsldev
    os.chdir(moddir)

    build_type = ""
    if options.debug:
        build_type = "debug"

    if options.clean:
        retval = os.system("make clean")
        check_error(retval, "Failed to clean %s" % moddir, options)
    retval = os.system("make %s" % build_type)
    check_error(retval, "Failed to build %s" % moddir, options)
    if options.install:
        retval = os.system("make install")
        check_error(retval, "Failed to install %s" % moddir, options)

def build_python(moddir, options, installdir=None):
    print("\nBuilding %s using setup.py" % moddir)
    if installdir is None:
        installdir = options.fsldev
    os.chdir(moddir)

    retval = os.system("python setup.py sdist bdist" )
    check_error(retval, "Failed to build python module %s" % moddir, options)
    #retval = os.system("conda build conda_recipes/meta.yaml --output-folder=dist")
    #check_error(retval, "Failed to build Conda package for %s" % moddir, options)
    if options.install:
        retval = os.system("python setup.py install" )
        check_error(retval, "Failed to install python module %s" % moddir, options)

def clone(mod, options):
    """
    Clone a git module and switch to a custom tag if required 
    """
    print("\nCloning %s" % mod)
    cleandir(mod, create=False)
    retval = os.system("git clone https://github.com/%s/%s.git" % (GITHUB_ORG, mod))
    check_error(retval, "Failed to clone %s/%s" % (GITHUB_ORG, mod), options)
    if mod in TAGS:
        os.chdir(mod)
        os.system("git checkout %s" % TAGS[mod])
        os.chdir(os.pardir)

def update(mod, options):
    """
    Update a git module and switch to a custom tag if required 
    """
    print("\nUpdating %s" % mod)
    if not os.path.exists(mod):
        clone(mod, options)
    else:
        os.chdir(mod)
        retval = os.system("git pull")
        check_error(retval, "Failed to update %s/%s" % (GITHUB_ORG, mod), options)
        retval = os.system("git checkout %s" % TAGS.get(mod, "master"))
        check_error(retval, "Failed to switch tags in %s/%s" % (GITHUB_ORG, mod), options)
        os.chdir(os.pardir)

def remove_readonly(func, path, _):
    """ 
    Error handler to deal with files having read-only permissions 
    """
    if os.path.exists(path):
        os.chmod(path, stat.S_IWRITE)
        if sys.platform.startswith("win"):
            import win32api, win32con
            win32api.SetFileAttributes(path, win32con.FILE_ATTRIBUTE_NORMAL)
        func(path)

def cleandir(d, create=True):
    """ 
    Remove a directory and then create a fresh new one
    """
    try:
        shutil.rmtree(d, onerror=remove_readonly)
    except:
        print("Error removing %s" % d)
        traceback.print_exc()
    if create:
        os.makedirs(d)
    return d

# Remember where we started so we can go back later
cwd = os.getcwd()

# Parse command line options and set up other build parameters
p = OptionParser(usage="build.py [--update] [--rebuild] [options]")
p.add_option("--debug", help="Debug build", action="store_true", default=False)
p.add_option("--arch", dest="arch", help="Build architecture (Windows only) - x86 or x64", default="x64")
p.add_option("--update", dest="update", action="store_true", help="Update code from git", default=False)
p.add_option("--rebuild", dest="rebuild", action="store_true", help="Rebuild code", default=False)
p.add_option("--clean", help="Do make clean before rebuilding", action="store_true", default=False)
p.add_option("--install", help="Install code after build", action="store_true", default=False)
p.add_option("--no-python", help="Don't build python modules", action="store_true", default=False)
p.add_option("--fsldev", dest="fsldev", help="Source directory for FSLDEVDIR. Defaults to install/fsldev ", default=None)
p.add_option("--build-bundles", dest="build_bundles", action="store_true", help="Build bundle releases", default=False)
p.add_option("--continue-on-error", dest="exit_on_error", action="store_false", help="Continue build if there is an error", default=True)
options, args = p.parse_args()

options.win = sys.platform.startswith("win")
options.osx = sys.platform.startswith("darwin")
options.platform = get_platform_name(options)
options.rootdir = os.path.abspath(os.path.dirname(__file__))

# Some Git configuration to make things go smoothly. Longfiles is required on Windows
os.system('git config --global core.longpaths true')
os.system('git config --global credential.helper "cache --timeout 28800"')

options.builddir = os.path.join(options.rootdir, "build")
options.installdir = os.path.join(options.rootdir, "install")
options.pkgdir = os.path.join(options.rootdir, "packages")

if not os.path.exists(options.builddir):
    os.makedirs(options.builddir)
    
if not options.fsldev:
    options.fsldev = os.path.join(options.installdir, "fsldev")
else:
    options.fsldev = os.path.abspath(options.fsldev)

options.fsldir = os.environ["FSLDIR"]
os.environ["FSLDIR"] = options.fsldir
os.environ["FSLDEVDIR"] = options.fsldev

if options.update:
    print("\nUpdating code from GIT\n")
    os.chdir(options.builddir)
    for mod in GITHUB_MODULES:
        update(mod, options)

if options.rebuild:
    print("\nRebuilding code\n")
    print("Building on: %s" % options.platform)
    print("Using FSL in: %s" % options.fsldir)
    print("Local FSL code installed to: %s" % options.fsldev)
    if options.debug:
        print("Doing debug build")
    if options.win: 
        # Set up build arch on Windows for Python modules with native code
        # Note that we don't build pure C++ on Windows - use WSL instead
        if "VCINSTALLDIR" not in os.environ:
            print("You must run this script from the Visual Studio tools command line")
            sys.exit(1)
        print('"%s\\Auxiliary\\Build\\vcvarsall" %s' % (os.environ["VCINSTALLDIR"], options.arch))
        os.system('"%s\\Auxiliary\\Build\\vcvarsall" %s' % (os.environ["VCINSTALLDIR"], options.arch))
        print("Build architecture: %s" % options.arch)

    # Set up options to build using Make
    os.environ["FSLCONFDIR"] = os.path.join(options.fsldir, "config")
    os.environ["FSLMACHTYPE"] = get_output([os.path.join(options.fsldir, "etc", "fslconf", "fslmachtype.sh")])
    
    print("Installing into %s" % options.fsldev)
    cleandir(options.fsldev)

    # Build all modules
    for mod in GITHUB_MODULES:
        os.chdir(options.builddir)
        moddir = os.path.join(options.builddir, mod)
        if not os.path.exists(moddir):
            update(mod, options)

        if os.path.exists(os.path.join(moddir, "setup.py")) and not options.no_python:
            build_python(moddir, options)
        elif not options.win:
            build_make(moddir, options)
        else:
            print("\nSkipping %s on Windows build" % mod)

# Make bundle release packages
if options.build_bundles:
    print("\nCreating bundle packages\n")
    for bundle_name, bundle_data in BUNDLES.items():
        if options.win and mod in WIN_SKIP: 
            continue
        os.chdir(options.pkgdir)
        cleandir(bundle_name)
        for src, dest_items in bundle_data.items():
            if src == "__version__": continue
            src = src.replace("${BUILDDIR}", options.builddir).replace("${FSLDEVDIR}", options.fsldev)
            if src == "${PYTHON}":
                for mod_name in dest_items:
                    bundle_module(mod_name, bundle_name)
            else:
                for item in dest_items:
                    src_glob = glob.glob(os.path.join(src, item))
                    for src_file in src_glob:
                        dest_dir = os.path.abspath(os.path.join(bundle_name, os.path.dirname(item)))
                        dest_path = os.path.join(dest_dir, os.path.basename(src_file))
                        print("%s -> %s" % (src_file, dest_path))
                        if not os.path.isdir(dest_dir):
                            cleandir(dest_dir)
                        if os.path.isdir(src_file):
                            shutil.copytree(src_file, dest_path)
                        else:
                            shutil.copy(src_file, dest_path)

        version_mod = bundle_data.get("__version__", bundle_name)
        version_str = get_version_str(os.path.join(options.builddir, version_mod))
        zipname = "%s/%s-%s-%s.tar.gz" % (options.pkgdir, bundle_name, version_str, options.platform)
        # Sadly shutil.make_archive is not in python 2.6 on Centos 6
        os.system("tar -czf %s %s" % (zipname, bundle_name))

os.chdir(cwd)