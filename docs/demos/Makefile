# Demo GIF generation
#
# Prerequisites:
#   brew install vhs ffmpeg
#   cd ../../web && mise exec -- bun add -D @playwright/test
#   mise exec -- bunx playwright install chromium

.PHONY: all cli web dry clean

all: cli web dry

# CLI demo using VHS
cli: cli-demo.gif

cli-demo.gif: cli-demo.tape
	vhs cli-demo.tape

# Web UI demo using Playwright
web: web-demo.gif

web-demo.gif: web-demo.webm
	ffmpeg -y -i web-demo.webm -vf "fps=10,scale=600:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" web-demo.gif

web-demo.webm:
	@echo "Clearing demo database..."
	@rm -f ~/.voicetest/data.duckdb ~/.voicetest/data.duckdb.wal
	@echo "Starting server in background..."
	(cd ../.. && uv run voicetest demo --serve) &
	@sleep 5
	@echo "Recording with Playwright..."
	cd ../../web && mise exec -- bunx playwright test --project=web || true
	@echo "Stopping server..."
	@pkill -f "voicetest demo" || true
	@sleep 1
	@mv test-results/*/video.webm web-demo.webm 2>/dev/null || echo "Video not found in test-results/"

# DRY analysis demo using Playwright
dry: dry-demo.gif

dry-demo.gif: dry-demo.webm
	ffmpeg -y -i dry-demo.webm -vf "fps=10,scale=600:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" dry-demo.gif

dry-demo.webm:
	@echo "Clearing demo database..."
	@rm -f ~/.voicetest/data.duckdb ~/.voicetest/data.duckdb.wal
	@echo "Starting server in background..."
	(cd ../.. && uv run voicetest demo --serve) &
	@sleep 5
	@echo "Recording with Playwright..."
	cd ../../web && mise exec -- bunx playwright test --project=dry || true
	@echo "Stopping server..."
	@pkill -f "voicetest demo" || true
	@sleep 1
	@mv test-results/*/video.webm dry-demo.webm 2>/dev/null || echo "Video not found in test-results/"

clean:
	rm -f cli-demo.gif web-demo.gif web-demo.webm dry-demo.gif dry-demo.webm
	rm -rf test-results/
