# Demo GIF generation
#
# Each web/dry demo is recorded in both light and dark theme variants.
#
# Prerequisites:
#   brew install vhs ffmpeg
#   cd ../../web && mise exec -- bun add -D @playwright/test
#   mise exec -- bunx playwright install chromium
#
# Usage:
#   make all          # Generate everything (cli + web + dry, both themes)
#   make web          # Both web-demo-light.gif and web-demo-dark.gif
#   make dry          # Both dry-demo-light.gif and dry-demo-dark.gif
#   make cli          # CLI demo only (theme N/A)
#   make clean        # Remove all generated files

.PHONY: all cli web dry clean

all: cli web dry

# ---------------------------------------------------------------------------
# CLI demo (VHS — no theme variants)
# ---------------------------------------------------------------------------
cli: cli-demo.gif

cli-demo.gif: cli-demo.tape
	vhs cli-demo.tape

# ---------------------------------------------------------------------------
# Web UI demos (light + dark)
# ---------------------------------------------------------------------------
web: web-demo-light.gif web-demo-dark.gif

# ---------------------------------------------------------------------------
# DRY analysis demos (light + dark)
# ---------------------------------------------------------------------------
dry: dry-demo-light.gif dry-demo-dark.gif

# ---------------------------------------------------------------------------
# Generic GIF conversion: any .webm → .gif via ffmpeg palette-optimised filter
# ---------------------------------------------------------------------------
%.gif: %.webm
	ffmpeg -y -i $< \
		-vf "fps=10,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
		$@

# ---------------------------------------------------------------------------
# Recording macro — spins up the server, runs a Playwright project, extracts
# the video, and tears down.  $(1) = output stem, $(2) = Playwright project.
# ---------------------------------------------------------------------------
define RECORD
$(1).webm:
	@echo "── Recording $(2) ──"
	@rm -f ../../.voicetest/data.duckdb ../../.voicetest/data.duckdb.wal
	(cd ../.. && DSPY_CACHEDIR=dist/.dspy_cache uv run voicetest demo --serve) &
	@sleep 5
	cd ../../web && mise exec -- bunx playwright test --project=$(2) || true
	@pkill -f "voicetest demo" || true
	@sleep 1
	@mv test-results/*/video.webm $(1).webm 2>/dev/null || echo "Video not found in test-results/"
	@rm -rf test-results/
endef

$(eval $(call RECORD,web-demo-light,web-light))
$(eval $(call RECORD,web-demo-dark,web-dark))
$(eval $(call RECORD,dry-demo-light,dry-light))
$(eval $(call RECORD,dry-demo-dark,dry-dark))

# ---------------------------------------------------------------------------
clean:
	rm -f cli-demo.gif
	rm -f web-demo-light.gif web-demo-light.webm web-demo-dark.gif web-demo-dark.webm
	rm -f dry-demo-light.gif dry-demo-light.webm dry-demo-dark.gif dry-demo-dark.webm
	rm -rf test-results/
	rm -rf ../../dist/.dspy_cache
