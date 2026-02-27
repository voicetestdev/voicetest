# voicetest Test Case Format

Test cases are JSON arrays. Each test case defines a simulated conversation scenario
and evaluation criteria.

## Test Types

### Simulation Tests (LLM-based)

Use an LLM to simulate the user, then evaluate with natural language metrics.

```json
{
  "name": "Customer billing inquiry",
  "user_prompt": "When asked for name, say Jane Smith. Say you're confused about a charge on your bill.",
  "metrics": [
    "Agent greeted the customer and addressed the billing concern.",
    "Agent was helpful and professional."
  ],
  "dynamic_variables": {
    "account_number": "12345"
  },
  "tool_mocks": [],
  "type": "simulation",
  "llm_model": "gpt-4o-mini"
}
```

**Fields:**

- `name` (required): Test case name
- `user_prompt` (required): Instructions for the simulated user
- `metrics` (required): Natural language evaluation criteria (each judged pass/fail)
- `dynamic_variables`: Key-value pairs injected into agent prompts via `{{key}}`
- `tool_mocks`: Mock tool responses (for testing tool-calling agents)
- `type`: `"simulation"` (default) or `"llm"` (alias)
- `llm_model`: Override LLM model for this test

### Rule-Based Tests (Pattern Matching)

Use pattern matching to validate agent responses without LLM evaluation.

```json
{
  "name": "Greeting includes company name",
  "user_prompt": "Say hello and ask about business hours.",
  "includes": ["Acme", "welcome", "help"],
  "excludes": ["goodbye", "transfer"],
  "patterns": [],
  "type": "unit"
}
```

**Fields:**

- `includes`: Strings that MUST appear in the agent's response
- `excludes`: Strings that MUST NOT appear in the agent's response
- `patterns`: Regex patterns that must match somewhere in the response
- `type`: `"unit"` or `"rule"`

### Pattern Examples

```json
{
  "name": "Confirmation number format",
  "user_prompt": "Book an appointment for tomorrow at 3pm.",
  "includes": ["confirmed", "appointment"],
  "patterns": ["[A-Z]{2,4}-[0-9]{4,8}"],
  "type": "unit"
}
```

## Full File Structure

A test file is a JSON array of test cases:

```json
[
  { "name": "Test 1", "user_prompt": "...", "metrics": ["..."], "type": "simulation" },
  { "name": "Test 2", "user_prompt": "...", "includes": ["..."], "type": "unit" }
]
```

## Dynamic Variables

Variables in agent prompts use `{{variable_name}}` syntax. Test cases provide values
via `dynamic_variables`:

```json
{
  "dynamic_variables": {
    "customer_name": "Jane Smith",
    "account_number": "12345",
    "appointment_date": "2024-03-15"
  }
}
```

## Tool Mocks

For agents that call external tools, provide mock responses:

```json
{
  "tool_mocks": [
    {
      "name": "lookup_account",
      "response": { "name": "Jane Smith", "balance": 150.00 }
    }
  ]
}
```
