# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2022 SUSE LLC <andrea.cervesato@suse.com>
#
# Install script for Linux Testing Project

top_srcdir		?= ../..

include $(top_srcdir)/include/mk/env_pre.mk

INSTALL_DIR		:= $(DESTDIR)/$(bindir)

install:
	mkdir -p $(INSTALL_DIR)/runltp-ng/ltp

	install -m 00644 $(top_srcdir)/tools/runltp-ng/ltp/*.py $(INSTALL_DIR)/runltp-ng/ltp
	install -m 00775 $(top_srcdir)/tools/runltp-ng/runltp-ng $(INSTALL_DIR)/runltp-ng/runltp-ng

	ln -sf $(INSTALL_DIR)/runltp-ng/runltp-ng $(DESTDIR)/$(prefix)/runltp-ng

include $(top_srcdir)/include/mk/generic_leaf_target.mk
