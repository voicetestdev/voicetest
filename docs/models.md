---
description: Pick the right LLM for each voicetest role — agent, simulator, judge — and balance quality against cost.
---

# Models guide

Voicetest uses three distinct LLM roles. Choosing the right model for each is the single biggest lever for run cost, run speed, and result quality.

## The three roles

| Role          | What it does                                                                                                   | What it needs                                                                                                           |
| ------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Agent**     | Plays your voice agent — generates responses node by node, decides when to transition, calls tools when needed | Strong instruction-following, structured output for transitions and tool calls, low latency for streaming               |
| **Simulator** | Plays the user — generates the next user turn given the persona and goal in the test case                      | Good at sustaining a believable persona, accepting hedging/filler, willing to be uncooperative when the test demands it |
| **Judge**     | Evaluates the finished transcript against each metric, producing a 0–1 score with reasoning                    | Strong reading comprehension, calibrated scoring, follows scoring rubrics consistently                                  |

Each role can be configured independently in `settings.toml`, in `RunOptions`, or per test case (when `test_model_precedence` is enabled).

## Quick recommendations

| Use case                            | Agent                       | Simulator                   | Judge                         |
| ----------------------------------- | --------------------------- | --------------------------- | ----------------------------- |
| **Free / local development**        | `groq/llama-3.1-8b-instant` | `groq/llama-3.1-8b-instant` | `groq/llama-3.1-8b-instant`   |
| **Highest quality** (production CI) | `openai/gpt-4o`             | `openai/gpt-4o-mini`        | `anthropic/claude-3-5-sonnet` |
| **Cost-optimized**                  | `openai/gpt-4o-mini`        | `gemini/gemini-1.5-flash`   | `anthropic/claude-3-5-haiku`  |
| **Fully offline** (Ollama)          | `ollama_chat/qwen2.5:14b`   | `ollama_chat/qwen2.5:7b`    | `ollama_chat/qwen2.5:14b`     |
| **Claude Code passthrough**         | `claudecode/sonnet`         | `claudecode/haiku`          | `claudecode/sonnet`           |

These are starting points. Validate against your own test suite before locking them in — model quality on voice-agent transcripts varies more than on general benchmarks.

## How to choose

### Agent model

The agent runs at every turn of every conversation, so latency and per-call cost compound fast. It also has the hardest job — your real production agent's behavior depends on this LLM. Match what your production deployment uses, when feasible:

- If you ship Retell with `gpt-4o`, test with `openai/gpt-4o`. Same provider tier eliminates surprises.
- If you ship with a custom model, test with the same one.
- For development iteration, downgrade to `gpt-4o-mini` or a free Groq model — you'll catch the obvious regressions without the production cost.

**Avoid**: tiny models (under 8B parameters) for agents with structured tool calls or many transitions. They'll fumble the JSON.

### Simulator model

The simulator's job is "play the user" — produce realistic next turns from a persona and goal. This is easier than the agent's job, so you can usually go a tier cheaper. But there are two caveats:

- **Don't go too cheap.** A simulator that can't sustain a persona produces unrealistic conversations, and your tests pass for the wrong reasons. Test the simulator quality by reading 5–10 transcripts and asking "would a real caller talk like this?"
- **Don't use the same model as the agent.** When agent and simulator are the same model, the LLM "knows itself" — the simulator anticipates the agent's next move in ways a real user wouldn't. Pick a different provider or family.

### Judge model

The judge reads a finished transcript and scores each metric. This is mostly reading comprehension; quality matters less than calibration consistency. Practical tips:

- **Pick one judge and stick with it.** Switching judges between runs makes scores incomparable.
- **Stronger judges are worth it for production CI.** If a regression slips past the judge, you ship the bug. The cost is small relative to the per-conversation agent cost.
- **Test the judge on known-good transcripts.** If a judge consistently mis-scores cases you know should pass, retire it.

## Setting models

Put it in `settings.toml`:

```toml
[models]
agent = "openai/gpt-4o-mini"
simulator = "gemini/gemini-1.5-flash"
judge = "anthropic/claude-3-5-haiku-20241022"
```

Or per run via `RunOptions`:

```python
from voicetest.models.test_case import RunOptions

options = RunOptions(
    agent_model="openai/gpt-4o",
    simulator_model="openai/gpt-4o-mini",
    judge_model="anthropic/claude-3-5-sonnet-20241022",
)
```

Or per test case (requires `test_model_precedence = true` in run options):

```json
{
  "name": "Hard escalation case",
  "user_prompt": "...",
  "metrics": ["..."],
  "llm_model": "openai/gpt-4o",
  "type": "llm"
}
```

## Provider-specific notes

- **LiteLLM format** — voicetest uses [LiteLLM](https://docs.litellm.ai/docs/providers) for all routing, so any provider LiteLLM supports works. Format: `provider/model-name`.
- **Vertex AI region** — set `VERTEXAI_LOCATION=global` for newer Gemini models. See [Configuration: Vertex AI](configuration.md#vertex-ai).
- **Claude Code passthrough** — use your existing Claude Code subscription instead of an API key. See [Claude Code Integration](claude-code.md).
- **Ollama for local** — fully offline, free, and reproducible. Install [Ollama](https://ollama.ai/), pull the model, and use `ollama_chat/<model>` in voicetest. Bigger models give better quality at the cost of speed.

## Caching

Voicetest caches LLM responses by default to avoid redundant calls when re-running tests. This makes the same suite cheap to re-run. Disable per call with `--no-cache` or `no_cache = true` in run options. See [Features: LLM response cache](features.md#llm-response-cache) for the disk and S3 backends.
