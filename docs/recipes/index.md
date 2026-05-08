# Recipes

Task-oriented walkthroughs for the most common voicetest workflows. Each recipe assumes you already have voicetest installed and a passing test against the demo agent — see [Getting Started](../getting-started.md) if not.

| Recipe                                                              | Use when                                                                    |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| [Regression-test prompt changes](regression-test-prompt-changes.md) | You're about to edit a prompt and want to know what breaks before you ship. |
| [Import call history as a regression suite](import-call-history.md) | You have production calls and want them as a replayable test set.           |
| [Diagnose and auto-fix a failing test](diagnose-failing-test.md)    | A test is red and you want voicetest to propose a prompt fix.               |
| [Run in GitHub Actions](ci-github-actions.md)                       | You want every push to fail loudly if the agent regresses.                  |
