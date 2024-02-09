# -----------------------------------------------------------------------------
# This Makefile is used to install the python3 packages and programs
#
# It uses wildard-based rules to install the packages and programs in the
# appropriate directories.
#
# Benefits:
#
# - Ease of use: To add the installation of a file, simply commit it to
#   one of the defined source directories that are installed.
#
# -  Note: `git` does not track directories:
#   - Only files, not directories are tracked by git:
#   - Simply create the directory and commit the file in the directory!
#
# - No conflicts: Because this central file should rarely need changes,
#   individual file moved here, there should be no conflicts on regular
#   commits that just move files here.
#
# - Consistency and guarantees:
#   If a file is in one of the defines directories, we know:
#   - it will be installed and
#   - where it will be installed.
#
#  - To check where a directory is installed to just jump to the end of the file
#    and look at the macro calls.


# The packages are installed using the distutils.sysconfig module to
# get the python site-packages directory. The programs are installed
# in the $OPTDIR/bin directory.
#
# The names of the packages and programs are found using the wildcard,
# so that the Makefile does not need to be updated for installing new files.
#
# -----------------------------------------------------------------------------
# Naming of programs in the source with the .py extension(removed during install):
#
# The programs have the .py extension in the source directory.
#
# Generally, it is not necessary to have the .py extension, but it is
# useful for the following reasons:
#
#  - Tests can import the programs as modules directly from the source
#
#  - It allows them to be discovered by regular python tools.
#    - For example, the programs can be formatted using tools like darker,
#      black and isort.
#
#  - It makes it clear that they are python programs.
#
# The .py extension is removed from the programs after they are installed
# -----------------------------------------------------------------------------

-include ../config.mk

# -----------------------------------------------------------------------------

# The recipe prefix is set to ">" so that the commands are not prefixed with a tab
.RECIPEPREFIX = >
# The default goal is the install target, even if other targets are defined before it
.DEFAULT_GOAL = install
# It executed even if a file called "install" exists
.PHONY:         install

IDATA=install -m 644
IPROG=install -m 755

# The directory where the packages will be installed
SITE3_PY  := "from distutils.sysconfig import get_python_lib as py; print(py())"
SITE3_DIR := $(shell python3 -c $(SITE3_PY))

# Set default values for the other installation directories (set by config.mk)
LIBEXECDIR ?= $(OPTDIR)/libexec
PLUGINDIR  ?= /etc/xensource/plugins
DESTDIR    ?= $(TESTDESTDIR)

# -----------------------------------------------------------------------------
# GNU Make Macros, for good information see Get Managing Projects with GNU Make:
# https://www.oreilly.com/library/view/managing-projects-with/0596006101/ch03.html
# -----------------------------------------------------------------------------
# Macro that installs the packages and programs
# Currently it only matches files that have a "." in them like .py or .conf,
# files that need to be renamed to have no extension in the target directory
# should be renamed in the target directory after the install, eithey by the
# REMOVE_DOT_PY macro or by a custom "install::" added rule after installation:
# The 1st argument is the IPRPG or IDATA macro name
# The 2nd argument is the source directory
# The 3rd argument is the target directory
# The 4th argument is a an optional macro to call,
# for example, it may removes the .py extension from bin programs
# All the files in the source directory are installed in the target directory
define INSTALL_FILES
  # Get the list of files in the given source directory (the 2nd argument)
  $(2) := $(filter-out __init__.py,$(subst $(2)/,,$(wildcard $(2)/*.*)))
  #
  # Append to the install rule: The "install ::" means that it appends to install,
  # so that the install rule is not overwritten, but appended to.
  # For this reason, the macro can be called multiple times to install different files,
  # and other rules can be added after the macro calls to make adjustments.
  # like renaming a few files after after the install to remove their .py extension
  #

  install ::
>   @# If we found files that matched the wildcard and weren't excluded by the filter
>   @# then install them in the target directory $(DESTDIR)/$(3)
    ifneq ($$($(2)),)
>     @# Create the target directory if it doesn't exist
>     @mkdir -p                      $(DESTDIR)$(3);set -xv
      # Install the files in the target directory using the given IPRPG or IDATA macro
>     @(cd $(2); $$($(1)) -v $$($(2)) $(DESTDIR)$(3))
      # Call the optional macro in  to make adjustments to the installed files if given
      ifneq ($(4),)
>       @$(call $(4), $$($(2)), $(DESTDIR)$(3))
      endif
  endif
endef
# Macro to remove the .py extension from the given programs in the install directory
# The 1st argument is the list of programs
# The 2nd argument is the installation directory
define REMOVE_DOT_PY
  cd $(2); for f in $(1); do mv -v $$$$f $$$${f%.py}; done
endef
# -----------------------------------------------------------------------------
# When testing, the first part of the install target is to  cleanup the temp dir
TESTDESTDIR = /tmp/$(USER)-xen-api-python3
ifeq ($(DESTDIR),$(TESTDESTDIR))
# Example test command (for editing in another terminal while the test is running):
# while inotifywait python3/Makefile;do make -C --no-print-directory python3;done
install::
# If install target is the default temporary target, cleanup the temporary directory
> rm -rf $(DESTDIR)
endif

# -----------------------------------------------------------------------------
# Define the install rule for the packages and programs:
# -----------------------------------------------------------------------------
# The programs are installed in the $OPTDIR/bin directory
# The .py extension is removed from the programs
$(eval $(call INSTALL_FILES,IPROG,bin,$(OPTDIR)/bin,REMOVE_DOT_PY))

# The packages are installed in the python site-packages directory
$(eval $(call INSTALL_FILES,IDATA,packages,$(SITE3_DIR)))
# The libraries are installed in the libexec directory
$(eval $(call INSTALL_FILES,IPROG,libexec,$(LIBEXECDIR)))
# The plugins are installed in the PLUGINDIR directory
$(eval $(call INSTALL_FILES,IPROG,plugins,$(PLUGINDIR)))

# The yum-plugin files are installed in the PLUGINDIR directory
$(eval $(call INSTALL_FILES,IPROG,yum-plugins,$(YUMPLUGINDIR)))
# The yum-plugin config files are installed in the PLUGINCONFDIR directory
$(eval $(call INSTALL_FILES,IPROG,yum-plugins/configs,$(YUMPLUGINCONFDIR)))

# The extensions are installed in the EXTENSIONDIR directory
$(eval $(call INSTALL_FILES,IPROG,extensions,$(EXTENSIONDIR),REMOVE_DOT_PY))

# The poweron plugins are installed in the PLUGINDIR directory
# TODO: Some need to be renamed in the target directory to remove
$(eval $(call INSTALL_FILES,IPROG,plugins/poweron,$(PLUGINDIR)))
# -----------------------------------------------------------------------------
