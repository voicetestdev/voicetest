# VHS tape file for CLI demo
# Run with: vhs docs/demos/cli-demo.tape

Output cli-demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 600
Set Theme "Catppuccin Mocha"

# Start with a clean terminal
Type "# Try voicetest with the built-in demo"
Enter
Sleep 500ms

Type "uv run voicetest demo"
Enter
Sleep 4s

# The shell should now be open with demo loaded
# Type run command to execute tests
Type "run"
Enter
Sleep 8s

# Show results for a moment
Sleep 3s

# Exit the shell
Type "quit"
Enter
Sleep 1s
