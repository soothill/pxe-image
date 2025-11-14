SHELL := /bin/bash

BIN := ./bin/build-image
KIWI := kiwi-ng
CONFIG ?= config/sample-config.json
DESCRIPTION ?= kiwi
TARGET_DIR ?= build/artifacts
OVERLAY_ROOT ?= build/overlay
SUDO ?= sudo
EXTRA_KIWI_ARGS ?=

EXTRA_ARG_OPTION = $(strip $(if $(EXTRA_KIWI_ARGS),--extra-kiwi-args -- $(EXTRA_KIWI_ARGS),))

.PHONY: help download build clean

help:
	@echo "Make targets for the KIWI image workflow"
	@echo "Usage: make <target> [VARIABLE=value ...]"
	@echo
	@echo "Targets:"
	@echo "  download  Prepare the overlay and fetch all RPM payloads (no ISO build)."
	@echo "  build     Run the full workflow, including ISO creation (depends on download)."
	@echo "  clean     Remove the build and overlay directories."
	@echo
	@echo "Common variables (override via make VAR=value):"
	@echo "  CONFIG=$(CONFIG)"
	@echo "  DESCRIPTION=$(DESCRIPTION)"
	@echo "  TARGET_DIR=$(TARGET_DIR)"
	@echo "  OVERLAY_ROOT=$(OVERLAY_ROOT)"
	@echo "  EXTRA_KIWI_ARGS=$(EXTRA_KIWI_ARGS)"
	@echo "  SUDO=$(SUDO)"

download:
	mkdir -p $(TARGET_DIR)
	$(SUDO) $(BIN) --config $(CONFIG) --description $(DESCRIPTION) --target-dir $(TARGET_DIR) --overlay-root $(OVERLAY_ROOT) --skip-build $(EXTRA_ARG_OPTION)
	$(SUDO) $(KIWI) system prepare --description $(DESCRIPTION) --target-dir $(TARGET_DIR) --overlay-root $(OVERLAY_ROOT) $(EXTRA_KIWI_ARGS)

build: download
	$(SUDO) $(BIN) --config $(CONFIG) --description $(DESCRIPTION) --target-dir $(TARGET_DIR) --overlay-root $(OVERLAY_ROOT) $(EXTRA_ARG_OPTION)

clean:
	rm -rf $(TARGET_DIR) $(OVERLAY_ROOT)
