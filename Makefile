# Copyright (c) 2025 Darren Soothill

SHELL := /bin/bash

BIN := ./bin/build-image
CONFIG_RENDER := ./bin/render-simple-config
SHELL := /bin/bash

BIN := ./bin/build-image
KIWI := kiwi-ng
CONFIG ?= config/sample-config.json
DESCRIPTION ?= kiwi
TARGET_DIR ?= build/artifacts
OVERLAY_ROOT ?= build/overlay
SUDO ?= sudo
EXTRA_KIWI_ARGS ?=
SIMPLE_USERS ?= config/users.txt
SIMPLE_PACKAGES ?= config/packages.txt
SIMPLE_SERVICES ?= config/services.txt
OUTPUT_CONFIG ?= config/generated-config.json

EXTRA_ARG_OPTION = $(strip $(if $(EXTRA_KIWI_ARGS),--extra-kiwi-args -- $(EXTRA_KIWI_ARGS),))

.PHONY: help config-json download build clean

EXTRA_ARG_OPTION = $(strip $(if $(EXTRA_KIWI_ARGS),--extra-kiwi-args -- $(EXTRA_KIWI_ARGS),))

.PHONY: help download build clean

help:
	@echo "Make targets for the KIWI image workflow"
	@echo "Usage: make <target> [VARIABLE=value ...]"
	@echo
	@echo "Targets:"
	@echo "  config-json Render JSON configuration from simple text files."
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
	@echo "  SIMPLE_USERS=$(SIMPLE_USERS)"
	@echo "  SIMPLE_PACKAGES=$(SIMPLE_PACKAGES)"
	@echo "  SIMPLE_SERVICES=$(SIMPLE_SERVICES)"
	@echo "  OUTPUT_CONFIG=$(OUTPUT_CONFIG)"

config-json:
	$(CONFIG_RENDER) --users $(SIMPLE_USERS) --packages $(SIMPLE_PACKAGES) --services $(SIMPLE_SERVICES) --output $(OUTPUT_CONFIG)

download:
	mkdir -p $(TARGET_DIR)
	$(SUDO) $(BIN) --config $(CONFIG) --description $(DESCRIPTION) --target-dir $(TARGET_DIR) --overlay-root $(OVERLAY_ROOT) --skip-build $(EXTRA_ARG_OPTION)
	$(SUDO) $(KIWI) system prepare --description $(DESCRIPTION) --target-dir $(TARGET_DIR) --overlay-root $(OVERLAY_ROOT) $(EXTRA_KIWI_ARGS)

build: download
	$(SUDO) $(BIN) --config $(CONFIG) --description $(DESCRIPTION) --target-dir $(TARGET_DIR) --overlay-root $(OVERLAY_ROOT) $(EXTRA_ARG_OPTION)

clean:
	rm -rf $(TARGET_DIR) $(OVERLAY_ROOT)
