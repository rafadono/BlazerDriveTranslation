ROM_IN  ?= rom/blazer_drive_jp.nds
ROM_OUT ?= rom/blazer_drive_translated.nds
PYTHON  ?= uv run python
CLI     := $(PYTHON) -m blazer_drive

.PHONY: setup emulators unpack extract batches import-batches audit inject gfx build all test qa-checkpoints qa-dialogs showcase

setup:            ## dependencies
	uv sync
emulators:        ## portable DeSmuME/melonDS in tools/emulators
	$(PYTHON) tools/download_emulators.py

unpack:           ## original ROM -> workspace/unpacked (reference)
	$(CLI) unpack --rom "$(ROM_IN)"
extract:          ## exact catalog of the .bmsg files (keeps translations)
	$(CLI) extract --rom "$(ROM_IN)"
batches:          ## JSON batches to translate
	$(CLI) batches export
import-batches:   ## validate and load the translated batches into the catalog
	$(CLI) batches import
audit:
	$(CLI) audit --lang en

inject:
	$(CLI) inject --rom "$(ROM_IN)" --lang en
gfx:
	$(CLI) gfx --rom "$(ROM_IN)" --preview workspace/textures
build:
	$(CLI) build --rom "$(ROM_IN)" --out-rom "$(ROM_OUT)"
all:              ## inject + gfx + build
	$(CLI) all --rom "$(ROM_IN)" --out-rom "$(ROM_OUT)"

test:             ## unit tests
	$(PYTHON) -m unittest discover -s tests -t .

qa-checkpoints:   ## test save states for the current build (real DeSmuME)
	$(PYTHON) qa/scenarios/checkpoints.py --rom "$(ROM_OUT)"
qa-dialogs:       ## step through the prologue dialogs from checkpoint 2
	$(PYTHON) qa/scenarios/prologue_dialogs.py --rom "$(ROM_OUT)"
showcase:         ## JP/EN comparison images for docs/images
	$(PYTHON) qa/scenarios/showcase.py
