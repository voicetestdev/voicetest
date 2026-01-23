# Demo GIF generation
#
# Prerequisites:
#   brew install vhs ffmpeg
#   cd ../../web && mise exec -- bun add -D @playwright/test
#   mise exec -- bunx playwright install chromium

.PHONY: all cli web clean

all: cli web

# CLI demo using VHS
cli: cli-demo.gif

cli-demo.gif: cli-demo.tape
	vhs cli-demo.tape

# Web UI demo using Playwright
web: web-demo.gif

web-demo.gif: web-demo.webm
	ffmpeg -y -i web-demo.webm -vf "fps=10,scale=1200:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" web-demo.gif

web-demo.webm:
	@echo "Starting server in background..."
	@uv run voicetest demo --serve &
	@sleep 5
	@echo "Recording with Playwright..."
	cd ../../web && mise exec -- bunx playwright test || true
	@echo "Stopping server..."
	@pkill -f "voicetest demo" || true
	@sleep 1
	@mv test-results/*/video.webm web-demo.webm 2>/dev/null || echo "Video not found in test-results/"

clean:
	rm -f cli-demo.gif web-demo.gif web-demo.webm
	rm -rf test-results/
