# codex-status-line

`codex-status-line` shows the folder, git branch, context use and cost of an [OpenAI Codex CLI](https://github.com/openai/codex) session. It reads the session log Codex writes to `~/.codex/sessions`. It shows the result in one of two places: a line in the Codex chat after every answer (a Codex hook), or a segment in your tmux status bar. Codex's own status line accepts only built-in items, so a custom script cannot draw there ([openai/codex#17827](https://github.com/openai/codex/issues/17827)).

```
~/project · main · ░░░░░ ctx 4% · session $0.0013
```

## Fields by billing type

The model name is left out because Codex's own footer already shows it. The tool detects who bills the session from the session log and your Codex `config.toml`, so you can switch models or providers without changing anything.

| Session billed by | Detected when | Billing fields |
|---|---|---|
| OpenRouter | the provider's `base_url` contains `openrouter.ai` | `session`: exact cost billed by OpenRouter |
| ChatGPT plan | the log carries usage-limit windows | each window, for example `5h ██░░░ 40% ↻14:30` and `week █░░░░ 21% ↻Thu 10:00` |
| OpenAI API key | provider `openai` without limit windows | `session ~$0.0123 est.`: token counts times the model's list price |
| Anything else, such as Ollama | none of the above | total tokens used |

The OpenRouter session cost is exact. Codex logs an OpenRouter request ID (`gen-…`) for every model call, and the tool asks OpenRouter's `/generation` endpoint what each ID cost. Each answer is cached in `~/.cache/codex-status-line`, so every request is looked up once. OpenRouter bills a request 5 to 10 seconds after it ends. Until then the tool estimates that request from its logged token counts and the model's price, and marks the total with `~`, as in `session ~$0.0042`. A trailing `+` means some requests have no figure yet, because the model is missing from OpenRouter's price list.

The API-key estimate uses the per-token prices in OpenRouter's public model list, which match OpenAI's list prices. OpenAI's API does not report a cost per request, so an estimate is the closest available figure.

The context meter is the share of the model's context window (the amount of text it can hold at once) used by the last request. Meters turn yellow at 50 % and red at 80 %.

## Install

`codex-status-line` needs Python 3.11 or newer and has no other dependencies. Install it as a command with [uv](https://docs.astral.sh/uv/) or pipx:

```sh
uv tool install git+https://github.com/shourovrm/codex-status-line
# or
pipx install git+https://github.com/shourovrm/codex-status-line
```

For OpenRouter sessions, the tool reads your key from the environment variable named in your provider's `env_key` setting, and from `OPENROUTER_API_KEY` if none is set. A minimal OpenRouter provider in `~/.codex/config.toml` is:

```toml
model_provider = "openrouter"
model = "openai/gpt-6-luna"

[model_providers.openrouter]
name = "OpenRouter"
base_url = "https://openrouter.ai/api/v1"
env_key = "OPENROUTER_API_KEY"
wire_api = "responses"
```

## Codex hook setup

The hook adds one line to the chat after every Codex answer, in any terminal. Add a `Stop` hook to `~/.codex/hooks.json`; if the file already has a `"Stop"` list, add the inner object to it:

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [{ "type": "command", "command": "codex-status-line hook", "timeout": 15 }] }
    ]
  }
}
```

Codex asks you to trust a new hook before it runs it; approve it with `/hooks`. The line then appears after each answer as `↳ Hook · ~/project · main · …`. The hook runs right after the last request, before OpenRouter has billed it, so its session cost usually carries the `~` estimate mark. The tmux bar shows the exact figure a few seconds later.

## tmux bar setup

The tmux segment stays on screen and refreshes every 5 seconds. It is empty whenever the active pane is not running Codex. Add these lines to `~/.tmux.conf` and reload with `tmux source ~/.tmux.conf`:

```tmux
set -g status-interval 5
set -g status-left-length 200
set -ag status-left " #(codex-status-line tmux --pane-pid #{pane_pid} --cwd '#{pane_current_path}') "
```

`set -ag` appends to your existing `status-left`. Use `status-right` instead if your left side is full.

## Tests and linting

The tests use only the standard library and need no network:

```sh
PYTHONPATH=src:tests python -m unittest discover -s tests
ruff check . && ruff format --check .
```

## Limitations

- **tmux matching by folder:** a shared background Codex process writes every session's log, so the tmux segment cannot trace a log to a pane directly. It picks the newest log written since the pane's Codex started, preferring one started in the pane's folder. Two Codex sessions in the same folder at the same time can therefore show each other's figures.
- **Estimated API-key cost:** for an OpenAI API key, the figure is an estimate. It is shown only for models in OpenRouter's public model list.
- **Plan detection:** a ChatGPT-plan session is recognised once Codex logs the first usage-limit snapshot, which arrives with the first answer.
- **Process lookup:** the tmux segment finds Codex with `ps`, which works on Linux and macOS but not on Windows.

## License

MIT. See [LICENSE](LICENSE).
